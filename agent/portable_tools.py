"""Typed phone-tool adapter over the existing Portable engine; never replays input."""
import copy,json,re
from portable_peer import OPERATIONS

def _images(value,blocks):
    if isinstance(value,dict):
        image=value.pop('screenshot',None)
        if image:
            if not isinstance(image,dict) or image.get('mime_type') not in ('image/png','image/jpeg') or not isinstance(image.get('base64'),str):
                value['screenshot_warning']='Invalid screenshot omitted; original operation receipt preserved'
            else:blocks.append({'type':'image','data':image['base64'],'mimeType':image['mime_type']})
        for item in value.values():_images(item,blocks)
    elif isinstance(value,list):
        for item in value:_images(item,blocks)

def invoke(operation,arguments):
    if operation not in OPERATIONS:raise ValueError('Unknown Portable operation')
    args=copy.deepcopy(arguments);request_id=args.pop('request_id',None)
    if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',request_id):raise ValueError('Invalid stable Portable request_id')
    if 'target_request_id' in args:args['request_id']=args.pop('target_request_id')
    from portable_peer import call
    try:result=call(operation,args,request_id)
    except FileNotFoundError:result={'error':'Existing Portable engine is unavailable; do not start a second engine or replay input','code':'IPC_UNAVAILABLE'}
    except (OSError,ValueError):result={'error':'Portable transport failed; inspect result/diagnostics with the original request identity before new input','code':'IPC_FAILED'}
    receipt=copy.deepcopy(result);images=[];_images(receipt,images)
    if len(images)>1:images=images[-1:] # Last observation is the current UI evidence.
    return {'content':[{'type':'text','text':json.dumps(receipt,ensure_ascii=False)},*images],
            'structuredContent':receipt,'isError':bool(receipt.get('error') or receipt.get('status')=='stopped')}

def wrapper(operation):
    def tool(**arguments):return invoke(operation,arguments)
    tool.__name__='phone_use_'+operation
    return tool
