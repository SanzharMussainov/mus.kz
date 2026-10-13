"""Consistent Docker Compose database + files backup without shell redirects."""
import argparse
import datetime
import hashlib
import json
import subprocess
from pathlib import Path


def run(*args,**kw):
    return subprocess.run(['docker','compose',*args],check=True,**kw)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='backups')
    args=parser.parse_args()
    target=Path(args.output)/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target.mkdir(parents=True,exist_ok=False)
    # Freeze writes so DB metadata and file bytes represent the same point in time.
    run('stop','web')
    try:
        with (target/'database.dump').open('wb') as out:
            run('exec','-T','db','pg_dump','-U','math','-d','math','-Fc',stdout=out)
        with (target/'files.tar').open('wb') as out:
            run('run','--rm','--no-deps','-T','web','tar','-C','/data/files','-cf','-','.',stdout=out)
        manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()}
        (target/'sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    finally:
        run('start','web')
    print(f'Backup: {target.resolve()}')


if __name__=='__main__': main()
