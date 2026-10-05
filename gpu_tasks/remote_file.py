"""Bounded public HTTP Range reader for real HDF5/TAR/Parquet source subsets."""
import io
from collections import OrderedDict
import requests

class RemoteFile(io.RawIOBase):
    def __init__(self,url,block_size=4*2**20,max_transfer=2*2**30,max_read=256*2**20):
        self.url=url;self.position=0;self.block_size=block_size;self.max_transfer=max_transfer;self.max_read=max_read;self.transferred=0;self.cache=OrderedDict();self.session=requests.Session()
        with self.session.get(url,headers={'Range':'bytes=0-0'},stream=True,timeout=(15,60)) as r:
            r.raise_for_status()
            if r.status_code!=206 or 'Content-Range' not in r.headers:raise ValueError('source does not support bounded range reads')
            self.size=int(r.headers['Content-Range'].rsplit('/',1)[1])
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        if whence==0:self.position=offset
        elif whence==1:self.position+=offset
        elif whence==2:self.position=self.size+offset
        else:raise ValueError(whence)
        if self.position<0:raise ValueError('negative source offset')
        return self.position
    def readinto(self,b):
        value=self.read(len(b));b[:len(value)]=value;return len(value)
    def read(self,size=-1):
        if size<0:size=self.size-self.position
        size=min(size,max(self.size-self.position,0))
        if size>self.max_read:raise ValueError('single range read exceeds trusted memory budget')
        result=[]
        while size:
            block=self.position//self.block_size
            if block not in self.cache:
                lo=block*self.block_size;hi=min(lo+self.block_size,self.size)-1
                if self.transferred+hi-lo+1>self.max_transfer:raise ValueError('source transfer budget exhausted')
                with self.session.get(self.url,headers={'Range':f'bytes={lo}-{hi}'},stream=True,timeout=(15,90)) as r:
                    r.raise_for_status()
                    if r.status_code!=206:raise ValueError('server ignored range request')
                    payload=b''.join(r.iter_content(1<<20))
                    if len(payload)!=hi-lo+1:raise IOError('range length mismatch')
                self.transferred+=len(payload);self.cache[block]=payload
                while len(self.cache)>16:self.cache.popitem(last=False)
            payload=self.cache[block];self.cache.move_to_end(block)
            offset=self.position%self.block_size;count=min(size,len(payload)-offset)
            if count<=0:raise IOError('range made no progress')
            result.append(payload[offset:offset+count]);size-=count;self.position+=count
        return b''.join(result)
    def close(self):
        self.session.close();self.cache.clear();super().close()
