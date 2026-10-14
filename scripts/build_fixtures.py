"""Build only owned, unprivileged UI acceptance fixtures with the runtime key."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(args):subprocess.run([str(a) for a in args],check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('--android-jar',required=True,type=Path);p.add_argument('--build-tools',required=True,type=Path);p.add_argument('--r8',required=True,type=Path);p.add_argument('--keystore',required=True,type=Path);p.add_argument('--password-file',required=True,type=Path);a=p.parse_args()
    if a.keystore.resolve().is_relative_to(ROOT) or a.password_file.resolve().is_relative_to(ROOT):raise ValueError('Signing inputs must be outside source')
    output=ROOT/'device-runtime/fixtures/artifacts';output.mkdir(exist_ok=True);proof=[]
    with tempfile.TemporaryDirectory() as tmp:
        t=Path(tmp);platform=t/'android.jar';shutil.copyfile(a.android_jar,platform);classes=t/'classes';classes.mkdir();dex=t/'dex';dex.mkdir()
        run(['javac','--release','8','-Xlint:-options','-encoding','UTF-8','-cp',platform,'-d',classes,ROOT/'device-runtime/fixtures/FixtureActivity.java'])
        jar=t/'fixture.jar'
        with zipfile.ZipFile(jar,'w') as z:
            for f in sorted(classes.rglob('*.class')):z.write(f,f.relative_to(classes).as_posix())
        run(['java','-cp',a.r8,'com.android.tools.r8.D8','--release','--min-api','30','--lib',platform,'--output',dex,jar])
        for label in ('a','b','c'):
            package='org.relaykite.fixture.'+label
            xml=t/'AndroidManifest.xml';xml.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="'+package+'" android:versionCode="1" android:versionName="acceptance-1"><uses-sdk android:minSdkVersion="30" android:targetSdkVersion="35"/><application android:label="RelayKite Test '+label.upper()+'" android:allowBackup="false"><activity android:name="org.relaykite.fixture.FixtureActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter><intent-filter><action android:name="android.intent.action.VIEW"/><category android:name="android.intent.category.DEFAULT"/><data android:mimeType="*/*"/></intent-filter></activity></application></manifest>')
            unsigned=t/'unsigned.apk';run([a.build_tools/('aapt2.exe' if os.name=='nt' else 'aapt2'),'link','-I',platform,'--manifest',xml,'-o',unsigned])
            with zipfile.ZipFile(unsigned,'a') as z:z.write(dex/'classes.dex','classes.dex')
            aligned=t/'aligned.apk';run([a.build_tools/('zipalign.exe' if os.name=='nt' else 'zipalign'),'-f','-p','4',unsigned,aligned])
            apk=output/('relaykite-fixture-'+label+'.apk');signer=a.build_tools/'lib/apksigner.jar'
            run(['java','-jar',signer,'sign','--ks',a.keystore,'--ks-key-alias','relaykite','--ks-pass','file:'+str(a.password_file),'--out',apk,aligned])
            run(['java','-jar',signer,'verify',apk]);proof.append({'package':package,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest()})
    (output/'manifest.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
if __name__=='__main__':main()
