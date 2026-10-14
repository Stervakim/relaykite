"""Relocate AArch64/Bionic ELF RUNPATH strings without changing code bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def relocate_bytes(raw,new_runpath):
    if len(raw)<64 or raw[:7]!=b'\x7fELF\x02\x01\x01':raise ValueError('Expected little-endian ELF64')
    header=struct.unpack_from('<HHIQQQIHHHHHH',raw,16)
    if header[1]!=183:raise ValueError('Expected Android AArch64 ELF')
    phoff,phsize,count=header[4],header[8],header[9]
    if count==0 and header[0]==1:return raw,False  # ET_REL compiler support object.
    if phsize!=56 or count>128 or phoff+count*phsize>len(raw):raise ValueError('Invalid ELF program table')
    segments=[struct.unpack_from('<IIQQQQQQ',raw,phoff+i*phsize) for i in range(count)]
    loads=[p for p in segments if p[0]==1];dynamic=[p for p in segments if p[0]==2]
    if not dynamic:return raw,False
    strings=None;size=None;paths=[]
    for segment in dynamic:
        offset,length=segment[2],segment[5]
        if offset+length>len(raw) or length%16:raise ValueError('Invalid dynamic table')
        for pos in range(offset,offset+length,16):
            tag,value=struct.unpack_from('<qQ',raw,pos)
            if tag==0:break
            if tag==5:strings=value
            if tag==10:size=value
            if tag in (15,29):paths.append(value)
    if not paths:return raw,False
    if strings is None or size is None:raise ValueError('Missing dynamic string table')
    segment=next((p for p in loads if p[3]<=strings and strings+size<=p[3]+p[5]),None)
    if segment is None:raise ValueError('Unmapped dynamic strings')
    start=segment[2]+strings-segment[3]
    if start+size>len(raw):raise ValueError('Strings exceed file')
    encoded=new_runpath.encode('ascii')
    if not encoded or b'\0' in encoded:raise ValueError('Invalid RUNPATH')
    out=bytearray(raw);changed=False
    for relative in paths:
        if relative>=size:raise ValueError('RUNPATH exceeds string table')
        pos=start+relative;end=raw.find(b'\0',pos,start+size)
        if end<0 or len(encoded)>end-pos:raise ValueError('New RUNPATH exceeds original allocation')
        if raw[pos:end]!=encoded:
            out[pos:end+1]=encoded+b'\0'*(end-pos+1-len(encoded));changed=True
    return bytes(out),changed

def relocate_directory(directory):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    changed=[];pending=[]
    for name,entry in manifest['files'].items():
        path=directory/name
        if path.is_symlink() or not path.is_file():raise ValueError('Nonregular runtime input')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Runtime input checksum mismatch')
        if raw[:4]!=b'\x7fELF':continue
        if name.startswith('bin/'):runpath='$ORIGIN/../lib'
        elif '/lib-dynload/' in name:runpath='$ORIGIN/../..'
        else:runpath='$ORIGIN'
        relocated,different=relocate_bytes(raw,runpath)
        if different:
            pending.append((path,relocated))
            entry['source_sha256']=entry['sha256'];entry['sha256']=hashlib.sha256(relocated).hexdigest();entry['elf_runpath']=runpath
            changed.append(name)
    # Validate every ELF/input before touching any file in this staging tree.
    for path,relocated in pending:path.write_bytes(relocated)
    manifest['relocation']={'mutation':'ELF DT_RUNPATH/DT_RPATH strings only','changed_files':changed}
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    return changed

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    print(json.dumps({'relocated':len(relocate_directory(args.directory))}))
