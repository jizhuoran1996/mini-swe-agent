"""Designer-side acquisition and precise debug contracts, never solver code."""
import concurrent.futures,io,json,os,sqlite3,zipfile,shutil,urllib.parse
from pathlib import Path
import numpy as np
import requests
from assets import ROOT,ASSETS,fetch,digest,dataset_rows
from prepare_graphs import manifest
from prepare_text import save,lock
from specify_ready import freeze
from remote_file import RemoteFile

def directory(tid):
    p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True);return p
def models_ready(repo):
    p=ASSETS/'models'/repo.replace('/','--')
    if not (p/'asset_lock.json').exists():raise RuntimeError('Model acquisition still pending: '+repo)
    return p
def media(tid,repo,rows,body,details):
    directory(tid);models_ready(repo);save(tid,'requests.jsonl',rows)
    lock(tid,'designer-authored benign production requests',repo,details)
    freeze(tid,body.split('\n')[0],body)

def generators():
    media('GPUv1-C01','segmind/tiny-sd',[{'id':str(i),'prompt':p,'seed':2026+i} for i,p in enumerate(['A watercolor landscape with a river and trees','A ceramic mug on a wooden table','A mountain cabin at sunrise','A small sailboat on a quiet lake'])],'''交付四张真实扩散模型生成的场景插图
用 /models/segmind--tiny-sd 的 StableDiffusionPipeline，CUDA fp16，256×256、12 inference steps、guidance_scale=7.5、每行给定 seed。输入 requests.jsonl，全部处理一次，输出 output/images/{id}.png、index.jsonl（id/prompt/seed/image/参数）、run.json。入口 python solution/main.py run --input input --output output；python solution/main.py generate --prompt TEXT --seed N --output PNG 支持新的请求，不能依赖既有输出。同步 GPU 后提交；不可只输出随机噪声或复制图片。独立评价重放一例，同 seed 图像容差，并验证完整覆盖、可解码、CUDA denoiser 真正执行。质量单独记录。本调试使用真实训练过的 distilled SD，不是随机 tiny fixture。''',{'width':256,'height':256,'steps':12,'deviations':['trained distilled SD instead of SDXL; four genuine user requests at 256px; no formal large quality claim']})
    source=ROOT/'tasks/GPUv1-B02/input/images'
    from PIL import Image,ImageDraw
    for kind in ['C02','C03']:
        tid='GPUv1-'+kind;p=directory(tid);(p/'images').mkdir(exist_ok=True);(p/'masks').mkdir(exist_ok=True)
        rows=[]
        for i,f in enumerate(sorted(source.glob('*'))[:2]):
            image=Image.open(f).convert('RGB').resize((512,512));image.save(p/'images'/f'{i}.png')
            mask=Image.new('L',(512,512));ImageDraw.Draw(mask).rectangle((160,160,350,350),fill=255);mask.save(p/'masks'/f'{i}.png')
            rows.append({'id':str(i),'image':f'images/{i}.png','mask':f'masks/{i}.png','prompt':'A realistic photograph with natural lighting','seed':2026+i})
        repo='stable-diffusion-v1-5/stable-diffusion-inpainting' if kind=='C02' else 'lllyasviel/sd-controlnet-canny'
        save(tid,'requests.jsonl',rows);models_ready(repo)
        lock(tid,'COCO 2017 val images with designer region masks',repo,{'dimensions':[512,512],'steps':12,'deviations':['SD1.5 native inpainting/Canny ControlNet rather than source XL; two real COCO images; designed masks are task inputs']})
        common='入口 python solution/main.py run --input input --output output；另支持相同 run 入口对新的 requests.jsonl 处理。输出 images/{id}.png、index.jsonl、run.json，记录原输入 hash、模型、seed、steps、device、同步耗时。独立检查 coverage、图像、GPU denoiser、fresh request 和种子重放。'
        if kind=='C02':body='为真实照片修复指定区域\n用 CUDA StableDiffusionInpaintPipeline /models/stable-diffusion-v1-5--stable-diffusion-inpainting，fp16，512×512，12 steps，guidance=7.5。mask白色区域生成，黑色保护区域最终与输入逐像素一致（生成结果按 mask composite）。不是无条件生成；应把 image 和 mask 真实送给模型。'+common
        else:body='把真实照片的边缘约束转换成新素材\n从输入图片计算 Canny (100,200) 边缘，加载 ControlNetModel /models/lllyasviel--sd-controlnet-canny 加 /models/stable-diffusion-v1-5--stable-diffusion-v1-5 的 StableDiffusionControlNetPipeline。CUDA fp16，512×512，12 steps，guidance=7.5，conditioning_scale=1。保存 control/{id}.png 以及生成图。mask 字段不用于本题。'+common
        freeze(tid,body.split('\n')[0],body)

def other_media():
    for tid,repo,title,protocol in [
      ('GPUv1-C04','damo-vilab/text-to-video-ms-1.7b','生成一段可播放的完整视频','TextToVideoSDPipeline，CUDA fp16，256×256，16 frames，12 steps，guidance=7.5，8 fps，输出 video.mp4 及逐帧 PNG；后续 run --seed 不同生成新视频'),
      ('GPUv1-C05','stabilityai/stable-video-diffusion-img2vid','让提供的真实照片成为运动素材','StableVideoDiffusionPipeline，CUDA fp16，14 frames，256×256，12 steps，decode_chunk_size=2，motion_bucket_id=127，noise_aug_strength=.02，7 fps，输出 video.mp4 和逐帧 PNG；图像来自 COCO，不能只复制输入14遍'),
      ('GPUv1-C07','facebook/musicgen-small','生成可交付的短音乐素材','AutoProcessor + MusicgenForConditionalGeneration，CUDA，text conditional，4秒约200 audio-code tokens，greedy decode；输出32kHz mono WAV，三条 prompt 全覆盖，不提供 melody conditioning，明确是小规模 text-to-music 变体'),
      ('GPUv1-C08','cvssp/audioldm-s-full-v2','生成可用于素材库的环境音效','AudioLDMPipeline，CUDA fp16，audio_length_in_s=4，12 steps，guidance=2.5，输出16kHz WAV，三条 prompt 全覆盖'),
      ('GPUv1-C09','Qwen/Qwen3-TTS-12Hz-0.6B-Base','交付复用参考声线的短语音','官方 qwen_tts Qwen3TTSModel，CUDA，0.6B Base，generate_voice_clone；input/reference.wav 与 reference_text 是同一真实 LibriSpeech录音/转写，三条新英文文本，x_vector_only_mode=False，输出模型原生采样率 WAV；必须复用参考录音，不能用不支持声线克隆的 MMS TTS 冒充'),
    ]:
        p=directory(tid);models_ready(repo)
        rows=[{'id':str(i),'prompt':text,'text':text,'seed':2026+i} for i,text in enumerate((['A small boat sailing on calm water'] if tid.endswith(('C04','C05')) else ['Gentle acoustic guitar music','A steady piano melody','Soft orchestral background music'] if tid.endswith('C07') else ['Rain falling on a roof','Birds singing in a forest','Gentle waves on a beach'] if tid.endswith('C08') else ['Welcome to the scientific data library.','The next observation will begin shortly.','Please save the result for later use.']))]
        if tid.endswith('C05'):
            f=next((ROOT/'tasks/GPUv1-B02/input/images').glob('*'));shutil.copy2(f,p/'reference.jpg');rows[0]['image']='reference.jpg'
        if tid.endswith('C09'):
            a=ROOT/'tasks/GPUv1-A04/input';train=[json.loads(x) for x in (a/'train.jsonl').read_text().splitlines()];r=train[0]
            wav=a/r.get('audio',r.get('path',r.get('wav','')));shutil.copy2(wav,p/'reference.wav')
            (p/'reference_text.txt').write_text(r.get('text',r.get('transcript','')))
        save(tid,'requests.jsonl',rows)
        lock(tid,'designer production prompts'+(' and genuine COCO/LibriSpeech conditioning' if tid.endswith(('C05','C09')) else ''),repo,{'protocol':protocol,'deviations':['explicit smaller publicly downloadable native model; formal source family/config may differ; compare only this frozen instance']})
        freeze(tid,title,title+'\n'+protocol+'。统一入口 python solution/main.py run --input input --output output，支持 --seed 覆盖用于后续新请求；按 ID 保存完整媒体和 index.jsonl、run.json（输入/模型引用、参数、实际时长、GPU同步耗时）。输出必须可解码且有限、有非零内容；质量由独立验收报告，不要求调参或 ensemble。支持再次 run 输入新的 requests.jsonl，不能用既有文件作为答案。音频可使用 Transformers/Diffusers 官方 API，禁止调用随机 fixture、静音或伪造输出。')

def documents():
    tid='GPUv1-D01';p=directory(tid)
    with zipfile.ZipFile(ASSETS/'text/longbench_data.zip') as z:
        name=next(n for n in z.namelist() if n.endswith('qasper.jsonl'));raw=[json.loads(x) for x in z.read(name).decode().splitlines()][:8]
    save(tid,'requests.jsonl',[{'id':str(i),'document':r['context'],'question':r['input']} for i,r in enumerate(raw)])
    (ROOT/'tasks'/tid/'oracle').mkdir(exist_ok=True);(ROOT/'tasks'/tid/'oracle/references.json').write_text(json.dumps(raw))
    lock(tid,'zai-org/LongBench/qasper','Qwen/Qwen2.5-0.5B-Instruct',{'max_tokens':2048,'max_new_tokens':128,'deviations':['eight native Qasper questions, 0.5B model and 2048-token debug budget vs 32B formal protocol']})
    freeze(tid,'交付长论文问答目录与后续查询','''对8个真实 LongBench Qasper 文档/问题执行 CUDA Qwen2.5-0.5B-Instruct 问答，document 最多2048 tokens，保留question并用chat template，greedy最多128新tokens。入口 python solution/main.py run --input input --output output；输出 answers.jsonl（id/answer/raw_text/token_ids/input_tokens/truncated）、run.json。另支持 serve --port PORT，/health 和 POST /infer {id,document,question}，模型必须加载到CUDA后ready，后续问题不能依赖原输出。独立检查coverage、模型重算、fresh request/idle/SIGTERM，答案准确率另报。''')
    tid='GPUv1-D04';p=directory(tid)
    source='https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite'
    fetch(source,p/'chinook.sqlite',max_bytes=8*2**20)
    db=sqlite3.connect('file:'+str(p/'chinook.sqlite')+'?mode=ro',uri=True)
    schema='\n'.join(x[0] for x in db.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name") if x[0]);(p/'schema.sql').write_text(schema)
    questions=[('How many tracks are in the database?','SELECT COUNT(*) FROM Track'),('Which ten artists have the most albums?','SELECT a.Name,COUNT(*) n FROM Artist a JOIN Album b ON a.ArtistId=b.ArtistId GROUP BY a.ArtistId ORDER BY n DESC,a.Name LIMIT 10'),('What are the ten most expensive tracks?','SELECT Name,UnitPrice FROM Track ORDER BY UnitPrice DESC,Name LIMIT 10'),('How many customers are there in each country?','SELECT Country,COUNT(*) FROM Customer GROUP BY Country ORDER BY Country'),('What is the total revenue by billing country?','SELECT BillingCountry,SUM(Total) FROM Invoice GROUP BY BillingCountry ORDER BY BillingCountry'),('Which five genres have the most tracks?','SELECT g.Name,COUNT(*) n FROM Genre g JOIN Track t ON g.GenreId=t.GenreId GROUP BY g.GenreId ORDER BY n DESC,g.Name LIMIT 5')]
    save(tid,'requests.jsonl',[{'id':str(i),'question':q,'database':'chinook.sqlite'} for i,(q,s) in enumerate(questions)])
    oracle=ROOT/'tasks'/tid/'oracle';oracle.mkdir(exist_ok=True);(oracle/'references.json').write_text(json.dumps([{'id':str(i),'sql':s,'result':db.execute(s).fetchall()} for i,(q,s) in enumerate(questions)]));db.close()
    lock(tid,'lerocha/chinook-database','Qwen/Qwen2.5-Coder-0.5B-Instruct',{'source':source,'deviations':['Chinook genuine public sample database and six designer SQL questions instead of BIRD corpus; one database vs11; tiny code model']})
    freeze(tid,'生成并执行可复用的数据库查询','''input/chinook.sqlite 是完整真实公开 Chinook 示例库，schema.sql 和6个问题只给输入，没有 gold SQL。用CUDA Qwen2.5-Coder-0.5B-Instruct，把schema与问题送入模型，greedy最多256新token，统一提取SQL，保存 raw output/token_ids/SQL。只允许SELECT或WITH只读查询，sqlite连接mode=ro，进度回调限制每条执行<=3秒；危险SQL应拒绝。入口 python solution/main.py run --input input --output output；输出 answers.jsonl（id/sql/results或真实execution_error/raw/token_ids）、run.json；支持 query --database PATH --question TEXT --output JSON 的新问题。不得agent直接写问题答案或gold SQL冒充模型输出，语义错误算任务模型质量。独立检查模型生成、SQL防写入、全覆盖、新查询及独立gold执行对比。''')
    tid='GPUv1-D07';p=directory(tid);repo='opendatalab/OmniDocBench';info=requests.get('https://huggingface.co/api/datasets/'+repo,timeout=30).json();rev=info['sha']
    ann=fetch(f'https://huggingface.co/datasets/{repo}/resolve/{rev}/OmniDocBench.json',ASSETS/'vision/OmniDocBench.json',max_bytes=128*2**20)
    records=json.loads(ann.read_text());selected=records[:4];(p/'images').mkdir(exist_ok=True);rows=[]
    for i,r in enumerate(selected):
        original=r.get('page_info',{}).get('image_path',r.get('image_path'))
        if not original:raise ValueError('OmniDocBench image path schema: '+str(r)[:500])
        remote=original if original.startswith('images/') else 'images/'+Path(original).name
        target=p/'images'/f'{i}.png';fetch(f'https://huggingface.co/datasets/{repo}/resolve/{rev}/'+urllib.parse.quote(remote),target,max_bytes=16*2**20)
        rows.append({'id':str(i),'image':f'images/{i}.png','prompt':'Transcribe this document into Markdown, preserving reading order, headings, tables and equations. Do not invent illegible text.'})
    save(tid,'requests.jsonl',rows);o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);(o/'references.json').write_text(json.dumps(selected))
    lock(tid,repo,'Qwen/Qwen2.5-VL-3B-Instruct',{'dataset_revision':rev,'pages':4,'max_new_tokens':512,'deviations':['four native OmniDocBench pages, 3B VL model vs72B/1651pages']})
    freeze(tid,'把真实文档页面整理成可复用的 Markdown','''用 /models/Qwen--Qwen2.5-VL-3B-Instruct 与 AutoProcessor 的真实image+text输入，CUDA bf16，每张页面生成最多512 tokens，greedy，限制max_pixels=262144。入口 python solution/main.py run --input input --output output；输出每个ID的Markdown、documents.jsonl（id/text/token_ids/图片hash）、run.json；支持 infer --image PATH --prompt TEXT --output JSON 的新页面。真实页面来自OmniDocBench，hidden reference不提供。独立验收全coverage、输出合法、实际vision encoder CUDA、fresh新图片推理；OCR字符误差、阅读顺序/表格质量单独报告。禁止只OCR占位或复制预存文本。''')
    tid='GPUv1-D10';p=directory(tid);rows=dataset_rows('wmt/wmt14','de-en','test',8)
    save(tid,'requests.jsonl',[{'id':str(r['row_idx']),'source_language':'English','target_language':'German','text':r['row']['translation']['en']} for r in rows]);o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);(o/'references.json').write_text(json.dumps([r['row']['translation']['de'] for r in rows]))
    lock(tid,'wmt/wmt14/de-en/test','Qwen/Qwen2.5-0.5B-Instruct',{'deviations':['eight English-to-German sentences and0.5B multilingual LM rather than WMT24++8lang/Aya32B']})
    freeze(tid,'生成完整翻译目录与可复用翻译入口','''用CUDA /models/Qwen--Qwen2.5-0.5B-Instruct chat template翻译input/requests.jsonl的8条真实WMT14英语句为德语，greedy最多128新tokens，不提供目标句。入口 python solution/main.py run --input input --output output；输出 translations.jsonl（id/translation/raw_text/token_ids）、run.json；另支持 translate --text TEXT --source-language English --target-language German --output JSON 新句子。独立检查全coverage、token生成重算、新句子、CUDA调用，BLEU/chrF单独报告；不得调用预存译文。''')

def criteo():
    rows=dataset_rows('reczoo/Criteo_x1','default','train',1100);raw=[r['row'] for r in rows]
    keys=sorted(raw[0]);print('CRITEO_FIELDS',keys,flush=True)
    dense=sorted([k for k in keys if k.startswith('I')],key=lambda s:int(s[1:]));cats=sorted([k for k in keys if k.startswith('C')],key=lambda s:int(s[1:]));label=next(k for k in keys if k.lower() in ['label','click','y'])
    assert len(dense)==13 and len(cats)==26
    for tid in ['GPUv1-A07','GPUv1-E02']:
        p=directory(tid);save(tid,'train.jsonl',raw[:1000]);save(tid,'validation.jsonl',[{k:v for k,v in r.items() if k!=label} for r in raw[1000:]])
        (p/'schema.json').write_text(json.dumps({'dense_columns':dense,'categorical_columns':cats,'label_column':label}))
        o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);np.save(o/'validation_labels.npy',np.asarray([r[label] for r in raw[1000:]],dtype=np.int64))
        manifest(tid,{'dataset':'reczoo/Criteo_x1','revision':'4ecadde5eb8473e6ed6c570d9fb57e71079c0ef4','rows':[0,1100],'deviations':['native genuine processed Criteo_x1 subset rather than complete Terabyte raw logs; 1000train/100heldout; categorical domain intentionally small']})
    freeze('GPUv1-A07','交付可重载的点击率预测网络','''input/train.jsonl有1000条真实Criteo_x1记录，13数值/26类别，schema.json明确字段；100条validation隐藏label。训练真实CUDA DLRM：数值bottom MLP到8维，每类别独立8维embedding，26embedding+1dense取所有pairwise dot interactions接top MLP输出logit，BCEWithLogitsLoss；每训练行至少一次更新，固定seed，类别字典仅从train构建，未知类别0，保存数值归一化。入口 python solution/main.py train --input input --output output；输出checkpoint.pt含模型/优化器/step/RNG/preprocessor、validation_predictions.npy(100,)概率、run.json。支持 predict --checkpoint PATH --input JSONL --output NPY 新数据。独立检查结构interaction和26表、真实参数改变、inputcoverage、finite BCE、reload与CUDA backward，AUC独立报告不设tiny实例质量门槛。''')
    freeze('GPUv1-E02','交付可复用的推荐特征处理流水线','''input/train.jsonl/validation.jsonl是真实Criteo_x1行，字段由schema.json给定。拟合训练集preprocessor：13数值缺失填0并作训练均值/标准差标准化（std为0时1）；26类别每列按string值排序建立ID从1开始，缺失/未知0。数值统计、标准化和最终特征tensor操作必须CUDA，类别字典可CPU构造。入口 python solution/main.py fit --input input --output output；输出preprocessor.json、train_features.npy(1000,39)float32、validation_features.npy(100,39)、train_labels.npy及run.json；transform --preprocessor PATH --input JSONL --output NPY 能处理新数据。独立按明确公式重算全部值、类别映射、未知/null负例、持久化重载、CUDA归约，不得仅复制源文件。''')

def sift_index():
    tid='GPUv1-E05';p=directory(tid);src=ROOT.parent/'pilot_gpu/agent/input'
    for name in ['base.npy','queries.npy']:
        if not (p/name).exists():os.link(src/('query.npy' if name=='queries.npy' else name),p/name)
    manifest(tid,{'dataset':'native SIFT1M','source':'https://ann-benchmarks.com/sift-128-euclidean.hdf5','deviations':['native SIFT1M, not SIFT1B100M; exact GPU top10 all10000queries']})
    freeze(tid,'构建可复用的百万向量检索索引','''input/base.npy有1000000个128维真实SIFT1M向量，queries.npy有10000个独立source query。实现真实CUDA L2 top10索引，可exact或高召回ANN；所有query必须查询，输出indices.npy(10000,10)和squared_distances.npy，index/保存完整可加载数据库/索引、run.json。入口 python solution/main.py build --input input --output output；query --index output/index --queries PATH --output DIR能处理新查询且无需原输入；serve --index PATH --port PORT，/health、POST /search {vectors:[...],k:10}必须真实CUDA就绪。独立CPU oracle全query recall>=.95、距离和ID一致、32个新扰动query、两轮idle、SIGTERM、重载。可使用PyTorch GPU矩阵计算，分块保持显存预算，不得全N×N。''')

def parquet_docs():
    import pyarrow.parquet as pq
    tid='GPUv1-D05';p=directory(tid);repo='nielsr/docvqa_1200_examples';rev='dc77ab0c3d98855d0f3cb3a00832f2423fbe7528';name='data/test-00000-of-00001-41a63b2e1b4ecc5e.parquet'
    with RemoteFile(f'https://huggingface.co/datasets/{repo}/resolve/{rev}/{name}',max_transfer=512*2**20) as f:
        reader=pq.ParquetFile(f);records=reader.read_row_group(0).slice(0,8).to_pylist()
    (p/'images').mkdir(exist_ok=True);rows=[];refs=[]
    from PIL import Image
    for i,r in enumerate(records):
        im=r['image'];Image.open(io.BytesIO(im['bytes'])).convert('RGB').save(p/'images'/f'{i}.png')
        rows.append({'id':str(i),'image':f'images/{i}.png','question':r.get('question',r.get('query',{}).get('en'))});refs.append(r.get('answers'))
    save(tid,'requests.jsonl',rows);o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);(o/'references.json').write_text(json.dumps(refs))
    lock(tid,repo,'Qwen/Qwen2.5-VL-3B-Instruct',{'dataset_revision':rev,'deviations':['eight native DocVQA sample test images/questions and3B model instead of32B fullvalidation']})
    freeze(tid,'为真实扫描文档生成问答目录','''输入8张真实DocVQA文档与问题，只有image/question。CUDA /models/Qwen--Qwen2.5-VL-3B-Instruct、AutoProcessor、bf16、max_pixels=262144，模型实际接收图片和question，greedy最多64新tokens。入口 python solution/main.py run --input input --output output；输出 answers.jsonl（id/answer/token_ids）、run.json；另 infer --image PATH --question TEXT --output JSON 新文档。全覆盖，视觉encoder CUDA、生成token重算、fresh图片/问题；ANLS参考答案独立评价。不得只用问题文本推理或读取隐藏gold。''')

def cityscapes():
    import pyarrow.parquet as pq
    from PIL import Image
    tid='GPUv1-B04';p=directory(tid);repo='Chris1/cityscapes';rev='f52497cda337820b4f4a4a8019cbe4965aa0710d'
    info=requests.get('https://huggingface.co/api/datasets/'+repo,timeout=30).json();rev=info['sha'];files=[s['rfilename'] for s in info['siblings'] if s['rfilename'].endswith('.parquet') and 'train' in s['rfilename']];name=sorted(files)[0]
    with RemoteFile(f'https://huggingface.co/datasets/{repo}/resolve/{rev}/{name}',max_transfer=768*2**20,max_read=512*2**20) as f:
        records=pq.ParquetFile(f).read_row_group(0).slice(0,32).to_pylist()
    (p/'images').mkdir(exist_ok=True);(p/'labels').mkdir(exist_ok=True);rows=[];labels=[]
    for i,r in enumerate(records):
        Image.open(io.BytesIO(r['image']['bytes'])).convert('RGB').resize((512,256)).save(p/'images'/f'{i}.png')
        a=np.asarray(Image.open(io.BytesIO(r['semantic_segmentation']['bytes'])).resize((512,256),Image.Resampling.NEAREST))
        if a.ndim==3:
            assert np.array_equal(a[:,:,0],a[:,:,1]) and np.array_equal(a[:,:,1],a[:,:,2]),'source is a color-coded mask requiring its official palette'
            a=a[:,:,0]
        labels.append(a);rows.append({'id':str(i),'image':f'images/{i}.png','label':f'labels/{i}.png'})
    values=np.unique(np.stack(labels)).tolist();print('CITYSCAPES_LABELS',values,flush=True)
    mapping=[7,8,11,12,13,17,19,20,21,22,23,24,25,26,27,28,31,32,33]
    mapped=[np.asarray([[mapping.index(int(v)) if int(v) in mapping else 255 for v in row] for row in a],dtype=np.uint8) if max(values)>19 else a.astype(np.uint8) for a in labels]
    for i in range(24):Image.fromarray(mapped[i]).save(p/'labels'/f'{i}.png')
    save(tid,'train.jsonl',rows[:24]);save(tid,'validation.jsonl',[{k:v for k,v in r.items() if k!='label'} for r in rows[24:]])
    o=ROOT/'tasks'/tid/'oracle';o.mkdir(exist_ok=True);np.save(o/'validation_labels.npy',np.stack(mapped[24:]))
    lock(tid,repo,'nvidia/segformer-b0-finetuned-cityscapes-1024-1024',{'dataset_revision':rev,'source_label_values':values,'deviations':['24/8 image disjoint debug split within genuine Cityscapes source train; 512x256B0 instead ofnativefulltrainB2; formalvalidationnotclaimed']})
    freeze(tid,'适配可重载的道路场景分割模型','''input有24train/8heldout真实Cityscapes图片，512×256，train label是19类trainID/255ignore。CUDA微调 /models/nvidia--segformer-b0-finetuned-cityscapes-1024-1024 的 SegformerForSemanticSegmentation，全部train至少一次更新，交叉熵ignore255；输入AutoImageProcessor但关闭resize，输出logits插值到原图尺寸。入口 python solution/main.py train --input input --output output；保存HF checkpoint、optimizer/step/RNG的training_state.pt、predictions.npy(8,256,512)int32、run.json；predict --checkpoint PATH --input validation.jsonl --output NPY 重载预测。独立检查真实权重改变、coverage、reload、CUDA backward和隐藏mIoU。''')

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('jobs',nargs='*');args=ap.parse_args()
    jobs={f.__name__:f for f in [generators,other_media,documents,criteo,sift_index,parquet_docs,cityscapes]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(jobs[n]):n for n in (args.jobs or jobs)}
        for fut in concurrent.futures.as_completed(futures):
            try:fut.result();print('PREP_READY',futures[fut],flush=True)
            except Exception as e:print('PREP_FAILURE',futures[fut],repr(e),flush=True)
