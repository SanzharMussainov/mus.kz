"""Rehearse PostgreSQL 16 backup/restore in two new, isolated installations."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request
import uuid
from compose_tools import Compose
from backup import create_backup
from restore import restore_backup


def wait_http(port):
    deadline = time.monotonic()+90
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=3) as response:
                if response.status==200:
                    return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f'Web server did not become ready on port {port}.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-port',type=int,default=18000)
    parser.add_argument('--restore-port',type=int,default=18001)
    args=parser.parse_args()
    if args.source_port==args.restore_port:
        raise ValueError('Source and restore ports must differ.')
    run_id='muscheck-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')+'-'+uuid.uuid4().hex[:6]
    source_name=run_id+'-source';target_name=run_id+'-restore'
    source=Compose(source_name,args.source_port);target=Compose(target_name,args.restore_port)
    report_dir=Path('backups')/run_id;report_dir.mkdir(parents=True)
    report={'source_project':source_name,'restore_project':target_name,'source_port':args.source_port,'restore_port':args.restore_port,'status':'running'}
    def save():
        (report_dir/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    save()
    try:
        print('Building source installation: '+source_name,flush=True)
        source.run('up','-d','--build','--wait','--wait-timeout','120')
        wait_http(args.source_port)
        version=source.run('exec','-T','db','psql','-U','math','-d','math','-Atc','SHOW server_version',capture_output=True,text=True).stdout.strip()
        if not version.startswith('16.'):
            raise RuntimeError('Expected PostgreSQL 16, got '+version)
        report['postgres_version']=version
        print('Running full teacher/student workflow.',flush=True)
        result=source.run('exec','-T','-e','ALLOW_ACCEPTANCE_FIXTURE=1','web','python','-m','app.acceptance','create',capture_output=True,text=True)
        baseline=json.loads(result.stdout.strip())
        print('Creating consistent database and file backup.',flush=True)
        backup=create_backup(source,report_dir);report['backup']=str(backup)
        print('Restoring to an empty, separate installation: '+target_name,flush=True)
        target.run('build','web')
        target.run('up','-d','db','--wait','--wait-timeout','120')
        restore_backup(target,backup)
        wait_http(args.restore_port)
        result=target.run('exec','-T','web','python','-m','app.acceptance','verify',capture_output=True,text=True)
        restored=json.loads(result.stdout.strip())
        if restored!=baseline:
            raise RuntimeError('Restored database or attachments do not match the original.')
        report.update(status='passed',comparison=restored)
        print('PASS: balance 390 minutes, 5 correct answers, attachment bytes, all table fingerprints and authenticated download match.',flush=True)
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__)
        raise
    finally:
        save()
        # Keep volumes and backup for inspection; do not remove data.
        for compose in (source,target):
            try:
                compose.run('stop')
            except Exception:
                pass
        print('Report: '+str(report_dir/'verification.json'),flush=True)


if __name__=='__main__':
    main()
