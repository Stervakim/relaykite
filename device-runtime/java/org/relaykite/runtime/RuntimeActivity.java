package org.relaykite.runtime;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.system.Os;
import org.json.JSONObject;
import java.util.UUID;
import android.os.Bundle;
import android.widget.*;
import java.io.*;
import java.util.concurrent.TimeUnit;

public final class RuntimeActivity extends Activity {
    private TextView modeStatus;
    private final Handler refresh=new Handler(Looper.getMainLooper());
    private final Runnable update=new Runnable(){public void run(){showMode();refresh.postDelayed(this,1000);}};
    protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);if(intent.getBooleanExtra("start_worker",false))startForegroundService(new Intent(this,WorkerService.class));}
    public void onCreate(Bundle saved){
        super.onCreate(saved);LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(24,40,24,24);
        TextView title=new TextView(this);title.setText("RelayKite 0.2.5");title.setTextSize(24);layout.addView(title);
        modeStatus=new TextView(this);layout.addView(modeStatus);
        final TextView status=new TextView(this);layout.addView(status);
        Button check=new Button(this);check.setText("Проверить без root и Termux");layout.addView(check);
        check.setOnClickListener(view -> probe(status));ScrollView scroll=new ScrollView(this);scroll.addView(layout);setContentView(scroll);
        Button start=new Button(this);start.setText("Запустить без root и Termux");layout.addView(start);
        start.setOnClickListener(view -> selectMode("app",status));
        Button root=new Button(this);root.setText("Root без Termux");layout.addView(root);root.setOnClickListener(view -> selectMode("root",status));
        Button termux=new Button(this);termux.setText("Root с Termux");layout.addView(termux);termux.setOnClickListener(view -> selectMode("root-termux",status));
        Button connect=new Button(this);connect.setText("Импортировать конфигурацию подключения");layout.addView(connect);
        connect.setOnClickListener(view -> startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE),25));
        Button stop=new Button(this);stop.setText("Остановить службу");layout.addView(stop);
        stop.setOnClickListener(view -> {if(rootControl())requestMode("stop",null,status);else{getSharedPreferences("worker",MODE_PRIVATE).edit().putBoolean("enabled",false).commit();stopService(new Intent(this,WorkerService.class));status.setText("Служба остановлена");}});
        Button reconcile=new Button(this);reconcile.setText("Проверить прерванное переключение");layout.addView(reconcile);
        reconcile.setOnClickListener(view -> {try{String original=readJson("mode-status.json").optString("uncertain_request","");if(original.isEmpty())status.setText("Прерванных переключений нет");else requestMode("reconcile",original,status);}catch(Exception error){status.setText("Статус переключения недоступен");}});
        if(getIntent().getBooleanExtra("start_worker",false))startForegroundService(new Intent(this,WorkerService.class));
        if(getIntent().getBooleanExtra("probe",false))probe(status);
    }
    protected void onResume(){super.onResume();refresh.post(update);}
    protected void onPause(){refresh.removeCallbacks(update);super.onPause();}
    private JSONObject readJson(String name) throws Exception{
        File file=new File(getFilesDir(),name);if(file.length()>8192)throw new IOException("Status size limit");
        ByteArrayOutputStream out=new ByteArrayOutputStream();try(InputStream in=new FileInputStream(file)){byte[] b=new byte[1024];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}return new JSONObject(out.toString("UTF-8"));
    }
    private boolean rootControl(){try{JSONObject value=readJson("root-control.json");long age=System.currentTimeMillis()/1000-value.optLong("updated",0);return value.optBoolean("available",false) && age>=0 && age<=75;}catch(Exception error){return false;}}
    private void showMode(){
        if(modeStatus==null)return;
        try{JSONObject state=readJson("mode-status.json");String mode=state.optString("mode","app");String label="root".equals(mode)?"Root без Termux":"root-termux".equals(mode)?"Root с Termux":"Без root и Termux";
            modeStatus.setText(label+(state.optBoolean("enabled",true)?"":" · остановлено")+(!state.isNull("uncertain_request")?"\nПереключение прервано: требуется проверка":""));
        }catch(Exception error){modeStatus.setText("Без root и Termux");}
    }
    private void selectMode(String mode,TextView status){
        if(rootControl()){requestMode(mode,null,status);return;}
        if(!"app".equals(mode)){status.setText("Сначала установите подписанный root-компонент RelayKite");return;}
        startForegroundService(new Intent(this,WorkerService.class));status.setText("Служба запущена. Конфигурация подключения импортируется отдельно.");
    }
    private void requestMode(String mode,String original,TextView status){
        try{
            JSONObject request=new JSONObject();request.put("request_id",original==null?"mode_"+UUID.randomUUID():original);request.put("mode",mode);
            File next=new File(getFilesDir(),".mode-"+UUID.randomUUID());
            try(OutputStream out=new FileOutputStream(next)){out.write(request.toString().getBytes("UTF-8"));out.flush();}
            Os.chmod(next.getPath(),0600);Os.rename(next.getPath(),new File(getFilesDir(),"mode-request.json").getPath());status.setText("Запрос сохранён: "+request.getString("request_id"));
        }catch(Exception error){status.setText("Запрос переключения не сохранён");}
    }
    protected void onActivityResult(int request,int result,Intent intent){
        super.onActivityResult(request,result,intent);if(request!=25 || result!=RESULT_OK || intent==null || intent.getData()==null)return;
        final Uri selected=intent.getData();new Thread(() -> {
            File input=new File(getCacheDir(),".config-import-"+UUID.randomUUID());String message;
            try{
                try(InputStream in=getContentResolver().openInputStream(selected);OutputStream out=new FileOutputStream(input)){byte[] b=new byte[4096];int n,total=0;while((n=in.read(b))!=-1){total+=n;if(total>32768)throw new IOException("Configuration size limit");out.write(b,0,n);}}
                Os.chmod(input.getPath(),0600);File runtime=RuntimeInstaller.prepare(this);
                ProcessBuilder builder=RuntimeInstaller.python(this,runtime,new File(getFilesDir(),"owner"),"import_app_config.py");builder.command().add(input.getCanonicalPath());builder.redirectErrorStream(true);
                Process process=builder.start();if(!process.waitFor(15,TimeUnit.SECONDS)){process.destroyForcibly();throw new IOException("Import timeout");}
                message=process.exitValue()==0?"Конфигурация импортирована. Можно запустить службу.":"Конфигурация отклонена; существующее подключение сохранено.";
            }catch(Exception error){message="Не удалось импортировать конфигурацию";}finally{input.delete();}
            final String text=message;runOnUiThread(() -> modeStatus.setText(text));
        },"relaykite-config-import").start();
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
                result=process.exitValue()==0?"Проверка встроенного runtime прошла.":"Проверка не прошла. Диагностика сохранена в приложении.";
            }catch(Exception error){result="Runtime check rejected: "+error.getClass().getSimpleName()+": "+error.getMessage();
                try(OutputStream file=new FileOutputStream(new File(getFilesDir(),"runtime-proof.txt"))){file.write(result.getBytes("UTF-8"));}catch(IOException ignored){}
            }
            final String text=result;runOnUiThread(() -> status.setText(text));
        },"relaykite-runtime-check").start();
    }
}
