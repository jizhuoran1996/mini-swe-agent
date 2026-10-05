"""Independent Java library and JavaScript compiler consumers."""
import json
import os
from pathlib import Path
import tarfile
from grader_inside import INSTALL,WORK,execute

JAVA={
'E01':('KafkaConsumer',r'''
import java.util.Arrays;import org.apache.kafka.common.serialization.ByteArraySerializer;import org.apache.kafka.common.serialization.ByteArrayDeserializer;import org.apache.kafka.common.serialization.StringSerializer;import org.apache.kafka.common.serialization.StringDeserializer;
public class KafkaConsumer{public static void main(String[]args){byte[]x={0,1,2,(byte)255};if(!Arrays.equals(x,new ByteArrayDeserializer().deserialize("new",new ByteArraySerializer().serialize("new",x))))throw new AssertionError();String s="new-编译";if(!s.equals(new StringDeserializer().deserialize("new",new StringSerializer().serialize("new",s))))throw new AssertionError();System.out.println("independent Kafka clients serialization passed");}}
'''),
'E02':('SparkConsumer',r'''
import org.apache.spark.SparkConf;import org.apache.spark.api.java.JavaSparkContext;import java.util.*;
public class SparkConsumer{public static void main(String[]a){SparkConf c=new SparkConf().setMaster("local[2]").setAppName("independent").set("spark.ui.enabled","false").set("spark.driver.host","127.0.0.1").set("spark.driver.bindAddress","127.0.0.1");try(JavaSparkContext s=new JavaSparkContext(c)){List<Integer>x=new ArrayList<>();for(int i=1;i<=100;i++)x.add(i);int r=s.parallelize(x,4).map(v->v*2).reduce((u,v)->u+v);if(r!=10100)throw new AssertionError(r);System.out.println("independent Spark RDD result "+r);}}}
'''),
'E03':('FlinkConsumer',r'''
import org.apache.flink.core.memory.DataInputDeserializer;import org.apache.flink.core.memory.DataOutputSerializer;import java.util.Arrays;
public class FlinkConsumer{public static void main(String[]a)throws Exception{DataOutputSerializer o=new DataOutputSerializer(16);o.writeInt(42);o.writeLong(123456789L);o.writeUTF("new-序列化");byte[]b=o.getCopyOfBuffer();DataInputDeserializer i=new DataInputDeserializer(b);if(i.readInt()!=42||i.readLong()!=123456789L||!i.readUTF().equals("new-序列化"))throw new AssertionError();System.out.println("independent Flink core serialization passed");}}
'''),
'E04':('LuceneConsumer',r'''
import org.apache.lucene.store.ByteBuffersDirectory;import org.apache.lucene.index.*;import org.apache.lucene.document.*;import org.apache.lucene.search.*;
public class LuceneConsumer{public static void main(String[]a)throws Exception{try(ByteBuffersDirectory dir=new ByteBuffersDirectory()){try(IndexWriter w=new IndexWriter(dir,new IndexWriterConfig(null))){for(int n=0;n<3;n++){Document d=new Document();d.add(new StringField("tag",n==1?"match":"other",Field.Store.YES));d.add(new StoredField("id",n));w.addDocument(d);}w.commit();}try(DirectoryReader r=DirectoryReader.open(dir)){IndexSearcher s=new IndexSearcher(r);TopDocs h=s.search(new TermQuery(new Term("tag","match")),10);if(h.totalHits.value!=1||s.storedFields().document(h.scoreDocs[0].doc).getField("id").numericValue().intValue()!=1)throw new AssertionError();System.out.println("independent Lucene index/search/reopen passed");}}}}
'''),
'E05':('ElasticConsumer',r'''
import org.elasticsearch.index.query.TermQueryBuilder;import org.elasticsearch.index.query.BoolQueryBuilder;import org.elasticsearch.index.query.QueryBuilders;
public class ElasticConsumer{public static void main(String[]a){TermQueryBuilder t=QueryBuilders.termQuery("tag","independent");if(!t.fieldName().equals("tag")||!t.value().toString().equals("independent"))throw new AssertionError();BoolQueryBuilder b=QueryBuilders.boolQuery().must(t).filter(QueryBuilders.existsQuery("value"));if(b.must().size()!=1||b.filter().size()!=1)throw new AssertionError();String json=b.toString();if(!json.contains("independent")||!json.contains("exists"))throw new AssertionError(json);System.out.println("independent Elasticsearch query API passed");}}
'''),
}


def java_consumer(short):
    jars=sorted(INSTALL.rglob('*.jar'));assert jars,'delivered Java target/dependency closure missing'
    cp=':'.join(map(str,jars));name,program=JAVA[short];source=WORK/(name+'.java');source.write_text(program)
    execute(['javac','-cp',cp,source]);cmd=['java','-Xmx2g','-XX:ActiveProcessorCount=2']
    if short=='E02':
        helper=WORK/'ModuleOptionsPrinter.java'
        helper.write_text('public class ModuleOptionsPrinter{public static void main(String[]a){System.out.print(org.apache.spark.launcher.JavaModuleOptions.defaultModuleOptions());}}')
        execute(['javac','-cp',cp,helper])
        options=execute(['java','-cp',str(WORK)+':'+cp,'ModuleOptionsPrinter']).stdout.decode().split()
        assert '--add-opens=java.base/sun.nio.ch=ALL-UNNAMED' in options,'original Spark Java17 launch options absent'
        cmd+=options
    return execute(cmd+['-cp',str(WORK)+':'+cp,name],env={'SPARK_LOCAL_IP':'127.0.0.1'},timeout=300).stdout.decode()


def delivered_file(name):
    choices=[p for p in INSTALL.rglob(name) if p.is_file() and 'node_modules' not in p.parts]
    assert choices,'source-built installed module missing: '+name
    return min(choices,key=lambda p:len(p.parts))


def typescript():
    module=delivered_file('typescript.js');script=WORK/'new_ts.cjs';script.write_text('const ts=require('+json.dumps(str(module))+');const src="const value: number = 6; exports.result = value * 7;";const r=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020},reportDiagnostics:true});if(r.diagnostics.some(d=>d.category===ts.DiagnosticCategory.Error))throw Error("diagnostics");const vm=require("node:vm");const c={exports:{}};vm.runInNewContext(r.outputText,c);if(c.exports.result!==42)throw Error("output mismatch");console.log("independent TypeScript compile/execute passed");');return execute(['node',script]).stdout.decode()


def rollup():
    npm_module=INSTALL/'node_modules/rollup/dist/rollup.js'
    if npm_module.is_file():
        metadata=json.loads((npm_module.parent.parent/'package.json').read_text())
        assert metadata['name']=='rollup' and metadata['version']=='4.40.2'
        module=npm_module
    else:
        module=delivered_file('rollup.js')
    (WORK/'dep.js').write_text('export const value=14;\n');(WORK/'entry.js').write_text('import {value} from "./dep.js";export const result=value*3;\n')
    script=WORK/'new_rollup.cjs';script.write_text('const {rollup}=require('+json.dumps(str(module))+');(async()=>{const b=await rollup({input:"entry.js"});const r=await b.generate({format:"cjs"});const native=Object.keys(require.cache).filter(p=>p.endsWith(".node"));if(native.length!==1||!native[0].startsWith('+json.dumps(str(INSTALL))+'+"/"))throw Error("submitted native parser not loaded");const vm=require("node:vm");const c={exports:{}};vm.runInNewContext(r.output[0].code,c);if(c.exports.result!==42)throw Error("bundle mismatch");await b.close();console.log("independent Rollup native parser/resolve/bundle/execute passed");})().catch(e=>{console.error(e);process.exit(1)});');return execute(['node',script]).stdout.decode()


def babel():
    bundle=INSTALL/'consumer-deps.tar.gz'
    if bundle.is_file():
        with tarfile.open(bundle) as archive:
            archive.extractall(WORK,filter='data')
        module=WORK/'node_modules/@babel/core'
        assert json.loads((module/'package.json').read_text())['name']=='@babel/core'
        packed=WORK/'packed_core';packed.mkdir()
        with tarfile.open(INSTALL/'tarballs/babel-core.tgz') as archive:
            archive.extractall(packed,filter='data')
        for file in (packed/'package').rglob('*'):
            if file.is_file():
                assert file.read_bytes()==(module/file.relative_to(packed/'package')).read_bytes(),'SDK core differs from source-built package'
    else:
        choices=[p for p in INSTALL.rglob('package.json') if json.loads(p.read_text()).get('name')=='@babel/core'];assert choices
        module=choices[0].parent
    script=WORK/'new_babel.cjs'
    script.write_text('const babel=require('+json.dumps(str(module))+');const vm=require("node:vm");const r=babel.transformSync("class Counter { value: number = 6; run = () => this.value * 7; } exports.result=new Counter().run();",{filename:"new_input.ts",configFile:false,babelrc:false,ast:true,sourceMaps:true,presets:[[require.resolve("@babel/preset-env"),{targets:{ie:"11"}}],require.resolve("@babel/preset-typescript")]});if(!r.ast||!r.map||!r.code||r.code.includes("=>")||r.code.includes(": number"))throw Error("compiler output absent or not lowered");const c={exports:{}};vm.runInNewContext(r.code,c);if(c.exports.result!==42)throw Error("output mismatch");let rejected=false;try{babel.transformSync("const = ;",{configFile:false,babelrc:false});}catch(e){rejected=true;}if(!rejected)throw Error("invalid input accepted");console.log("independent Babel SDK TypeScript/ES5/execute/negative passed");')
    return execute(['node',script]).stdout.decode()


def esbuild():
    candidates=[p for p in INSTALL.rglob('esbuild') if p.is_file() and os.access(p,os.X_OK)];assert candidates
    (WORK/'new.ts').write_text('const x: number=6;console.log(x*7);\n');execute([candidates[0],'new.ts','--bundle','--platform=node','--outfile=new.js']);assert execute(['node','new.js']).stdout.strip()==b'42';return 'independent esbuild TypeScript/bundle/execute passed'


def swc():
    choices=[p for p in INSTALL.rglob('package.json') if json.loads(p.read_text()).get('name')=='@swc/core'];assert choices
    script=WORK/'new_swc.cjs';script.write_text('const swc=require('+json.dumps(str(choices[0].parent))+');const vm=require("node:vm");const r=swc.transformSync("const value: number=6;exports.result=value*7;",{jsc:{parser:{syntax:"typescript"},target:"es2019"},module:{type:"commonjs"}});const c={exports:{}};vm.runInNewContext(r.code,c);if(c.exports.result!==42)throw Error("compiled output mismatch");console.log("independent SWC native transform/execute passed");');return execute(['node',script]).stdout.decode()

CONSUMERS={'BUILDv1-'+short:(lambda short=short:java_consumer(short)) for short in JAVA}
CONSUMERS.update({'BUILDv1-E%02d'%n:fn for n,fn in enumerate([typescript,rollup,babel,esbuild,swc],6)})
