package org.relaykite.fixture;
import android.app.Activity;
import android.content.Intent;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.InputStream;

/** Owned UI acceptance app: no network, root grant, user data or messages. */
public final class FixtureActivity extends Activity {
    private TextView state;
    private int clicks,longClicks,maxFingers,moves;
    private void summary(){state.setText("Clicks="+clicks+" Long="+longClicks+" Fingers="+maxFingers+" Moves="+moves);}
    public void onCreate(Bundle saved){super.onCreate(saved);show(getIntent());}
    protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);show(intent);}
    private void show(Intent intent){
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(24,40,24,24);
        state=new TextView(this);state.setTextSize(18);layout.addView(state);summary();
        if(Intent.ACTION_VIEW.equals(intent.getAction()) && intent.getData()!=null){
            TextView title=new TextView(this);title.setText("Owned scoped file opened");layout.addView(title);
            try(InputStream input=getContentResolver().openInputStream(intent.getData())){
                if(intent.getType()!=null && intent.getType().startsWith("image/")){
                    ImageView image=new ImageView(this);image.setImageBitmap(BitmapFactory.decodeStream(input));image.setContentDescription("Owned shared image");layout.addView(image,new LinearLayout.LayoutParams(400,300));
                }else{
                    byte[] data=new byte[65536];int count=input.read(data);TextView value=new TextView(this);value.setText(count>0?new String(data,0,count,"UTF-8"):"Empty file");layout.addView(value);
                }
            }catch(Exception error){TextView failure=new TextView(this);failure.setText("Scoped file read failed: "+error.getClass().getSimpleName()+": "+error.getMessage());layout.addView(failure);}
        }
        EditText edit=new EditText(this);edit.setSingleLine(true);edit.setText("initial");edit.setContentDescription("Owned editable field");layout.addView(edit);
        Button increment=new Button(this);increment.setText("Increment");increment.setOnClickListener(new View.OnClickListener(){public void onClick(View view){clicks++;summary();}});layout.addView(increment);
        Button hold=new Button(this);hold.setText("Hold");hold.setOnLongClickListener(new View.OnLongClickListener(){public boolean onLongClick(View view){longClicks++;summary();return true;}});layout.addView(hold);
        View pad=new View(this);pad.setContentDescription("Owned gesture pad");pad.setBackgroundColor(0xff236f6b);
        pad.setOnTouchListener(new View.OnTouchListener(){public boolean onTouch(View view,MotionEvent event){maxFingers=Math.max(maxFingers,event.getPointerCount());if(event.getActionMasked()==MotionEvent.ACTION_MOVE)moves++;summary();return true;}});
        layout.addView(pad,new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,180));
        ScrollView scroll=new ScrollView(this);scroll.setContentDescription("Owned scrolling area");LinearLayout items=new LinearLayout(this);items.setOrientation(LinearLayout.VERTICAL);
        for(int i=0;i<30;i++){TextView row=new TextView(this);row.setText("Owned row "+i);row.setPadding(10,18,10,18);items.addView(row);}scroll.addView(items);layout.addView(scroll,new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,220));
        setContentView(layout);
    }
}
