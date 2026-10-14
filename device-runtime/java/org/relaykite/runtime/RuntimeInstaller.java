package org.relaykite.runtime;
import android.content.Context;
import android.system.Os;
import android.system.OsConstants;
import android.system.ErrnoException;
import org.json.JSONObject;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

/** Install only the signed embedded assets; executable ELF stays in nativeLibDir. */
final class RuntimeInstaller {
    static String digest(InputStream input) throws Exception{
        MessageDigest hash=MessageDigest.getInstance("SHA-256");byte[] buffer=new byte[65536];int n;
        while((n=input.read(buffer))!=-1)hash.update(buffer,0,n);
        StringBuilder out=new StringBuilder();for(byte b:hash.digest())out.append(String.format(Locale.ROOT,"%02x",b&255));return out.toString();
    }
    static String digest(File file) throws Exception{try(InputStream in=new FileInputStream(file)){return digest(in);}}
    static synchronized File prepare(Context context) throws Exception{
        String hash;try(InputStream in=context.getAssets().open("runtime.zip")){hash=digest(in);}
        File root=new File(context.getFilesDir(),"runtime-"+hash.substring(0,24));
        if(!root.exists()){
            File stage=new File(context.getFilesDir(),"runtime-stage-"+UUID.randomUUID());
            if(!stage.mkdir())throw new IOException("Runtime staging unavailable");
            Os.chmod(stage.getPath(),0700);
            try(ZipInputStream zip=new ZipInputStream(context.getAssets().open("runtime.zip"))){
                ZipEntry entry;int count=0;long total=0;byte[] buffer=new byte[65536];
                while((entry=zip.getNextEntry())!=null){
                    String name=entry.getName();File dest=new File(stage,name);
                    if(++count>2000 || entry.isDirectory() || name.startsWith("/") || name.contains("\\")
                        || !dest.getCanonicalPath().startsWith(stage.getCanonicalPath()+"/"))throw new IOException("Invalid runtime asset");
                    if(!dest.getParentFile().isDirectory() && !dest.getParentFile().mkdirs())throw new IOException("Runtime directory unavailable");
                    try(OutputStream output=new FileOutputStream(dest)){int n;while((n=zip.read(buffer))!=-1){total+=n;if(total>64*1024*1024)throw new IOException("Asset capacity exceeded");output.write(buffer,0,n);}}
                    Os.chmod(dest.getPath(),0400);
                }
            }
            if(!stage.renameTo(root))throw new IOException("Runtime commit unavailable");
        }
        // Trust the manifest in the signed APK, not a mutable cached manifest.
        ByteArrayOutputStream manifestBytes=new ByteArrayOutputStream();
        try(InputStream in=context.getAssets().open("runtime-manifest.json")){
            byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1){if(manifestBytes.size()+n>1024*1024)throw new IOException("Runtime manifest exceeds limit");manifestBytes.write(buffer,0,n);}
        }
        byte[] data=manifestBytes.toByteArray();
        JSONObject manifest=new JSONObject(new String(data,"UTF-8"));
        JSONObject files=manifest.getJSONObject("files");Iterator<String> keys=files.keys();
        while(keys.hasNext()){
            String name=keys.next();File file=new File(root,name);
            if(!file.getCanonicalPath().startsWith(root.getCanonicalPath()+"/") || !file.isFile() || !digest(file).equals(files.getString(name)))throw new IOException("Runtime asset verification failed");
        }
        File nativeRoot=new File(context.getApplicationInfo().nativeLibraryDir);
        JSONObject libraries=manifest.getJSONObject("native");keys=libraries.keys();
        while(keys.hasNext()){String name=keys.next();File file=new File(nativeRoot,name);
            if(!file.getCanonicalFile().getParentFile().equals(nativeRoot.getCanonicalFile()) || !digest(file).equals(libraries.getJSONObject(name).getString("sha256")))throw new IOException("Native runtime verification failed");}
        JSONObject links=manifest.getJSONObject("links");keys=links.keys();
        while(keys.hasNext()){
            String name=keys.next();File link=new File(root,name),target=new File(nativeRoot,links.getString(name));
            if(!link.getAbsolutePath().startsWith(root.getAbsolutePath()+"/") || !target.getCanonicalFile().getParentFile().equals(nativeRoot.getCanonicalFile()))throw new IOException("Invalid runtime link");
            if(!link.getParentFile().isDirectory() && !link.getParentFile().mkdirs())throw new IOException("Native module directory unavailable");
            // APK updates change nativeLibraryDir while the asset hash can stay
            // identical. Replace only our generated symlink, never a regular file.
            boolean exists=true;
            try{if(!OsConstants.S_ISLNK(Os.lstat(link.getPath()).st_mode))throw new IOException("Native module link replaced by regular file");}
            catch(ErrnoException error){if(error.errno!=OsConstants.ENOENT)throw error;exists=false;}
            if(!exists || !link.getCanonicalFile().equals(target.getCanonicalFile())){
                File next=new File(link.getParentFile(),".link-"+UUID.randomUUID());
                Os.symlink(target.getAbsolutePath(),next.getAbsolutePath());Os.rename(next.getAbsolutePath(),link.getAbsolutePath());
            }
            if(!link.getCanonicalFile().equals(target.getCanonicalFile()))throw new IOException("Runtime link mismatch");
        }
        return root;
    }
    static ProcessBuilder python(Context context,File runtime,File base,String script) throws Exception{
        // Android exposes a system-managed /data/user/0 alias on some devices.
        // Pass its canonical app-private directory to the strict Python guards.
        base=base.getCanonicalFile();runtime=runtime.getCanonicalFile();
        File nativeRoot=new File(context.getApplicationInfo().nativeLibraryDir);
        if(!base.isDirectory() && !base.mkdirs())throw new IOException("Private worker storage unavailable");
        Os.chmod(base.getPath(),0700);File temporary=new File(base,"tmp");temporary.mkdirs();
        ProcessBuilder builder=new ProcessBuilder(new File(nativeRoot,"librelaykite_python.so").getPath(),new File(runtime,"agent/"+script).getPath());
        builder.directory(base);Map<String,String> env=builder.environment();env.remove("LD_PRELOAD");
        env.put("LD_LIBRARY_PATH",nativeRoot.getPath());env.put("PYTHONHOME",runtime.getPath());env.put("PYTHONPATH",new File(runtime,"agent").getPath());
        env.put("PYTHONNOUSERSITE","1");env.put("PYTHONDONTWRITEBYTECODE","1");env.put("PATH","/system/bin");env.put("HOME",base.getPath());env.put("TMPDIR",temporary.getPath());
        env.put("SSL_CERT_FILE",new File(runtime,"etc/tls/cert.pem").getPath());env.put("RELAYKITE_BASE",base.getPath());env.put("RELAYKITE_NATIVE",nativeRoot.getPath());env.put("RELAYKITE_MODE","app");
        return builder;
    }
}
