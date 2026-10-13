"""Apply owner-supplied course information from stdin, without seeding students."""
import json
import re
import sys
from sqlalchemy import select
from .db import Session
from .models import Course, Group, Settings, Meeting


def configure(db, payload):
    site = payload['site']
    course_data = payload['course']
    group_data = payload['group']
    if not re.fullmatch(r'\d{10,15}',site['whatsapp']):
        raise ValueError('WhatsApp must contain 10-15 digits.')
    if not re.fullmatch(r'https://meet\.google\.com/[a-zA-Z0-9-]+',group_data['meet_url']):
        raise ValueError('Invalid Google Meet URL.')
    if not 1 <= group_data['min_students'] <= group_data['max_students'] or group_data['hourly_price'] < 0:
        raise ValueError('Invalid group size or hourly price.')
    settings = db.get(Settings,1)
    if settings is None:
        settings = Settings(id=1);db.add(settings)
    for key in ('title','headline','about','teacher','contact','whatsapp'):
        setattr(settings,key,site[key])
    course = db.scalar(select(Course).where(Course.title==course_data['title']))
    if course is None:
        course = Course();db.add(course)
    for key in ('title','description','direction','grade','level','public'):
        setattr(course,key,course_data[key])
    db.flush()
    group = db.scalar(select(Group).where(Group.course_id==course.id,Group.title==group_data['title']))
    if group is None:
        group=Group(course_id=course.id);db.add(group)
    for key in ('title','schedule','hourly_price','min_students','max_students','meet_url'):
        setattr(group,key,group_data[key])
    # This setup intentionally does not invent a start date or schedule dated meetings.
    if group.id is None:
        group.status='recruiting'
    db.flush()
    if payload.get('hide_demo'):
        for demo in db.scalars(select(Course).where(Course.title.contains('· демо'))):
            demo.public=False
        for demo in db.scalars(select(Meeting).where(Meeting.title.contains('· демо'),Meeting.is_event==True)):
            demo.public=False
    return {'course_id':course.id,'group_id':group.id,'has_start_date':group.starts_at is not None}


if __name__=='__main__':
    payload=json.loads(sys.stdin.buffer.read().decode('utf-8-sig'))
    with Session() as db:
        result=configure(db,payload);db.commit()
    print(json.dumps(result))
