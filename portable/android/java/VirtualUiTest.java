package com.oai.androiduse;
import java.lang.reflect.*;
import java.util.*;
public class VirtualUiTest extends com.android.uiautomator.testrunner.UiAutomatorTestCase {
    static Object call(Object obj,String method,Class<?>[] types,Object... args) throws Exception {
        Method m=obj.getClass().getMethod(method,types);
        m.setAccessible(true);return m.invoke(obj,args);
    }
    static String quote(Object v) {
        String s=String.valueOf(v==null?"":v);
        StringBuilder b=new StringBuilder("\"");
        for(int i=0;i<s.length();i++){
            char c=s.charAt(i);
            if(c=='"'||c=='\\')b.append('\\').append(c);
            else if(c=='\n')b.append("\\n");
            else if(c=='\r')b.append("\\r");
            else if(c=='\t')b.append("\\t");
            else if(c<32||c>126)b.append(String.format(java.util.Locale.ROOT,"\\u%04x",(int)c));
            else b.append(c);
        }
        return b.append('"').toString();
    }
    static Object getUiAutomation(Object self) throws Exception {
        Object device=Class.forName("com.android.uiautomator.testrunner.UiAutomatorTestCase")
                 .getMethod("getUiDevice").invoke(self);
        Field bridgeField=device.getClass().getDeclaredField("mUiAutomationBridge");
        bridgeField.setAccessible(true);
        Object bridge=bridgeField.get(device);
        Class<?> bridgeType=Class.forName("com.android.uiautomator.core.UiAutomatorBridge");
        Field f=bridgeType.getDeclaredField("mUiAutomation");f.setAccessible(true);
        return f.get(bridge);
    }
    Object getParam(String key) throws Exception{
        Object bundle=Class.forName("com.android.uiautomator.testrunner.UiAutomatorTestCase")
               .getMethod("getParams").invoke(this);
        return call(bundle,"getString",new Class<?>[]{String.class},key);
    }
    static class T {
        Object node;int depth;
        T(Object n,int d){node=n;depth=d;}
    }
    List<Object> roots(Object automation,int displayId) throws Exception {
        if(displayId<=0)throw new IllegalArgumentException("Physical display prohibited");
        // Set service flags only while this standalone test process is running.
        Object info=call(automation,"getServiceInfo",new Class<?>[0]);
        Class<?> infoCls=Class.forName("android.accessibilityservice.AccessibilityServiceInfo");
        Field ff=infoCls.getField("flags");
        ff.setInt(info,ff.getInt(info) | 0x40 | 0x10);
        call(automation,"setServiceInfo",new Class<?>[]{infoCls},info);
        long deadline=System.nanoTime()+850000000L;
        while(true){
            Object all=call(automation,"getWindowsOnAllDisplays",new Class<?>[0]);
            Object target=call(all,"get",new Class<?>[]{int.class},displayId);
            List<Object> roots=new ArrayList<>();
            if(target instanceof List){
                for(Object window: (List<?>)target){
                    int id=(Integer)call(window,"getDisplayId",new Class<?>[0]);
                    if(id!=displayId)continue;
                    Object root=call(window,"getRoot",new Class<?>[0]);
                    if(root!=null) roots.add(root);
                    if(roots.size()>=8)break;
                }
            }
            long remaining=(deadline-System.nanoTime())/1000000L;
            if(!roots.isEmpty() || remaining<=0)return roots;
            Thread.sleep(Math.min(40L,remaining));
        }
    }
    void runAction(boolean edit) throws Exception {
        String value=String.valueOf(getParam("display"));
        if(!value.matches("[1-9][0-9]{0,3}"))throw new Exception("Only a nonzero display may be inspected");
        int displayId=Integer.parseInt(value);
        Object automation=getUiAutomation(this);
        List<Object> roots=roots(automation,displayId);
        ArrayDeque<T> queue=new ArrayDeque<>();
        for(Object root:roots)queue.add(new T(root,0));
        ArrayList<Object> fields=new ArrayList<>();
        ArrayList<String> nodes=new ArrayList<>();
        int visited=0;
        while(!queue.isEmpty()&&visited++<260){
            T current=queue.removeFirst();
            Object node=current.node;
            if(node==null||current.depth>20)continue;
            try {
                boolean pwd=(Boolean)call(node,"isPassword",new Class<?>[0]);
                boolean editable=(Boolean)call(node,"isEditable",new Class<?>[0]);
                boolean clickable=(Boolean)call(node,"isClickable",new Class<?>[0]);
                String text=pwd?"":String.valueOf(call(node,"getText",new Class<?>[0]));
                String desc=pwd?"":String.valueOf(call(node,"getContentDescription",new Class<?>[0]));
                String cls=String.valueOf(call(node,"getClassName",new Class<?>[0]));
                if(editable&& !pwd)fields.add(node);
                if(!"null".equals(text)||!"null".equals(desc)||clickable||editable){
                    Class<?> rc=Class.forName("android.graphics.Rect");
                    Object bounds=rc.getDeclaredConstructor().newInstance();
                    call(node,"getBoundsInScreen",new Class<?>[]{rc},bounds);
                    nodes.add("{\"text\":"+quote(text)+",\"desc\":"+quote(desc)+
                       ",\"class\":"+quote(cls)+",\"editable\":"+editable+",\"clickable\":"+clickable+
                       ",\"password\":"+pwd+",\"bounds\":["+rc.getField("left").getInt(bounds)+","+
                       rc.getField("top").getInt(bounds)+","+rc.getField("right").getInt(bounds)+","+
                       rc.getField("bottom").getInt(bounds)+"]}");
                }
                int count=(Integer)call(node,"getChildCount",new Class<?>[0]);
                for(int j=0;j<Math.min(count,45);j++){
                    Object child=call(node,"getChild",new Class<?>[]{int.class},j);
                    if(child!=null)queue.add(new T(child,current.depth+1));
                }
            }catch(Exception ignored){}
        }
        if(edit){
            ArrayList<Object> active=new ArrayList<>();
            for(Object field:fields) if(Boolean.TRUE.equals(call(field,"isFocused",new Class<?>[0])))active.add(field);
            if(active.size()!=1)throw new Exception("Expected one focused non-password editable field, found "+active.size());
            Object packed=getParam("text64");
            if(packed==null)throw new Exception("Missing encoded input text");
            byte[] utf8=java.util.Base64.getDecoder().decode(String.valueOf(packed));
            if(utf8.length>4000)throw new Exception("Text exceeds byte limit");
            String text=new String(utf8,java.nio.charset.StandardCharsets.UTF_8);
            if(text.length()>1000||text.contains("\u0000"))throw new Exception("Invalid text");
            Class<?> bundleType=Class.forName("android.os.Bundle");
            Object bundle=bundleType.getDeclaredConstructor().newInstance();
            call(bundle,"putCharSequence",new Class<?>[]{String.class,CharSequence.class},
                "ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE",text);
            boolean success=(Boolean)call(active.get(0),"performAction",
                 new Class<?>[]{int.class,bundleType},2097152,bundle);
            System.out.println("ANDROID_USE_SET_TEXT\t{\"display\":"+displayId+
                ",\"ok\":"+success+",\"length\":"+text.length()+"}");
            if(!success)throw new Exception("ACTION_SET_TEXT returned false");
        }else{
            System.out.println("ANDROID_USE_INSPECT\t{\"display\":"+displayId+
               ",\"windows\":"+roots.size()+",\"nodes\":["+String.join(",",nodes)+"]}");
        }
    }
    public void testInspect() throws Exception{runAction(false);}
    public void testSetText() throws Exception{runAction(true);}
}
