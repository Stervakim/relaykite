import pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ProviderPolicyTests(unittest.TestCase):
 def test_only_owned_regular_nonce_files_can_be_resolved(self):
  source=ROOT/'device-runtime/java/org/relaykite/runtime/ScopedFiles.java'
  self.assertTrue(source.exists(),'Scoped content provider policy is missing')
  harness='''import java.io.*; import org.relaykite.runtime.ScopedFiles;
public class ProviderProbe { public static void main(String[] args) throws Exception {
 File root=new File(args[0]);root.mkdirs(); String token="0123456789abcdef0123456789abcdef.txt";
 File file=new File(root,token);try(FileOutputStream s=new FileOutputStream(file)){s.write(65);}
 if(!ScopedFiles.resolve(root,token).equals(file.getCanonicalFile()))throw new AssertionError("own file rejected");
 for(String bad:new String[]{"../secret","/secret","missing.txt",token+"/child",token+"?query","0123456789abcdef0123456789abcdef"}){
  boolean denied=false;try{ScopedFiles.resolve(root,bad);}catch(IOException e){denied=true;}if(!denied)throw new AssertionError("unsafe token accepted");
 }
 File directory=new File(root,"abcdefabcdefabcdefabcdefabcdefab.txt");directory.mkdir();
 try{ScopedFiles.resolve(root,directory.getName());throw new AssertionError("directory accepted");}catch(IOException expected){}
 System.out.println("owned nonce file accepted; traversal, absolute paths, missing files and directories rejected");
}}'''
  with tempfile.TemporaryDirectory() as tmp:
   tmp=pathlib.Path(tmp);probe=tmp/'ProviderProbe.java';probe.write_text(harness)
   compile=subprocess.run(['javac','--release','8','-d',str(tmp),str(source),str(probe)],capture_output=True,text=True)
   self.assertEqual(compile.returncode,0,compile.stderr)
   result=subprocess.run(['java','-cp',str(tmp),'ProviderProbe',str(tmp/'cache')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertIn('traversal',result.stdout)

if __name__=='__main__':unittest.main()
