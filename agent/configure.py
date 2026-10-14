"""Import each owner's relay credentials locally. No network traffic or secret output."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import urllib.parse

from runtime_paths import BASE,MODULE


def safe_path(path):
    """Reject links in every existing component before touching private storage."""
    path = Path(path).absolute()
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise ValueError('Symbolic links are not allowed in private storage')
    return path


def validate(values, base=BASE, module=MODULE):
    if not isinstance(values, dict):
        raise ValueError('Configuration must be a JSON object')
    allowed = {'relay_url','agent_token','sites_authorization','poll_seconds',
               'state_dir','memory_dir','disable_file','outbound_proxy'}
    if set(values)-allowed:
        raise ValueError('Unknown configuration fields')
    url = values.get('relay_url', '')
    if not isinstance(url,str) or len(url)>2048 or any(c.isspace() or ord(c)<32 for c in url):
        raise ValueError('Use a valid HTTPS relay URL')
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
        host = parsed.hostname
        if not host or parsed.scheme!='https' or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
        host.encode('idna')
        if host=='localhost' or '.' not in host or any(c in host for c in '\\"<>'):
            raise ValueError()
        try:
            address=ipaddress.ip_address(host)
        except ValueError:
            address=None
        if address is not None and not address.is_global:
            raise ValueError()
        if address is None and any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',part) for part in host.encode('idna').decode().split('.')):
            raise ValueError()
        if port is not None and not 1<=port<=65535:
            raise ValueError()
    except (ValueError,UnicodeError):
        raise ValueError('Use a valid public HTTPS relay URL without credentials, query or fragment') from None
    token=values.get('agent_token')
    bypass=values.get('sites_authorization','')
    if not isinstance(token,str) or not 40<=len(token)<=4096 or any(c.isspace() or ord(c)<32 for c in token):
        raise ValueError('Agent credential must contain 40–4096 non-whitespace characters')
    if not isinstance(bypass,str) or len(bypass)>4096 or any(ord(c)<32 for c in bypass):
        raise ValueError('Invalid optional Sites authorization credential')
    delay=values.get('poll_seconds',3)
    if isinstance(delay,bool) or not isinstance(delay,(int,float)) or not 1<=delay<=30:
        raise ValueError('Poll interval must be between 1 and 30 seconds')
    # Only a loopback HTTP proxy is permitted; never embed subscription URLs or
    # send relay credentials through an arbitrary public proxy.
    proxy=values.get('outbound_proxy','')
    if not isinstance(proxy,str):
        raise ValueError('Invalid local proxy URL')
    if proxy:
        if any(ord(c)<33 or c.isspace() for c in proxy):
            raise ValueError('Invalid local proxy URL')
        parsed_proxy=urllib.parse.urlsplit(proxy)
        try:
            proxy_port=parsed_proxy.port
            proxy_host=parsed_proxy.hostname
        except ValueError:
            raise ValueError('Invalid local proxy port') from None
        if (parsed_proxy.scheme!='http' or proxy_host not in ('127.0.0.1','::1')
                or proxy_port is None or not 1<=proxy_port<=65535
                or parsed_proxy.username or parsed_proxy.password or parsed_proxy.path
                or parsed_proxy.query or parsed_proxy.fragment):
            raise ValueError('Proxy must be a local HTTP listener with an explicit port')
    result={'relay_url':url.rstrip('/'),'agent_token':token,'sites_authorization':bypass,
            'outbound_proxy':proxy,
            'poll_seconds':delay,'state_dir':str(base/'state'),
            'memory_dir':str(base/'memory'),'disable_file':str(module/'disable')}
    for key in ('state_dir','memory_dir','disable_file'):
        if key in values and values[key]!=result[key]:
            raise ValueError('Runtime paths must use this installation’s private directories')
    return result


def inspect_storage(base):
    safe_path(base)
    if base.exists() and not base.is_dir():
        raise ValueError('Private storage is not a directory')
    for name in ('state','memory'):
        path=safe_path(base/name)
        if path.exists() and not path.is_dir():
            raise ValueError('Private runtime storage is not a directory')
    for name in ('config.json','enabled','agent.pid','startup.log'):
        path=safe_path(base/name)
        if path.exists() and not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
            raise ValueError('Private runtime file is not a regular file')
    for name in ('agent.lock','jobs.sqlite3','jobs.sqlite3-journal','agent.log',*(f'agent.log.{n}' for n in range(1,5))):
        path=safe_path(base/'state'/name)
        if path.exists() and not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
            raise ValueError('Private state file is not a regular file')


def read_config(path,base=BASE,module=MODULE):
    safe_path(path)
    if not path.is_file() or path.stat().st_size>32768:
        raise ValueError('Use a regular configuration file smaller than 32 KiB')
    return validate(json.loads(path.read_text(encoding='utf-8')),base,module)


def install_config(values, base=BASE, module=MODULE, confirm=input):
    base=Path(base)
    config=validate(values,base,module)
    inspect_storage(base)
    target=base/'config.json'
    if target.exists() and confirm('Replace existing relay configuration? Type REPLACE: ')!='REPLACE':
        raise ValueError('Configuration preserved; replacement cancelled')
    base.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(base,0o700)
    for name in ('state','memory'):
        (base/name).mkdir(mode=0o700,exist_ok=True)
        os.chmod(base/name,0o700)
    fd,temp=tempfile.mkstemp(prefix='.config-',dir=base)
    try:
        os.chmod(temp,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            json.dump(config,output,ensure_ascii=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp,target)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    # This private marker is created only after importing the owner's credentials.
    flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(base/'enabled',flags,0o600)
    os.close(fd)
    os.chmod(base/'enabled',0o600)


def interactive_values(prompt=input, hidden=getpass.getpass):
    return {'relay_url':prompt('Your private relay HTTPS URL: ').strip(),
            'agent_token':hidden('Your agent credential (hidden): '),
            'sites_authorization':hidden('Optional Sites bypass credential (hidden; Enter to skip): ')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import',dest='source',type=Path)
    parser.add_argument('--validate',action='store_true')
    args=parser.parse_args()
    if getattr(os,'geteuid',lambda:1)()!=0:
        parser.exit(1,'Run this local configuration command with Magisk root.\n')
    os.umask(0o077)
    try:
        inspect_storage(BASE)
        if args.validate:
            read_config(BASE/'config.json')
        else:
            values=read_config(args.source) if args.source else interactive_values()
            install_config(values)
            print('Own relay configuration imported. Reboot to start the agent. No secrets were printed.')
    except (ValueError,OSError,json.JSONDecodeError):
        parser.exit(1,'Configuration rejected or cancelled; check URL, credentials, private paths and replacement confirmation.\n')


if __name__=='__main__':
    main()
