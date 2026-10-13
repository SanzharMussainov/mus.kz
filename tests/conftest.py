import os
os.environ['SECRET_KEY']='test-secret-only-not-for-production-0123456789'
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.db import Base, get_db, now
from app.models import *
from app.security import hash_password
from app.main import app
from datetime import timedelta
import uuid
from sqlalchemy import text


@pytest.fixture
def db():
    pg=os.getenv('TEST_DATABASE_URL')
    schema='test_'+uuid.uuid4().hex
    if pg:
        base_engine=create_engine(pg)
        with base_engine.begin() as conn:
            conn.execute(text('CREATE SCHEMA '+schema))
        engine=base_engine.execution_options(schema_translate_map={None:schema})
    else:
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(engine,expire_on_commit=False)() as session:
        yield session
    if pg:
        with base_engine.begin() as conn:
            conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
    engine.dispose()


@pytest.fixture
def data(db):
    users=[User(name=name,email=f'{name}@example.test',password_hash=hash_password('Testing-12345'),role=role) for name,role in [('admin','admin'),('alice','student'),('bob','student')]]
    db.add_all(users); db.add(Settings(id=1)); db.flush()
    c=Course(title='Math',direction='School',grade=7,level='Base');db.add(c);db.flush()
    groups=[Group(title='G1',course_id=c.id),Group(title='G2',course_id=c.id)];db.add_all(groups);db.flush()
    db.add_all([Membership(group_id=groups[0].id,user_id=users[1].id),Membership(group_id=groups[1].id,user_id=users[2].id)])
    task=Task(title='Fraction',prompt='Find value',kind='fraction',answer='2/3',solution='SECRET_SOLUTION_742',status='ready');db.add(task);db.flush()
    template=HomeworkTemplate(title='Reusable',task_ids=str(task.id));db.add(template);db.flush()
    db.commit()
    return dict(admin=users[0],alice=users[1],bob=users[2],course=c,g1=groups[0],g2=groups[1],task=task,template=template)


@pytest.fixture
def client(db,tmp_path,monkeypatch):
    monkeypatch.setenv('STORAGE_DIR',str(tmp_path))
    def override(): yield db
    app.dependency_overrides[get_db]=override
    with TestClient(app) as client: yield client
    app.dependency_overrides.clear()


def token(client,path='/login'):
    import re
    response=client.get(path)
    match=re.search(r'name="csrf" value="([^"]+)"',response.text)
    assert match, response.text
    return match.group(1)


def login(client,name):
    response=client.post('/login',data={'csrf':token(client),'email':name+'@example.test','password':'Testing-12345'})
    assert response.status_code==200, response.text


def assignment(db,data,group=None,**kw):
    from app.services import publish
    values=dict(group_id=(group or data['g1']).id,template_id=data['template'].id,title='Work',opens_at=now()-timedelta(days=1),deadline=now()+timedelta(days=1),solutions_at=now()+timedelta(days=2),max_attempts=2,allow_late=False)
    values.update(kw); a=Assignment(**values);publish(db,a);db.add(a);db.commit();return a
