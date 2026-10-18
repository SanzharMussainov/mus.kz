from io import BytesIO
from datetime import timedelta
from pathlib import Path
import pytest
from sqlalchemy import select, func
from app.db import now
from app.models import *
from app.services import balance, payment, confirm_meeting
from app.reports import weekly_report
from app.deletion import remove
from conftest import login, token




def test_membership_bulk_add_remove_idempotence_capacity(client,db,data):
    login(client,'admin');csrf=token(client,'/dashboard')
    path=f'/groups/{data["g1"].id}/members'
    values={'csrf':csrf,'students':[data['alice'].id,data['bob'].id]}
    for _ in range(2): assert client.post(path,data=values).status_code==200
    assert db.scalar(select(func.count()).select_from(Membership).where(Membership.group_id==data['g1'].id))==2
    assert 'Добавить учеников в группу' in client.get('/admin/memberships').text
    assert client.post(path+f'/{data["bob"].id}/remove',data={'csrf':csrf}).status_code==200
    data['g1'].max_students=1;db.commit()
    assert client.post(path,data=values).status_code==400
    assert client.get('/admin/access').status_code==404
    login(client,'bob')
    assert client.post(path,data={'csrf':token(client,'/dashboard'),'students':data['bob'].id}).status_code==403


def test_meeting_delete_refunds_once_and_restores_without_charge(client,db,data):
    uid=data['alice'].id
    m=Meeting(title='Удаляемый урок',group_id=data['g1'].id,starts_at=now()-timedelta(hours=2),duration=60,covered_topics='Дроби')
    db.add(m);db.flush();payment(db,uid,480,28000,'Оплата');confirm_meeting(db,m.id,60,{uid:'present'});db.commit()
    login(client,'admin');csrf=token(client,'/dashboard');path=f'/admin/meetings/{m.id}/delete'
    assert client.get(path).status_code==200
    assert client.post(path,data={'csrf':csrf}).status_code==400
    for _ in range(2):assert client.post(path,data={'csrf':csrf,'confirm':'yes'}).status_code==200
    assert balance(db,uid)==480
    assert db.scalar(select(Meeting).where(Meeting.id==m.id)) is None
    assert weekly_report(db,uid)['attended']==0
    assert 'Удаляемый урок' in client.get('/admin/meetings?trash=true').text
    assert client.post(f'/admin/meetings/{m.id}/restore',data={'csrf':csrf}).status_code==200
    assert balance(db,uid)==480 and m.status=='scheduled'


def test_course_delete_cascades_future_but_preserves_history(client,db,data):
    for offset in (-2,2):
        m=Meeting(title=f'Урок {offset}',group_id=data['g1'].id,starts_at=now()+timedelta(hours=offset),duration=60,covered_topics='Дроби')
        db.add(m);db.flush()
        if offset<0:confirm_meeting(db,m.id,60,{data['alice'].id:'present'})
    db.commit();login(client,'admin');csrf=token(client,'/dashboard')
    assert client.post(f'/admin/courses/{data["course"].id}/delete',data={'csrf':csrf,'confirm':'yes'}).status_code==200
    assert len(db.scalars(select(Group)).all())==0
    meetings=db.scalars(select(Meeting)).all()
    assert len(meetings)==1 and meetings[0].status=='held'
    assert balance(db,data['alice'].id)==-60
    assert db.scalar(select(Membership).where(Membership.user_id==data['alice'].id)).active is False
    assert client.post(f'/admin/groups/{data["g1"].id}/restore',data={'csrf':csrf}).status_code==400
    assert client.post(f'/admin/courses/{data["course"].id}/restore',data={'csrf':csrf}).status_code==200
    assert client.post(f'/admin/groups/{data["g1"].id}/restore',data={'csrf':csrf}).status_code==200


def test_delete_students_blocks_login_and_preserves_ledger(client,db,data):
    uid=data['alice'].id;payment(db,uid,120,7000,'Оплата');db.commit()
    login(client,'admin');csrf=token(client,'/dashboard')
    assert client.post(f'/admin/students/{uid}/delete',data={'csrf':csrf,'confirm':'yes'}).status_code==200
    assert balance(db,uid)==120 and not data['alice'].active
    assert 'alice@example.test' not in client.get('/admin/students').text
    assert 'alice@example.test' in client.get('/admin/students?trash=true').text
    assert client.post(f'/admin/students/{data["admin"].id}/delete',data={'csrf':csrf,'confirm':'yes'}).status_code==400
    assert client.post('/login',data={'csrf':token(client,'/login'),'email':'alice@example.test','password':'Testing-12345'}).status_code==400


@pytest.mark.parametrize('section,model', [('leads',Lead),('messages',MessageTemplate)])
def test_delete_other_records_permissions_csrf(client,db,data,section,model):
    obj=model(name='Заявка',contact='x') if model==Lead else model(title='Шаблон',body='{student}')
    db.add(obj);db.commit();path=f'/admin/{section}/{obj.id}/delete'
    login(client,'alice')
    assert client.post(path,data={'csrf':token(client,'/dashboard'),'confirm':'yes'}).status_code==403
    login(client,'admin')
    assert client.post(path,data={'confirm':'yes'}).status_code==403
    assert client.post(path,data={'csrf':token(client,'/dashboard'),'confirm':'yes'}).status_code==200
    assert db.scalar(select(model).where(model.id==obj.id)) is None






def test_delete_meeting_after_student_deleted_keeps_refund(db,data):
    m=Meeting(title='History',group_id=data['g1'].id,starts_at=now()-timedelta(hours=2),duration=60)
    db.add(m);db.flush();confirm_meeting(db,m.id,60,{data['alice'].id:'present'});db.commit()
    remove(db,data['alice']);db.commit();remove(db,m);db.commit()
    assert balance(db,data['alice'].id)==0


def test_delete_success_notice_survives_fetch_and_is_shown_once(client,db,data):
    login(client,'admin')
    path=f'/admin/courses/{data["course"].id}/delete'
    csrf=token(client,path)
    failed=client.post(path,data={'csrf':csrf})
    assert failed.status_code==400 and 'Курс успешно удалён.' not in failed.text
    response=client.post(path,data={'csrf':csrf,'confirm':'yes'},headers={'X-Form-Submission':'fetch'})
    assert response.status_code==200 and 'Курс успешно удалён.' in response.text
    page=client.get('/admin/courses')
    assert 'Курс успешно удалён.' in page.text and 'Восстановить запись можно в корзине.' in page.text
    assert 'Курс успешно удалён.' not in client.get('/admin/courses').text


def test_photo_uploads_removed_and_public_photo_is_static(client,data):
    login(client,'admin')
    assert 'type="file"' not in client.get('/profile').text
    assert 'type="file"' not in client.get('/admin/settings/1').text
    for path in ('/profile/avatar','/settings/teacher-photo',f'/admin/students/{data["alice"].id}/avatar'):
        assert client.post(path,data={'csrf':token(client,'/profile')}).status_code==404
    assert 'src="/static/teacher.jpg"' in client.get('/').text
    assert client.get('/static/teacher.jpg').status_code==200
