"""Mini PC client for the existing owner's Portable loopback RPC."""
import copy,json,os,re,urllib.request,urllib.parse
from pathlib import Path

DEFINITIONS=json.loads((Path(__file__).parent/'portable-tools.json').read_text(encoding='utf-8'))
OPERATIONS={x['name'].removeprefix('pc_use_') for x in DEFINITIONS}
LIMIT=4*1024*1024

def endpoint_path():return Path(os.environ.get('LOCALAPPDATA',''))/'CodakiPortableUseIPC'/'endpoint.json'

def validate(schema,value):
    kind=schema.get('type')
    if kind=='object':
        if not isinstance(value,dict):raise ValueError('Expected object')
        if any(k not in value for k in schema.get('required',[])):raise ValueError('Missing argument')
        for k,v in value.items():
            if k not in schema.get('properties',{}):
                if schema.get('additionalProperties') is False:raise ValueError('Unknown argument')
            else:validate(schema['properties'][k],v)
    elif kind=='string':
        if not isinstance(value,str) or '\0' in value or not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',100000):raise ValueError('Invalid string')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'],value):raise ValueError('Invalid request identity')
    elif kind=='integer':
        if type(value)!=int or not schema.get('minimum',-2147483648)<=value<=schema.get('maximum',2147483647):raise ValueError('Invalid integer')
    elif kind=='boolean' and type(value)!=bool:raise ValueError('Expected boolean')
    elif kind=='array':
        if not isinstance(value,list) or not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',10000):raise ValueError('Invalid array')
        for item in value:validate(schema['items'],item)
    if 'enum' in schema and value not in schema['enum']:raise ValueError('Invalid choice')

def descriptor():
    if not os.environ.get('LOCALAPPDATA'):raise FileNotFoundError('Windows Portable endpoint unavailable')
    path=endpoint_path()
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('Unsafe endpoint path')
    if path.stat().st_nlink!=1:raise ValueError('Unsafe endpoint file')
    with path.open('rb') as stream:raw=stream.read(4097)
    if len(raw)>4096:raise ValueError('Invalid endpoint descriptor')
    desc=json.loads(raw);url=urllib.parse.urlsplit(desc.get('url',''))
    if desc.get('version')!=1 or url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port or url.username or url.password or url.query or url.fragment or url.path!='/rpc':raise ValueError('Endpoint must be owner-local loopback RPC')
    if not isinstance(desc.get('token'),str) or not re.fullmatch(r'[a-f0-9]{64}',desc['token']):raise ValueError('Invalid local RPC credential')
    return desc

def status(capabilities=()):
    try:descriptor();configured=True
    except (OSError,ValueError):configured=False
    granted='terminal' in capabilities
    return {'configured':configured,'available':configured and granted,'grant_enabled':granted,'backend':'existing Portable Windows engine','capability':'terminal','operations':['pc_use_'+op for op in sorted(OPERATIONS)] if configured and granted else [],'desktop_isolation':False,'verify_with':'pc_use_capabilities'}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def request(payload):
    desc=descriptor();raw=json.dumps(payload,ensure_ascii=False).encode()
    if len(raw)>1024*1024:raise ValueError('Portable request too large')
    req=urllib.request.Request(desc['url'],data=raw,headers={'Authorization':'Bearer '+desc['token'],'Content-Type':'application/json'})
    # Environment proxy settings must never forward this private local secret.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(req,timeout=65) as response:data=response.read(LIMIT+1)
    if len(data)>LIMIT:raise OSError('Portable response exceeded limit')
    value=json.loads(data)
    if not isinstance(value,dict):raise OSError('Malformed Portable receipt')
    return value

def envelope(value):
    receipt=copy.deepcopy(value);images=[]
    def extract(item):
        if isinstance(item,dict):
            image=item.pop('screenshot',None)
            if image:
                if isinstance(image,dict) and image.get('mime_type') in ('image/png','image/jpeg') and isinstance(image.get('base64'),str):images.append({'type':'image','data':image['base64'],'mimeType':image['mime_type']})
                else:item['screenshot_warning']='Invalid screenshot omitted; original receipt preserved'
            for child in item.values():extract(child)
        elif isinstance(item,list):
            for child in item:extract(child)
    extract(receipt)
    def build():return {'content':[{'type':'text','text':json.dumps(receipt,ensure_ascii=False)},*images[-1:]],'structuredContent':receipt,'isError':bool(receipt.get('error') or receipt.get('status')=='stopped')}
    out=build()
    if len(json.dumps(out,ensure_ascii=False).encode())>LIMIT:
        images.clear();receipt['transport_warning']='Screenshot omitted to fit the PC relay limit; operation receipt retained. Observe again instead of replaying input.';out=build()
    if len(json.dumps(out,ensure_ascii=False).encode())>LIMIT:
        receipt={k:receipt[k] for k in ('applied','status','completed','total','stopped_at','code','request_id','session_id') if k in receipt}
        receipt.update(error='Original receipt exceeds PC relay limit; inspect the engine journal without replay',transport_warning='Detailed payload omitted',original_code=receipt.get('code'),code='RESULT_TOO_LARGE');out=build()
    return out

def invoke(operation,arguments,scope):
    if operation not in OPERATIONS:raise ValueError('Unknown Portable operation')
    if not isinstance(scope,str) or not re.fullmatch(r'[a-f0-9-]{36}',scope):raise ValueError('Paired Mini connection scope required')
    schema=next(x['inputSchema'] for x in DEFINITIONS if x['name']=='pc_use_'+operation)
    validate(schema,arguments);args=copy.deepcopy(arguments);rid=args.pop('request_id')
    if 'target_request_id' in args:args['request_id']=args.pop('target_request_id')
    try:value=request({'scope':scope,'op':operation,'args':args,'request_id':rid})
    except FileNotFoundError:value={'error':'Existing Portable local RPC is unavailable; no second engine started','code':'IPC_UNAVAILABLE','executed':False,'request_id':rid}
    except (OSError,ValueError):value={'error':'Portable transport outcome unavailable; inspect the original receipt without replay','code':'IPC_FAILED','request_id':rid}
    return envelope(value)
