#!/data/data/com.termux/files/usr/bin/python
"""Android Use Core: isolated virtual-display control, no root commands or UI0 fallback.
This is a local MCP endpoint reached by the private Android Use relay.
Requires a live CodakiPortableUse screen created by the separate display owner.
"""
import argparse,json,re,socket,socketserver,subprocess,os,time,signal,base64
from pathlib import Path
HOME=Path("/data/local/tmp/codaki-portable-core")
SOCK=HOME/"core.sock"
NAME="CodakiPortableUse"
COMP=re.compile(r"^[A-Za-z_][\w.]*/[A-Za-z_][\w.$]*$",re.ASCII)
KEYS={"BACK","ENTER","TAB","DPAD_UP","DPAD_DOWN","DPAD_LEFT","DPAD_RIGHT"}
class Denied(Exception): pass
ENGINE_CLASS="com.oai.androiduse.DisplayEngine"
ENGINE_JAR=HOME/"display-engine.jar"
ENGINE_PID=HOME/"engine.pid"
ENGINE_LOG=HOME/"engine.log"

def system_env():
    env={k:v for k,v in os.environ.items() if not k.startswith('LD_')}
    env['PATH']='/system/bin:/system/xbin:/vendor/bin'
    return env

def engine_pid():
    if not ENGINE_PID.exists():return None
    try:
        record=json.loads(ENGINE_PID.read_text().strip());pid=record['pid'] if isinstance(record,dict) else int(record)
        if type(pid)!=int or pid<=0:raise ValueError('Invalid PID')
    except (ValueError,OSError,KeyError,TypeError):raise Denied("Invalid display owner process record")
    cmdfile=Path("/proc")/str(pid)/"cmdline"
    if not cmdfile.exists():
        ENGINE_PID.unlink(missing_ok=True)
        return None
    raw=cmdfile.read_bytes().replace(b"\x00",b" ").decode("utf-8","replace")
    if NAME!='CodakiPortableUse' or isinstance(record,dict):
        if not isinstance(record,dict):raise Denied('Owned display PID requires a generation record')
        start=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        status=Path('/proc',str(pid),'status').read_text()
        args=cmdfile.read_bytes().split(b'\0')
        if (start!=record.get('start_ticks') or NAME.encode() not in args
            or str(HOME/'lease-deadline').encode() not in args
            or not re.search(r'^Uid:\s+0\s+0\s+0\s+0\s*$',status,re.M)):
            raise Denied('Owned display process generation or identity mismatch')
    if ENGINE_CLASS not in raw or "app_process" not in raw:
        # Android can reuse a PID after the display's lease expires. Clear
        # only the stale record, only after confirming our display is absent.
        dump=run("dumpsys","display")
        if "DisplayDeviceInfo{" in dump and NAME not in dump:
            ENGINE_PID.unlink(missing_ok=True)
            return None
        raise Denied("Display owner PID mismatch; will not signal other processes")
    return pid

def start_engine():
    if os.geteuid()!=0:raise Denied("Privileged display owner is unavailable")
    pid=engine_pid()
    if pid:
        try:
            did=find_display()
            return {"ok":True,"display":did,"pid":pid,"alreadyRunning":True}
        except Denied:
            raise Denied("Display owner is running but has no verified independent display")
    if not ENGINE_JAR.is_file():raise Denied("Verified local display engine is missing")
    try:
        orphan=find_display()
    except Denied:pass
    else:raise Denied("An unowned display exists; refusing a duplicate")
    with ENGINE_LOG.open("w") as log:
        os.chmod(ENGINE_LOG,0o600)
        env=system_env()
        env["CLASSPATH"]=str(ENGINE_JAR)
        p=subprocess.Popen(["/system/bin/app_process","/",ENGINE_CLASS,NAME,str(HOME/"lease-deadline")],
                           stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                           env=env,start_new_session=True)
    start=Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    ENGINE_PID.write_text(json.dumps({'pid':p.pid,'start_ticks':start}))
    ENGINE_PID.chmod(0o600)
    for attempt in range(32):
        if p.poll() is not None:break
        try:
            did=find_display()
            return {"ok":True,"display":did,"pid":p.pid,"alreadyRunning":False}
        except Denied:time.sleep(0.25)
    if p.poll() is None:
        p.terminate()
    error=ENGINE_LOG.read_text(errors="replace")[-300:]
    raise Denied("Virtual display failed to start: "+error)

def stop_engine():
    if os.geteuid()!=0:raise Denied("Cannot stop a privileged display from here")
    pid=engine_pid()
    if pid is None:
        try:did=find_display()
        except Denied:return {"ok":True,"stopped":True,"alreadyStopped":True}
        raise Denied("Found an unowned independent display; refusing to stop it")
    # Remove only stacks currently owned by our independently verified display.
    # HyperOS can keep task cards in Recents even after a display is released.
    did=find_display()
    listing=subprocess.run(["am","stack","list"],capture_output=True,text=True,timeout=12,env=system_env())
    if listing.returncode != 0:
        raise Denied("Cannot verify display-scoped tasks for cleanup")
    owned=[]
    for line in listing.stdout.splitlines():
        match=re.search(r"^RootTask id=(\d+) .* displayId=(\d+) ",line)
        if match and int(match.group(2))==did:
            owned.append(int(match.group(1)))
    # Recheck ownership before modifying any task. Do not touch display 0.
    if did!=find_display():raise Denied("Virtual display changed before cleanup")
    for task in owned:
        removed=subprocess.run(["am","stack","remove",str(task)],capture_output=True,text=True,timeout=12,env=system_env())
        if removed.returncode!=0:
            raise Denied("Could not remove an owned virtual stack")
    os.kill(pid,signal.SIGTERM)
    for attempt in range(36):
        try:find_display()
        except Denied:
            ENGINE_PID.unlink(missing_ok=True)
            return {"ok":True,"stopped":True,"physicalScreenUntouched":True,"removedVirtualStacks":len(owned)}
        time.sleep(0.25)
    raise Denied("Display did not release after SIGTERM; process requires inspection")

def run(*args):
    try:
        p=subprocess.run(args,check=False,capture_output=True,text=True,timeout=12,env=system_env())
    except subprocess.TimeoutExpired: raise Denied("Android command timeout")
    if "Permission Denial" in p.stdout: raise Denied("System permission denied; requires authorized Codaki Mini Codex broker")
    if p.returncode:raise Denied("Android refused command: "+(p.stderr or p.stdout)[-150:])
    return p.stdout

def find_display(dump=None):
    """Map a trusted virtual display device to its nonzero logical display.

    HyperOS exposes OWN_FOCUS at DisplayDeviceInfo level, but may omit it from
    LogicalDisplay DisplayInfo. Both layers must match the same unique ID.
    """
    raw=run("dumpsys","display") if dump is None else dump
    target=[line.strip() for line in raw.splitlines()
            if 'DisplayDeviceInfo{"'+NAME+'": uniqueId=' in line]
    if len(target)!=1:
        raise Denied("No unique Android Use display device; physical screen untouched")
    device=target[0]
    required={"FLAG_TRUSTED","FLAG_OWN_FOCUS","FLAG_OWN_DISPLAY_GROUP",
              "FLAG_STEAL_TOP_FOCUS_DISABLED","FLAG_ALWAYS_UNLOCKED",
              "FLAG_DESTROY_CONTENT_ON_REMOVAL"}
    found=set(re.findall(r"FLAG_[A-Z_]+",device))
    if not required.issubset(found) or "virtual:" not in device:
        raise Denied("Virtual display lacks mandatory isolation flags")
    unique=re.search(r'uniqueId="([^"]+)"',device)
    if not unique:
        raise Denied("No virtual display unique ID")
    chunks=re.split(r"(?=^\s*Display \d+:\s*$)",raw,flags=re.M)
    ids=[]
    for chunk in chunks:
        head=re.match(r"\s*Display (\d+):",chunk)
        if not head:continue
        did=int(head.group(1))
        if did==0:continue
        primary=re.search(r"mPrimaryDisplayDevice=([^\n]+)",chunk)
        base=re.search(r"mBaseDisplayInfo=DisplayInfo\{[^\n]*",chunk)
        if not primary or not base:continue
        info=base.group()
        if ('DisplayInfo{"'+NAME+'"' in info and "type VIRTUAL" in info
                and "FLAG_TRUSTED" in info and "FLAG_OWN_DISPLAY_GROUP" in info
                and NAME+"(" in primary.group()
                and unique.group(1) in primary.group()):
            ids.append(did)
    if len(ids)!=1:
        raise Denied("No uniquely mapped independent virtual display")
    return ids[0]

def capture_virtual():
    did=find_display()  # Fail closed: no physical-display fallback.
    sf=run("dumpsys","SurfaceFlinger","--display-id")
    ids=re.findall(r'Display (\d+) \(Virtual display\): displayName="'+re.escape(NAME)+r'"',sf)
    if len(ids)!=1:
        raise Denied("No unique virtual SurfaceFlinger capture target")
    try:
        shot=subprocess.run(["screencap","-p","-d",ids[0]],
                            capture_output=True,timeout=9,env=system_env())
    except subprocess.TimeoutExpired:
        raise Denied("Virtual screenshot timed out")
    if shot.returncode or not shot.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        raise Denied("Virtual screenshot failed or returned invalid PNG")
    if len(shot.stdout)>3000000:
        raise Denied("Virtual screenshot exceeded size limit")
    return {"display":did,"png":base64.b64encode(shot.stdout).decode("ascii")}

def sanitize_ui_snapshot(data,did):
    if (type(did)!=int or did<=0 or not isinstance(data,dict)
            or type(data.get("display"))!=int or data["display"]!=did
            or not isinstance(data.get("nodes"),list)):
        raise Denied("UI display identity mismatch")
    nodes=[]
    for node in data["nodes"][:260]:
        if not isinstance(node,dict) or node.get("password"):continue
        bounds=node.get("bounds")
        if not isinstance(bounds,list) or len(bounds)!=4 or any(type(v)!=int for v in bounds):continue
        left,top,right,bottom=bounds
        # The owned display has fixed 720 x 1280 geometry. Keep only visible
        # targets and clip partial bounds before they can become tap centres.
        left,top,right,bottom=max(0,left),max(0,top),min(720,right),min(1280,bottom)
        if right<=left or bottom<=top:continue
        clean={"bounds":[left,top,right,bottom]}
        for key in ("text","desc","class"):
            value=node.get(key)
            if isinstance(value,str) and value and value!="null":clean[key]=value[:180]
        for key in ("clickable","editable"):
            if type(node.get(key))==bool:clean[key]=node[key]
        if not any(clean.get(key) for key in ("text","desc","clickable","editable")):continue
        nodes.append(clean)
        if len(nodes)>=160:break
    windows=data.get("windows",0)
    if type(windows)!=int or not 0<=windows<=8:windows=0
    return {"ok":True,"display":did,"windows":windows,"nodes":nodes}

def inspect_ui():
    did=find_display()
    jar=HOME/"ui-test.jar"
    if not jar.is_file():raise Denied("Verified UI Automator inspector unavailable")
    args=["/system/bin/uiautomator","runtest",str(jar),
          "-c","com.oai.androiduse.VirtualUiTest#testInspect",
          "-e","display",str(did),"-s"]
    try:
        proc=subprocess.run(args,capture_output=True,text=True,timeout=19,env=system_env())
    except subprocess.TimeoutExpired:
        raise Denied("UI inspector timed out; no actions were performed")
    if proc.returncode:
        raise Denied("UI inspection could not complete: "+(proc.stderr+proc.stdout)[-200:])
    lines=[line.split("ANDROID_USE_INSPECT\t",1)[1]
           for line in proc.stdout.splitlines() if "ANDROID_USE_INSPECT\t" in line]
    if len(lines)!=1:
        raise Denied("UI inspector did not return a unique target result")
    try:data=json.loads(lines[0])
    except (ValueError,TypeError):raise Denied("Invalid target UI snapshot")
    return sanitize_ui_snapshot(data,did)

def click_by_text(text):
    if not isinstance(text,str) or not text or len(text)>180:
        raise Denied("Invalid text selector")
    ui=inspect_ui()
    valid=[n for n in ui["nodes"] if n.get("text")==text]
    if len(valid)!=1:
        raise Denied("Expected exactly one text target, found "+str(len(valid)))
    bounds=valid[0].get("bounds")
    if not isinstance(bounds,list) or len(bounds)!=4 or any(type(v)!=int for v in bounds):
        raise Denied("Target has no usable bounds")
    left,top,right,bottom=bounds
    if right<=left or bottom<=top:raise Denied("Target has empty bounds")
    # Re-resolve the private display immediately before executing input.
    did=find_display()
    if did!=ui["display"]:raise Denied("Display changed during inspection")
    x,y=(left+right)//2,(top+bottom)//2
    if x<0 or y<0 or x>=4000 or y>=4000:raise Denied("Tap outside virtual screen")
    run("input","touchscreen","-d",str(did),"tap",str(x),str(y))
    return {"ok":True,"display":did,"clickedText":text,"x":x,"y":y}

def set_text_utf8(text):
    # The test runner receives ASCII base64, preserving Unicode whitespace
    # without using a shared clipboard or the physical display's IME.
    if not isinstance(text,str) or not text or len(text)>1000 or "\x00" in text:
        raise Denied("Invalid UI input text")
    did=find_display()
    package=HOME/"ui-test.jar"
    if not package.is_file():raise Denied("System UiAutomation adapter unavailable")
    arg=base64.b64encode(text.encode("utf-8")).decode("ascii")
    proc_args=["/system/bin/uiautomator","runtest",str(package),
             "-c","com.oai.androiduse.VirtualUiTest#testSetText",
             "-e","display",str(did),"-e","text64",arg,"-s"]
    try:
        result=subprocess.run(proc_args,text=True,capture_output=True,timeout=19,env=system_env())
    except subprocess.TimeoutExpired:
        raise Denied("UI text operation timed out: outcome unknown, do not replay blindly")
    if result.returncode:
        raise Denied("Android text operation refused: "+(result.stdout+result.stderr)[-220:])
    markers=[line.split("ANDROID_USE_SET_TEXT\t",1)[1] for line in result.stdout.splitlines()
             if "ANDROID_USE_SET_TEXT\t" in line]
    if len(markers)!=1:raise Denied("Missing unique text operation receipt")
    try:receipt=json.loads(markers[0])
    except ValueError:raise Denied("Malformed text operation receipt")
    if receipt.get("display")!=did or receipt.get("ok") is not True:
        raise Denied("Text operation was not confirmed on the isolated display")
    return {"ok":True,"display":did,"length":len(text),"method":"ACTION_SET_TEXT"}

def execute_batch(steps):
    if not isinstance(steps,list) or not 1<=len(steps)<=18:
        raise Denied("Batch must contain 1 to 18 GUI actions")
    completed=[]
    allowed={
        "privileges":{"op"},
        "start":{"op"},
        "stop":{"op"},
        "launch":{"op","component"},
        "tap":{"op","x","y"},
        "swipe":{"op","x1","y1","x2","y2","ms"},
        "key":{"op","key"},
        "wait":{"op","ms"},
        "status":{"op"},
        "windows":{"op"},
        "inspect_ui":{"op"},
        "click_text":{"op","text"},
        "set_text":{"op","text"},
    }
    for i,step in enumerate(steps):
        if not isinstance(step,dict):
            return {"ok":False,"completed":i,"error":"Invalid action object","trace":completed}
        action=step.get("op")
        if action not in allowed or not set(step).issubset(allowed.get(action,set())):
            return {"ok":False,"completed":i,"error":"Invalid or unsafe GUI action","trace":completed}
        try:
            if action=="wait":
                ms=step.get("ms",150)
                if type(ms)!=int or not 0<=ms<=2000:raise Denied("Invalid wait time")
                time.sleep(ms/1000)
                data={"ok":True,"waitedMs":ms}
            elif action in ("privileges","start","stop","status","windows","inspect_ui"):
                data=op("android_"+action,{})
            else:
                data=op("android_"+action,{k:v for k,v in step.items() if k!="op"})
            completed.append({"op":action,"result":data})
        except (Denied,TypeError,ValueError) as err:
            return {"ok":False,"completed":i,"error":str(err),"trace":completed}
    return {"ok":True,"completed":len(completed),"trace":completed}

def op(name,args):
    if not isinstance(args,dict):raise Denied("Invalid arguments")
    if name=="android_privileges" and not args:
        import os
        return {"ok":True,"uid":os.geteuid(),"root":os.geteuid()==0,"arbitraryShell":False,"physicalScreenProtected":True}
    if name=="android_set_text" and set(args)=={"text"}:return set_text_utf8(args["text"])
    if name=="android_inspect_ui" and not args:return inspect_ui()
    if name=="android_click_text" and set(args)=={"text"}:return click_by_text(args["text"])
    if name=="android_batch" and set(args)=={"steps"}:return execute_batch(args["steps"])
    if name=="android_capture" and not args:return capture_virtual()
    if name=="android_start" and not args:return start_engine()
    if name=="android_stop" and not args:return stop_engine()
    if name=="android_status" and not args:
        d=find_display()
        m=re.search(r"FocusedDisplayId:\s*(\d+)",run("dumpsys","input"))
        return {"ok":True,"display":d,"mainProtected":True,"focus":int(m.group(1)) if m else None}
    if name=="android_windows" and not args:
        d=find_display()
        a=run("dumpsys","activity","activities")
        match=re.search(r"^Display #"+str(d)+r" \(activities.*$",a,re.M)
        if not match:raise Denied("No tasks on virtual display")
        # ActivityManager appends global task/window sections after the
        # per-display section. Never return other displays' application names.
        tail=a[match.end():]
        boundaries=[]
        for pattern in (r"^Display #\d+ \(activities",
                        r"^Resumed activities in task display areas",
                        r"^ActivityTaskSupervisor state:"):
            other=re.search(pattern,tail,re.M)
            if other:boundaries.append(other.start())
        excerpt=tail[:min(boundaries)] if boundaries else tail
        out=[]
        for line in excerpt.splitlines():
            # Do not read the global ResumedActivity line: it can describe
            # the user's physical display even inside a display-scoped dump.
            if not re.match(r"^\s*(?:\* Hist\s|topResumedActivity:|topPausingActivity:|mLastPausedActivity:)",line):
                continue
            m=re.search(r"ActivityRecord\{[^\s]+ u\d+ ([A-Za-z_.]+/[A-Za-z_.$]+)",line)
            if m and m.group(1) not in out:out.append(m.group(1))
        return {"ok":True,"display":d,"activities":out[:25]}
    if name=="android_launch" and set(args)=={"component"}:
        c=args["component"]
        if not isinstance(c,str) or not COMP.fullmatch(c) or len(c)>200:raise Denied("Invalid app component")
        d=find_display()
        result=run("am","start","--display",str(d),"-f","0x18800000","-n",c)
        return {"ok":True,"display":d,"requested":c,"launch":result[:150]}
    if name=="android_tap" and set(args)=={"x","y"}:
        x,y=args["x"],args["y"]
        if type(x)!=int or type(y)!=int or not 0<=x<4000 or not 0<=y<4000:raise Denied("Invalid coordinates")
        d=find_display()
        run("input","touchscreen","-d",str(d),"tap",str(x),str(y))
        return {"ok":True,"display":d,"action":"tap","x":x,"y":y}
    if name=="android_swipe" and set(args)=={"x1","y1","x2","y2","ms"}:
        coords=[args[k] for k in ("x1","y1","x2","y2")]
        ms=args["ms"]
        if any(type(v)!=int or not 0<=v<4000 for v in coords):
            raise Denied("Invalid virtual-display swipe coordinates")
        if type(ms)!=int or not 80<=ms<=2500:
            raise Denied("Invalid swipe duration")
        did=find_display()
        run("input","touchscreen","-d",str(did),"swipe",
            *(str(v) for v in coords),str(ms))
        return {"ok":True,"display":did,"action":"swipe","durationMs":ms}
    if name=="android_key" and set(args)=={"key"}:
        if args["key"] not in KEYS:raise Denied("Key not permitted")
        d=find_display()
        run("input","keyboard","-d",str(d),"keyevent","KEYCODE_"+args["key"])
        return {"ok":True,"display":d,"action":"key"}
    raise Denied("Unsupported operation or extra arguments")

TOOLS=[]
for name,description,fields,required in [
 ("android_status","Verified virtual-display status",{},[]),
 ("android_windows","Activity names only, never physical UI",{},[]),
 ("android_launch","Launch on own virtual display",{"component":{"type":"string"}},["component"]),
 ("android_tap","Tap on own virtual display",{"x":{"type":"integer"},"y":{"type":"integer"}},["x","y"]),
 ("android_key","Navigation key on own virtual display",{"key":{"type":"string"}},["key"]),
 ("android_swipe","Swipe on own virtual display",
  {"x1":{"type":"integer"},"y1":{"type":"integer"},
   "x2":{"type":"integer"},"y2":{"type":"integer"},
   "ms":{"type":"integer"}},["x1","y1","x2","y2","ms"])
]:
    TOOLS.append({"name":name,"description":description,"inputSchema":{
        "type":"object","properties":fields,"required":required,"additionalProperties":False}})
TOOLS.append({"name":"android_privileges","description":"Report Android Use Core service identity only.","inputSchema":{"type":"object","properties":{},"required":[],"additionalProperties":False}})
for name,description in (
    ("android_start","Create or reuse the dedicated trusted virtual display"),
    ("android_stop","Release only the verified Android Use virtual display")):
    TOOLS.append({"name":name,"description":description,
                  "inputSchema":{"type":"object","properties":{},"required":[],"additionalProperties":False}})
TOOLS.append({"name":"android_capture",
              "description":"Capture only the verified private virtual screen as a PNG image",
              "inputSchema":{"type":"object","properties":{},"required":[],"additionalProperties":False}})
TOOLS.append({"name":"android_batch",
              "description":"Execute 1-18 validated GUI actions on the independent Android display. Returns partial trace if an action fails; never automatically replays.",
              "inputSchema":{"type":"object","properties":{
                 "steps":{"type":"array","minItems":1,"maxItems":18,"items":{"type":"object"}}},
                 "required":["steps"],"additionalProperties":False}})
TOOLS.append({"name":"android_inspect_ui","description":"Read UI nodes ONLY from verified isolated display via system UiAutomator; passwords are redacted.",
              "inputSchema":{"type":"object","properties":{},"required":[],"additionalProperties":False}})
TOOLS.append({"name":"android_click_text","description":"Click exactly one matching clickable text on the private display; refuses ambiguity.",
              "inputSchema":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":False}})
TOOLS.append({"name":"android_set_text",
              "description":"Set Unicode text in exactly one non-password editable field on the private display. Never sends messages by itself.",
              "inputSchema":{"type":"object","properties":{"text":{"type":"string","maxLength":1000}},"required":["text"],"additionalProperties":False}})
def rpc(req):
    if not isinstance(req,dict):return {"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Invalid request"}}
    method=req.get("method");ident=req.get("id")
    if method=="notifications/initialized":return None
    if method=="initialize":
        result={"protocolVersion":"2025-03-26","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"Android Use Core","version":"0.0.1"}}
    elif method=="tools/list":result={"tools":TOOLS}
    elif method=="ping":result={}
    elif method=="tools/call":
        params=req.get("params") or {}
        try:
            data=op(params.get("name"),params.get("arguments") or {})
            if params.get("name")=="android_capture":
                result={"content":[{"type":"image","data":data["png"],"mimeType":"image/png"}],"isError":False}
            else:
                result={"content":[{"type":"text","text":json.dumps(data,ensure_ascii=False)}],"isError":data.get("ok",True) is False}
        except (Denied,TypeError,KeyError) as exc:
            result={"content":[{"type":"text","text":str(exc)}],"isError":True}
    else:
        return {"jsonrpc":"2.0","id":ident,"error":{"code":-32601,"message":"Unknown method"}}
    return {"jsonrpc":"2.0","id":ident,"result":result}
class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            raw=self.rfile.readline(16385)
            if not raw or len(raw)>16384:break
            try:out=rpc(json.loads(raw.decode()))
            except (ValueError,UnicodeError):out={"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"Invalid JSON"}}
            if out is not None:self.wfile.write((json.dumps(out,ensure_ascii=False)+"\n").encode())
class Server(getattr(socketserver,'ThreadingUnixStreamServer',socketserver.ThreadingTCPServer)):daemon_threads=True

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["test","status","serve","request"])
    p.add_argument("payload",nargs="?")
    a=p.parse_args()
    if a.command=="test":
        device='    DisplayDeviceInfo{"CodakiPortableUse": uniqueId="virtual:android,0,CodakiPortableUse,0", FLAG_TRUSTED, FLAG_OWN_FOCUS, FLAG_OWN_DISPLAY_GROUP, FLAG_ALWAYS_UNLOCKED, FLAG_STEAL_TOP_FOCUS_DISABLED, FLAG_DESTROY_CONTENT_ON_REMOVAL}\n'
        base='  Display 0:\n    mBaseDisplayInfo=DisplayInfo{"Screen", type INTERNAL}\n  Display 6:\n    mPrimaryDisplayDevice=CodakiPortableUse(virtual:android,0,CodakiPortableUse,0)\n    mBaseDisplayInfo=DisplayInfo{"CodakiPortableUse", FLAG_TRUSTED, FLAG_OWN_DISPLAY_GROUP, type VIRTUAL}\n'
        good=device+base
        assert find_display(good)==6
        for bad in (good.replace("FLAG_TRUSTED",""),
                    good.replace("FLAG_OWN_FOCUS","FLAG_NOT_OWN_FOCUS"),
                    good.replace("FLAG_DESTROY_CONTENT_ON_REMOVAL",""),
                    good.replace("CodakiPortableUse","MagicDesk"),
                    good.replace("Display 6:","Display 0:")):
            try:find_display(bad);raise AssertionError("Unsafe virtual display accepted")
            except Denied:pass
        for bad in ({"key":"POWER"},{"key":"HOME"},{"x":-1,"y":2}):
            try:op("android_key" if "key" in bad else "android_tap",bad);raise AssertionError("Unsafe command accepted")
            except Denied:pass
        assert len(rpc({"jsonrpc":"2.0","id":2,"method":"tools/list"})["result"]["tools"])==14
        print("PASS: isolated display identity, focus flags and API validation",flush=True)
        return
    if a.command=="status":
        try:print(json.dumps(op("android_status",{})))
        except Denied as e:print(json.dumps({"ok":False,"error":str(e)}))
        return
    if a.command=="request":
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.connect(str(SOCK));s.sendall(((a.payload or '{"jsonrpc":"2.0","id":1,"method":"tools/list"}')+"\n").encode())
            with s.makefile("rb") as stream:
                print(stream.readline(6000000).decode());return
    HOME.mkdir(parents=True,exist_ok=True)
    if SOCK.exists():
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
                probe.settimeout(1.0)
                probe.connect(str(SOCK))
                probe.sendall(b'{"jsonrpc":"2.0","id":9,"method":"ping"}\n')
                if b'"result"' in probe.recv(1024):
                    print("Android Use Core already running",flush=True)
                    return
        except (OSError,ValueError):
            pass
        SOCK.unlink()
    with Server(str(SOCK),Handler) as server:
        SOCK.chmod(0o600)
        server.serve_forever()

if __name__=="__main__":main()
