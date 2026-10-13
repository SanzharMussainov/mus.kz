from sqlalchemy import select,func
from app.models import Course,Group,Meeting,Task
from app.setup_course import configure
from conftest import login,token


def payload():
    return {
        'site':{'title':'Test school','headline':'Math','about':'Online','teacher':'Owner biography','contact':'Contact','whatsapp':'77770000000'},
        'course':{'title':'Grade 6','description':'Books pending','direction':'School','grade':6,'level':'School','public':True},
        'group':{'title':'Grade 6 group','schedule':'Mon Wed Fri 11:00–12:00','hourly_price':3500,'min_students':2,'max_students':8,'meet_url':'https://meet.google.com/abc-defg-hij'},
    }


def test_owner_setup_no_invented_dates_or_lessons(db,client):
    first=configure(db,payload());db.commit()
    second=configure(db,payload());db.commit()
    assert first==second and not first['has_start_date']
    assert db.scalar(select(func.count()).select_from(Course))==1
    assert db.scalar(select(func.count()).select_from(Group))==1
    assert db.scalar(select(func.count()).select_from(Meeting))==0
    assert db.scalar(select(func.count()).select_from(Task))==0
    page=client.get('/').text
    assert '3500' in page and '2–8' in page
    assert 'abc-defg-hij' not in page
    assert 'Начало:' not in page


def test_group_conditions_editable_and_validated(db,data,client):
    login(client,'admin');csrf=token(client,'/dashboard')
    values={'csrf':csrf,'title':'Terms','course_id':data['course'].id,'status':'recruiting','hourly_price':'3500','min_students':'2','max_students':'8','meet_url':'https://meet.google.com/abc-defg-hij'}
    assert client.post('/admin/groups/new',data=values).status_code==200
    values['min_students']='9'
    assert client.post('/admin/groups/new',data=values).status_code==400
