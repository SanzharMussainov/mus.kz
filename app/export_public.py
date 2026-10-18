"""Export only fields already displayed on the public landing page."""
import json
from sqlalchemy import select
from .db import Session, now
from .models import Settings, Course, Group, Meeting

def export(db):
    def fields(obj,names):
        return {name:getattr(obj,name) for name in names.split()}
    settings=db.get(Settings,1)
    if settings is None: raise ValueError('Site settings are missing')
    courses=db.scalars(select(Course).where(Course.public==True)).all()
    groups=db.scalars(select(Group).where(Group.status=='recruiting',Group.course_id.in_([c.id for c in courses]))).all()
    events=db.scalars(select(Meeting).where(Meeting.is_event==True,Meeting.public==True,Meeting.status=='scheduled',Meeting.starts_at>now()).order_by(Meeting.starts_at)).all()
    return dict(settings=fields(settings,'title headline about teacher contact whatsapp'),
        courses=[fields(c,'title description direction grade level') for c in courses],
        groups=[fields(g,'title schedule starts_at ends_at hourly_price min_students max_students') for g in groups],
        events=[fields(e,'title description starts_at duration payment_mode audience') for e in events])

if __name__=='__main__':
    with Session() as db: print(json.dumps(export(db),ensure_ascii=False,indent=2,default=lambda value:value.isoformat()))
