"""Independent database persistence, IPC and local routing consumers."""
import contextlib
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.request
from grader_inside import INSTALL,WORK,execute,COMMANDS,find_library


def binary(name):
    candidates=[INSTALL/'bin'/name,INSTALL/'sbin'/name,INSTALL/name,*INSTALL.rglob(name)]
    for p in candidates:
        if p.is_file() and os.access(p,os.X_OK):return p
    raise AssertionError('delivered executable missing: '+name)


def env():return {'LD_LIBRARY_PATH':str(INSTALL/'lib')+':'+str(INSTALL/'lib64')}


def unused_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


@contextlib.contextmanager
def service(argv,ready=None,extra=None):
    log=WORK/'service.log';f=log.open('wb')
    p=subprocess.Popen([str(x) for x in argv],cwd=WORK,env={**os.environ,**env(),**(extra or {})},stdout=f,stderr=subprocess.STDOUT)
    COMMANDS.append({'argv':[str(x) for x in argv],'cwd':str(WORK),'kind':'service_start','pid':p.pid})
    try:
        deadline=time.monotonic()+40
        if ready:
            while True:
                assert p.poll() is None,log.read_text(errors='replace')[-5000:]
                try:
                    if ready():break
                except (OSError,subprocess.SubprocessError):pass
                assert time.monotonic()<deadline,'service never became ready: '+log.read_text(errors='replace')[-3000:]
                time.sleep(.1)
        yield p
    finally:
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        f.close();COMMANDS.append({'kind':'service_stop','pid':p.pid,'exit_code':p.returncode,'log_tail':log.read_text(errors='replace')[-4000:]})


def postgres():
    data=WORK/'pgdata';sock=WORK/'sock';sock.mkdir();e={**env(),'PGHOST':str(sock),'PGUSER':'sbench','PGDATABASE':'postgres'}
    execute([binary('initdb'),'-D',data,'-U','sbench','--no-locale','--encoding=UTF8'],env=e)
    ctl=binary('pg_ctl');execute([ctl,'-D',data,'-o','-k '+str(sock)+" -c listen_addresses=''",'-w','start'],env=e)
    try:
        sql='CREATE TABLE independent(id int PRIMARY KEY,v text);BEGIN;INSERT INTO independent VALUES(1,\'alpha\'),(2,\'beta\');COMMIT;BEGIN;UPDATE independent SET v=\'wrong\';ROLLBACK;SELECT string_agg(v,\',\' ORDER BY id) FROM independent;'
        out=execute([binary('psql'),'-X','-v','ON_ERROR_STOP=1','-At','-c',sql],env=e).stdout;assert b'alpha,beta' in out
    finally:execute([ctl,'-D',data,'-m','fast','-w','stop'],env=e)
    execute([ctl,'-D',data,'-o','-k '+str(sock)+" -c listen_addresses=''",'-w','start'],env=e)
    try:assert execute([binary('psql'),'-X','-At','-c','SELECT count(*) FROM independent'],env=e).stdout.strip()==b'2'
    finally:execute([ctl,'-D',data,'-m','fast','-w','stop'],env=e)
    return 'independent PostgreSQL transaction/rollback/restart persisted 2 rows'


def mariadb():
    data=WORK/'mariadb';sock=WORK/'maria.sock'
    execute([binary('mariadb-install-db'),'--basedir='+str(INSTALL),'--datadir='+str(data),'--auth-root-authentication-method=normal'],timeout=300)
    argv=[binary('mariadbd'),'--no-defaults','--basedir='+str(INSTALL),'--datadir='+str(data),'--socket='+str(sock),'--pid-file='+str(WORK/'maria.pid'),'--skip-networking']
    def ready():return sock.exists()
    cli=[binary('mariadb'),'--no-defaults','--socket='+str(sock),'-u','root','-N','-B']
    with service(argv,ready):
        execute(cli+['-e',"CREATE DATABASE independent;USE independent;CREATE TABLE t(id INT PRIMARY KEY,v INT) ENGINE=InnoDB;START TRANSACTION;INSERT INTO t VALUES(1,7),(2,9);COMMIT;START TRANSACTION;DELETE FROM t;ROLLBACK;"])
        assert execute(cli+['-e','SELECT SUM(v) FROM independent.t']).stdout.strip()==b'16'
    with service(argv,ready):assert execute(cli+['-e','SELECT COUNT(*) FROM independent.t']).stdout.strip()==b'2'
    return 'independent MariaDB transaction/restart passed'


def redis():
    port=unused_port();argv=[binary('redis-server'),'--port',str(port),'--bind','127.0.0.1','--dir',str(WORK),'--appendonly','yes','--appendfsync','always','--save','']
    cli=[binary('redis-cli'),'-p',str(port),'--raw']
    def ready():
        with socket.create_connection(('127.0.0.1',port),timeout=.2):return True
    with service(argv,ready):
        assert execute(cli+['SET','independent','alpha']).stdout.strip()==b'OK'
        execute(cli+['INCRBY','count','17']);assert execute(cli+['GET','count']).stdout.strip()==b'17'
        execute(cli+['RPUSH','items','one','two']);assert execute(cli+['LRANGE','items','0','-1']).stdout.splitlines()==[b'one',b'two']
    with service(argv,ready):assert execute(cli+['GET','independent']).stdout.strip()==b'alpha'
    return 'independent Redis commands/AOF restart passed'


def rocksdb():
    code=WORK/'new_rocks.cpp';code.write_text(r'''
#include <rocksdb/db.h>
#include <rocksdb/write_batch.h>
#include <iostream>
int main(){rocksdb::DB*d;rocksdb::Options o;o.create_if_missing=true;if(!rocksdb::DB::Open(o,"new-db",&d).ok())return 1;rocksdb::WriteBatch b;b.Put("alpha","7");b.Put("beta","9");if(!d->Write(rocksdb::WriteOptions(),&b).ok())return 2;delete d;if(!rocksdb::DB::Open(o,"new-db",&d).ok())return 3;std::string v;if(!d->Get(rocksdb::ReadOptions(),"alpha",&v).ok()||v!="7")return 4;if(!d->Delete(rocksdb::WriteOptions(),"beta").ok())return 5;if(!d->Get(rocksdb::ReadOptions(),"beta",&v).IsNotFound())return 6;delete d;std::cout<<"new RocksDB static SDK persist/delete passed\n";return 0;}
''');app=WORK/'new_rocks';execute(['g++','-std=c++17',code,'-I',INSTALL/'include',find_library('rocksdb',static=True),'-lsnappy','-lz','-lbz2','-llz4','-lzstd','-ldl','-lpthread','-o',app]);return execute([app]).stdout.decode()


def duckdb():
    cli=binary('duckdb');execute([cli,'new.duckdb','-c',"CREATE TABLE independent AS SELECT i, i*i AS sq FROM range(10) t(i);BEGIN;DELETE FROM independent;ROLLBACK;"],env=env())
    result=execute([cli,'new.duckdb','-csv','-noheader','-c','SELECT count(*),sum(sq) FROM independent'],env=env());assert result.stdout.strip()==b'10,285';return 'independent DuckDB SQL/transaction/reopen passed'


def arrow():
    (WORK/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(NewArrow CXX)\nset(CMAKE_CXX_STANDARD 17)\nfind_package(Arrow REQUIRED)\nadd_executable(new_arrow new_arrow.cpp)\ntarget_link_libraries(new_arrow PRIVATE Arrow::arrow_shared)\n')
    (WORK/'new_arrow.cpp').write_text(r'''
#include <arrow/api.h>
#include <arrow/io/api.h>
#include <arrow/ipc/api.h>
#include <iostream>
int main(){arrow::Int64Builder b;if(!b.AppendValues({3,5,7}).ok())return 1;std::shared_ptr<arrow::Array>a;if(!b.Finish(&a).ok())return 2;auto s=arrow::schema({arrow::field("values",arrow::int64())});auto batch=arrow::RecordBatch::Make(s,3,{a});auto file=arrow::io::FileOutputStream::Open("new.arrow");if(!file.ok())return 3;auto writer=arrow::ipc::MakeFileWriter(*file,s);if(!writer.ok()||!(*writer)->WriteRecordBatch(*batch).ok()||!(*writer)->Close().ok()||!(*file)->Close().ok())return 4;auto in=arrow::io::ReadableFile::Open("new.arrow");if(!in.ok())return 5;auto r=arrow::ipc::RecordBatchFileReader::Open(*in);if(!r.ok()||(*r)->num_record_batches()!=1)return 6;auto rb=(*r)->ReadRecordBatch(0);if(!rb.ok()||!(*rb)->Equals(*batch))return 7;std::cout<<"new Arrow C++ IPC write/read passed\n";}
''');execute(['cmake','-S',WORK,'-B',WORK/'build','-DCMAKE_PREFIX_PATH='+str(INSTALL)]);execute(['cmake','--build',WORK/'build','-j2']);app=WORK/'build/new_arrow';assert str(INSTALL) in execute(['ldd',app],env=env()).stdout.decode();return execute([app],env=env()).stdout.decode()


def clickhouse():
    cli=binary('clickhouse');(WORK/'new.csv').write_text('a,7\nb,9\na,3\n')
    out=execute([cli,'local','--structure','key String, value UInt64','--input-format','CSV','--file','new.csv','--query','SELECT key,sum(value) FROM table GROUP BY key ORDER BY key FORMAT TSV']).stdout;assert out.splitlines()==[b'a\t10',b'b\t9'];return 'new ClickHouse local SQL aggregate passed'


def etcd():
    client=unused_port();peer=unused_port();url='http://127.0.0.1:'+str(client);peerurl='http://127.0.0.1:'+str(peer)
    argv=[binary('etcd'),'--name','independent','--data-dir',WORK/'etcd-data','--listen-client-urls',url,'--advertise-client-urls',url,'--listen-peer-urls',peerurl,'--initial-advertise-peer-urls',peerurl,'--initial-cluster','independent='+peerurl]
    cli=[binary('etcdctl'),'--endpoints',url]
    def ready():
        with socket.create_connection(('127.0.0.1',client),timeout=.2):return True
    with service(argv,ready,{'ETCDCTL_API':'3'}):
        execute(cli+['put','new-key','new-value']);assert execute(cli+['get','new-key','--print-value-only']).stdout.strip()==b'new-value';execute(cli+['snapshot','save','new-snapshot.db'])
    with service(argv,ready,{'ETCDCTL_API':'3'}):assert execute(cli+['get','new-key','--print-value-only']).stdout.strip()==b'new-value'
    assert (WORK/'new-snapshot.db').stat().st_size>4096;execute([binary('etcdutl'),'snapshot','status','new-snapshot.db']);return 'new etcd put/get/restart/snapshot passed'


@contextlib.contextmanager
def upstream():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(b'new independent upstream')
        def log_message(self,*a):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    try:yield server.server_port
    finally:server.shutdown();server.server_close()


def nginx():
    port=unused_port();root=WORK/'www';root.mkdir();(root/'index.html').write_text('new delivered nginx static file')
    with upstream() as up:
        config=WORK/'nginx.conf';config.write_text('daemon off;\npid '+str(WORK/'nginx.pid')+';\nerror_log '+str(WORK/'nginx-error.log')+';\nevents {worker_connections 32;}\nhttp {access_log off;client_body_temp_path '+str(WORK/'client-temp')+';proxy_temp_path '+str(WORK/'proxy-temp')+';server {listen 127.0.0.1:'+str(port)+';location / {root '+str(root)+';}location /proxy {proxy_pass http://127.0.0.1:'+str(up)+';}}}\n')
        def ready():
            with socket.create_connection(('127.0.0.1',port),timeout=.2):return True
        with service([binary('nginx'),'-p',str(WORK),'-c',str(config)],ready):
            assert urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/').read()==b'new delivered nginx static file'
            assert urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/proxy').read()==b'new independent upstream'
    return 'new NGINX static/proxy localhost consumer passed'


def envoy():
    port=unused_port()
    with upstream() as up:
        config=WORK/'envoy.json';data={'static_resources':{'listeners':[{'name':'local','address':{'socket_address':{'address':'127.0.0.1','port_value':port}},'filter_chains':[{'filters':[{'name':'envoy.filters.network.http_connection_manager','typed_config':{'@type':'type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager','stat_prefix':'independent','route_config':{'name':'routes','virtual_hosts':[{'name':'local','domains':['*'],'routes':[{'match':{'prefix':'/'},'route':{'cluster':'backend'}}]}]},'http_filters':[{'name':'envoy.filters.http.router','typed_config':{'@type':'type.googleapis.com/envoy.extensions.filters.http.router.v3.Router'}}]}}]}]}],'clusters':[{'name':'backend','connect_timeout':'1s','type':'STATIC','load_assignment':{'cluster_name':'backend','endpoints':[{'lb_endpoints':[{'endpoint':{'address':{'socket_address':{'address':'127.0.0.1','port_value':up}}}}]}]}}]}}
        config.write_text(json.dumps(data))
        def ready():
            with socket.create_connection(('127.0.0.1',port),timeout=.2):return True
        try:app=binary('envoy')
        except AssertionError:app=binary('envoy-static')
        with service([app,'-c',config,'--concurrency','2','--disable-hot-restart'],ready):assert urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/new').read()==b'new independent upstream'
    return 'new Envoy HTTP route/real backend passed'

CONSUMERS={'BUILDv1-D%02d'%n:fn for n,fn in enumerate([postgres,mariadb,redis,rocksdb,duckdb,arrow,clickhouse,etcd,nginx,envoy],1)}
