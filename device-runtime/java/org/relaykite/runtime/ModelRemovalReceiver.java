package org.relaykite.runtime;
import android.content.*;
import android.system.Os;
import org.json.JSONObject;
import java.io.*;
import java.util.UUID;
/** System-protected package event; preserve the request until paired PC confirms cleanup. */
public final class ModelRemovalReceiver extends BroadcastReceiver {
    public void onReceive(Context context,Intent intent){
        if(!Intent.ACTION_PACKAGE_REMOVED.equals(intent.getAction()) || intent.getBooleanExtra(Intent.EXTRA_REPLACING,false)
           || intent.getData()==null || !"com.openai.chatgpt".equals(intent.getData().getSchemeSpecificPart()))return;
        try{
            JSONObject request=new JSONObject();request.put("request_id","model-remove-"+UUID.randomUUID());request.put("package","com.openai.chatgpt");
            File pending=new File(context.getFilesDir(),"model-cleanup.json");
            if(pending.exists())return;
            File stage=new File(context.getFilesDir(),".model-cleanup-"+UUID.randomUUID());
            try(OutputStream out=new FileOutputStream(stage)){out.write(request.toString().getBytes("UTF-8"));}
            Os.chmod(stage.getPath(),0600);Os.rename(stage.getPath(),pending.getPath());
        }catch(Exception ignored){}
    }
}
