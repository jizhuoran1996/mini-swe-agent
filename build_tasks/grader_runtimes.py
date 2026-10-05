"""Functional checks for newly built compiler and language runtime deliveries."""
import json
from pathlib import Path
from grader_inside import INSTALL, WORK, execute


def binary(*names):
    for name in names:
        path=INSTALL/'bin'/name
        if path.is_file():return path
    raise AssertionError('new installed executable missing: '+repr(names))


def compiler(kind):
    source=WORK/'new.cpp'
    source.write_text('''#include <algorithm>
#include <future>
#include <iostream>
#include <numeric>
#include <vector>
int main(){std::vector<int> a={9,1,7,5,3};std::sort(a.begin(),a.end());
auto f=std::async(std::launch::async,[a]{return std::accumulate(a.begin(),a.end(),0);});
if(a.front()!=1||a.back()!=9||f.get()!=25)return 1;std::cout<<"NEW_COMPILER_OK";return 0;}
''')
    compiler=binary('clang++') if kind=='clang' else binary('g++')
    program=WORK/'compiled'
    execute([compiler,'-std=c++17','-O2',source,'-pthread','-o',program])
    assert execute([program]).stdout==b'NEW_COMPILER_OK'
    return {'compiler':str(compiler),'generated_executable':str(program),'cxx17_sort_and_threads':True}


def binutils():
    (WORK/'new.s').write_text('.global _start\n.text\n_start:\n mov $60,%rax\n mov $42,%rdi\n syscall\n')
    execute([binary('as'),'new.s','-o','new.o'])
    execute([binary('ar'),'rcs','new.a','new.o'])
    assert execute([binary('ar'),'t','new.a']).stdout.strip()==b'new.o'
    execute([binary('ld'),'new.o','-o','new_program'])
    execute([WORK/'new_program'],expected=42)
    assert b'ELF64' in execute([binary('readelf'),'-h','new_program']).stdout
    assert b'_start' in execute([binary('objdump'),'-t','new_program']).stdout
    return {'assembler_linker_archive_consumer':True}


def python():
    program=r'''
import concurrent.futures,json,pathlib,sqlite3,subprocess,sys
assert pathlib.Path(sys.executable).resolve().is_relative_to(pathlib.Path('/workspace/output/install'))
db=sqlite3.connect('fresh.db');db.execute('create table t(k integer,v text)')
db.executemany('insert into t values (?,?)',[(3,'c'),(1,'a'),(2,'b')]);db.commit();db.close()
db=sqlite3.connect('fresh.db');assert db.execute('select group_concat(v,\'\') from (select v from t order by k)').fetchone()[0]=='abc'
assert json.loads(json.dumps({'a':[1,None,True]}))=={'a':[1,None,True]}
with concurrent.futures.ThreadPoolExecutor(2) as p:assert list(p.map(lambda i:i*i,range(10)))==[i*i for i in range(10)]
assert subprocess.check_output([sys.executable,'-I','-c','print(6*7)']).strip()==b'42'
print(json.dumps({'executable':sys.executable,'sqlite_module':sqlite3.__file__,'version':sys.version}))
'''
    return execute([binary('python3.12','python3'),'-I','-c',program],env={'PYTHONPATH':''}).stdout.decode()


def node():
    source=r'''
const assert=require('assert'),{Transform,Readable}=require('stream'),{pipeline}=require('stream/promises'),cp=require('child_process');
(async()=>{let s='';const t=new Transform({transform(c,e,cb){cb(null,c.toString().toUpperCase())}});
t.on('data',c=>s+=c);await pipeline(Readable.from(['a','b','c']),t);assert.equal(s,'ABC');
assert.equal(cp.execFileSync(process.execPath,['-e','process.stdout.write(String(6*7))']).toString(),'42');
assert(new Intl.DateTimeFormat('en-US',{timeZone:'UTC',year:'numeric'}).format(new Date('2025-01-02')).includes('2025'));
console.log(JSON.stringify({executable:process.execPath,version:process.version,stream:s}));})().catch(e=>{console.error(e);process.exit(1)});
'''
    (WORK/'new.js').write_text(source)
    return execute([binary('node'),WORK/'new.js']).stdout.decode()


def ruby():
    program='require "json"; require "zlib"; a=(1..100).to_a; raise unless a.sum==5050; x=JSON.generate({"v"=>a}); raise unless JSON.parse(x)["v"]==a; raise unless Zlib::Inflate.inflate(Zlib::Deflate.deflate(x))==x; q=Queue.new; t=Thread.new{q << 42}; raise unless q.pop==42;t.join;puts "NEW_RUBY_OK"'
    assert b'NEW_RUBY_OK' in execute([binary('ruby'),'-e',program]).stdout
    return {'strings_json_compression_and_threads':True}


def php():
    program='$x=["a"=>[1,null,true]];if(json_decode(json_encode($x),true)!=$x)exit(1);$db=new PDO("sqlite:fresh.sqlite");$db->exec("create table t(v integer)");$db->exec("insert into t values(10),(20),(30)");if($db->query("select sum(v) from t")->fetchColumn()!=60)exit(2);echo "NEW_PHP_OK";'
    assert execute([binary('php'),'-r',program]).stdout==b'NEW_PHP_OK'
    return {'json_pdo_sqlite':True}


def go():
    program=r'''package main
import("bytes";"compress/gzip";"encoding/json";"fmt";"io";"os")
func main(){var compressed bytes.Buffer;w:=gzip.NewWriter(&compressed);w.Write([]byte("source-built toolchain"));w.Close();r,e:=gzip.NewReader(&compressed);if e!=nil{panic(e)};b,e:=io.ReadAll(r);if e!=nil||string(b)!="source-built toolchain"{panic("gzip")};var a []int;if json.Unmarshal([]byte("[10,20,12]"),&a)!=nil{panic("json")};if a[0]+a[1]+a[2]!=42{panic("sum")};fmt.Println("NEW_GO_OK");_ = os.Stdout}
'''
    (WORK/'new.go').write_text(program)
    (WORK/'go-cache').mkdir(exist_ok=True)
    env={'GOROOT':str(INSTALL),'GOCACHE':str(WORK/'go-cache'),'GOPROXY':'off','GOTOOLCHAIN':'local','CGO_ENABLED':'0'}
    execute([binary('go'),'build','-o','new_go','new.go'],env=env)
    assert execute([WORK/'new_go']).stdout.strip()==b'NEW_GO_OK'
    return {'new_toolchain_compile_json_gzip':True}


def rust():
    (WORK/'new.rs').write_text('''use std::{fs,thread};fn main(){let mut v=vec![9,3,7,1,5];v.sort();let t=thread::spawn(move||v.iter().sum::<i32>());assert_eq!(t.join().unwrap(),25);fs::write("new.txt",b"fresh compiler").unwrap();assert_eq!(fs::read("new.txt").unwrap(),b"fresh compiler");println!("NEW_RUST_OK");}''')
    execute([binary('rustc'),'--edition=2021',WORK/'new.rs','-o',WORK/'new_rust'])
    assert execute([WORK/'new_rust']).stdout.strip()==b'NEW_RUST_OK'
    execute([binary('rustdoc'),WORK/'new.rs','-o',WORK/'docs'])
    assert list((WORK/'docs').rglob('*.html'))
    return {'new_rustc_std_threads_files_rustdoc':True}


def jdk():
    (WORK/'Fresh.java').write_text('''import java.util.*;import java.util.concurrent.*;import java.nio.file.*;
public class Fresh{public static void main(String[] args)throws Exception{var pool=Executors.newFixedThreadPool(2);var future=pool.submit(()->List.of(10,20,12).stream().mapToInt(Integer::intValue).sum());if(future.get()!=42)throw new AssertionError();pool.shutdown();Files.writeString(Path.of("new.txt"),"fresh JDK");if(!Files.readString(Path.of("new.txt")).equals("fresh JDK"))throw new AssertionError();System.out.println("NEW_JDK_OK");}}''')
    execute([binary('javac'),WORK/'Fresh.java'])
    assert execute([binary('java'),'-cp',WORK,'Fresh']).stdout.strip()==b'NEW_JDK_OK'
    return {'javac_jvm_concurrency_files':True}


CONSUMERS={
 'BUILDv1-B01':lambda:compiler('clang'),'BUILDv1-B02':lambda:compiler('gcc'),
 'BUILDv1-B03':binutils,'BUILDv1-B04':python,'BUILDv1-B05':node,
 'BUILDv1-B06':ruby,'BUILDv1-B07':php,'BUILDv1-B08':go,'BUILDv1-B09':rust,'BUILDv1-B10':jdk,
}
