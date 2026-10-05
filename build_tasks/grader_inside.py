"""Independent consumers run in fresh containers without an extracted source tree."""
import argparse
import base64
import gzip
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import threading

ARTIFACTS = Path('/artifacts')
INSTALL = Path('/workspace/output/install')
WORK = Path('/workspace/consumer')
RESULTS = Path('/workspace/output/evaluation')
COMMANDS = []


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(8 << 20), b''):
            h.update(part)
    return h.hexdigest()


def log_hash(path):
    if path.exists():
        return sha(path)
    digest=hashlib.sha256()
    with gzip.open(path.with_suffix(path.suffix+'.gz'),'rb') as stream:
        for block in iter(lambda:stream.read(8<<20),b''):
            digest.update(block)
    return digest.hexdigest()


def read_log(path):
    if path.exists():
        return path.read_text(errors='replace')
    with gzip.open(path.with_suffix(path.suffix+'.gz'),'rt',errors='replace') as stream:
        return stream.read()


def execute(argv, cwd=WORK, env=None, expected=0, timeout=300):
    result = subprocess.run([str(x) for x in argv], cwd=cwd,
                            env={**os.environ, **(env or {})}, capture_output=True, timeout=timeout)
    record = {'argv': [str(x) for x in argv], 'cwd': str(cwd), 'exit_code': result.returncode,
              'stdout': result.stdout.decode(errors='replace')[-16000:],
              'stderr': result.stderr.decode(errors='replace')[-8000:]}
    COMMANDS.append(record)
    assert result.returncode == expected, json.dumps(record)
    return result


def find_library(name, static=False):
    suffix = '.a' if static else '.so'
    for directory in [INSTALL / 'lib', INSTALL / 'lib64', INSTALL / 'lib/x86_64-linux-gnu']:
        path = directory / ('lib' + name + suffix)
        if path.is_file():
            return path
    raise AssertionError('new installed library missing: ' + name + suffix)


def c_consumer(name, source, libraries, static=False, extra=None):
    code = WORK / (name + '.c')
    code.write_text(source)
    binary = WORK / name
    targets = [find_library(lib, static=static) for lib in libraries]
    argv = ['gcc','-O2','-std=c11','-D_POSIX_C_SOURCE=200809L','-I',INSTALL / 'include',code,
            *targets,'-Wl,-rpath,' + ':'.join(str(p.parent) for p in targets),'-o',binary]
    execute(argv + (extra or []))
    if not static:
        linkage = execute(['ldd', binary]).stdout.decode()
        for lib in libraries:
            assert 'lib' + lib in linkage and str(INSTALL) in linkage
    return execute([binary]).stdout.decode()


ZLIB = r'''
#include <zlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void){
 unsigned char src[131072], dst[131072], packed[140000];
 for(size_t i=0;i<sizeof(src);i++)src[i]=(unsigned char)(i*i+31*i+(i>>7));
 uLongf cap=sizeof(packed), size=sizeof(dst);
 if(compress2(packed,&cap,src,sizeof(src),6)!=Z_OK)return 1;
 if(uncompress(dst,&size,packed,cap)!=Z_OK||size!=sizeof(src)||memcmp(src,dst,size))return 2;
 size=sizeof(dst);if(uncompress(dst,&size,packed,cap/2)==Z_OK)return 3;
 gzFile gz=gzopen("new.gz","wb");if(!gz)return 4;
 for(size_t i=0;i<sizeof(src);i+=1024)if(gzwrite(gz,src+i,1024)!=1024)return 5;
 if(gzclose(gz)!=Z_OK)return 6;
 gz=gzopen("new.gz","rb");if(!gz)return 7;
 int n=gzread(gz,dst,sizeof(dst));if(n!=sizeof(src)||memcmp(src,dst,sizeof(src)))return 8;
 if(gzclose(gz)!=Z_OK)return 9;
 printf("zlib independent roundtrip/truncation/gzip OK %s\n",zlibVersion());return 0;
}
'''

ZSTD = r'''
#include <zstd.h>
#include <stdio.h>
#include <string.h>
int main(void){
 unsigned char input[65536],compressed[70000],decoded[65536],dictionary[2048];
 for(int i=0;i<65536;i++)input[i]=(unsigned char)(i*13+(i>>8));
 memcpy(dictionary,input,sizeof(dictionary));
 ZSTD_CCtx*c=ZSTD_createCCtx();ZSTD_DCtx*d=ZSTD_createDCtx();if(!c||!d)return 1;
 if(ZSTD_isError(ZSTD_CCtx_loadDictionary(c,dictionary,sizeof(dictionary))))return 2;
 ZSTD_inBuffer in={input,sizeof(input),0};ZSTD_outBuffer out={compressed,sizeof(compressed),0};
 size_t remain=1;while(in.pos<in.size||remain){remain=ZSTD_compressStream2(c,&out,&in,ZSTD_e_end);if(ZSTD_isError(remain))return 3;}
 if(ZSTD_isError(ZSTD_DCtx_loadDictionary(d,dictionary,sizeof(dictionary))))return 4;
 ZSTD_inBuffer encoded={compressed,out.pos,0};ZSTD_outBuffer plain={decoded,sizeof(decoded),0};
 remain=1;while(encoded.pos<encoded.size||remain){remain=ZSTD_decompressStream(d,&plain,&encoded);if(ZSTD_isError(remain))return 5;}
 if(plain.pos!=sizeof(input)||memcmp(input,decoded,sizeof(input)))return 6;
 size_t error=ZSTD_decompress(decoded,sizeof(decoded),compressed,3);if(!ZSTD_isError(error))return 7;
 ZSTD_freeCCtx(c);ZSTD_freeDCtx(d);printf("zstd independent dictionary stream OK %u\n",ZSTD_versionNumber());return 0;
}
'''

ARCHIVE = r'''
#include <archive.h>
#include <archive_entry.h>
#include <stdio.h>
#include <string.h>
int main(void){
 struct archive*a=archive_write_new();archive_write_add_filter_gzip(a);archive_write_set_format_pax_restricted(a);
 if(archive_write_open_filename(a,"new.tar.gz")!=ARCHIVE_OK)return 1;
 char bytes[4096];for(int i=0;i<4096;i++)bytes[i]=(char)(i*7);
 struct archive_entry*e=archive_entry_new();archive_entry_set_pathname(e,"payload.bin");archive_entry_set_size(e,sizeof(bytes));archive_entry_set_filetype(e,AE_IFREG);archive_entry_set_perm(e,0640);
 if(archive_write_header(a,e)!=ARCHIVE_OK||archive_write_data(a,bytes,sizeof(bytes))!=sizeof(bytes))return 2;
 archive_entry_free(e);if(archive_write_close(a)!=ARCHIVE_OK)return 3;archive_write_free(a);
 a=archive_read_new();archive_read_support_filter_all(a);archive_read_support_format_all(a);
 if(archive_read_open_filename(a,"new.tar.gz",10240)!=ARCHIVE_OK)return 4;
 if(archive_read_next_header(a,&e)!=ARCHIVE_OK||strcmp(archive_entry_pathname(e),"payload.bin")||archive_entry_size(e)!=4096)return 5;
 char restored[4096];if(archive_read_data(a,restored,sizeof(restored))!=4096||memcmp(bytes,restored,4096))return 6;
 if(archive_read_next_header(a,&e)!=ARCHIVE_EOF)return 7;
 archive_read_close(a);archive_read_free(a);printf("archive independent tar+gzip+metadata OK\n");return 0;
}
'''

UV = r'''
#include <uv.h>
#include <stdio.h>
static uv_timer_t timer;static uv_work_t work;static int ticks=0,done=0,result=0;
static void tick(uv_timer_t*t){if(++ticks==3){uv_timer_stop(t);uv_close((uv_handle_t*)t,0);}}
static void worker(uv_work_t*w){(void)w;for(int i=0;i<10000;i++)result+=(i%7);}
static void after(uv_work_t*w,int status){(void)w;if(status==0)done=1;}
int main(void){uv_loop_t loop;if(uv_loop_init(&loop))return 1;uv_timer_init(&loop,&timer);uv_timer_start(&timer,tick,1,1);
 if(uv_queue_work(&loop,&work,worker,after))return 2;uv_run(&loop,UV_RUN_DEFAULT);
 if(ticks!=3||done!=1||result!=29994||uv_loop_close(&loop))return 3;
 printf("libuv independent timers/work/loop OK %s\n",uv_version_string());return 0;}
'''

EVENT = r'''
#include <event2/event.h>
#include <event2/buffer.h>
#include <stdio.h>
#include <string.h>
static int count=0;static struct event_base*base;
static void callback(evutil_socket_t fd,short what,void*arg){(void)fd;(void)what;(void)arg;count++;event_base_loopbreak(base);}
int main(void){base=event_base_new();if(!base)return 1;struct event*e=evtimer_new(base,callback,0);struct timeval tv={0,1000};evtimer_add(e,&tv);event_base_dispatch(base);
 struct evbuffer*b=evbuffer_new();char buf[7]={0};evbuffer_add(b,"abc",3);evbuffer_add(b,"xyz",3);if(evbuffer_remove(b,buf,6)!=6||strcmp(buf,"abcxyz")||count!=1)return 2;
 evbuffer_free(b);event_free(e);event_base_free(base);printf("libevent independent dispatch/buffer OK\n");return 0;}
'''

PCRE = r'''
#define PCRE2_CODE_UNIT_WIDTH 8
#include <pcre2.h>
#include <stdio.h>
#include <string.h>
int main(void){int error;PCRE2_SIZE off;pcre2_code*c=pcre2_compile((PCRE2_SPTR)"(?<word>[A-Z][a-z]+)-(\\d+)",PCRE2_ZERO_TERMINATED,PCRE2_UTF|PCRE2_UCP,&error,&off,0);if(!c)return 1;
 pcre2_match_data*m=pcre2_match_data_create_from_pattern(c,0);int n=pcre2_match(c,(PCRE2_SPTR)"Alpha-42",8,0,0,m,0);if(n!=3)return 2;
 PCRE2_SIZE*v=pcre2_get_ovector_pointer(m);if(v[2]!=0||v[3]!=5||v[4]!=6||v[5]!=8)return 3;
 if(pcre2_match(c,(PCRE2_SPTR)"no-match",8,0,0,m,0)!=PCRE2_ERROR_NOMATCH)return 4;
 pcre2_match_data_free(m);pcre2_code_free(c);c=pcre2_compile((PCRE2_SPTR)"(",1,0,&error,&off,0);if(c)return 5;
 printf("pcre2 independent capture/error/UTF OK\n");return 0;}
'''

NGHTTP = r'''
#include <nghttp2/nghttp2.h>
#include <stdio.h>
#include <string.h>
int main(void){nghttp2_hd_deflater*d;nghttp2_hd_inflater*i;if(nghttp2_hd_deflate_new(&d,4096)||nghttp2_hd_inflate_new(&i))return 1;
 nghttp2_nv fields[2]={{(uint8_t*)":method",(uint8_t*)"GET",7,3,NGHTTP2_NV_FLAG_NONE},{(uint8_t*)":path",(uint8_t*)"/new",5,4,NGHTTP2_NV_FLAG_NONE}};
 uint8_t buf[4096];ssize_t n=nghttp2_hd_deflate_hd(d,buf,sizeof(buf),fields,2);if(n<=0)return 2;
 size_t off=0;int count=0,final=0;
 for(int step=0;step<100&&!final;step++){nghttp2_nv field;int flags=0;ssize_t used=nghttp2_hd_inflate_hd2(i,&field,&flags,buf+off,n-off,1);if(used<0)return 3;off+=used;
 if(flags&NGHTTP2_HD_INFLATE_EMIT){if(count>=2||field.namelen!=fields[count].namelen||field.valuelen!=fields[count].valuelen||memcmp(field.name,fields[count].name,field.namelen)||memcmp(field.value,fields[count].value,field.valuelen))return 4;count++;}
 final=(flags&NGHTTP2_HD_INFLATE_FINAL)!=0;}
 if(!final||count!=2||off!=(size_t)n)return 5;nghttp2_hd_inflate_end_headers(i);nghttp2_hd_inflate_del(i);nghttp2_hd_deflate_del(d);
 printf("nghttp2 independent HPACK roundtrip OK\n");return 0;}
'''

GIT = r'''
#include <git2.h>
#include <stdio.h>
#include <string.h>
int main(void){git_repository*r=0;git_index*idx=0;git_signature*s=0;git_tree*t=0;git_oid tree,commit;
 if(git_libgit2_init()<0||git_repository_init(&r,"repo",0))return 1;FILE*f=fopen("repo/new.txt","wb");if(!f)return 2;fwrite("source built consumer\n",1,22,f);fclose(f);
 if(git_repository_index(&idx,r)||git_index_add_bypath(idx,"new.txt")||git_index_write(idx)||git_index_write_tree(&tree,idx)||git_tree_lookup(&t,r,&tree))return 3;
 if(git_signature_now(&s,"consumer","test@example.invalid")||git_commit_create(&commit,r,"HEAD",s,s,0,"new commit",t,0,0))return 4;
 git_tree_free(t);git_index_free(idx);git_signature_free(s);git_repository_free(r);r=0;
 if(git_repository_open(&r,"repo"))return 5;git_commit*c=0;if(git_commit_lookup(&c,r,&commit)||strcmp(git_commit_message(c),"new commit"))return 6;
 git_commit_free(c);git_repository_free(r);git_libgit2_shutdown();printf("libgit2 independent index/commit/reopen OK\n");return 0;}
'''


def consume_curl():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'new source-built HTTP consumer\x00\xff'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if self.headers.get('Authorization') != 'Basic ' + base64.b64encode(b'user:pass').decode():
                self.send_error(401)
                return
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        binary = INSTALL / 'bin/curl'
        url = f'http://127.0.0.1:{server.server_port}/new'
        curl_env={'LD_LIBRARY_PATH':str(INSTALL/'lib')+':'+str(INSTALL/'lib64')}
        assert execute([binary,'--silent','--show-error','--fail',url],env=curl_env).stdout == b'new source-built HTTP consumer\x00\xff'
        (WORK / 'post.bin').write_bytes(bytes(range(256))*8)
        assert execute([binary,'--silent','--show-error','--fail','--user','user:pass','--data-binary','@post.bin',url],env=curl_env).stdout == (WORK/'post.bin').read_bytes()
        source = r'''
        #include <curl/curl.h>
        #include <stdio.h>
        #include <string.h>
        static char out[1024];static size_t size=0;
        static size_t write_data(char*p,size_t a,size_t b,void*x){(void)x;size_t n=a*b;if(size+n>sizeof(out))return 0;memcpy(out+size,p,n);size+=n;return n;}
        int main(void){curl_global_init(CURL_GLOBAL_DEFAULT);CURL*c=curl_easy_init();curl_easy_setopt(c,CURLOPT_URL,"URL");curl_easy_setopt(c,CURLOPT_WRITEFUNCTION,write_data);curl_easy_setopt(c,CURLOPT_TIMEOUT,5L);
        CURLcode e=curl_easy_perform(c);long status=0;curl_easy_getinfo(c,CURLINFO_RESPONSE_CODE,&status);curl_easy_cleanup(c);curl_global_cleanup();
        static unsigned char golden[]="new source-built HTTP consumer\x00\xff";
        if(e!=CURLE_OK||status!=200||size!=sizeof(golden)-1||memcmp(out,golden,sizeof(golden)-1))return 1;return 0;}
        '''.replace('"URL"',json.dumps(url))
        c_consumer('new_curl',source,['curl'])
    finally:
        server.shutdown()
        server.server_close()


def consume_ssl():
    binary = INSTALL / 'bin/openssl'
    payload = bytes(range(256))*257
    (WORK/'payload').write_bytes(payload)
    env = {'LD_LIBRARY_PATH': str(INSTALL/'lib64')+':'+str(INSTALL/'lib')}
    assert execute([binary,'dgst','-sha256','-binary','payload'],env=env).stdout == hashlib.sha256(payload).digest()
    execute([binary,'genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048','-out','private.pem'],env=env)
    execute([binary,'pkey','-in','private.pem','-pubout','-out','public.pem'],env=env)
    execute([binary,'dgst','-sha256','-sign','private.pem','-out','signature','payload'],env=env)
    assert b'Verified OK' in execute([binary,'dgst','-sha256','-verify','public.pem','-signature','signature','payload'],env=env).stdout
    source = r'''
    #include <openssl/evp.h>
    #include <stdio.h>
    #include <string.h>
    int main(void){unsigned char out[64];unsigned int size=0;EVP_MD_CTX*c=EVP_MD_CTX_new();if(!c)return 1;
    if(EVP_DigestInit_ex(c,EVP_sha256(),0)!=1||EVP_DigestUpdate(c,"abc",3)!=1||EVP_DigestFinal_ex(c,out,&size)!=1)return 2;
    EVP_MD_CTX_free(c);unsigned char golden[32]={0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad};
    if(size!=32||memcmp(out,golden,32))return 3;printf("OpenSSL independent EVP SHA256 OK\n");return 0;}
    '''
    c_consumer('new_crypto',source,['crypto'])


def verify_evidence(task_id):
    manifest = json.loads(Path('/workspace/input/manifest.json').read_text())
    run = json.loads((ARTIFACTS/'run.json').read_text())
    assert run['task_id']==task_id and run['source']['sha256']==manifest['source']['sha256']
    assert run['profile']=='core' and run['execution_complete'] is True
    commands = json.loads((ARTIFACTS/'commands.json').read_text())
    tests = json.loads((ARTIFACTS/'tests.json').read_text())
    assert commands and tests
    for command in commands:
        assert log_hash(ARTIFACTS/command['log'])==command['log_sha256']
        if command['phase']=='official_test':
            assert command['exit_code']==0,command
    successful_builds=[command for command in commands if command['phase'] in ['build','configure+build','compile','configure_and_build'] and command['exit_code']==0]
    assert successful_builds,'at least one successful real compilation is required'
    for command in commands:
        if command['phase'] in ['build','compile','configure+build','configure_and_build'] and command['exit_code']!=0:
            assert any(retry['index']>command['index'] for retry in successful_builds),'failed compilation has no successful retry'
    for test in tests:
        command=commands[test['command_index']]
        assert command['phase']=='official_test' and command['exit_code']==0
        text=read_log(ARTIFACTS/test['raw_log'])
        assert text.strip() and not re.search(r'No tests were found|no tests ran|collected 0 items',text,re.I)
        assert log_hash(ARTIFACTS/test['raw_log'])==test['log_sha256']
        assert test.get('parsed_count') is None or test['parsed_count']>0
        if 'ctest' in command['argv']:
            total=re.findall(r'\d+% tests passed,\s*\d+ tests failed out of (\d+)',text)
            assert total and len(re.findall(r'\*\*\*Skipped',text))<int(total[-1]),'all CTest targets skipped'
        assert not re.search(r'(?m)^\s*0 passing',text),'empty Mocha execution'
        unexpected=re.findall(r'# of (?:unexpected failures|unexpected successes|unresolved testcases)\s+(\d+)',text)
        assert not any(int(value)>0 for value in unexpected),'unexpected DejaGNU results'
    native_counts={}
    recovered_steps=[{'index':command['index'],'phase':command['phase'],'exit_code':command['exit_code']}
                     for command in commands if command['phase'] in ['configure','build','compile','configure+build','configure_and_build','install'] and command['exit_code']!=0]
    if recovered_steps:
        native_counts['recovered_build_steps']=recovered_steps
    if task_id=='BUILDv1-B01':
        for test in tests:
            raw=read_log(ARTIFACTS/test['raw_log'])
            passed=re.findall(r'(?m)^\s*Passed\s*:\s*(\d+)',raw)
            failed=re.findall(r'(?m)^\s*(?:Failed|Unexpectedly Passed|Unresolved|Timed Out)\s*:\s*(\d+)',raw)
            assert passed and int(passed[-1])>0 and not any(int(value)>0 for value in failed),'lit suite must have passing cases and no unexpected results'
            workers=re.findall(r'-- Testing: \d+ tests, (\d+) workers --',raw)
            native_counts[test['selector']]={'passed':int(passed[-1]),'actual_lit_workers':int(workers[-1]) if workers else None}
    if task_id=='BUILDv1-A10':
        raw='\n'.join(read_log(ARTIFACTS/t['raw_log']) for t in tests)
        suites=re.findall(r'(?m)^\d+:\s+([a-zA-Z0-9_:]+?)([.SFE]+)\s*$',raw)
        passed=sum(states.count('.') for _,states in suites);skipped=sum(states.count('S') for _,states in suites)
        failed=sum(states.count('F')+states.count('E') for _,states in suites)
        assert passed>0 and failed==0,'Clar internal case execution missing/failing'
        assert all(any(name.startswith(prefix) for name,_ in suites) for prefix in ['index::','object::','repo::'])
        native_counts={'clar_cases_passed':passed,'clar_cases_skipped':skipped,'clar_cases_failed':failed,'clar_suites_observed':len(suites)}
    inventory=json.loads((ARTIFACTS/'install_manifest.json').read_text())
    assert inventory or list(ARTIFACTS.glob('*.whl'))
    for entry in inventory:
        path=INSTALL/entry['path']
        assert path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256']
    return {'source_locked':True,'source_sha256':manifest['source']['sha256'],
            'official_entries':len(tests),'official_evidence':tests,'installed_files_checked':len(inventory),'native_case_counts':native_counts}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('task_id')
    args=parser.parse_args()
    WORK.mkdir(parents=True,exist_ok=True)
    RESULTS.mkdir(parents=True,exist_ok=True)
    INSTALL.parent.mkdir(parents=True,exist_ok=True)
    if (ARTIFACTS/'install.tar.gz').exists():
        with tarfile.open(ARTIFACTS/'install.tar.gz') as archive:
            archive.extractall(INSTALL.parent,filter='data')
    elif (ARTIFACTS/'install').exists():
        shutil.copytree(ARTIFACTS/'install',INSTALL,symlinks=True)
    evidence=verify_evidence(args.task_id)
    consumers={
        'BUILDv1-A01':lambda:c_consumer('new_zlib',ZLIB,['z'],static=True),
        'BUILDv1-A02':lambda:c_consumer('new_zstd',ZSTD,['zstd']),
        'BUILDv1-A03':lambda:c_consumer('new_archive',ARCHIVE,['archive']),
        'BUILDv1-A04':consume_curl,
        'BUILDv1-A05':consume_ssl,
        'BUILDv1-A06':lambda:c_consumer('new_uv',UV,['uv'],extra=['-lpthread','-ldl','-lrt']),
        'BUILDv1-A07':lambda:c_consumer('new_event',EVENT,['event_core']),
        'BUILDv1-A08':lambda:c_consumer('new_pcre',PCRE,['pcre2-8'],static=True),
        'BUILDv1-A09':lambda:c_consumer('new_nghttp',NGHTTP,['nghttp2']),
        'BUILDv1-A10':lambda:c_consumer('new_git',GIT,['git2']),
    }
    sys.modules['grader_inside']=sys.modules[__name__]
    from grader_runtimes import CONSUMERS as runtime_consumers
    consumers.update(runtime_consumers)
    from grader_python import CONSUMERS as python_consumers
    from grader_media import CONSUMERS as media_consumers
    consumers.update(python_consumers)
    consumers.update(media_consumers)
    from grader_databases import CONSUMERS as database_consumers
    from grader_languages import CONSUMERS as language_consumers
    consumers.update(database_consumers)
    consumers.update(language_consumers)
    from grader_lightgbm import CONSUMERS as lightgbm_consumers
    consumers.update(lightgbm_consumers)
    assert args.task_id in consumers,'independent consumer not implemented for '+args.task_id
    result=consumers[args.task_id]()
    (RESULTS/'commands.json').write_text(json.dumps(COMMANDS,indent=2))
    (RESULTS/'results.json').write_text(json.dumps({**evidence,'task_id':args.task_id,'passed':True,
                                                   'fresh_container':True,'extracted_source_present':False,
                                                   'independent_consumer':str(result)},ensure_ascii=False,indent=2))
    print('INDEPENDENT_ACCEPTANCE',args.task_id,'passed')


if __name__=='__main__':
    main()
