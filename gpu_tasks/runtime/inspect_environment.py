import importlib.metadata,json,pathlib,sys,torch
records={}
for d in importlib.metadata.distributions():
 name=d.metadata.get('Name')
 if name:records.setdefault(name.lower().replace('_','-'),{'name':name,'version':d.version,'metadata_path':str(d._path)})
pathlib.Path('evaluation').mkdir(exist_ok=True);pathlib.Path('evaluation/environment.json').write_text(json.dumps({'python':sys.version,'torch':torch.__version__,'torch_cuda':torch.version.cuda,'packages':records},indent=2))
