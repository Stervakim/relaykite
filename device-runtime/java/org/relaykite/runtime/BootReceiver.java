package org.relaykite.runtime;
import android.content.*;
public final class BootReceiver extends BroadcastReceiver {
    public void onReceive(Context context,Intent intent){
        if(!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()) && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction()))return;
        if(context.getSharedPreferences("worker",Context.MODE_PRIVATE).getBoolean("enabled",false)){
            try{context.startForegroundService(new Intent(context,WorkerService.class));}
            catch(RuntimeException error){android.util.Log.w("RelayKiteWorker","Owner must reopen worker after restricted background start");}
        }
    }
}
