"""Build a portable ChatGPT card; installation never pairs a computer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

FILES=('plugin.json','.app.json','README.md','assets/icon.png',
       'skills/setup/SKILL.md','skills/pc-control/SKILL.md','skills/update/SKILL.md','skills/remove/SKILL.md','skills/using-codaki-pc-use/SKILL.md','skills/using-codaki-memory/SKILL.md')

def build_card(root, output, app_id=None):
    root=Path(root).resolve()
    source=root/'chatgpt'/'plugin'
    manifest=json.loads((source/'plugin.json').read_text(encoding='utf-8'))
    if app_id is not None and not re.fullmatch(r'(?:asdk_app_|connector_|templated_apps_)[A-Za-z0-9_-]+',app_id):
        raise ValueError('Use a registered App ID, not a plugin ID, URL or credential')
    mapping={'apps':{}}
    if app_id:
        mapping['apps'][manifest['name']]={'id':app_id,'required':True}
    entries={}
    for name in FILES:
        path=source/name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError('Card inputs must be regular files inside the template')
        raw=path.read_bytes()
        entries[name]=raw if name.endswith('.png') else raw.replace(b'\r\n',b'\n')
    license_path=root/'LICENSE'
    if license_path.is_symlink() or not license_path.is_file():
        raise ValueError('Missing regular LICENSE file')
    entries['LICENSE']=license_path.read_bytes().replace(b'\r\n',b'\n')
    entries['.app.json']=(json.dumps(mapping,indent=2)+'\n').encode('utf-8')
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    target=output/(manifest['name']+'-chatgpt-'+manifest['version']+'.zip')
    # Store card entries verbatim: zlib versions can produce different compressed bytes.
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as archive:
        for name,data in sorted(entries.items()):
            info=zipfile.ZipInfo(name,(2026,10,10,0,0,0))
            info.create_system=3
            info.external_attr=0o100644<<16
            info.compress_type=zipfile.ZIP_STORED
            archive.writestr(info,data)
    return target

def previous_app_id(previous_card, expected_name):
    """Read only the previous card's identity and App mapping, never its instructions."""
    with zipfile.ZipFile(previous_card) as archive:
        for name in ('plugin.json','.app.json'):
            members=[item for item in archive.infolist() if item.filename==name]
            if len(members)!=1 or members[0].file_size>64*1024:
                raise ValueError('Previous card must contain one bounded root '+name)
        manifest=json.loads(archive.read('plugin.json'))
        if manifest.get('name')!=expected_name:
            raise ValueError('Previous card belongs to a different plugin')
        apps=json.loads(archive.read('.app.json')).get('apps')
        if apps=={}:return None
        if not isinstance(apps,dict) or set(apps)!={expected_name}:
            raise ValueError("Previous card must reference only this plugin's App")
        entry=apps[expected_name]
        if not isinstance(entry,dict) or entry.get('required') is not True:
            raise ValueError('Previous card must require its App')
        value=entry.get('id')
        if not isinstance(value,str) or not re.fullmatch(r'(?:asdk_app_|connector_|templated_apps_)[A-Za-z0-9_-]+',value):
            raise ValueError('Invalid previous App ID')
        return value

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    connection=parser.add_mutually_exclusive_group()
    connection.add_argument('--previous-card',type=Path,help='Retain the App reference from a verified previous card')
    connection.add_argument('--app-id',help="App ID returned by the owner's private Sites deployment")
    parser.add_argument('--output',type=Path,help='Output directory; bound cards default to ignored .private/chatgpt')
    args=parser.parse_args()
    if args.previous_card:
        expected=json.loads((root/'chatgpt/plugin/plugin.json').read_text(encoding='utf-8'))['name']
        args.app_id=previous_app_id(args.previous_card,expected)
    output=args.output or (root/'.private'/'chatgpt' if args.app_id else root/'chatgpt')
    if args.app_id and output.resolve().is_relative_to(root) and not output.resolve().is_relative_to(root/'.private'):
        parser.error('Bound cards must be stored outside the repository or under .private/')
    target=build_card(root,output,args.app_id)
    (output/(target.name+'.sha256')).write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n',encoding='ascii')
    print(target)
