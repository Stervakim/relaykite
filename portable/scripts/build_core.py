"""Compile owned Java source to Android Dex; compile-only stub is excluded."""
import argparse,hashlib,json,subprocess,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(args):subprocess.run([str(a) for a in args],check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('--r8',required=True,type=Path);p.add_argument('--java',default='java');p.add_argument('--javac',default='javac');a=p.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        t=Path(temp);stub=t/'com/android/uiautomator/testrunner/UiAutomatorTestCase.java';stub.parent.mkdir(parents=True)
        stub.write_text('package com.android.uiautomator.testrunner; public class UiAutomatorTestCase {}')
        classes=t/'classes';classes.mkdir();sources=sorted((ROOT/'android/java').glob('*.java'))
        run([a.javac,'--release','8','-Xlint:-options','-encoding','UTF-8','-d',classes,stub,*sources])
        for name,pattern in [('display-engine.jar','DisplayEngine*.class'),('ui-v2.jar','PortableUiTest*.class')]:
            javajar=t/name
            with zipfile.ZipFile(javajar,'w') as z:
                selected=list(classes.rglob(pattern))
                if name=='ui-v2.jar':selected+=list(classes.rglob('VirtualUiTest*.class'))
                for q in selected:z.write(q,q.relative_to(classes).as_posix())
            out=ROOT/'core'/name
            run([a.java,'-cp',a.r8,'com.android.tools.r8.D8','--release','--min-api','30','--output',out,javajar])
            with zipfile.ZipFile(out) as z:
                if not z.read('classes.dex').startswith(b'dex\n'):raise RuntimeError('Invalid Dex')
    manifest={'source_origin':'Recovered owner project 2026-10-10/new-chat-9; reviewed display parameters and per-request inspector display',
              'r8_sha256':hashlib.sha256(a.r8.read_bytes()).hexdigest(),
              'sources':{q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in sources},
              'jars':{q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in (ROOT/'core').glob('*.jar')}}
    (ROOT/'core/build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest['jars']))
if __name__=='__main__':main()
