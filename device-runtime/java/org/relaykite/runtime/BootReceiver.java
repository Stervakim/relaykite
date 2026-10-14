package org.relaykite.runtime;
import android.content.*;
import java.io.*;
import org.json.JSONObject;
public final class BootReceiver extends BroadcastReceiver {
    public void onReceive(Context context,Intent intent){
        if(!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()) && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction()))return;
        // A previous app preference must not reopen an inactive app copy after
        // switching to root, or undo an owner stop during APK replacement.
        File mode=new File(context.getFilesDir(),"mode-status.json");
        if(mode.exists()){
            try{
                if(mode.length()>8192)return;
                ByteArrayOutputStream bytes=new ByteArrayOutputStream();
                try(InputStream input=new FileInputStream(mode)){byte[] buffer=new byte[1024];int n;while((n=input.read(buffer))!=-1){if(bytes.size()+n>8192)return;bytes.write(buffer,0,n);}}
                JSONObject state=new JSONObject(bytes.toString("UTF-8"));
                if(!"app".equals(state.optString("mode","app")) || !state.optBoolean("enabled",false))return;
            }catch(Exception error){return;}
        }
        if(context.getSharedPreferences("worker",Context.MODE_PRIVATE).getBoolean("enabled",false)){
            try{context.startForegroundService(new Intent(context,WorkerService.class));}
            catch(RuntimeException error){android.util.Log.w("RelayKiteWorker","Owner must reopen worker after restricted background start");}
        }
    }
}
