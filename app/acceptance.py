"""Disposable acceptance data and restore comparison; never a production seed."""
import argparse
import base64
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
from sqlalchemy import select, func
from .db import Base, Session, now
from .models import User, Settings, File, Attempt, Ledger, Course, Assignment, Meeting
from .security import hash_password
from .services import balance

EMAIL = 'restore-student@example.test'
PASSWORD = 'Acceptance-only-2026'
IMAGE = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=')


def create_fixture():
    if os.getenv('ALLOW_ACCEPTANCE_FIXTURE') != '1':
        raise RuntimeError('Set ALLOW_ACCEPTANCE_FIXTURE=1 only for a disposable installation.')
    with Session() as db:
        for table in Base.metadata.sorted_tables:
            if db.scalar(select(func.count()).select_from(table)):
                raise RuntimeError('Acceptance fixture requires an entirely empty application database.')
        db.add(User(name='TEST ONLY - Teacher', email='restore-teacher@example.test', role='admin', password_hash=hash_password(PASSWORD)))
        db.add(Settings(id=1))
        db.commit()
    from fastapi.testclient import TestClient
    from .main import app
    with TestClient(app) as client:
        def csrf(path='/dashboard'):
            response = client.get(path)
            match = re.search(r'name="csrf" value="([^"]+)"', response.text)
            if not match:
                raise RuntimeError('CSRF form not found: '+path)
            return match[1]

        def post(path, data=None, **kwargs):
            response = client.post(path, data={'csrf':csrf('/login' if path=='/login' else '/dashboard'), **(data or {})}, **kwargs)
            if response.status_code != 200:
                raise RuntimeError(f'Acceptance HTTP {response.status_code}: {path}')
            return response

        def create(section, data):
            return int(post(f'/admin/{section}/new', data).url.path.rsplit('/',1)[-1])

        post('/login', {'email':'restore-teacher@example.test','password':PASSWORD})
        course = create('courses', {'title':'TEST ONLY - Fractions','description':'Backup acceptance fixture','direction':'School','grade':'7','level':'Base'})
        student = create('students', {'name':'TEST ONLY - Student','email':EMAIL,'password':PASSWORD,'active':'on'})
        group = create('groups', {'title':'TEST ONLY - Group','course_id':course,'schedule':'Test only','status':'active'})
        create('memberships', {'group_id':group,'user_id':student,'active':'on'})
        task_ids = []
        examples = [('fraction','2/3','','4/6'),('number','3.5','','3,5'),('set','-2;2','','2;-2'),('single','7','4\n7\n9','7'),('multiple','2;4','2\n3\n4','2;4')]
        for kind, answer, options, response in examples:
            task_ids.append(create('tasks', {'title':'TEST ONLY - '+kind,'prompt':'Control question','kind':kind,'answer':answer,'options':options,'tolerance':'0','solution':'Control solution','grade':'7','status':'ready'}))
        template = create('templates', {'title':'TEST ONLY - Homework','task_ids':','.join(map(str,task_ids))})
        assignment = create('assignments', {'title':'TEST ONLY - Issuance','group_id':group,'template_id':template,'opens_at':(now()-timedelta(days=1)).isoformat(),'deadline':(now()+timedelta(days=1)).isoformat(),'solutions_at':(now()+timedelta(days=2)).isoformat(),'max_attempts':'3','status':'published'})
        meeting = create('meetings', {'title':'TEST ONLY - Lesson','group_id':group,'audience':'all','starts_at':(now()-timedelta(hours=2)).isoformat(),'duration':'90','payment_mode':'subscription'})
        post('/billing/payment', {'user_id':student,'minutes':'480','amount':'0','reason':'TEST ONLY - not a real payment'})
        post('/logout')
        post('/login', {'email':EMAIL,'password':PASSWORD})
        for index, (_,_,_,response) in enumerate(examples):
            answers = response.split(';') if examples[index][0]=='multiple' else response
            post(f'/homework/{assignment}/answer/{index}', {'answer':answers})
        post('/files/upload', {'scope':'assignment','target':assignment}, files={'file':('control.png', IMAGE, 'image/png')})
        post('/logout')
        post('/login', {'email':'restore-teacher@example.test','password':PASSWORD})
        post(f'/meetings/{meeting}/confirm', {'duration':'90',f'status_{student}':'present','reason':'TEST ONLY - attendance','action':'confirm'})
        post(f'/meetings/{meeting}/confirm', {'duration':'90',f'status_{student}':'present','reason':'TEST ONLY - repeat confirmation','action':'confirm'})
    return fingerprint()


def fingerprint():
    with Session() as db:
        user = db.scalar(select(User).where(User.email==EMAIL))
        if not user:
            raise RuntimeError('Acceptance student not found.')
        rows = {}
        counts = {}
        for table in Base.metadata.sorted_tables:
            records = [dict(row) for row in db.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
            rows[table.name] = records
            counts[table.name] = len(records)
        files = []
        for file in db.scalars(select(File).order_by(File.id)):
            path = Path(os.getenv('STORAGE_DIR','storage')) / file.path
            with path.open('rb') as stream:
                files.append({'id':file.id, 'size':path.stat().st_size, 'sha256':hashlib.file_digest(stream,'sha256').hexdigest()})
        attempts = [{'task':a.task_index,'answer':a.answer,'correct':a.correct} for a in db.scalars(select(Attempt).where(Attempt.user_id==user.id).order_by(Attempt.id))]
        minutes = balance(db,user.id)
        if minutes!=390 or len(attempts)!=5 or not all(a['correct'] for a in attempts) or len(files)!=1:
            raise RuntimeError('Unexpected acceptance result: balance, answers or files differ.')
        canonical = json.dumps(rows, default=lambda value:value.isoformat(), ensure_ascii=False, sort_keys=True, separators=(',',':')).encode('utf-8')
        return {'balance_minutes':minutes,'attempts':attempts,'files':files,'table_counts':counts,'database_sha256':hashlib.sha256(canonical).hexdigest()}


def check_download():
    from fastapi.testclient import TestClient
    from .main import app
    with Session() as db:
        file_id = db.scalar(select(File.id))
    with TestClient(app) as client:
        page = client.get('/login')
        token = re.search(r'name="csrf" value="([^"]+)"',page.text)[1]
        response = client.post('/login',data={'csrf':token,'email':EMAIL,'password':PASSWORD})
        if response.status_code!=200:
            raise RuntimeError('Restored student cannot log in.')
        response = client.get(f'/files/{file_id}')
        if response.status_code!=200 or response.content!=IMAGE:
            raise RuntimeError('Restored attachment download failed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['create','verify'])
    args = parser.parse_args()
    result = create_fixture() if args.action=='create' else fingerprint()
    check_download()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
