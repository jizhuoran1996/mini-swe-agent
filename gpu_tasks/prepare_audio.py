import concurrent.futures
import io
import json
import os
import numpy as np
import pyarrow.parquet as pq
import requests
import soundfile as sf
from assets import ROOT,ASSETS,fetch,digest
from prepare_graphs import manifest
from specify_ready import freeze

def speech():
    repo='hf-internal-testing/librispeech_asr_dummy'
    info=requests.get('https://huggingface.co/api/datasets/'+repo,timeout=30).json();rev=info['sha']
    p=fetch(f'https://huggingface.co/datasets/{repo}/resolve/{rev}/clean/validation-00000-of-00001.parquet',ASSETS/'audio/librispeech_native_subset.parquet',max_bytes=64*2**20)
    rows=pq.read_table(p).to_pylist()
    for tid in ['GPUv1-A04','GPUv1-A06']:
        task=ROOT/'tasks'/tid;(task/'input/audio').mkdir(parents=True,exist_ok=True);(task/'oracle').mkdir(exist_ok=True)
        items=[]
        for row in rows[:24]:
            rid=row['id'];audio,sr=sf.read(io.BytesIO(row['audio']['bytes']),dtype='float32')
            assert audio.ndim==1 and sr==16000 and np.isfinite(audio).all()
            sf.write(task/'input/audio'/(rid+'.wav'),audio,sr,subtype='PCM_16')
            item={'id':rid,'path':'audio/'+rid+'.wav','sample_rate':sr,'samples':len(audio)}
            if tid.endswith('A04'):item['text']=row['text']
            items.append(item)
        (task/'input/train.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in items[:16]))
        (task/'input/validation.jsonl').write_text(''.join(json.dumps({k:v for k,v in x.items() if k!='text'})+'\n' for x in items[16:24]))
        (task/'oracle/references.json').write_text(json.dumps([{'id':x['id'],'text':rows[16+i]['text']} for i,x in enumerate(items[16:24])]))
        manifest(tid,{'dataset':repo,'dataset_revision':rev,'source_parquet_sha256':digest(p),'source_lineage':'24 unmodified native LibriSpeech dev-clean recordings redistributed as a small subset; not synthetic audio','audio_sha256':{x['path']:digest(task/'input'/x['path']) for x in items},'train_ids':[x['id'] for x in items[:16]],'validation_ids':[x['id'] for x in items[16:24]],'model_container_path':'/models/'+('openai--whisper-tiny' if tid.endswith('A04') else 'facebook--wav2vec2-base'),'deviations':['True 16/8 recording partition of source dev-clean; differs from formal corpus/split and model scale']})
    freeze('GPUv1-A04','适配真实语音转写模型并交付完整转录','''input/train.jsonl 有 16 个真实 LibriSpeech 16kHz WAV 与官方英文转录，validation.jsonl 有 8 个独立录音，没有提供转录标签；audio 路径相对于 input/。用 /models/openai--whisper-tiny 实际 CUDA teacher-forced seq2seq 微调，Whisper 标准 80-bin 特征，音频最长30秒（本输入都小于30秒），目标仅来自训练转录，padding=-100，每条录音至少进入一次优化器更新、固定 seed。
入口 python solution/main.py train --input input --output output；python solution/main.py transcribe --checkpoint output/checkpoint --input input/validation.jsonl --output output/transcripts.jsonl。后者 audio 相对路径默认从输入清单父目录解析。交付标准 HF model+processor checkpoint/、training_state.pt（optimizer/step/RNG）、transcripts.jsonl（id/text/token_ids/duration）、run.json（参数/loss/每录音覆盖与截断/同步耗时）。独立检查更新、CUDA encoder/decoder/backward、标准重载新录音、所有验证录音处理和 WER（debug 单独报告），禁止输出训练文本查表或把任务模型换成 solving LLM。''')
    freeze('GPUv1-A06','在无标注录音上扩展可复用语音表示','''input/train.jsonl 的16段真实16kHz语音没有文本标签；validation.jsonl 是8个不同录音。基础模型 /models/facebook--wav2vec2-base。用 Wav2Vec2ForPreTraining 在 CUDA 上执行 masked latent contrastive pretraining（含 codevector diversity loss；不能用纯 waveform MSE 或 ASR 标签代替）。每段最多取开头4秒，mask span、negative samples 按官方 Wav2Vec2 方法生成，记录配置与固定seed，所有录音至少一次有效 optimizer update。
入口 python solution/main.py train --input input --output output；python solution/main.py encode --checkpoint output/checkpoint --input input/validation.jsonl --output output/reloaded。交付标准 HF checkpoint/、training_state.pt（optimizer/step/RNG）、features.npy（8条录音 attention-mask mean pooled、768维且L2 normalized）、run.json（contrastive/diversity loss、mask/negative数、源和截断/同步计时）。独立要求梯度/权重真实改变、loss finite、mask不选padding、CUDA forward/backward、fresh checkpoint相同录音可重算特征。禁止生成随机音频或从目标文本伪造特征。''')
    print('A04/A06_READY',flush=True)

if __name__=='__main__':speech()
