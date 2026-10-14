"""Build/sign the owned scoped provider with pinned SDK/R8 inputs.

Private keystore and password file stay outside source/releases. The builder
does not download dependencies or change global Java/Git identity.
"""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(argv,env=None):subprocess.run([str(a) for a in argv],check=True,env=env)
def main():
    p=argparse.ArgumentParser();p.add_argument('--android-jar',required=True,type=Path);p.add_argument('--build-tools',required=True,type=Path);p.add_argument('--r8',required=True,type=Path)
    p.add_argument('--keystore',required=True,type=Path);p.add_argument('--password-file',required=True,type=Path);p.add_argument('--runtime-bundle',type=Path);p.add_argument('--java',default='java');p.add_argument('--javac',default='javac');a=p.parse_args()
    for path in (a.keystore,a.password_file):
        if path.resolve().is_relative_to(ROOT):raise ValueError('Private signing inputs must remain outside the repository')
    source=ROOT/'device-runtime';out=ROOT/'dist/runtime';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        t=Path(tmp);classes=t/'classes';classes.mkdir();dex=t/'dex';dex.mkdir()
        # Native Windows SDK tools cannot reliably open non-ASCII workspace
        # paths. Use only transient ASCII paths for their input files.
        platform=t/'android.jar';shutil.copyfile(a.android_jar,platform)
        xml=t/'AndroidManifest.xml';shutil.copyfile(source/'AndroidManifest.xml',xml)
        files=sorted((source/'java').rglob('*.java'))
        run([a.javac,'--release','8','-encoding','UTF-8','-cp',a.android_jar,'-d',classes,*files])
        jar=t/'provider.jar'
        with zipfile.ZipFile(jar,'w') as z:
            for f in sorted(classes.rglob('*.class')):z.write(f,f.relative_to(classes).as_posix())
        run([a.java,'-cp',a.r8,'com.android.tools.r8.D8','--release','--min-api','30','--lib',a.android_jar,'--output',dex,jar])
        aapt=a.build_tools/('aapt2.exe' if os.name=='nt' else 'aapt2');unsigned=t/'unsigned.apk'
        run([aapt,'link','-I',platform,'--manifest',xml,'-o',unsigned])
        with zipfile.ZipFile(unsigned,'a') as z:
            z.write(dex/'classes.dex','classes.dex')
            if a.runtime_bundle:
                z.write(a.runtime_bundle/'runtime.zip','assets/runtime.zip')
                z.write(a.runtime_bundle/'runtime-manifest.json','assets/runtime-manifest.json')
                with zipfile.ZipFile(a.runtime_bundle/'native.zip') as native:
                    for name in native.namelist():
                        if not name.startswith('lib/arm64-v8a/lib') or not name.endswith('.so'):raise ValueError('Invalid native package path')
                        z.writestr(name,native.read(name),compress_type=zipfile.ZIP_DEFLATED)
        aligned=t/'aligned.apk';zipalign=a.build_tools/('zipalign.exe' if os.name=='nt' else 'zipalign')
        run([zipalign,'-f','-p','4',unsigned,aligned])
        signed=out/'relaykite-runtime-0.2.5.apk';signer=a.build_tools/'lib/apksigner.jar'
        run([a.java,'-jar',signer,'sign','--ks',a.keystore,'--ks-key-alias','relaykite','--ks-pass','file:'+str(a.password_file),'--out',signed,aligned])
        run([a.java,'-jar',signer,'verify','--verbose','--print-certs',signed])
        manifest={'version':'0.2.5','package':'org.relaykite.runtime','apk_sha256':hashlib.sha256(signed.read_bytes()).hexdigest(),
            'dex_sha256':hashlib.sha256((dex/'classes.dex').read_bytes()).hexdigest(),'r8_sha256':hashlib.sha256(a.r8.read_bytes()).hexdigest(),
            'android_jar_sha256':hashlib.sha256(a.android_jar.read_bytes()).hexdigest(),'source_sha256':{f.relative_to(source).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files+[source/'AndroidManifest.xml']}}
        (source/'artifacts/provider-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(json.dumps({'apk':str(signed),'sha256':manifest['apk_sha256']}))
if __name__=='__main__':main()
