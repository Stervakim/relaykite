package org.relaykite.runtime;
import android.app.Activity;
import android.app.ActivityOptions;
import android.content.ComponentName;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import java.io.File;

/** Own the grant instead of asking a root shell to grant another UID's URI. */
public final class FileLaunchActivity extends Activity {
    public void onCreate(Bundle saved){
        super.onCreate(saved);
        try{
            Intent supplied=getIntent();
            Uri uri=supplied.getData();
            if(uri==null || !"content".equals(uri.getScheme()) || !"org.relaykite.runtime.files".equals(uri.getAuthority())
                || uri.getPathSegments().size()!=1 || uri.getQuery()!=null || uri.getFragment()!=null)throw new IllegalArgumentException();
            ScopedFiles.resolve(new File(getCacheDir(),"shared"),uri.getLastPathSegment());
            ComponentName target=ComponentName.unflattenFromString(supplied.getStringExtra("target"));
            if(target==null || target.getPackageName().equals(getPackageName()))throw new IllegalArgumentException();
            int display=getDisplay().getDisplayId();
            if(display<=0)throw new IllegalArgumentException("Owned virtual display required");
            Intent view=new Intent(Intent.ACTION_VIEW).setComponent(target).setDataAndType(uri,supplied.getType());
            view.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_MULTIPLE_TASK);
            ActivityOptions options=ActivityOptions.makeBasic();options.setLaunchDisplayId(display);
            startActivity(view,options.toBundle());
        }catch(Exception error){android.util.Log.w("RelayKiteFile","Scoped file launch rejected: "+error.getClass().getSimpleName());}
        finally{finish();}
    }
}
