package com.oai.androiduse;
import java.util.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Display-scoped UiAutomation adapter. Never obtains a physical-window root. */
public final class PortableUiTest extends VirtualUiTest {
    static Map<String,Object> map(){return new LinkedHashMap<>();}
    static Object optional(Object o,String name,Object fallback){try{return call(o,name,new Class<?>[0]);}catch(Exception e){return fallback;}}
    static String text(Object o){return o==null?"":String.valueOf(o);}
    static boolean protectedNode(Object node){
        if(Boolean.TRUE.equals(optional(node,"isPassword",true)))return true;
        try{return Boolean.TRUE.equals(call(node,"isAccessibilityDataSensitive",new Class<?>[0]));}
        catch(NoSuchMethodException oldApi){return false;}
        catch(Exception unknown){return true;}
    }
    static String json(Object o){
        if(o==null)return "null";
        if(o instanceof String)return quote(o);
        if(o instanceof Number || o instanceof Boolean)return String.valueOf(o);
        if(o instanceof Map){List<String> parts=new ArrayList<>();for(Object key:((Map<?,?>)o).keySet())parts.add(quote(key)+":"+json(((Map<?,?>)o).get(key)));return "{"+String.join(",",parts)+"}";}
        if(o instanceof Iterable){List<String> parts=new ArrayList<>();for(Object v:(Iterable<?>)o)parts.add(json(v));return "["+String.join(",",parts)+"]";}
        throw new IllegalArgumentException("Unsupported JSON type");
    }
    static Object unpack(Object o)throws Exception{
        if(o==null||o instanceof String||o instanceof Number||o instanceof Boolean)return o;
        if(o.getClass().getName().equals("org.json.JSONObject")){
            Map<String,Object> m=map();Iterator<?> it=(Iterator<?>)call(o,"keys",new Class<?>[0]);
            while(it.hasNext()){String key=String.valueOf(it.next());m.put(key,unpack(call(o,"get",new Class<?>[]{String.class},key)));}return m;
        }
        if(o.getClass().getName().equals("org.json.JSONArray")){
            List<Object> a=new ArrayList<>();int n=(Integer)call(o,"length",new Class<?>[0]);
            for(int i=0;i<n;i++)a.add(unpack(call(o,"get",new Class<?>[]{int.class},i)));return a;
        }
        return null;
    }
    static int integer(Map<String,Object> m,String key,int fallback){Object v=m.get(key);return v instanceof Number?((Number)v).intValue():fallback;}
    static String hash(Object o)throws Exception{
        byte[] bytes=MessageDigest.getInstance("SHA-256").digest(json(o).getBytes(StandardCharsets.UTF_8));
        StringBuilder b=new StringBuilder();for(byte x:bytes)b.append(String.format("%02x",x&255));return b.toString();
    }
    final Map<String,Object> handles=new LinkedHashMap<>();
    static class Visit {Object node;String id,parent,window;int depth;Visit(Object n,String i,String p,String w,int d){node=n;id=i;parent=p;window=w;depth=d;}}
    Map<String,Object> snapshot(Object automation,int display)throws Exception{
        if(display<=0)throw new IllegalArgumentException("Physical display prohibited");
        handles.clear();roots(automation,display); // Bounded readiness and interactive-window flags from 003.
        Object all=call(automation,"getWindowsOnAllDisplays",new Class<?>[0]);
        Object found=call(all,"get",new Class<?>[]{int.class},display);
        List<Object> windows=new ArrayList<>(),nodes=new ArrayList<>();ArrayDeque<Visit> q=new ArrayDeque<>();
        if(found instanceof List)for(Object window:(List<?>)found){
            if(!Integer.valueOf(display).equals(call(window,"getDisplayId",new Class<?>[0])))continue;
            String id=String.valueOf(call(window,"getId",new Class<?>[0]));Map<String,Object> w=map();
            w.put("window_id",id);w.put("title",text(optional(window,"getTitle","")));w.put("focused",optional(window,"isFocused",false));w.put("active",optional(window,"isActive",false));w.put("layer",optional(window,"getLayer",0));windows.add(w);
            Object root=call(window,"getRoot",new Class<?>[0]);if(root!=null)q.add(new Visit(root,id+"/0",null,id,0));
        }
        int visited=0;boolean truncated=false;
        while(!q.isEmpty()){
            if(visited++>=2000){truncated=true;break;}
            Visit v=q.removeFirst();Object n=v.node;if(n==null)continue;
            Map<String,Object> item=map();boolean password=protectedNode(n);
            item.put("node_id",v.id);item.put("parent_id",v.parent);item.put("window_id",v.window);
            item.put("resource_id",text(optional(n,"getViewIdResourceName","")));item.put("role",text(optional(n,"getClassName","")));
            item.put("text",password?"":text(optional(n,"getText","")));item.put("description",password?"":text(optional(n,"getContentDescription","")));
            String[][] states={{"enabled","isEnabled"},{"visible","isVisibleToUser"},{"focused","isFocused"},{"editable","isEditable"},{"checked","isChecked"},{"selected","isSelected"},{"scrollable","isScrollable"}};
            for(String[] state:states)item.put(state[0],optional(n,state[1],false));item.put("password",password);
            Class<?> rect=Class.forName("android.graphics.Rect");Object bounds=rect.getDeclaredConstructor().newInstance();
            call(n,"getBoundsInScreen",new Class<?>[]{rect},bounds);List<Integer> b=new ArrayList<>();for(String key:new String[]{"left","top","right","bottom"})b.add(rect.getField(key).getInt(bounds));item.put("bounds",b);
            List<String> actions=new ArrayList<>();int bits=(Integer)optional(n,"getActions",0);
            int[] values={16,32,1,2097152,131072,4};String[] labels={"click","long_click","focus","set_text","selection","select"};
            for(int i=0;i<values.length;i++)if((bits&values[i])!=0)actions.add(labels[i]);if((bits&(4096|8192))!=0)actions.add("scroll");item.put("actions",actions);
            if(password){item.put("text","");item.put("description","");}
            nodes.add(item);handles.put(v.id,n);
            if(v.depth>=128){truncated=true;continue;}
            int count=(Integer)call(n,"getChildCount",new Class<?>[0]);
            for(int i=0;i<count;i++){Object child=call(n,"getChild",new Class<?>[]{int.class},i);if(child!=null)q.add(new Visit(child,v.id+"/"+i,v.id,v.window,v.depth+1));}
        }
        Map<String,Object> data=map(),geometry=map();geometry.put("width",720);geometry.put("height",1280);
        data.put("target",String.valueOf(display));data.put("geometry",geometry);data.put("windows",windows);data.put("nodes",nodes);data.put("truncated",truncated);
        data.put("native_fingerprint",hash(data));return data;
    }
    Object bundle()throws Exception{return Class.forName("android.os.Bundle").getDeclaredConstructor().newInstance();}
    void putInt(Object bundle,String key,int value)throws Exception{call(bundle,"putInt",new Class<?>[]{String.class,int.class},key,value);}
    void validateSemantic(Object node,Map<String,Object> a){
        String kind=text(a.get("kind"));
        if(!Arrays.asList("click","long_click","focus","select","set_text","selection","scroll").contains(kind))throw new IllegalArgumentException("Unsupported semantic action");
        if(kind.equals("set_text")){
            Object value=a.get("text");
            if(!(value instanceof String)||((String)value).indexOf(0)>=0||((String)value).codePointCount(0,((String)value).length())>65536)throw new IllegalArgumentException("Invalid input text");
        }
        if(kind.equals("selection")){
            int start=integer(a,"start",-1),end=integer(a,"end",-1);
            if(start<0||end<start||end>text(optional(node,"getText","")).length())throw new IllegalArgumentException("Invalid selection range");
        }
    }
    boolean semantic(Object node,Map<String,Object> a)throws Exception{
        validateSemantic(node,a);
        String kind=text(a.get("kind"));int action=0;Object b=bundle();
        switch(kind){
            case "click":action=16;break;case "long_click":action=32;break;case "focus":action=1;break;case "select":action=4;break;
            case "set_text":action=2097152;call(b,"putCharSequence",new Class<?>[]{String.class,CharSequence.class},"ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE",text(a.get("text")));break;
            case "selection":action=131072;putInt(b,"ACTION_ARGUMENT_SELECTION_START_INT",integer(a,"start",0));putInt(b,"ACTION_ARGUMENT_SELECTION_END_INT",integer(a,"end",0));break;
            case "scroll":action=text(a.get("direction")).equals("backward")?8192:4096;break;
            default:throw new IllegalArgumentException("Unsupported semantic action");
        }
        return (Boolean)call(node,"performAction",new Class<?>[]{int.class,Class.forName("android.os.Bundle")},action,b);
    }
    void inject(Object automation,Object event,int display)throws Exception{
        try{
            if(display<=0)throw new IllegalArgumentException("Physical display prohibited");
            call(event,"setDisplayId",new Class<?>[]{int.class},display);
            boolean ok=(Boolean)call(automation,"injectInputEvent",new Class<?>[]{Class.forName("android.view.InputEvent"),boolean.class},event,true);
            if(!ok)throw new IllegalStateException("Input injection outcome unknown");
        }finally{try{call(event,"recycle",new Class<?>[0]);}catch(Exception ignored){}}
    }
    int validateGesture(int display,List<?> paths,int duration){
        if(display<=0)throw new IllegalArgumentException("Physical display prohibited");
        if(paths==null||paths.size()<1||paths.size()>5||duration<=0||duration>5000)throw new IllegalArgumentException("Invalid gesture");
        int steps=-1;
        for(Object path:paths){
            if(!(path instanceof List))throw new IllegalArgumentException("Invalid gesture path");
            List<?> points=(List<?>)path;
            if(points.size()<2||points.size()>120||(steps!=-1&&steps!=points.size()))throw new IllegalArgumentException("All fingers need equal point counts, 2..120");
            steps=points.size();
            for(Object point:points){
                if(!(point instanceof List)||((List<?>)point).size()!=2)throw new IllegalArgumentException("Invalid point");
                List<?> p=(List<?>)point;
                if(!(p.get(0) instanceof Number)||!(p.get(1) instanceof Number))throw new IllegalArgumentException("Invalid coordinate");
                double x=((Number)p.get(0)).doubleValue(),y=((Number)p.get(1)).doubleValue();
                if(!Double.isFinite(x)||!Double.isFinite(y)||x!=Math.rint(x)||y!=Math.rint(y)||x<0||y<0||x>=720||y>=1280)throw new IllegalArgumentException("Point outside virtual display");
            }
        }
        return steps;
    }
    void gesture(Object automation,int display,List<?> paths,int duration)throws Exception{
        int steps=validateGesture(display,paths,duration);
        Class<?> event=Class.forName("android.view.MotionEvent"),prop=Class.forName("android.view.MotionEvent$PointerProperties"),coord=Class.forName("android.view.MotionEvent$PointerCoords");
        int count=paths.size();Object properties=Array.newInstance(prop,count),coordinates=Array.newInstance(coord,count);
        for(int i=0;i<count;i++){Object p=prop.getDeclaredConstructor().newInstance();prop.getField("id").setInt(p,i);prop.getField("toolType").setInt(p,1);Array.set(properties,i,p);}
        Method obtain=event.getMethod("obtain",long.class,long.class,int.class,int.class,properties.getClass(),coordinates.getClass(),int.class,int.class,float.class,float.class,int.class,int.class,int.class,int.class);
        long down=((Number)Class.forName("android.os.SystemClock").getMethod("uptimeMillis").invoke(null)).longValue();
        int active=0;boolean completed=false;
        try{
        for(int step=0;step<steps;step++){
            for(int i=0;i<count;i++){List<?> point=(List<?>)((List<?>)paths.get(i)).get(step);Object c=coord.getDeclaredConstructor().newInstance();coord.getField("x").setFloat(c,((Number)point.get(0)).floatValue());coord.getField("y").setFloat(c,((Number)point.get(1)).floatValue());coord.getField("pressure").setFloat(c,1);coord.getField("size").setFloat(c,1);Array.set(coordinates,i,c);}
            if(step==0){for(int i=0;i<count;i++){active=i+1;inject(automation,obtain.invoke(null,down,down,i==0?0:5|(i<<8),active,properties,coordinates,0,0,1f,1f,0,0,0x1002,0),display);}}
            else{
                long target=down+(long)duration*step/(steps-1);long now=((Number)Class.forName("android.os.SystemClock").getMethod("uptimeMillis").invoke(null)).longValue();if(target>now)Thread.sleep(target-now);
                inject(automation,obtain.invoke(null,down,target,2,count,properties,coordinates,0,0,1f,1f,0,0,0x1002,0),display);
            }
        }
        long up=((Number)Class.forName("android.os.SystemClock").getMethod("uptimeMillis").invoke(null)).longValue();
        for(int i=count-1;i>=0;i--){inject(automation,obtain.invoke(null,down,up,i==0?1:6|(i<<8),i+1,properties,coordinates,0,0,1f,1f,0,0,0x1002,0),display);active=i;}
        completed=true;
        }finally{
            if(!completed&&active>0){
                // Injection failure may still have reached Android. Cancel once; never replay input.
                try{long now=((Number)Class.forName("android.os.SystemClock").getMethod("uptimeMillis").invoke(null)).longValue();inject(automation,obtain.invoke(null,down,now,3,active,properties,coordinates,0,0,1f,1f,0,0,0x1002,0),display);}catch(Exception ignored){}
            }
        }
    }
    static String readRequestFile(java.nio.file.Path home,String name)throws Exception{
        if(!name.matches("request-[A-Za-z0-9_-]{8,64}\\.json"))throw new IllegalArgumentException("Invalid request filename");
        java.nio.file.Path file=home.resolve(name);
        if(java.nio.file.Files.isSymbolicLink(file)||!file.toFile().getCanonicalFile().getParentFile().equals(home.toFile().getCanonicalFile()))throw new IllegalArgumentException("Request file outside own directory");
        try(java.io.InputStream in=java.nio.file.Files.newInputStream(file);java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream()){
            byte[] chunk=new byte[8192];int count;
            while((count=in.read(chunk))!=-1){if(bytes.size()+count>524288)throw new IllegalArgumentException("Request exceeds byte limit");bytes.write(chunk,0,count);}
            return new String(bytes.toByteArray(),StandardCharsets.UTF_8);
        }
    }
    void key(Object automation,int display,String chord)throws Exception{
        String[] parts=chord.toUpperCase(Locale.ROOT).split("\\+");int meta=0;
        for(int i=0;i<parts.length-1;i++){switch(parts[i]){case "CTRL":meta|=4096;break;case "SHIFT":meta|=1;break;case "ALT":meta|=2;break;default:throw new IllegalArgumentException("Unknown modifier");}}
        String name=parts[parts.length-1];if(name.equals("BACKSPACE"))name="DEL";if(name.equals("DELETE"))name="FORWARD_DEL";if(name.equals("ESC"))name="ESCAPE";
        Set<String> allowed=new HashSet<>(Arrays.asList("BACK","ENTER","TAB","DPAD_UP","DPAD_DOWN","DPAD_LEFT","DPAD_RIGHT","DEL","FORWARD_DEL","ESCAPE","MOVE_HOME","MOVE_END","SPACE","PAGE_UP","PAGE_DOWN"));
        if(!allowed.contains(name)&&!name.matches("[A-Z0-9]"))throw new IllegalArgumentException("Key is not allowed");
        Class<?> cls=Class.forName("android.view.KeyEvent");int code=cls.getField("KEYCODE_"+name).getInt(null);
        long now=((Number)Class.forName("android.os.SystemClock").getMethod("uptimeMillis").invoke(null)).longValue();
        Constructor<?> ctor=cls.getConstructor(long.class,long.class,int.class,int.class,int.class,int.class,int.class,int.class,int.class,int.class);
        for(int action:new int[]{0,1})inject(automation,ctor.newInstance(now,now,action,code,0,meta,-1,0,0,0x101),display);
    }
    private String serveRequest,serveReply;
    @SuppressWarnings("unchecked") public void testRequest()throws Exception{
        Map<String,Object> receipt=map();int display=Integer.parseInt(String.valueOf(getParam("display")));receipt.put("display",display);boolean attempting=false;
        try{
            if(display<=0)throw new IllegalArgumentException("Physical display prohibited");
            Object filename=getParam("request_file");String raw;
            if(serveRequest!=null)raw=serveRequest;
            else if(filename!=null)raw=readRequestFile(java.nio.file.Paths.get("/data/local/tmp/codaki-portable-core"),text(filename));
            else{
                String encoded=text(getParam("request64"));if(encoded.length()>100000)throw new IllegalArgumentException("Inline request exceeds byte limit");
                raw=new String(Base64.getDecoder().decode(encoded),StandardCharsets.UTF_8);
            }
            Map<String,Object> request=(Map<String,Object>)unpack(Class.forName("org.json.JSONObject").getConstructor(String.class).newInstance(raw));
            if(serveRequest!=null){display=integer(request,"display",0);receipt.put("display",display);}
            if(display<=0)throw new IllegalArgumentException("Physical display prohibited");
            if(integer(request,"display",0)!=display)throw new IllegalArgumentException("Display mismatch");
            Object automation=getUiAutomation(this);Map<String,Object> data=snapshot(automation,display);
            if(text(request.get("op")).equals("observe")){receipt.put("snapshot",data);receipt.put("ok",true);}
            else{
                if(!text(data.get("native_fingerprint")).equals(text(request.get("expected"))))throw new IllegalArgumentException("STALE: interface changed");
                Map<String,Object> a=(Map<String,Object>)request.get("action");String kind=text(a.get("kind"));Object node=handles.get(text(a.get("node_id")));
                int repeats=integer(a,"click_count",1);if(repeats<1||repeats>3)throw new IllegalArgumentException("click_count must be 1..3");
                if(node!=null){
                    if(protectedNode(node)||!Boolean.TRUE.equals(optional(node,"isEnabled",false))||!Boolean.TRUE.equals(optional(node,"isVisibleToUser",false)))throw new IllegalArgumentException("Protected, disabled or invisible element");
                    validateSemantic(node,a);
                    attempting=true;
                    for(int repeat=0;repeat<repeats;repeat++)if(!semantic(node,a))throw new IllegalStateException("Semantic action did not confirm success");
                }else{
                    if(a.containsKey("node_id"))throw new IllegalArgumentException("Missing element");
                    if(kind.equals("key")){attempting=true;key(automation,display,text(a.get("key")));}
                    else{
                        List<?> paths=(List<?>)a.get("paths");int duration=integer(a,"duration_ms",kind.equals("long_click")?700:120);
                        if(kind.equals("click")||kind.equals("long_click")||kind.equals("focus")){List<Integer> p=Arrays.asList(integer(a,"x",-1),integer(a,"y",-1));paths=Arrays.asList(Arrays.asList(p,p));}
                        if(kind.equals("drag"))paths=Arrays.asList(Arrays.asList(Arrays.asList(integer(a,"from_x",-1),integer(a,"from_y",-1)),Arrays.asList(integer(a,"to_x",-1),integer(a,"to_y",-1))));
                        if(kind.equals("scroll")){
                            int x=integer(a,"x",-1),y=integer(a,"y",-1),dx=integer(a,"scroll_x",0),dy=integer(a,"scroll_y",0);
                            int tx=Math.max(0,Math.min(719,x-dx)),ty=Math.max(0,Math.min(1279,y-dy));
                            paths=Arrays.asList(Arrays.asList(Arrays.asList(x,y),Arrays.asList(tx,ty)));duration=350;
                        }
                        if(a.containsKey("button")&&!text(a.get("button")).equals("left"))throw new IllegalArgumentException("Android supports touch, not secondary mouse buttons");
                        if(paths==null)throw new IllegalArgumentException("Unsupported coordinate action");
                        validateGesture(display,paths,duration);
                        attempting=true;for(int repeat=0;repeat<repeats;repeat++)gesture(automation,display,paths,duration);
                    }
                }
                receipt.put("ok",true);receipt.put("applied",true);
            }
        }catch(Throwable e){receipt.put("ok",false);receipt.put("applied",attempting?null:false);receipt.put("code",text(e.getMessage()).startsWith("STALE")?"STALE":text(e.getMessage()).equals("Semantic action did not confirm success")?"SEMANTIC_NOT_CONFIRMED":"REJECTED");receipt.put("error",e.getClass().getSimpleName()+": "+text(e.getMessage()));}
        if(serveRequest!=null)serveReply=json(receipt);
        else System.out.println("PORTABLE_USE\t"+json(receipt));
    }
    /** Keeps the same UiAutomation connection and native window IDs alive. */
    public void testServe() throws Exception {
        int display=Integer.parseInt(String.valueOf(getParam("display")));
        if(display<=0)throw new IllegalArgumentException("Physical display prohibited");
        String path="/data/local/tmp/codaki-portable-core/inspector.sock";
        Class<?> socketType=Class.forName("android.net.LocalSocket");
        Class<?> addressType=Class.forName("android.net.LocalSocketAddress");
        Class<?> namespaceType=Class.forName("android.net.LocalSocketAddress$Namespace");
        Object namespace=namespaceType.getField("FILESYSTEM").get(null);
        java.nio.file.Files.deleteIfExists(java.nio.file.Paths.get(path));
        Object bound=socketType.getConstructor().newInstance();
        Object address=addressType.getConstructor(String.class,namespaceType).newInstance(path,namespace);
        call(bound,"bind",new Class<?>[]{addressType},address);
        Object fd=call(bound,"getFileDescriptor",new Class<?>[0]);
        final Object server=Class.forName("android.net.LocalServerSocket").getConstructor(java.io.FileDescriptor.class).newInstance(fd);
        java.nio.file.Files.setPosixFilePermissions(java.nio.file.Paths.get(path),java.nio.file.attribute.PosixFilePermissions.fromString("rw-------"));
        Thread watchdog=new Thread(()->{
            java.nio.file.Path lease=java.nio.file.Paths.get("/data/local/tmp/codaki-portable-core/lease-deadline");
            try {
                while(java.nio.file.Files.exists(lease)){
                    long deadline=Long.parseLong(new String(java.nio.file.Files.readAllBytes(lease),StandardCharsets.US_ASCII).trim());
                    if(System.currentTimeMillis()>=deadline)break;
                    Thread.sleep(500);
                }
            }catch(Exception ignored){}
            try{call(server,"close",new Class<?>[0]);}catch(Exception ignored){}
        });
        watchdog.setDaemon(true);watchdog.start();
        try {
            while(true){
                Object client=call(server,"accept",new Class<?>[0]);
                try{
                    call(client,"setSoTimeout",new Class<?>[]{int.class},35000);
                    java.io.DataInputStream in=new java.io.DataInputStream((java.io.InputStream)call(client,"getInputStream",new Class<?>[0]));
                    int size=in.readInt();if(size<1||size>524288)throw new IllegalArgumentException("Invalid request size");
                    byte[] bytes=new byte[size];in.readFully(bytes);
                    serveRequest=new String(bytes,StandardCharsets.UTF_8);serveReply=null;
                    testRequest();
                    byte[] reply=serveReply.getBytes(StandardCharsets.UTF_8);
                    java.io.DataOutputStream out=new java.io.DataOutputStream((java.io.OutputStream)call(client,"getOutputStream",new Class<?>[0]));
                    out.writeInt(reply.length);out.write(reply);out.flush();
                }finally{serveRequest=null;serveReply=null;call(client,"close",new Class<?>[0]);}
            }
        }finally{
            try{call(server,"close",new Class<?>[0]);}finally{call(bound,"close",new Class<?>[0]);java.nio.file.Files.deleteIfExists(java.nio.file.Paths.get(path));}
        }
    }

}
