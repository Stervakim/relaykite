package org.relaykite.runtime;
import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.*;
import java.io.*;
import java.util.concurrent.TimeUnit;

public final class RuntimeActivity extends Activity {
    protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);if(intent.getBooleanExtra("start_worker",false))startForegroundService(new Intent(this,WorkerService.class));}
    public void onCreate(Bundle saved){
        super.onCreate(saved);LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(24,40,24,24);
        TextView title=new TextView(this);title.setText("RelayKite 0.2.5\nПроверка встроенного runtime");layout.addView(title);
        final TextView status=new TextView(this);layout.addView(status);
        Button check=new Button(this);check.setText("Проверить без root и Termux");layout.addView(check);
        check.setOnClickListener(view -> probe(status));setContentView(layout);
        Button start=new Button(this);start.setText("Запустить без root и Termux");layout.addView(start);
        start.setOnClickListener(view -> {startForegroundService(new Intent(this,WorkerService.class));status.setText("Служба запущена. Без импортированной конфигурации она ждёт подключения.");});
        Button stop=new Button(this);stop.setText("Остановить службу");layout.addView(stop);
        stop.setOnClickListener(view -> {getSharedPreferences("worker",MODE_PRIVATE).edit().putBoolean("enabled",false).commit();stopService(new Intent(this,WorkerService.class));status.setText("Служба остановлена");});
        if(getIntent().getBooleanExtra("start_worker",false))startForegroundService(new Intent(this,WorkerService.class));
        if(getIntent().getBooleanExtra("probe",false))probe(status);
    }
    private void probe(final TextView status){
        status.setText("Проверка…");
        new Thread(() -> {
            String result;
            try{
                File runtime=RuntimeInstaller.prepare(this),base=new File(getFilesDir(),"owner");
                final Process process=RuntimeInstaller.python(this,runtime,base,"runtime_probe.py").redirectErrorStream(true).start();
                final ByteArrayOutputStream output=new ByteArrayOutputStream();
                Thread reader=new Thread(() -> {try(InputStream input=process.getInputStream()){byte[] buffer=new byte[4096];int n;while((n=input.read(buffer))!=-1){if(output.size()+n<=65536)output.write(buffer,0,n);}}catch(IOException ignored){}});reader.start();
                if(!process.waitFor(30,TimeUnit.SECONDS)){process.destroyForcibly();throw new IOException("Probe timeout");}
                reader.join(2000);result=output.toString("UTF-8");
                try(OutputStream file=new FileOutputStream(new File(getFilesDir(),"runtime-proof.txt"))){file.write(result.getBytes("UTF-8"));}
                if(process.exitValue()!=0)result="Runtime check failed\n"+result;
            }catch(Exception error){result="Runtime check rejected: "+error.getClass().getSimpleName()+": "+error.getMessage();
                try(OutputStream file=new FileOutputStream(new File(getFilesDir(),"runtime-proof.txt"))){file.write(result.getBytes("UTF-8"));}catch(IOException ignored){}
            }
            final String text=result;runOnUiThread(() -> status.setText(text));
        },"relaykite-runtime-check").start();
    }
}
