"""Execute production reflection code on the JVM; these are not device runtime tests."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from portable.android import AndroidBackend
from portable.engine import UseError

ROOT = Path(__file__).resolve().parents[1]

STUBS = {
    'com/android/uiautomator/testrunner/UiAutomatorTestCase.java': r'''
package com.android.uiautomator.testrunner;
public class UiAutomatorTestCase {
 public static android.os.Bundle params = new android.os.Bundle();
 public static Device device = new Device();
 public android.os.Bundle getParams(){return params;}
 public Device getUiDevice(){return device;}
 public static class Device { public com.android.uiautomator.core.UiAutomatorBridge mUiAutomationBridge = new com.android.uiautomator.core.UiAutomatorBridge(); }
}''',
    'com/android/uiautomator/core/UiAutomatorBridge.java': r'''
package com.android.uiautomator.core;
public class UiAutomatorBridge { public Object mUiAutomation; }''',
    'android/os/Bundle.java': r'''
package android.os;
public class Bundle extends java.util.HashMap<String,Object> {
 public void putInt(String k,int v){put(k,v);}
 public void putCharSequence(String k,CharSequence v){put(k,v);}
 public String getString(String k){return (String)get(k);}
}''',
    'android/os/SystemClock.java': r'''
package android.os; public class SystemClock { public static long uptimeMillis(){return System.nanoTime()/1000000;} }''',
    'android/graphics/Rect.java': r'''
package android.graphics; public class Rect {public int left,top,right,bottom;}''',
    'android/accessibilityservice/AccessibilityServiceInfo.java': r'''
package android.accessibilityservice; public class AccessibilityServiceInfo {public int flags;}''',
    'android/view/InputEvent.java': r'''
package android.view;
public class InputEvent {public int display=-1;public boolean recycled;public void setDisplayId(int d){display=d;} public void recycle(){recycled=true;} }''',
    'android/view/MotionEvent.java': r'''
package android.view;
public class MotionEvent extends InputEvent {
 public int action,count; public long down,time; public int[] ids; public float[] xs,ys;
 public static class PointerProperties {public int id,toolType;}
 public static class PointerCoords {public float x,y,pressure,size;}
 public static MotionEvent obtain(long down,long time,int action,int count,PointerProperties[] p,PointerCoords[] c,int meta,int buttons,float xp,float yp,int device,int edges,int source,int flags){
  MotionEvent e=new MotionEvent();e.down=down;e.time=time;e.action=action;e.count=count;e.ids=new int[count];e.xs=new float[count];e.ys=new float[count];
  for(int i=0;i<count;i++){e.ids[i]=p[i].id;e.xs[i]=c[i].x;e.ys[i]=c[i].y;}return e;
 }
}''',
    'org/json/JSONObject.java': r'''
package org.json;
public class JSONObject {
 public static java.util.Map<String,Object> request; final java.util.Map<String,Object> value;
 public JSONObject(String ignored){value=request;} public JSONObject(java.util.Map<String,Object> m){value=m;}
 public java.util.Iterator<String> keys(){return value.keySet().iterator();}
 public Object get(String k){return wrap(value.get(k));}
 static Object wrap(Object o){if(o instanceof java.util.Map)return new JSONObject((java.util.Map)o);if(o instanceof java.util.List)return new JSONArray((java.util.List)o);return o;}
}''',
    'org/json/JSONArray.java': r'''
package org.json;
public class JSONArray {final java.util.List value;public JSONArray(java.util.List a){value=a;}public int length(){return value.size();}public Object get(int i){return JSONObject.wrap(value.get(i));}}''',
    'com/oai/androiduse/Harness.java': r'''
package com.oai.androiduse;
import java.util.*;import java.io.*;import android.view.*;import android.os.*;
public class Harness {
 static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
 static void rejects(RunnableWithException f)throws Exception {try{f.run();throw new AssertionError("Expected rejection");}catch(IllegalArgumentException expected){}}
 interface RunnableWithException {void run()throws Exception;}
 public static class Node {
  String value="A\ud83d\ude00B",desc="hint";boolean password,sensitive,throwsSensitive,enabled=true,visible=true,success=true,throwsAction;int calls,lastAction;Bundle arguments;
  List<Node> children=new ArrayList<>();
  public boolean isPassword(){return password;}public boolean isAccessibilityDataSensitive(){if(throwsSensitive)throw new IllegalStateException("IPC died");return sensitive;}public boolean isEditable(){return true;}public boolean isClickable(){return true;}
  public boolean isEnabled(){return enabled;}public boolean isVisibleToUser(){return visible;}public boolean isFocused(){return true;}
  public boolean isChecked(){return false;}public boolean isSelected(){return false;}public boolean isScrollable(){return true;}
  public String getText(){return value;}public String getContentDescription(){return desc;}public String getViewIdResourceName(){return "pkg:id/edit";}
  public String getClassName(){return "android.widget.EditText";}public int getActions(){return 16|32|1|4|2097152|131072|4096|8192;}
  public int getChildCount(){return children.size();}public Node getChild(int i){return children.get(i);}
  public void getBoundsInScreen(android.graphics.Rect b){b.left=2;b.top=3;b.right=90;b.bottom=100;}
  public boolean performAction(int a,Bundle b){calls++;lastAction=a;arguments=b;if(throwsAction)throw new IllegalStateException("IPC died");if(success&&a==2097152)value=(String)b.get("ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE");return success;}
 }
 public static class Window {
  int id,display,rootReads;Node node;Window(int id,int display,Node n){this.id=id;this.display=display;node=n;}
  public int getDisplayId(){return display;}public int getId(){return id;}public String getTitle(){return "form";}
  public boolean isFocused(){return true;}public boolean isActive(){return true;}public int getLayer(){return 1;}
  public Node getRoot(){rootReads++;return node;}
 }
 public static class Sparse {
  Map<Integer,List<Window>> all=new HashMap<>();List<Integer> reads=new ArrayList<>();public List<Window> get(int d){reads.add(d);return all.get(d);}
 }
 public static class Automation {
  public android.accessibilityservice.AccessibilityServiceInfo info=new android.accessibilityservice.AccessibilityServiceInfo();
  Sparse windows=new Sparse();List<InputEvent> events=new ArrayList<>();int failAt=-1;boolean throwInjection;
  public Object getServiceInfo(){return info;}public void setServiceInfo(android.accessibilityservice.AccessibilityServiceInfo i){info=i;}
  public Sparse getWindowsOnAllDisplays(){return windows;}
  public boolean injectInputEvent(InputEvent e,boolean sync){check(sync,"Synchronous receipt required");events.add(e);if(events.size()==failAt){if(throwInjection)throw new IllegalStateException("Binder died");return false;}return true;}
 }
 static Automation automation;static Node root;static Window foreign;
 static PortableUiTest setup(){automation=new Automation();root=new Node();foreign=new Window(91,0,new Node());automation.windows.all.put(7,Arrays.asList(foreign,new Window(11,7,root)));com.android.uiautomator.testrunner.UiAutomatorTestCase.device.mUiAutomationBridge.mUiAutomation=automation;return new PortableUiTest();}
 static Map<String,Object> action(String kind){Map<String,Object>a=new LinkedHashMap<>();a.put("kind",kind);a.put("node_id","11/0");return a;}
 static String request(PortableUiTest p,Map<String,Object> a,String expected)throws Exception{
  Map<String,Object>r=new LinkedHashMap<>();r.put("display",7);r.put("op","action");r.put("action",a);r.put("expected",expected);org.json.JSONObject.request=r;
  Bundle params=com.android.uiautomator.testrunner.UiAutomatorTestCase.params;params.put("display","7");params.put("request64","e30=");
  PrintStream old=System.out;ByteArrayOutputStream bytes=new ByteArrayOutputStream();try{System.setOut(new PrintStream(bytes,true,"UTF-8"));p.testRequest();}finally{System.setOut(old);}return new String(bytes.toByteArray(),"UTF-8");
 }
 static String fingerprint(PortableUiTest p)throws Exception{return (String)p.snapshot(automation,7).get("native_fingerprint");}
 static List<?> paths(){return Arrays.asList(Arrays.asList(Arrays.asList(10,20),Arrays.asList(30,40)),Arrays.asList(Arrays.asList(50,60),Arrays.asList(70,80)));}
 @SuppressWarnings("unchecked")public static void main(String[] args)throws Exception{
  PortableUiTest p=setup();String name=args[0];
  if(name.equals("owner_args")){
   check(DisplayEngine.ownerArgs(new String[0])[0].equals("CodakiPortableUse"),"default");
   String t=String.join("",Collections.nCopies(32,"a"));
   check(DisplayEngine.ownerArgs(new String[]{"CodakiPortableUse_"+t,"/data/local/tmp/codaki-portable-core/sessions/"+t+"/lease-deadline"})[0].endsWith(t),"owned");
   rejects(()->DisplayEngine.ownerArgs(new String[]{"Physical","/tmp/lease"}));
   rejects(()->DisplayEngine.ownerArgs(new String[]{"CodakiPortableUse_"+t,"/data/local/tmp/codaki-portable-core/lease-deadline"}));
  }
  else if(name.equals("serve_display")){
   Node second=new Node();second.value="Second display";automation.windows.all.put(8,Arrays.asList(new Window(12,8,second)));
   com.android.uiautomator.testrunner.UiAutomatorTestCase.params.put("display","7");
   java.lang.reflect.Field req=PortableUiTest.class.getDeclaredField("serveRequest");req.setAccessible(true);
   java.lang.reflect.Field reply=PortableUiTest.class.getDeclaredField("serveReply");reply.setAccessible(true);
   Map<String,Object> r=new LinkedHashMap<>();r.put("display",8);r.put("op","observe");org.json.JSONObject.request=r;req.set(p,"{}");p.testRequest();
   check(((String)reply.get(p)).contains("Second display"),"Server did not route second display");check(foreign.rootReads==0,"Physical root read");
   r.put("display",0);p.testRequest();check(((String)reply.get(p)).contains("\"applied\":false"),"Zero display accepted");
  }
  else
  if(name.equals("roots")){check(p.roots(automation,7).size()==1,"Only requested roots");check(foreign.rootReads==0,"Physical root was read");check((automation.info.flags&0x50)==0x50,"Interactive window flags");}
  else if(name.equals("zero_roots")){rejects(()->p.roots(automation,0));check(automation.windows.reads.isEmpty(),"No physical lookup");}
  else if(name.equals("snapshot")){
   root.children.add(null);Node child=new Node();root.children.add(child);Node pwd=new Node();pwd.password=true;root.children.add(pwd);
   Map<String,Object>s=p.snapshot(automation,7);List<Map<String,Object>>nodes=(List<Map<String,Object>>)s.get("nodes");
   check(nodes.size()==3,"Null holes retained as indexes");check(nodes.get(1).get("node_id").equals("11/0/1"),"Child path ID");check(nodes.get(1).get("parent_id").equals("11/0"),"Parent ID");
   check(nodes.get(1).get("bounds").equals(Arrays.asList(2,3,90,100)),"Bounds");check(nodes.get(2).get("text").equals(""),"Password masking");check(nodes.get(2).get("description").equals(""),"Password description masking");check(foreign.rootReads==0,"No physical root");
   String before=(String)s.get("native_fingerprint");child.value="changed";check(!before.equals(fingerprint(p)),"Native fingerprint changes with UI");
  }
  else if(name.equals("deep_response")){
   Node current=root;root.value="";
   for(int depth=1;depth<=64;depth++){Node child=new Node();child.value=depth==64?"Saved chat response below Compose wrappers":"";current.children.add(child);current=child;}
   Map<String,Object>s=p.snapshot(automation,7);List<Map<String,Object>>nodes=(List<Map<String,Object>>)s.get("nodes");
   check(nodes.size()==65,"Nested response missing from snapshot: "+nodes.size());check(nodes.get(64).get("text").equals("Saved chat response below Compose wrappers"),"Response text lost below layout wrappers");
   check(Boolean.FALSE.equals(s.get("truncated")),"Complete nested response marked truncated");check(p.handles.get(nodes.get(64).get("node_id"))==current,"Deep response handle missing");check(foreign.rootReads==0,"Physical root was read");
  }
  else if(name.equals("snapshot_depth_bound")){
   Node current=root;
   for(int depth=1;depth<=140;depth++){Node child=new Node();child.value="depth-"+depth;current.children.add(child);current=child;}
   Map<String,Object>s=p.snapshot(automation,7);List<Map<String,Object>>nodes=(List<Map<String,Object>>)s.get("nodes");
   check(nodes.size()==129,"Traversal depth bound changed: "+nodes.size());check(nodes.get(128).get("text").equals("depth-128"),"Unexpected depth boundary");check(Boolean.TRUE.equals(s.get("truncated")),"Depth limit not reported");check(p.handles.size()==129,"Handles exceed depth-limited snapshot");
  }
  else if(name.equals("snapshot_node_bound")){
   for(int i=0;i<2005;i++){Node child=new Node();child.value="wide-"+i;root.children.add(child);}
   Map<String,Object>s=p.snapshot(automation,7);List<Map<String,Object>>nodes=(List<Map<String,Object>>)s.get("nodes");
   check(nodes.size()==2000,"Snapshot exceeded node bound: "+nodes.size());check(nodes.get(1999).get("text").equals("wide-1998"),"Unexpected node boundary");check(Boolean.TRUE.equals(s.get("truncated")),"Node limit not reported");check(p.handles.size()==2000,"Handles exceed node-limited snapshot");
  }
  else if(name.equals("sensitive")){root.sensitive=true;List<Map<String,Object>>nodes=(List<Map<String,Object>>)p.snapshot(automation,7).get("nodes");check(nodes.get(0).get("text").equals(""),"Sensitive text escaped masking");check(nodes.get(0).get("description").equals(""),"Sensitive description escaped masking");String r=request(p,action("click"),fingerprint(p));check(r.contains("\"applied\":false"),r);check(root.calls==0,"Sensitive action occurred");}
  else if(name.equals("empty_text")){Map<String,Object>a=action("set_text");a.put("text","");String r=request(p,a,fingerprint(p));check(r.contains("\"applied\":true"),r);check(root.value.equals(""),"Empty text must clear");check(root.lastAction==2097152,"Set text action ID");}
  else if(name.equals("selection")){Map<String,Object>a=action("selection");a.put("start",1);a.put("end",3);String r=request(p,a,fingerprint(p));check(r.contains("\"applied\":true"),r);check(root.lastAction==131072,"Selection action ID");check(root.arguments.get("ACTION_ARGUMENT_SELECTION_END_INT").equals(3),"UTF16 offset must stay 3");}
  else if(name.equals("stale")){String before=fingerprint(p);root.value="new";String r=request(p,action("click"),before);check(r.contains("\"code\":\"STALE\""),r);check(root.calls==0,"Stale input happened");}
  else if(name.equals("fresh_handles")){String before=fingerprint(p);Node old=root;root=new Node();automation.windows.all.put(7,Arrays.asList(new Window(11,7,root)));String r=request(p,action("click"),before);check(r.contains("\"applied\":true"),r);check(old.calls==0&&root.calls==1,"Old Java handle used after fresh snapshot");}
  else if(name.equals("protected")){root.password=true;String r=request(p,action("set_text"),fingerprint(p));check(r.contains("\"applied\":false"),r);check(root.calls==0,"Password input happened");}
  else if(name.equals("unknown")){root.throwsAction=true;String r=request(p,action("click"),fingerprint(p));check(r.contains("\"applied\":null"),r);check(root.calls==1,"Attempt must be recorded once");}
  else if(name.equals("semantic_false")){root.success=false;String r=request(p,action("click"),fingerprint(p));check(r.contains("\"applied\":null"),r);check(r.contains("\"code\":\"SEMANTIC_NOT_CONFIRMED\""),r);check(root.calls==1,"No automatic retry");}
  else if(name.equals("multi_touch")){p.gesture(automation,7,paths(),1);int[]actions={0,261,2,262,1};int[]counts={1,2,2,2,1};check(automation.events.size()==5,"Multitouch event sequence");long down=-1;for(int i=0;i<5;i++){MotionEvent e=(MotionEvent)automation.events.get(i);check(e.action==actions[i]&&e.count==counts[i],"Pointer action/index/count");check(e.display==7&&e.recycled,"Display route and recycling");check(e.ids[0]==0,"Stable pointer ID");if(i==0)down=e.down;check(e.down==down,"Shared downTime");}check(((MotionEvent)automation.events.get(2)).xs[1]==70,"Second finger move");}
  else if(name.equals("inject_zero")){MotionEvent e=MotionEvent.obtain(1,1,0,1,new MotionEvent.PointerProperties[]{new MotionEvent.PointerProperties()},new MotionEvent.PointerCoords[]{new MotionEvent.PointerCoords()},0,0,1,1,0,0,0,0);rejects(()->p.inject(automation,e,0));check(automation.events.isEmpty(),"Injected onto physical display");check(e.recycled,"Rejected event not recycled");}
  else if(name.equals("gesture_cleanup")||name.equals("gesture_throw_cleanup")){automation.failAt=2;automation.throwInjection=name.equals("gesture_throw_cleanup");try{p.gesture(automation,7,paths(),1);throw new AssertionError("Failure swallowed");}catch(Exception expected){}check(automation.events.size()==3,"Expected failed pointer down then CANCEL");check(((MotionEvent)automation.events.get(2)).action==3,"Failed gesture left touch active");for(InputEvent e:automation.events)check(e.recycled&&e.display==7,"Failed event leaked or wrong display");}
  else if(name.equals("invalid_paths")){List<?>bad=Arrays.asList(Arrays.asList(Arrays.asList(1,2),Arrays.asList(3,4)),Arrays.asList(Arrays.asList(5,6)));rejects(()->p.gesture(automation,7,bad,100));check(automation.events.isEmpty(),"Partial gesture before validation");}
  else if(name.equals("invisible")){root.visible=false;String r=request(p,action("click"),fingerprint(p));check(r.contains("\"applied\":false"),r);check(root.calls==0,"Invisible node input");}
  else if(name.equals("privacy_failure")){root.throwsSensitive=true;List<Map<String,Object>>nodes=(List<Map<String,Object>>)p.snapshot(automation,7).get("nodes");check(nodes.get(0).get("text").equals(""),"Failed protection lookup exposed text");String r=request(p,action("click"),fingerprint(p));check(r.contains("\"applied\":false"),r);check(root.calls==0,"Failed privacy lookup must not enable input");}
  else if(name.equals("zero_click_count")){Map<String,Object>a=action("click");a.put("click_count",0);String r=request(p,a,fingerprint(p));check(r.contains("\"ok\":false")&&r.contains("\"applied\":false"),r);check(root.calls==0,"Invalid click count");}
  else if(name.equals("unknown_semantic")){String r=request(p,action("bogus"),fingerprint(p));check(r.contains("\"applied\":false"),r);check(root.calls==0,"Unsupported semantic executed");}
  else if(name.equals("invalid_paths_receipt")){Map<String,Object>a=new LinkedHashMap<>();a.put("kind","gesture");a.put("paths",Arrays.asList(Arrays.asList(Arrays.asList(1,2),Arrays.asList(3,4)),Arrays.asList(Arrays.asList(5,6))));String r=request(p,a,fingerprint(p));check(r.contains("\"applied\":false"),r);check(automation.events.isEmpty(),"Bad paths partially injected");}
  else if(name.equals("request_file")){
   java.nio.file.Path dir=java.nio.file.Files.createTempDirectory("portable-request");java.nio.file.Path file=dir.resolve("request-abcdefgh.json");
   try{String value=String.join("",Collections.nCopies(65536,"\ud83d\ude00"));java.nio.file.Files.write(file,value.getBytes(java.nio.charset.StandardCharsets.UTF_8));check(PortableUiTest.readRequestFile(dir,file.getFileName().toString()).equals(value),"Full Unicode request truncated");rejects(()->PortableUiTest.readRequestFile(dir,"../request-abcdefgh.json"));rejects(()->PortableUiTest.readRequestFile(dir,file.toString()));java.nio.file.Files.write(file,new byte[524289]);rejects(()->PortableUiTest.readRequestFile(dir,file.getFileName().toString()));}
   finally{java.nio.file.Files.deleteIfExists(file);java.nio.file.Files.deleteIfExists(dir);}
  }
  else throw new IllegalArgumentException(name);
  System.out.println("PASS "+name);
 }
}''',
}


@unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'JDK required for reflection checks')
class JavaReflectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        t = Path(cls.temp.name)
        sources = []
        for name, content in STUBS.items():
            p = t / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
            sources.append(p)
        cls.classes = t / 'classes'
        cls.classes.mkdir()
        result = subprocess.run(['javac', '--release', '8', '-encoding', 'UTF-8', '-d', str(cls.classes),
                                 *map(str, sources), *map(str, (ROOT/'android/java').glob('*.java'))],
                                text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_case(self, name):
        result = subprocess.run(['java', '-cp', str(self.classes), 'com.oai.androiduse.Harness', name],
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS ' + name)


for _name in ('owner_args','serve_display','roots', 'zero_roots', 'snapshot', 'deep_response', 'snapshot_depth_bound', 'snapshot_node_bound', 'sensitive', 'empty_text', 'selection', 'stale',
              'fresh_handles', 'protected', 'unknown', 'semantic_false', 'multi_touch', 'inject_zero',
              'gesture_cleanup', 'gesture_throw_cleanup', 'invalid_paths', 'invisible',
              'privacy_failure', 'zero_click_count', 'unknown_semantic', 'invalid_paths_receipt', 'request_file'):
    setattr(JavaReflectionTests, 'test_' + _name, lambda self, name=_name: self.run_case(name))


class PythonAndroidBoundaryTests(unittest.TestCase):
    def test_batch_static_constraints_rejected_before_any_input(self):
        b=AndroidBackend.__new__(AndroidBackend)
        for action in ({'kind':'key','key':'CMD+ENTER'},{'kind':'key','key':'CTRL+'},{'kind':'key','key':'HOME'},{'kind':'click','button':'right'}):
            with self.assertRaises(UseError):b.validate_batch_action(action)
        for key in ('CTRL+A','SHIFT+TAB','BACK','ESC','BACKSPACE'):b.validate_batch_action({'kind':'key','key':key})
    def backend(self):
        b = AndroidBackend.__new__(AndroidBackend)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = Path(self.temp.name)
        (p/'ui-v2.jar').touch()
        b.legacy = SimpleNamespace(HOME=p, find_display=lambda: 7)
        return b

    def test_selection_codepoints_are_converted_to_utf16_without_mutating_input(self):
        b = self.backend()
        sent = []
        b.request = lambda r: sent.append(r) or {'applied': True}
        action = {'kind': 'selection', 'node_id': '11/0', 'start': 1, 'end': 2}
        b.action(action, {'nodes': [{'node_id': '11/0', 'text': 'A😀B'}], 'native_fingerprint': 'native'})
        self.assertEqual(sent[0]['action']['end'], 3)
        self.assertEqual(action['end'], 2)
        self.assertEqual(sent[0]['expected'], 'native')

    def test_unknown_receipt_does_not_retry(self):
        b = self.backend()
        r = SimpleNamespace(stdout='PORTABLE_USE\t'+json.dumps({'display':7, 'ok':False, 'applied':None}), returncode=0)
        with patch('portable.android.subprocess.run', return_value=r) as run:
            with self.assertRaises(RuntimeError): b.request({'op':'action'})
        self.assertEqual(run.call_count, 1)
    def test_semantic_refusal_reason_survives_android_boundary(self):
        b=self.backend()
        r=SimpleNamespace(stdout='PORTABLE_USE\t'+json.dumps({'display':7,'ok':False,'applied':None,'code':'SEMANTIC_NOT_CONFIRMED'}),returncode=0)
        with patch('portable.android.subprocess.run',return_value=r) as run:
            with self.assertRaises(RuntimeError) as err:b.request({'op':'action'})
        self.assertEqual(getattr(err.exception,'reason',None),'SEMANTIC_NOT_CONFIRMED')
        self.assertEqual(run.call_count,1)
    def test_system_process_does_not_inherit_termux_libraries(self):
        b=self.backend()
        r=SimpleNamespace(stdout='PORTABLE_USE\t'+json.dumps({'display':7,'ok':True}),returncode=0)
        with patch.dict('os.environ',{'LD_LIBRARY_PATH':'/termux/lib','LD_PRELOAD':'/termux/hook.so'}),patch('portable.android.subprocess.run',return_value=r) as run:
            b.request({'op':'observe'})
        env=run.call_args.kwargs['env']
        self.assertNotIn('LD_LIBRARY_PATH',env);self.assertNotIn('LD_PRELOAD',env)
        self.assertEqual(env['PATH'],'/system/bin:/system/xbin:/vendor/bin')

    def test_definite_rejection_remains_use_error(self):
        b = self.backend()
        r = SimpleNamespace(stdout='PORTABLE_USE\t'+json.dumps({'display':7, 'ok':False, 'applied':False, 'code':'STALE'}), returncode=0)
        with patch('portable.android.subprocess.run', return_value=r):
            with self.assertRaises(UseError) as err: b.request({'op':'action'})
        self.assertEqual(err.exception.code, 'STALE')

    def test_timeout_is_unknown_and_never_retried(self):
        b = self.backend()
        with patch('portable.android.subprocess.run', side_effect=subprocess.TimeoutExpired('uiautomator', 30)) as run:
            with self.assertRaises(RuntimeError): b.request({'op':'action'})
        self.assertEqual(run.call_count, 1)

    def test_large_unicode_request_uses_private_file_and_short_argv(self):
        b = self.backend()
        text = '😀' * 65536
        observed = []
        def transport(argv, **kwargs):
            self.assertLess(max(map(len, argv)), 4096)
            self.assertNotIn('request64', argv)
            i = argv.index('request_file')
            p = b.legacy.HOME / argv[i+1]
            self.assertEqual(json.loads(p.read_text(encoding='utf-8'))['action']['text'], text)
            observed.append(p)
            return SimpleNamespace(stdout='PORTABLE_USE\t'+json.dumps({'display':7, 'ok':True, 'applied':True}), returncode=0)
        with patch('portable.android.subprocess.run', side_effect=transport):
            b.request({'op':'action', 'action':{'kind':'set_text', 'text':text}})
        self.assertEqual(len(observed), 1)
        self.assertFalse(observed[0].exists(), 'Input text file leaked after receipt')

    def test_failed_transport_removes_private_request_file(self):
        b = self.backend()
        observed = []
        def transport(argv, **kwargs):
            i = argv.index('request_file')
            observed.append(b.legacy.HOME / argv[i+1])
            raise subprocess.TimeoutExpired('uiautomator', 30)
        with patch('portable.android.subprocess.run', side_effect=transport):
            with self.assertRaises(RuntimeError): b.request({'op':'action'})
        self.assertFalse(observed[0].exists())

    def test_start_exception_is_uncertain_after_attempt(self):
        b = self.backend()
        b.legacy.start_engine = lambda: (_ for _ in ()).throw(RuntimeError('display receipt lost'))
        with self.assertRaises(RuntimeError): b.start()


if __name__ == '__main__':
    unittest.main()
