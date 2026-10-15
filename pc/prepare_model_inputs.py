"""Explicit PC-only installer for the pinned local Qwen CPU model."""
import argparse,hashlib,json,os,sys,time,urllib.request,zipfile
from pathlib import Path,PurePosixPath
from model_runtime import MODEL_SHA,LLAMA_SHA,install,checked,storage,cleanup_inputs
from mini_codex_pc import prepare,protect
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',required=True,choices=('yes','no'));a=p.parse_args(argv)
    if a.model=='no':print(json.dumps({'model_installed':False}));return
    if storage().exists():raise ValueError('Inspect the existing owned model before installing again')
    root=prepare(Path(os.environ['LOCALAPPDATA'])/'RelayKiteMemoryInputs');status=root/'install-status.json'
    def state(phase,**values):
        from model_runtime import private_json
        private_json(status,{'phase':phase,'model_location':'pc','explicit_choice':'yes','updated':time.time(),**values})
    def fetch(url,name,size,digest):
        target=root/name
        if target.is_file() and target.stat().st_size==size and hashlib.file_digest(target.open('rb'),'sha256').hexdigest()==digest:return
        part=checked(target.with_suffix('.part'));hasher=hashlib.sha256();received=0;next_update=0
        request=urllib.request.Request(url,headers={'User-Agent':'RelayKite-model-installer/0.3.0'})
        with urllib.request.urlopen(request,timeout=30) as response,part.open('wb') as out:
            if not response.url.startswith('https://'):raise ValueError('Model download redirected away from HTTPS')
            while True:
                block=response.read(1024*1024)
                if not block:break
                received+=len(block)
                if received>size:raise ValueError('Model input exceeds pinned size')
                out.write(block);hasher.update(block)
                if received>=next_update:state('downloading',file=name,received=received,total=size);next_update=received+16*1024*1024
        if received!=size or hasher.hexdigest()!=digest:raise ValueError('Model input checksum mismatch')
        os.replace(part,target);protect(target)
    try:
        state('starting')
        fetch('https://github.com/ggml-org/llama.cpp/releases/download/b11588/llama-b11588-bin-win-cpu-x64.zip','llama-b11588-bin-win-cpu-x64.zip',19509605,LLAMA_SHA)
        fetch('https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/23749fefcc72300e3a2ad315e1317431b06b590a/Qwen3-0.6B-Q8_0.gguf','Qwen3-0.6B-Q8_0.gguf',639446688,MODEL_SHA)
        binary=root/'llama';binary.mkdir(exist_ok=True)
        with zipfile.ZipFile(root/'llama-b11588-bin-win-cpu-x64.zip') as archive:
            for entry in archive.infolist():
                name=PurePosixPath(entry.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in entry.filename or (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe CPU archive member')
            archive.extractall(binary)
        state('installing');install(root);state('installed',model_root=str(storage()));cleanup_inputs()
        print(json.dumps({'installed':True,'model_location':'pc','phone_model_installed':False}))
    except Exception as error:
        state('failed',error_type=type(error).__name__);raise
if __name__=='__main__':main()
