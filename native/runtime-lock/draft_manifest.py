"""Draft a hash inventory for a private runtime; notice mappings remain empty."""
import argparse
import json
from pathlib import Path
from verify_runtime import files_under, no_links, read_json, sha256


def draft(runtime, archive, lock):
    _,paths=files_under(Path(runtime))
    archive=Path(archive)
    if not archive.is_absolute() or archive.name!='python-3.12.10-embed-amd64.zip':raise ValueError('Provide the absolute path to python-3.12.10-embed-amd64.zip.')
    no_links(archive)
    if not archive.is_file():raise ValueError('The Python archive must be a regular file.')
    if lock.get('format')!='mbdyn-python-wheel-lock/1' or not isinstance(lock.get('packages'),dict) or not isinstance(lock.get('pythonArtifact'),dict):raise ValueError('The runtime lock is invalid.')
    if archive.name!=lock['pythonArtifact'].get('filename') or sha256(archive)!=lock['pythonArtifact'].get('sha256'):raise ValueError('The Python embedded archive does not match its pinned hash.')
    files={name:sha256(path) for name,path in sorted(paths.values()) if name.casefold()!='runtime-manifest.json'}
    binaries=[name for name in files if name.lower().endswith(('.dll','.pyd','.exe'))]
    return {'format':'mbdyn-python-runtime/1','target':'windows-x86_64-cpython-312',
            'pythonArtifact':{'filename':archive.name,'sha256':sha256(archive),'source':'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'},
            'wheels':{name:{'filename':item['filename'],'sha256':item['sha256']} for name,item in lock['packages'].items()},
            'files':files,'notices':{name:[] for name in ['python',*lock['packages']]},'nativeNotices':{name:[] for name in binaries}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',required=True);parser.add_argument('--python-archive',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    output=Path(args.output)
    if output.exists():parser.exit(1,'Refusing to overwrite an existing manifest; choose another output path.\n')
    try:
        data=draft(args.runtime,args.python_archive,read_json(Path(__file__).with_name('windows-cp312.json')))
        with output.open('x',encoding='utf8') as stream:json.dump(data,stream,indent=2,sort_keys=True);stream.write('\n')
        print('Draft created. Empty notice mappings must be completed and reviewed; this is not a redistribution approval.')
    except (OSError,ValueError,KeyError,TypeError) as exc:parser.exit(1,f'Cannot draft runtime manifest: {exc}\n')

if __name__=='__main__':main()

