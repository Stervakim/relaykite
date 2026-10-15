"""Keep public relay/PC schemas identical to the phone's typed registry."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
from managed_tools import definitions
from development_tools import definition as development_definition

def main():
    paths=[ROOT/'agent/tool-definitions.json',ROOT/'relay/lib/phone-tools.json',ROOT/'pc/phone-tools.json']
    additions=definitions()+[development_definition()];names={d['name'] for d in additions}
    old=json.loads(paths[0].read_text(encoding='utf-8'))
    merged=[d for d in old if d['name'] not in names]+additions
    for path in paths:path.write_text(json.dumps(merged,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Synchronized '+str(len(merged))+' owner-bound phone tools')

if __name__=='__main__':main()
