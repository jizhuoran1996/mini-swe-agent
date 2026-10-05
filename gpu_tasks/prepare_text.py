import concurrent.futures
import json
from pathlib import Path
import requests
from assets import ROOT,ASSETS,fetch,digest,dataset_rows,model
from prepare_graphs import manifest
from specify_ready import freeze

def save(tid,name,rows):
    p=ROOT/'tasks'/tid/'input';p.mkdir(exist_ok=True)
    (p/name).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))

def lock(tid,dataset,repo,details):
    mdir=ASSETS/'models'/repo.replace('/','--')
    ml=json.loads((mdir/'asset_lock.json').read_text())
    manifest(tid,dict(dataset=dataset,model_repo=repo,model_revision=ml['revision'],model_container_path='/models/'+mdir.name,**details))

def preferences():
    tid='GPUv1-A02';train=dataset_rows('HuggingFaceH4/ultrafeedback_binarized','default','train_prefs',32);val=dataset_rows('HuggingFaceH4/ultrafeedback_binarized','default','test_prefs',8)
    for filename,rows in [('train.jsonl',train),('validation.jsonl',val)]:save(tid,filename,[{'id':x['row']['prompt_id'],'prompt':x['row']['prompt'],'chosen':x['row']['chosen'],'rejected':x['row']['rejected']} for x in rows])
    lock(tid,'HuggingFaceH4/ultrafeedback_binarized','HuggingFaceTB/SmolLM2-135M-Instruct',{'train_rows':32,'validation_rows':8,'max_tokens':256,'deviations':['135M instead of source 7B, 32/8 authentic preference pairs; debug only']})
    freeze(tid,'训练可复用的偏好对齐对话模型','''input/train.jsonl 为 32 个真实 UltraFeedback chosen/rejected 对，validation.jsonl 为 8 个独立 test_prefs 对。基础模型 /models/HuggingFaceTB--SmolLM2-135M-Instruct 已冻结。实现真实 CUDA DPO：基础模型作为固定 reference，策略模型执行梯度更新；assistant response 才计入 log-prob，prompt padding 不计入，长度最多 256，不能截掉 response 后把空值当偏好学习。beta=0.1、固定 seed，全部训练对至少使用一次，可调学习率/epoch。
入口 python solution/main.py train --input input --output output；支持 python solution/main.py evaluate --checkpoint output/checkpoint --input input/validation.jsonl --output output/reloaded.json。交付可由标准 HF/PEFT 加载的 checkpoint/、training_state.pt（optimizer/reference binding/step）、preferences.json（每个验证 ID 的策略与 reference chosen/rejected log-prob，DPO loss 和 preference margin）、run.json。独立检查真实 policy 权重改变、reference 未变、正负样本 mask 正确、8 对完整覆盖、每个 log-prob 可从 checkpoint 重算且 finite、DPO loss 有限及 GPU backward。小实例报告 preference accuracy，不要求替代正式 7B 质量目标。''')

def translation():
    tid='GPUv1-A03';repo='Helsinki-NLP/opus-mt-en-de';model(repo)
    train=dataset_rows('wmt/wmt14','de-en','train',64);val=dataset_rows('wmt/wmt14','de-en','test',8)
    for name,rows in [('train.jsonl',train),('validation.jsonl',val)]:save(tid,name,[{'id':f'{name}:{x["row_idx"]}','en':x['row']['translation']['en'],'de':x['row']['translation']['de']} for x in rows])
    lock(tid,'wmt/wmt14/de-en',repo,{'train_rows':64,'validation_rows':8,'max_tokens':128,'deviations':['Marian pretrained model and 64/8 WMT14 sentences instead of full source Transformer training']})
    freeze(tid,'适配并交付可离线英德翻译模型','''对真实 WMT14 英德 parallel sentences 微调 Marian 模型 /models/Helsinki-NLP--opus-mt-en-de。input/train.jsonl 有 64 个 en/de 对，validation.jsonl 有 8 个官方 test 对。CUDA seq2seq teacher forcing，目标 padding label=-100，max_length=128，全部训练句至少一次优化器更新，固定 seed。翻译验证句仅以 en 为输入，禁止将验证 de 拼进生成 prompt。
入口 python solution/main.py train --input input --output output；python solution/main.py translate --checkpoint output/checkpoint --input input/validation.jsonl --output output/translations.jsonl。交付标准 HF checkpoint（tokenizer/config/weights）、training_state.pt（optimizer/step/RNG）、translations.jsonl（id/en/translation/token_ids）、run.json（before/after loss 和 source hash/真实参数/同步耗时）。独立检查参数更新、teacher forcing NLL、完整 coverage、新进程重载产生相同 token、空输出失败。质量统计独立 chrF/BLEU，但 debug 仅验真模型执行及可复用交付，不宣称达到正式翻译 benchmark 质量。''')

def language_pretraining():
    tid='GPUv1-A10';train=dataset_rows('Salesforce/wikitext','wikitext-2-raw-v1','train',200);val=dataset_rows('Salesforce/wikitext','wikitext-2-raw-v1','test',80)
    for name,rows in [('train.jsonl',train),('validation.jsonl',val)]:save(tid,name,[{'id':f'{name}:{x["row_idx"]}','text':x['row']['text']} for x in rows if len(x['row']['text'].strip())>40])
    lock(tid,'Salesforce/wikitext/wikitext-2-raw-v1','prajjwal1/bert-tiny',{'max_tokens':128,'mask_rate':.15,'deviations':['BERT-tiny and native WikiText-2 rows rather than BERT-Large on full Wikipedia; actual MLM objective preserved']})
    freeze(tid,'适配可复用的百科文本编码器','''对 WikiText-2 真实百科段落执行 CUDA masked-language-model training。输入 train.jsonl/validation.jsonl 是真实文本，模型 /models/prajjwal1--bert-tiny。使用标准 BERT MLM head；每次训练 mask_rate=0.15，排除特殊 token 和 padding，80% mask/10% random/10% unchanged，未选 token 的 label=-100。至少一次完整训练集 pass，max_tokens=128、固定 seed。
入口 python solution/main.py train --input input --output output；python solution/main.py embed --checkpoint output/checkpoint --input input/validation.jsonl --output output/embeddings.npy。交付标准 HF checkpoint/、training_state.pt（optimizer/step/RNG）、validation_mlm.json（固定 seed mask 的 loss 与 masked_tokens）、embeddings.npy（每条真实段落的 mean-pooled normalized 编码）、run.json。独立检查 MLM 梯度更新与 finite loss、padding 不参与平均、embedding coverage/shape/归一化、fresh process 重载 embedding 一致和 CUDA forward/backward。不要求小模型重现全 Wikipedia BERT-Large 的准确率。''')

def retrieval_training():
    tid='GPUv1-A09';train=dataset_rows('rajpurkar/squad','plain_text','train',100);val=dataset_rows('rajpurkar/squad','plain_text','validation',24)
    for name,rows in [('train.jsonl',train),('validation.jsonl',val)]:save(tid,name,[{'id':x['row']['id'],'question':x['row']['question'],'context':x['row']['context']} for x in rows])
    lock(tid,'rajpurkar/squad','prajjwal1/bert-tiny',{'max_tokens':128,'deviations':['SQuAD question/context supervision instead of DPR Natural Questions triplets; BERT-tiny instead of BERT-base']})
    freeze(tid,'交付可重载的问答双编码检索模型','''用真实 SQuAD train question/context 对训练 CUDA 双编码器，基础模型 /models/prajjwal1--bert-tiny，question 与 passage encoder 可共享或独立。最大 128 tokens，attention-mask mean pooling + L2 normalize，in-batch contrastive cross entropy；同一个 context 对应多道 question 时必须用 multi-positive mask 或去重批次，不能把相同 context 当负例。至少一次完整训练样本 pass，固定 seed。
入口 python solution/main.py train --input input --output output；python solution/main.py encode --checkpoint output/checkpoint --input input/validation.jsonl --output output/reloaded。输出 checkpoint/（HF encoder 或标准 state/config）、training_state.pt、question_embeddings.npy、passage_embeddings.npy（validation 顺序）、retrieval.json（cosine top-k 与对应 IDs）、run.json。独立检查更新、归一化、全部覆盖、CUDA backward、fresh-process 双编码一致。报告 validation Recall@1/5；同 passage 的多个 IDs 必须采用内容组判断。''')

def summaries():
    dataset='ccdv/govreport-summarization'
    train=dataset_rows(dataset,'document','train',32);test=dataset_rows(dataset,'document','test',16)
    def standard(rows):
        return [{'id':str(x['row_idx']),'document':x['row']['report'],'summary':x['row']['summary']} for x in rows]
    train=standard(train);test=standard(test)
    tid='GPUv1-A08';save(tid,'train.jsonl',train);save(tid,'validation.jsonl',test[:4])
    lock(tid,dataset,'Qwen/Qwen2.5-0.5B-Instruct',{'max_tokens':512,'max_report_tokens':384,'deviations':['0.5B Qwen LoRA instead of Llama2-70B; authentic GovReport 32/4 rows, explicit input truncation']})
    freeze(tid,'训练并交付长报告摘要 LoRA adapter','''用 GovReport 真实报告/摘要微调 /models/Qwen--Qwen2.5-0.5B-Instruct。train.jsonl 为 32 个 document/summary 对，validation.jsonl 为 4 个不同官方 test 报告。报告仅前 384 tokens，目标 summary 最多 128 tokens。CUDA LoRA，rank=8，目标 q_proj/v_proj，仅 assistant summary 的 token 计入 loss，prompt/padding label=-100，每个报告至少使用一次、固定 seed。冻结基础模型。
入口 python solution/main.py train --input input --output output；python solution/main.py summarize --adapter output/adapter --input input/validation.jsonl --output output/summaries.jsonl。交付标准 PEFT adapter/，training_state.pt（optimizer、step、RNG、基础 model/revision 引用）、summaries.jsonl（id/text/token_ids）、run.json。独立要求 adapter 非零且基础权重未改、完整覆盖、valid finite loss、fresh process 加载基础+adapter 生成相同 tokens；验证 summary 不可加入生成 prompt。小上下文/模型输出质量单独报告。''')
    tid='GPUv1-D02';save(tid,'requests.jsonl',[{'id':x['id'],'document':x['document']} for x in test]);(ROOT/'tasks'/tid/'oracle').mkdir(exist_ok=True);(ROOT/'tasks'/tid/'oracle/references.json').write_text(json.dumps(test))
    lock(tid,dataset,'Qwen/Qwen2.5-0.5B-Instruct',{'max_input_tokens':2048,'max_new_tokens':128,'deviations':['0.5B model and 16 genuine GovReport test reports rather than 72B/full corpus; first 2048 tokens explicitly preserved']})
    freeze(tid,'交付完整政府报告摘要目录与后续接口','''input/requests.jsonl 有 16 个真实 GovReport test 报告，仅 id/document，不提供参考摘要。使用 CUDA /models/Qwen--Qwen2.5-0.5B-Instruct，报告最多 2048 tokens，greedy decode 至多 128 新 tokens。创建每个报告的可读摘要，保留对应 ID 和 truncation。禁止直接摘取前缀代替模型生成或用任何参考摘要。
入口 python solution/main.py run --input input --output output；python solution/main.py infer --input input/requests.jsonl --output output/reloaded.jsonl。输出 summaries.jsonl（id/summary/token_ids/input_token_count/truncated）、run.json（actual model revision、parameters、GPU阶段耗时/coverage）。支持 --serve 作为可继续查询的 HTTP 服务（/health 与 POST /infer {id,document}），ready 必须在真实 CUDA model load 后；后续新报告用同一模型处理。独立检查全覆盖、正确重载、greedy token 重算、new request、idle 后继续响应、SIGTERM 清理；ROUGE/summary correctness 独立报告，不把 debug 当正式质量通过。''')

def embeddings():
    tid='GPUv1-D08';rows=[]
    for lang in ['ar','hi']:
        rows.extend({'id':lang+':'+r['row']['docid'],'lang':lang,'title':r['row']['title'],'text':r['row']['text']} for r in dataset_rows('miracl/miracl-corpus',lang,'train',100))
    save(tid,'documents.jsonl',rows)
    lock(tid,'miracl/miracl-corpus/ar+hi','sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',{'documents':200,'max_tokens':128,'deviations':['multilingual MiniLM rather than 8B encoder; 100 Arabic+100 Hindi authentic unique paragraphs, not 2.57M formal scale']})
    freeze(tid,'生产可复用的多语言文档向量与常驻编码接口','''input/documents.jsonl 是 MIRACL 的真实 Arabic/Hindi 各 100 个段落，字段 id/lang/title/text。模型 /models/sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2。使用原模型 tokenizer 与 Transformer encoder，attention-mask mean pool + L2 normalize，max_length=128；模型实际 CUDA 推理。不需要 sentence-transformers 包，可薄封装 Transformers。
入口 python solution/main.py encode --input input/documents.jsonl --output output；输出 embeddings.npy (200,384) float32、document_ids.json（原顺序）、run.json（source/model hash、参数/覆盖/同步耗时）。另实现 python solution/main.py serve --port PORT，GET /health 在真实 CUDA ready 后返回 model/device，POST /encode {texts:[...]} 返回 normalized embeddings。独立标准 tokenizer/encoder/mean-pooling 重算全部向量，cosine >= .9999、fresh process 后不依赖离线结果的新文本、两轮间 idle 继续可调用、SIGTERM 释放进程。''')

def reranking():
    tid='GPUv1-D09';rows=dataset_rows('microsoft/ms_marco','v1.1','train',8);items=[];references=[]
    for row in rows:
        r=row['row'];rid=str(r['query_id']);passages=[{'id':str(i),'text':p} for i,p in enumerate(r['passages']['passage_text'])]
        items.append({'id':rid,'query':r['query'],'passages':passages});references.append({'id':rid,'relevance':r['passages']['is_selected']})
    save(tid,'requests.jsonl',items);(ROOT/'tasks'/tid/'oracle').mkdir(exist_ok=True);(ROOT/'tasks'/tid/'oracle/references.json').write_text(json.dumps(references))
    lock(tid,'microsoft/ms_marco/v1.1','cross-encoder/ms-marco-MiniLM-L6-v2',{'queries':8,'max_tokens':256,'deviations':['MiniLM cross-encoder instead of source 8B reranker; 8 authentic candidate lists']})
    freeze(tid,'交付可继续使用的候选文档重排器','''input/requests.jsonl 有 8 个真实 MS MARCO query/candidate-list，不提供 relevance。模型 /models/cross-encoder--ms-marco-MiniLM-L6-v2；用 AutoModelForSequenceClassification 实际 CUDA cross-encode query/passage pair，max_length=256，score=raw logit，稳定按 score 降序、同分 passage id 升序。
入口 python solution/main.py run --input input --output output；输出 rankings.jsonl（query id、全部 passage id/raw_score、rank），run.json；另实现 python solution/main.py serve --port PORT，GET /health 和 POST /rerank {query,passages:[{id,text}]}。独立标准模型重算 logits <=1e-4、全候选无漏项无重复、排名正确、fresh service 新候选/idle 后复用、SIGTERM 清理；真实标签 MRR 另行报告。''')

def code_completion():
    tid='GPUv1-D03';rows=dataset_rows('openai/openai_humaneval','openai_humaneval','test',8)
    save(tid,'requests.jsonl',[{'id':x['row']['task_id'],'prompt':x['row']['prompt']} for x in rows]);(ROOT/'tasks'/tid/'oracle').mkdir(exist_ok=True);(ROOT/'tasks'/tid/'oracle/references.json').write_text(json.dumps([x['row'] for x in rows]))
    lock(tid,'openai/openai_humaneval','Qwen/Qwen2.5-Coder-0.5B-Instruct',{'problems':8,'max_new_tokens':256,'deviations':['0.5B code model, 8 native prompts instead of full 32B corpus; hidden tests retained independently']})
    freeze(tid,'交付完整代码补全目录与可调用接口','''input/requests.jsonl 为 HumanEval 的 8 个原始 Python function prefix，只给 id/prompt，不给 solution/tests。用 CUDA /models/Qwen--Qwen2.5-Coder-0.5B-Instruct，为每个问题生成可与原始 prefix 组合的 function-body completion。greedy、最多 256 新 tokens、固定 prompt 模板并记录。不得求解 agent 自己写答案代替任务模型生成；可统一去除模型输出的 Markdown 包裹，但必须保存 raw output 和对应 token IDs。
入口 python solution/main.py run --input input --output output；交付 completions.jsonl（id/prompt/raw_generation/token_ids/completion/normalization规则）、run.json；另实现 python solution/main.py serve --port PORT，GET /health 和 POST /complete {id,prompt}。独立检查所有 IDs、fresh greedy model generation、后续新请求、隔离的代码语法与隐藏 unit tests；pass@1 单独报告，debug 不要求 tiny model 全部问题通过。''')

if __name__=='__main__':
    jobs=[preferences,translation,language_pretraining,retrieval_training,summaries,embeddings,reranking,code_completion]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(job):job.__name__ for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            try:future.result();print('READY',futures[future],flush=True)
            except Exception as e:print('PREP_FAILED',futures[future],type(e).__name__,str(e)[:300],flush=True)
