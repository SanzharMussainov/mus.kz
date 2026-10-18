from datetime import datetime, timedelta
from sqlalchemy import select
from app.db import now
from app.models import Attendance, Meeting, MessageTemplate, Membership, Lead
from app.services import confirm_meeting, balance, payment
from app.reports import weekly_report, ZONE
from app.messages import validate_template
from conftest import login, token
import pytest


def lesson(db, data, day, status='present', **kw):
    values=dict(title='Урок',group_id=data['g1'].id,starts_at=datetime.fromisoformat(day).replace(tzinfo=ZONE),
                duration=60,actual_duration=60,status='held',planned_topics='Непройденный план',covered_topics='Пропорции')
    values.update(kw)
    m=Meeting(**values);db.add(m);db.flush()
    db.add(Attendance(meeting_id=m.id,user_id=data['alice'].id,status=status));db.commit()
    return m


def test_report_attendance_timezone_and_real_topics(db,data):
    lesson(db,data,'2026-09-06T23:59',covered_topics='Прошлая неделя')
    lesson(db,data,'2026-09-07T00:00',covered_topics='Пропорции\nПроценты')
    lesson(db,data,'2026-09-13T23:59',status='trial',covered_topics='Пропорции')
    lesson(db,data,'2026-09-14T00:00',covered_topics='Следующая неделя')
    for status in ('absent','warned','cancelled'):
        lesson(db,data,'2026-09-08T11:00',status=status,covered_topics='Пропущено')
    cancelled=lesson(db,data,'2026-09-09T11:00',covered_topics='Отменённый урок')
    cancelled.status='cancelled'
    scheduled=lesson(db,data,'2026-09-10T11:00',covered_topics='Не подтверждено')
    scheduled.status='scheduled';db.commit()
    r=weekly_report(db,data['alice'].id,'2026-09-10')
    assert r['attended']==2 and r['minutes']==120
    assert r['topics']==['Пропорции','Проценты']
    assert 'Непройденный план' not in r['text']
    # Historical reports survive leaving a group; another pupil gets no data.
    db.scalar(select(Membership).where(Membership.user_id==data['alice'].id)).active=False;db.commit()
    assert weekly_report(db,data['alice'].id,'2026-09-10')['attended']==2
    assert weekly_report(db,data['bob'].id,'2026-09-10')['attended']==0


def test_report_updates_after_topics_and_attendance_corrections(client,db,data):
    m=lesson(db,data,'2026-09-07T11:00',covered_topics='')
    assert weekly_report(db,data['alice'].id,'2026-09-07')['missing']==1
    login(client,'admin');csrf=token(client,'/dashboard')
    assert client.post(f'/meetings/{m.id}/topics',data={'csrf':csrf,'planned_topics':'План','covered_topics':'Рациональные числа'}).status_code==200
    assert weekly_report(db,data['alice'].id,'2026-09-07')['topics']==['Рациональные числа']
    confirm_meeting(db,m.id,60,{data['alice'].id:'absent'});db.commit()
    assert balance(db,data['alice'].id)==-60
    assert weekly_report(db,data['alice'].id,'2026-09-07')['topics']==[]


def test_teacher_confirms_topics_once_and_student_sees_report(client,db,data):
    m=Meeting(title='Тестовый урок',group_id=data['g1'].id,starts_at=now()-timedelta(hours=2),duration=60,planned_topics='Дроби')
    db.add(m);payment(db,data['alice'].id,480,28000,'Абонемент');db.commit()
    login(client,'admin');csrf=token(client,'/dashboard')
    values={'csrf':csrf,'duration':'60',f'status_{data["alice"].id}':'present','action':'confirm'}
    assert client.post(f'/meetings/{m.id}/confirm',data=values).status_code==400
    values['covered_topics']='Сложение дробей'
    for _ in range(2):assert client.post(f'/meetings/{m.id}/confirm',data=values).status_code==200
    assert balance(db,data['alice'].id)==420
    login(client,'alice')
    page=client.get('/reports?week='+m.starts_at.astimezone(ZONE).date().isoformat())
    assert page.status_code==200 and 'Сложение дробей' in page.text
    assert '7 ч 00 мин' in client.get('/dashboard').text
    assert client.get('/reports?student='+str(data['bob'].id)).status_code==403
    assert client.get('/messages').status_code==403
    assert client.post(f'/meetings/{m.id}/topics',data={'csrf':token(client,'/dashboard'),'covered_topics':'Подмена'}).status_code==403
    assert client.get('/reports?week=bad').status_code==400


def test_management_links_and_retired_endpoints(client,db,data):
    login(client,'admin')
    for path in ['/admin/tasks','/admin/templates','/admin/assignments','/homework','/results','/study/1','/packs/1']:
        assert client.get(path).status_code==404
    assert client.post('/files/upload').status_code in (404,405,422)
    data['course'].stepik_url='https://stepik.org/course/123';db.commit()
    login(client,'alice')
    page=client.get('/courses').text
    assert 'https://stepik.org/course/123' in page and '/homework' not in page
    assert client.post('/profile',data={'phone':'bad'}).status_code==403


def test_stepik_url_validation(client,db,data):
    login(client,'admin');csrf=token(client,'/dashboard')
    values={'csrf':csrf,'title':'Stepik test','direction':'Математика','level':'Базовый'}
    for url in ('javascript:alert(1)','https://stepik.org.evil.test/course/1','https://stepik.org@evil.test/course/1'):
        assert client.post('/admin/courses/new',data={**values,'stepik_url':url}).status_code==400
    assert client.post('/admin/courses/new',data={**values,'stepik_url':'https://stepik.org/course/123'}).status_code==200


def test_message_templates_validation_and_rendering(client,db,data):
    login(client,'admin');csrf=token(client,'/dashboard')
    assert client.post('/admin/messages/new',data={'csrf':csrf,'title':'Отчёт','body':'{student}: {balance}\n{weekly_report}'}).status_code==200
    page=client.get('/messages?student='+str(data['alice'].id)+'&week=2026-09-07')
    assert page.status_code==200 and 'alice: 0 ч 00 мин' in page.text
    for bad in ('{student.__class__}','{unknown}','{student!r}','{student:100000}','{'):
        with pytest.raises(ValueError):validate_template(bad)


def test_lead_group_must_be_open_and_public(client,db,data):
    data['course'].public=True;db.commit()
    values={'csrf':token(client,'/login'),'name':'Родитель','contact':'example@example.test','group_id':data['g1'].id}
    assert client.post('/apply',data=values).status_code==200
    assert db.scalar(select(Lead)).group_id==data['g1'].id




def test_meeting_audience_validation_is_relevant_and_specific(client, data):
    login(client,'admin')
    values=dict(csrf=token(client,'/admin/meetings/new'),title='Lesson',
                group_id=str(data['g1'].id),audience='all',audience_groups='999999',
                audience_users='999999',starts_at='2026-11-01T11:00',duration='60',
                payment_mode='subscription')
    assert client.post('/admin/meetings/new',data=values).status_code==200
    values.update(is_event='on',audience='selected')
    result=client.post('/admin/meetings/new',data=values)
    assert result.status_code==400 and 'Номера групп аудитории' in result.text and '#999999' in result.text
    values.update(audience_groups=str(data['g1'].id))
    result=client.post('/admin/meetings/new',data=values)
    assert result.status_code==400 and 'Номера учеников аудитории' in result.text
    values.update(audience_users=str(data['alice'].id))
    assert client.post('/admin/meetings/new',data=values).status_code==200
    values.update(group_id='999999')
    result=client.post('/admin/meetings/new',data=values)
    assert result.status_code==400 and 'Группа (для обычного занятия)' in result.text


def test_success_notice_survives_fetch_redirect_then_disappears(client,data):
    login(client,'admin')
    values=dict(csrf=token(client,'/admin/messages/new'),title='Notice test',body='Hello {student}')
    response=client.post('/admin/messages/new',data=values,headers={'X-Form-Submission':'fetch'})
    assert response.status_code==200 and 'Шаблон сообщения успешно создан.' in response.text
    destination=str(response.url)
    page=client.get(destination)
    assert 'Шаблон сообщения успешно создан.' in page.text and 'role="status"' in page.text
    assert 'Шаблон сообщения успешно создан.' not in client.get(destination).text
    values['csrf']=token(client,destination)
    response=client.post(destination,data=values)
    assert 'Изменения успешно сохранены.' in response.text
    assert 'Изменения успешно сохранены.' not in client.get(destination).text
