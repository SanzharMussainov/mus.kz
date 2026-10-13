"""Restore into a NEW, empty Docker Compose project only."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def run(*args,**kw):
    return subprocess.run(['docker','compose',*args],check=True,**kw)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('backup')
    args=parser.parse_args();source=Path(args.backup)
    manifest=json.loads((source/'sha256.json').read_text(encoding='utf-8'))
    for name in ('database.dump','files.tar'):
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=manifest[name]: raise SystemExit('Checksum mismatch: '+name)
    run('stop','web')
    result=run('exec','-T','db','psql','-U','math','-d','math','-Atc',"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",capture_output=True,text=True)
    if result.stdout.strip()!='0': raise SystemExit('Отказ: база не пуста. Используйте новый проект Compose с новыми volumes.')
    check=run('run','--rm','--no-deps','-T','web','find','/data/files','-mindepth','1','-maxdepth','1',capture_output=True,text=True)
    if check.stdout.strip(): raise SystemExit('Отказ: файловое хранилище не пусто.')
    with (source/'database.dump').open('rb') as inp:
        run('exec','-T','db','pg_restore','-U','math','-d','math','--no-owner','--exit-on-error',stdin=inp)
    with (source/'files.tar').open('rb') as inp:
        run('run','--rm','--no-deps','-T','web','tar','-C','/data/files','-xf','-',stdin=inp)
    run('up','-d','web'); print('Восстановлено. Проверьте вход, баланс и скачивание учебного файла.')


if __name__=='__main__': main()
