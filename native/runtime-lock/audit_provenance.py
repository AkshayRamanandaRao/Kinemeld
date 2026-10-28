"""Compare staged Python and wheel payload bytes with pinned source archives, offline.

This is a byte-identity check, not an authenticity, license, or security review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile

from prepare_runtime import artifacts_for
from verify_runtime import files_under, read_json, safe_name, sha256

MAX_ARCHIVE_FILES = 20000
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024


def archive_digest(source, entry):
    digest=hashlib.sha256()
    with source.open(entry) as stream:
        while block:=stream.read(1024*1024):digest.update(block)
    return digest.hexdigest()


def audit(runtime, artifacts, lock):
    """Compare installed payloads; report generated metadata and unproven files separately."""
    root,actual=files_under(Path(runtime))
    python,wheels=artifacts_for(artifacts,lock)
    expected={};checked={};ignored=[]
    def add(source, entry, target, origin):
        safe_name(target);key=target.casefold()
        if key in expected:raise ValueError(f'Duplicate installed payload path: {target}')
        expected[key]=target
        item=actual.get(key)
        if item is None or item[0]!=target:raise ValueError(f'Installed payload missing or misnamed: {target}')
        digest=archive_digest(source,entry)
        if sha256(item[1])!=digest:raise ValueError(f'Installed payload differs from {origin}: {target}')
        checked[target]=origin
    def items(source):
        entries=source.infolist()
        if len(entries)>MAX_ARCHIVE_FILES or sum(entry.file_size for entry in entries)>MAX_ARCHIVE_BYTES:raise ValueError('Artifact archive exceeds audit limits.')
        seen=set()
        for entry in entries:
            name=entry.filename.rstrip('/')
            if not name:continue
            safe_name(name)
            if name.casefold() in seen:raise ValueError(f'Duplicate artifact path: {name}')
            seen.add(name.casefold())
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:raise ValueError(f'Unsupported artifact entry: {name}')
            if not entry.is_dir():yield entry
    with zipfile.ZipFile(python) as source:
        for entry in items(source):
            if entry.filename=='python312._pth':ignored.append('python312._pth: locally configured import paths');continue
            add(source,entry,entry.filename,python.name)
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as source:
            for entry in items(source):
                name=entry.filename
                if name.endswith('.dist-info/RECORD'):
                    ignored.append(f'{wheel.name}: installed RECORD is generated');continue
                parts=name.split('/')
                if len(parts)>1 and parts[0].endswith('.data'):
                    if parts[1] in ('scripts','headers'):
                        ignored.append(f'{wheel.name}: excluded {parts[1]} payload');continue
                    if parts[1] not in ('data','purelib','platlib') or len(parts)<3:raise ValueError(f'Unsupported wheel data path: {name}')
                    name='/'.join(parts[2:])
                add(source,entry,'Lib/site-packages/'+name,wheel.name)
    required={'python312.zip','.','lib/site-packages','../../backend'}
    pth=actual.get('python312._pth')
    if not pth:raise ValueError('Configured python312._pth is missing.')
    lines=[line.strip().lower().replace('\\','/') for line in pth[1].read_text(encoding='utf8').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if len(lines)!=len(required) or set(lines)!=required:raise ValueError('Configured python312._pth has unexpected entries.')
    unproven=sorted(name for key,(name,_) in actual.items() if key not in expected and key not in ('python312._pth','runtime-manifest.json'))
    if any(name.lower().endswith(('.exe','.dll','.pyd','.py','.pyc','.pyo','.zip','.pth')) for name in unproven):raise ValueError('Runtime contains executable or importable files not proven by locked artifacts.')
    if any(name.lower().endswith('.dist-info/direct_url.json') for name in unproven):raise ValueError('Runtime contains machine-specific direct_url.json metadata.')
    artifacts_for(artifacts,lock)
    return {'ok':True,'runtime':str(root),'matchedFiles':len(checked),'pythonArchive':python.name,'wheelCount':len(wheels),
            'unprovenFiles':unproven,'excludedOrGenerated':ignored,
            'scope':'Locked archive-to-runtime byte matches; not source build provenance, publisher authentication, license review, or security certification.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime',required=True);parser.add_argument('--artifacts',required=True)
    args=parser.parse_args()
    try:print(json.dumps(audit(args.runtime,args.artifacts,read_json(Path(__file__).with_name('windows-cp312.json'))),indent=2))
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as exc:parser.exit(1,f'Runtime provenance audit failed: {exc}\n')


if __name__=='__main__':main()
