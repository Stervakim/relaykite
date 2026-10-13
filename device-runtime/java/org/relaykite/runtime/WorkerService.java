package org.relaykite.runtime;
import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import java.io.*;
import java.util.concurrent.TimeUnit;

/** Visible, owner-stoppable foreground worker, with bounded restart/output. */
public final class WorkerService extends Service {
    private volatile boolean stopping;
    private volatile Process child;
    private Thread worker;
    private final Object processLock=new Object();
    public IBinder onBind(Intent intent){return null;}
    public void onCreate(){
        super.onCreate();NotificationManager manager=getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("relaykite-worker","RelayKite",NotificationManager.IMPORTANCE_LOW));
        Intent stop=new Intent(this,WorkerService.class).setAction("stop");
        PendingIntent stopping=PendingIntent.getService(this,2,stop,PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent open=PendingIntent.getActivity(this,1,new Intent(this,RuntimeActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification=new Notification.Builder(this,"relaykite-worker").setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle("RelayKite 0.2.5").setContentText("Режим без root и Termux").setContentIntent(open).setOngoing(true)
            .addAction(new Notification.Action.Builder(null,"Остановить",stopping).build()).build();
        if(Build.VERSION.SDK_INT>=34)startForeground(25,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);else startForeground(25,notification);
    }
    public synchronized int onStartCommand(Intent intent,int flags,int id){
        if(intent!=null && "stop".equals(intent.getAction())){
            getSharedPreferences("worker",MODE_PRIVATE).edit().putBoolean("enabled",false).commit();stopSelf();return START_NOT_STICKY;
        }
        if(worker==null){
            getSharedPreferences("worker",MODE_PRIVATE).edit().putBoolean("enabled",true).commit();
            worker=new Thread(this::supervise,"relaykite-app-worker");worker.start();
        }
        return START_STICKY;
    }
    private void status(String text){
        try(OutputStream out=new FileOutputStream(new File(getFilesDir(),"worker-status.txt"))){out.write(text.getBytes("UTF-8"));}catch(IOException ignored){}
    }
    private void supervise(){
        int delay=2;
        while(!stopping){
            try{
                File runtime=RuntimeInstaller.prepare(this),base=new File(getFilesDir(),"owner");
                Process started;
                synchronized(processLock){if(stopping)break;started=RuntimeInstaller.python(this,runtime,base,"app_worker.py").redirectErrorStream(true).start();child=started;}
                status("app running");
                try(InputStream input=started.getInputStream()){
                    byte[] buffer=new byte[4096];int n;
                    while((n=input.read(buffer))!=-1){
                        File log=new File(getFilesDir(),"worker.log");
                        if(log.length()>1024*1024){File old=new File(getFilesDir(),"worker.previous.log");old.delete();log.renameTo(old);}
                        try(OutputStream out=new FileOutputStream(log,true)){out.write(buffer,0,n);}
                    }
                }
                started.waitFor();status("app stopped exit="+started.exitValue());child=null;
            }catch(Exception error){status("app rejected "+error.getClass().getSimpleName());child=null;}
            for(int i=0;i<delay*10 && !stopping;i++)try{Thread.sleep(100);}catch(InterruptedException ignored){}
            delay=Math.min(30,delay*2);
        }
        status("stopped");
    }
    public void onDestroy(){
        Process owned;synchronized(processLock){stopping=true;owned=child;if(owned!=null)owned.destroy();}
        if(owned!=null){new Thread(() -> {try{if(!owned.waitFor(30,TimeUnit.SECONDS))owned.destroyForcibly();}catch(InterruptedException ignored){Thread.currentThread().interrupt();}},"relaykite-stop").start();}
        super.onDestroy();
    }
}
