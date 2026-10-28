"""Validate a supplied application-private Windows Python runtime without executing it.

Hashes establish file identity, not derivation from an archive, authenticity, security,
or complete redistribution compliance. The caller must separately review notices.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

FORMAT='mbdyn-python-runtime/1'
HASH=re.compile(r'^[0-9a-f]{64}$')
INVALID=re.compile(r'[<>:"\\|?*\x00-\x1f]')


def safe_name(name):
    if not isinstance(name,str) or not name or INVALID.search(name): raise ValueError('Runtime path contains unsafe characters.')
    parts=name.split('/')
    if any(not part or part in ('.','..') or part.endswith(('.',' ')) or re.fullmatch(r'(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part) for part in parts): raise ValueError(f'Unsafe runtime path: {name}')
    path=PurePosixPath(name)
    if path.is_absolute():raise ValueError(f'Runtime path must be relative: {name}')
    return name


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024): digest.update(block)
    return digest.hexdigest()


def no_links(path):
    # Windows junctions and reparse points are not safe to recursively package.
    info=path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):
        raise ValueError(f'Refusing a link or reparse point: {path}')


def files_under(root):
    if not root.is_absolute():raise ValueError('Runtime directory must be absolute.')
    no_links(root)
    root=root.resolve(strict=True)
    if not root.is_dir():raise ValueError('Runtime directory is not a directory.')
    paths={}
    def visit(directory):
        no_links(directory)
        for item in directory.iterdir():
            no_links(item)
            if item.is_dir():visit(item)
            elif item.is_file():
                relative=safe_name(item.relative_to(root).as_posix())
                key=relative.casefold()
                if key in paths:raise ValueError(f'Duplicate Windows runtime path: {relative}')
                paths[key]=(relative,item)
            else:raise ValueError(f'Refusing a non-file runtime entry: {item}')
    visit(root)
    return root,paths


def read_json(path):
    if path.stat().st_size>16*1024*1024:raise ValueError('Runtime metadata is too large.')
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:raise ValueError(f'Duplicate JSON key: {key}')
            out[key]=value
        return out
    with path.open(encoding='utf-8-sig') as stream:return json.load(stream,object_pairs_hook=pairs)


def validate(runtime, artifacts, lock):
    root,actual=files_under(Path(runtime))
    artifact_root=Path(artifacts)
    if not artifact_root.is_absolute():raise ValueError('Artifact directory must be absolute.')
    no_links(artifact_root)
    if not artifact_root.is_dir():raise ValueError('Artifact directory is not a directory.')
    metadata=actual.get('runtime-manifest.json')
    if metadata is None:raise ValueError('runtime-manifest.json is required.')
    manifest=read_json(metadata[1])
    if not isinstance(manifest,dict) or set(manifest)!={'format','target','pythonArtifact','wheels','files','notices','nativeNotices'} or manifest['format']!=FORMAT or manifest['target']!='windows-x86_64-cpython-312':raise ValueError('Unsupported runtime manifest or target.')
    if not isinstance(lock,dict) or lock.get('format')!='mbdyn-python-wheel-lock/1' or not isinstance(lock.get('packages'),dict):raise ValueError('Invalid pinned wheel lock.')
    expected_files=manifest['files']
    if not isinstance(expected_files,dict) or not expected_files:raise ValueError('Runtime file hashes are required.')
    declared={}
    for name,value in expected_files.items():
        safe_name(name);key=name.casefold()
        if key=='runtime-manifest.json' or key in declared or not isinstance(value,str) or not HASH.fullmatch(value):raise ValueError(f'Invalid or duplicate file hash: {name}')
        declared[key]=(name,value)
    if set(actual)-{'runtime-manifest.json'}!=set(declared):raise ValueError('Runtime file inventory does not exactly match the manifest.')
    for key,(name,want) in declared.items():
        if actual[key][0]!=name or sha256(actual[key][1])!=want:raise ValueError(f'Runtime file hash or spelling mismatch: {name}')
    for required in ('python.exe','python312.dll','python312.zip','python312._pth'):
        if required not in declared:raise ValueError(f'Required Python runtime file missing: {required}')
    pth=actual['python312._pth'][1].read_text(encoding='utf8')
    lines=[line.strip().lower().replace('\\','/') for line in pth.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    expected_paths={'python312.zip','.','lib/site-packages','../../backend'}
    if len(lines)!=len(expected_paths) or set(lines)!=expected_paths:raise ValueError('python312._pth must contain exactly python312.zip, ., Lib/site-packages and ../../backend; import site is forbidden to prevent user-site imports.')
    if any(name.casefold().startswith('lib/site-packages/') and name.casefold().endswith('.pth') and name.count('/')==2 for name,_ in declared.values()):raise ValueError('Unreviewed site-packages .pth files are not allowed.')
    if any(re.fullmatch(r'lib/site-packages/[^/]+\.dist-info/direct_url\.json', name, re.IGNORECASE) for name,_ in declared.values()):raise ValueError('Remove machine-specific direct_url.json metadata before packaging.')
    python=manifest['pythonArtifact']
    locked_python=lock.get('pythonArtifact')
    if not isinstance(locked_python,dict) or set(locked_python)!={'filename','sha256','source','sbom'} or not isinstance(locked_python['sha256'],str) or not HASH.fullmatch(locked_python['sha256']):raise ValueError('Python embedded archive lock is missing or invalid.')
    if not isinstance(python,dict) or set(python)!={'filename','sha256','source'} or python!={key:locked_python[key] for key in ('filename','sha256','source')}:raise ValueError('Python embedded archive does not match its pinned provenance and hash.')
    packages=lock['packages']; wheels=manifest['wheels']
    if not isinstance(wheels,dict) or set(wheels)!=set(packages):raise ValueError('Runtime must declare the exact pinned wheel closure.')
    checked=[(python['filename'],python['sha256'])]
    for name,item in packages.items():
        if not isinstance(item,dict) or set(('filename','sha256'))-set(item):raise ValueError(f'Invalid lock entry: {name}')
        if wheels[name]!={'filename':item['filename'],'sha256':item['sha256']}:raise ValueError(f'Wheel identity does not match lock: {name}')
        checked.append((item['filename'],item['sha256']))
    for filename,want in checked:
        safe_name(filename)
        if '/' in filename:raise ValueError('Artifact filenames cannot contain directories.')
        path=artifact_root/filename
        try:no_links(path)
        except FileNotFoundError:raise ValueError(f'Required runtime source artifact is missing: {filename}') from None
        if not path.is_file() or sha256(path)!=want:raise ValueError(f'Source artifact hash mismatch: {filename}')
    notices=manifest['notices']
    if not isinstance(notices,dict) or set(notices)!=set(packages)|{'python'}:raise ValueError('Supply notice file references for Python and every wheel component.')
    def check_notice_list(value):
        if not isinstance(value,list) or not value or any(not isinstance(item,str) for item in value):raise ValueError('Each component needs at least one notice file.')
        for name in value:
            safe_name(name);entry=actual.get(name.casefold())
            if entry is None or entry[0]!=name or name.casefold() not in declared or entry[1].stat().st_size==0:raise ValueError(f'Notice file is missing or empty: {name}')
    for paths in notices.values():check_notice_list(paths)
    native=manifest['nativeNotices']
    binaries={name for name,_ in declared.values() if name.lower().endswith(('.dll','.pyd','.exe'))}
    if not isinstance(native,dict) or set(native)!=binaries:raise ValueError('Map each packaged EXE, DLL and PYD to its applicable notice files.')
    for paths in native.values():check_notice_list(paths)
    return {'format':FORMAT,'root':str(root),'files':[name for name,_ in sorted(actual.values())], 'hashes':{name:(sha256(path) if name=='runtime-manifest.json' else declared[name.casefold()][1]) for name,path in actual.values()}, 'runtimeFileCount':len(actual),'wheelCount':len(wheels),'redistributionStatus':'not-established'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True);parser.add_argument('--artifacts',required=True);parser.add_argument('--lock',default=str(Path(__file__).with_name('windows-cp312.json')));args=parser.parse_args()
    try:print(json.dumps(validate(args.runtime,args.artifacts,read_json(Path(args.lock))),separators=(',',':')))
    except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError) as exc:
        parser.exit(1,f'Private runtime verification failed: {exc}\n')

if __name__=='__main__':main()
