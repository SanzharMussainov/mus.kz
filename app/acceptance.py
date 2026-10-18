"""Disposable acceptance data and restore comparison; never a production seed."""
import argparse
import base64
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
from io import BytesIO
from sqlalchemy import select, func
from .db import Base, Session, now
from .models import User, Settings, File, Attendance, Meeting, MessageTemplate
from .reports import weekly_report, ZONE
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
            if table.name!='message_templates' and db.scalar(select(func.count()).select_from(table)):
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
        meeting = create('meetings', {'title':'TEST ONLY - Lesson','group_id':group,'audience':'all','starts_at':(now()-timedelta(hours=2)).isoformat(),'duration':'90','payment_mode':'subscription','planned_topics':'Пропорции и проценты'})
        post('/billing/payment', {'user_id':student,'minutes':'480','amount':'0','reason':'TEST ONLY - not a real payment'})
        post(f'/meetings/{meeting}/confirm', {'duration':'90',f'status_{student}':'present','reason':'TEST ONLY - attendance','action':'confirm','covered_topics':'Пропорции\nПроценты'})
        post(f'/meetings/{meeting}/confirm', {'duration':'90',f'status_{student}':'present','reason':'TEST ONLY - repeat confirmation','action':'confirm','covered_topics':'Пропорции\nПроценты'})
        with Session() as db:
            # Simulate one pre-existing attachment: updates must preserve old files.
            owner=db.scalar(select(User).where(User.email==EMAIL))
            file=File(owner_id=owner.id,meeting_id=meeting,name='legacy-control.png',path='legacy-control',mime='image/png',size=len(IMAGE))
            db.add(file);db.commit()
            storage=Path(os.getenv('STORAGE_DIR','storage'));storage.mkdir(parents=True,exist_ok=True)
            (storage/file.path).write_bytes(IMAGE)
        post('/logout')
        post('/login', {'email':EMAIL,'password':PASSWORD})
        report=client.get('/reports')
        if report.status_code!=200 or 'Пропорции' not in report.text:
            # Near a Monday boundary the lesson may be in the previous week.
            with Session() as db:
                date=db.get(Meeting,meeting).starts_at.astimezone(ZONE).date().isoformat()
            report=client.get('/reports?week='+date)
            if report.status_code!=200 or 'Пропорции' not in report.text:
                raise RuntimeError('Student weekly report missing covered topics.')
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
        meeting=db.scalar(select(Meeting).where(Meeting.status=='held'))
        report=weekly_report(db,user.id,meeting.starts_at.astimezone(ZONE).date().isoformat())
        minutes = balance(db,user.id)
        if minutes!=390 or report['attended']!=1 or report['topics']!=['Пропорции','Проценты'] or len(files)!=1:
            raise RuntimeError('Unexpected acceptance result: balance, weekly report or legacy files differ.')
        canonical = json.dumps(rows, default=lambda value:value.isoformat(), ensure_ascii=False, sort_keys=True, separators=(',',':')).encode('utf-8')
        return {'balance_minutes':minutes,'report':{'topics':report['topics'],'attended':report['attended'],'minutes':report['minutes']},'files':files,'table_counts':counts,'database_sha256':hashlib.sha256(canonical).hexdigest()}


def check_download():
    from fastapi.testclient import TestClient
    from .main import app
    with Session() as db:
        file_id = db.scalar(select(File.id))
        student_id = db.scalar(select(User.id).where(User.email==EMAIL))
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
