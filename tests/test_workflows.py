from datetime import timedelta
from sqlalchemy import select,func
import pytest
from app.db import now
from app.models import *
from app.services import *
from conftest import assignment,login,token


def test_reuse_snapshot_schedule_and_attempts(db,data):
    a=assignment(db,data); b=assignment(db,data,group=data['g2'],opens_at=now()+timedelta(hours=1))
    data['task'].answer='9'; db.commit()
    assert a.snapshot[0]['answer']=='2/3'
    assert submit(db,a.id,data['alice'].id,0,'4/6').correct
    with pytest.raises(ValueError): submit(db,b.id,data['bob'].id,0,'4/6')
    assert submit(db,b.id,data['bob'].id,0,'2/3',now()+timedelta(hours=2)).correct
    assert submit(db,a.id,data['alice'].id,0,'1').number==2
    with pytest.raises(ValueError): submit(db,a.id,data['alice'].id,0,'2/3')
    assert len(db.scalars(select(Attempt).where(Attempt.assignment_id==b.id)).all())==1


def test_deadline_and_solution_close(db,data):
    a=assignment(db,data,deadline=now()-timedelta(hours=1))
    with pytest.raises(ValueError): submit(db,a.id,data['alice'].id,0,'2/3')
    a.allow_late=True
    assert submit(db,a.id,data['alice'].id,0,'2/3').late
    with pytest.raises(ValueError): submit(db,a.id,data['alice'].id,0,'2/3',a.solutions_at)
    a.status='hidden'
    assert not accessible(db,a,data['alice'].id)


def test_student_isolation_and_solutions(client,db,data):
    a=assignment(db,data); b=assignment(db,data,group=data['g2'])
    login(client,'alice')
    response=client.get(f'/homework/{a.id}')
    assert response.status_code==200
    assert 'SECRET_SOLUTION_742' not in response.text and 'Правильный ответ' not in response.text
    assert client.get(f'/homework/{b.id}').status_code==403
    assert client.get('/admin/students').status_code==403
    assert 'bob@example.test' not in client.get('/billing?student='+str(data['bob'].id)).text
    a.solutions_at=now()-timedelta(seconds=1);db.commit()
    assert 'SECRET_SOLUTION_742' in client.get(f'/homework/{a.id}').text


def event(db,**kw):
    values=dict(title='Event',starts_at=now()+timedelta(days=1),duration=90,is_event=True,audience='all',payment_mode='subscription')
    values.update(kw);m=Meeting(**values);db.add(m);db.commit();return m


def test_registration_cancel_rejoin_and_cutoff(db,data):
    m=event(db);uid=data['alice'].id
    register(db,m.id,uid);register(db,m.id,uid);db.flush()
    assert db.scalar(select(func.count()).select_from(Registration))==1
    register(db,m.id,uid,False);register(db,m.id,uid,True);db.flush()
    assert db.scalar(select(func.count()).select_from(RegistrationHistory))==3
    assert balance(db,uid)==0
    with pytest.raises(ValueError): register(db,m.id,uid,False,at=m.starts_at)
    m.audience='selected';m.audience_groups=str(data['g2'].id)
    with pytest.raises(ValueError): register(db,m.id,uid)


@pytest.mark.parametrize('status,charged',[('present',90),('absent',90),('warned',0),('trial',0),('cancelled',0)])
def test_attendance(db,data,status,charged):
    m=event(db,group_id=data['g1'].id,is_event=False,starts_at=now()-timedelta(hours=2));uid=data['alice'].id
    confirm_meeting(db,m.id,90,{uid:status});confirm_meeting(db,m.id,90,{uid:status})
    assert balance(db,uid)==-charged
    assert db.scalar(select(func.count()).select_from(Ledger))==(1 if charged else 0)


@pytest.mark.parametrize('mode',['free','separate'])
def test_non_subscription_no_charge(db,data,mode):
    m=event(db,payment_mode=mode);uid=data['alice'].id;register(db,m.id,uid)
    m.starts_at=now()-timedelta(hours=2);db.commit();confirm_meeting(db,m.id,90,{uid:'present'})
    assert balance(db,uid)==0


def test_refund_correction_and_reconfirmation(db,data):
    uid=data['alice'].id;m=event(db,group_id=data['g1'].id,is_event=False,starts_at=now()-timedelta(hours=2))
    payment(db,uid,480,20000,'Оплата');confirm_meeting(db,m.id,90,{uid:'present'})
    assert balance(db,uid)==390
    debit=db.scalar(select(Ledger).where(Ledger.kind=='charge'))
    refund(db,debit.id,30,'Частичный возврат');assert balance(db,uid)==420
    confirm_meeting(db,m.id,90,{uid:'present'});assert balance(db,uid)==420
    with pytest.raises(ValueError): refund(db,debit.id,61,'Слишком много')
    confirm_meeting(db,m.id,90,{uid:'warned'});assert balance(db,uid)==480
    confirm_meeting(db,m.id,90,{uid:'present'});assert balance(db,uid)==420
    confirm_meeting(db,m.id,90,{},cancelled=True);assert balance(db,uid)==480


def test_notice_payment_clears(db,data):
    uid=data['alice'].id;event(db,group_id=data['g1'].id,is_event=False,duration=60)
    payment(db,uid,30,0,'Начисление');assert payment_notice(db,uid)['balance']==30
    data['alice'].payment_requested=True;payment(db,uid,120,10000,'Оплата')
    assert payment_notice(db,uid) is None and not data['alice'].payment_requested


def test_all_pages_admin(client,db,data):
    assignment(db,data); m=event(db)
    login(client,'admin')
    from app.admin import SPECS
    for path in ['/','/dashboard','/courses','/homework','/results','/calendar','/billing','/profile',f'/meetings/{m.id}']:
        assert client.get(path).status_code==200,path
    for section in SPECS:
        assert client.get('/admin/'+section).status_code==200,section
        assert client.get('/admin/'+section+'/new').status_code==200,section


def test_create_course_group_student_via_ui(client,db,data):
    login(client,'admin');csrf=token(client,'/dashboard')
    for section,values in [('courses',{'title':'Course UI','description':'Desc','direction':'SAT','grade':'','level':'Base','public':'on'}),('students',{'name':'New student','email':'new@example.test','password':'Long-password-2026','active':'on'})]:
        response=client.post('/admin/'+section+'/new',data={'csrf':csrf,**values})
        assert response.status_code==200,response.text
    course=db.scalar(select(Course).where(Course.title=='Course UI'))
    response=client.post('/admin/groups/new',data={'csrf':csrf,'title':'New group','course_id':course.id,'status':'active','schedule':'Tue 18:00'})
    assert response.status_code==200,response.text


def test_csrf_upload_and_file_isolation(client,db,data):
    a=assignment(db,data);login(client,'alice')
    assert client.post('/profile',data={'phone':'bad'}).status_code==403
    csrf=token(client,'/profile')
    response=client.post('/files/upload',data={'csrf':csrf,'scope':'assignment','target':a.id},files={'file':('solution.pdf',b'%PDF-1.4\n test','application/pdf')})
    assert response.status_code==200,response.text
    file=db.scalar(select(File));assert client.get(f'/files/{file.id}').status_code==200
    login(client,'bob');assert client.get(f'/files/{file.id}').status_code==403
    login(client,'alice');csrf=token(client,'/profile')
    assert client.post('/files/upload',data={'csrf':csrf,'scope':'assignment','target':a.id},files={'file':('evil.svg',b'<svg><script/></svg>','image/svg+xml')}).status_code==400


def test_answer_http_and_invalid_does_not_consume(client,db,data):
    a=assignment(db,data);login(client,'alice');csrf=token(client,f'/homework/{a.id}')
    assert client.post(f'/homework/{a.id}/answer/0',data={'csrf':csrf,'answer':'not numeric'}).status_code==400
    assert db.scalar(select(func.count()).select_from(Attempt))==0
    response=client.post(f'/homework/{a.id}/answer/0',data={'csrf':csrf,'answer':'4/6'})
    assert response.status_code==200 and 'Верно' in response.text


def test_public_application(client,db,data):
    csrf=token(client,'/')
    response=client.post('/apply',data={'csrf':csrf,'name':'Демо-заявка','contact':'demo@example.test','message':'7 класс'})
    assert response.status_code==200
    assert db.scalar(select(Lead)).status=='new'
    assert client.post('/apply',data={'csrf':csrf,'name':'Повтор','contact':'demo@example.test'}).status_code==400


def test_manual_grade_audit(client,db,data):
    a=assignment(db,data);attempt=submit(db,a.id,data['alice'].id,0,'1');db.commit()
    login(client,'admin');csrf=token(client,'/dashboard')
    assert client.post(f'/results/{attempt.id}/correct',data={'csrf':csrf,'correct':'true','reason':'Проверено по фото'}).status_code==200
    assert db.get(Attempt,attempt.id).correct is False
    assert db.scalar(select(GradeCorrection)).reason=='Проверено по фото'
    login(client,'alice');page=client.get(f'/homework/{a.id}').text
    assert '1 / 1' in page and 'Проверено по фото' in page


def test_session_invalidated_after_password_reset(client,db,data):
    from app.security import hash_password
    login(client,'alice');data['alice'].password_hash=hash_password('Another-password-2026');db.commit()
    assert client.get('/dashboard',follow_redirects=False).headers['location']=='/login'


def test_course_file_and_task_snapshot_access(client,db,data,tmp_path,monkeypatch):
    monkeypatch.setenv('STORAGE_DIR',str(tmp_path))
    topic=Topic(title='T',course_id=data['course'].id);db.add(topic);db.flush()
    lesson=Lesson(title='L',topic_id=topic.id);db.add(lesson);db.flush()
    file=File(owner_id=data['admin'].id,lesson_id=lesson.id,name='lesson.pdf',path='lesson',mime='application/pdf',size=5)
    task_file=File(owner_id=data['admin'].id,task_id=data['task'].id,name='task.pdf',path='task',mime='application/pdf',size=5)
    db.add_all([file,task_file]);db.commit();(tmp_path/'lesson').write_bytes(b'%PDF-');(tmp_path/'task').write_bytes(b'%PDF-')
    a=assignment(db,data);login(client,'alice')
    assert client.get(f'/files/{file.id}').status_code==200
    assert client.get(f'/files/{task_file.id}').status_code==200
    a.status='hidden';db.commit();assert client.get(f'/files/{task_file.id}').status_code==403
    db.scalar(select(Membership).where(Membership.user_id==data['alice'].id)).active=False;db.commit()
    assert client.get(f'/files/{file.id}').status_code==403


def test_admin_template_copy_and_result_filter(client,db,data):
    login(client,'admin');csrf=token(client,'/dashboard')
    assert client.post(f'/templates/{data["template"].id}/copy',data={'csrf':csrf}).status_code==200
    assert db.scalar(select(func.count()).select_from(HomeworkTemplate))==2
    assert client.get('/results?group_id=&student_id=&assignment_id=').status_code==200


def test_cannot_confirm_future_or_omit_attendance(db,data):
    m=event(db,group_id=data['g1'].id,is_event=False);uid=data['alice'].id
    with pytest.raises(ValueError): confirm_meeting(db,m.id,60,{uid:'present'})
    m.starts_at=now()-timedelta(hours=1);db.commit()
    with pytest.raises(ValueError): confirm_meeting(db,m.id,60,{})


def test_full_refund_and_late_admin_removal(db,data):
    m=event(db);uid=data['alice'].id;register(db,m.id,uid);m.starts_at=now()-timedelta(hours=2);db.commit()
    confirm_meeting(db,m.id,90,{uid:'absent'});debit=db.scalar(select(Ledger).where(Ledger.kind=='charge'))
    refund(db,debit.id,90,'Полный возврат');assert balance(db,uid)==0
    register(db,m.id,uid,False,admin=True);assert balance(db,uid)==0
    assert not registration(db,m.id,uid).active


def test_separate_payment_is_idempotent(client,db,data):
    m=event(db,payment_mode='separate');uid=data['alice'].id;register(db,m.id,uid);db.commit()
    login(client,'admin');csrf=token(client,'/dashboard')
    for _ in range(2):
        assert client.post(f'/meetings/{m.id}/paid/{uid}',data={'csrf':csrf,'paid':'1'}).status_code==200
    assert registration(db,m.id,uid).paid
    assert balance(db,uid)==0
    assert db.scalar(select(func.count()).select_from(RegistrationHistory).where(RegistrationHistory.action=='paid'))==1


def test_event_http_cannot_register_another_student(client,db,data):
    m=event(db);login(client,'alice');csrf=token(client,'/dashboard')
    response=client.post(f'/meetings/{m.id}/register',data={'csrf':csrf,'action':'register','user_id':data['bob'].id})
    assert response.status_code==200
    assert registration(db,m.id,data['alice'].id).active
    assert registration(db,m.id,data['bob'].id) is None
