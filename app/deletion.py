"""Recoverable deletion; never erase attendance or the financial ledger."""
from sqlalchemy import select
from .models import User, Course, Group, Membership, Meeting, Lead, MessageTemplate, Registration
from .services import confirm_meeting, lock

DELETABLE = dict(students=User,courses=Course,groups=Group,meetings=Meeting,leads=Lead,messages=MessageTemplate)


def remove(db, obj):
    if obj.deleted:
        return
    if isinstance(obj, User):
        if obj.role!='student':
            raise ValueError('Учётную запись преподавателя удалить нельзя.')
        obj.active=False
        for member in db.scalars(select(Membership).where(Membership.user_id==obj.id)):
            member.active=False
        for registration in db.scalars(select(Registration).join(Meeting).where(Registration.user_id==obj.id,Meeting.status=='scheduled')):
            registration.active=False
    elif isinstance(obj, Course):
        for group in db.scalars(select(Group).where(Group.course_id==obj.id).order_by(Group.id)):
            remove(db,lock(db,Group,group.id))
        obj.public=False
    elif isinstance(obj, Group):
        # Past meetings remain in reports; future meetings cannot use a deleted group.
        for meeting in db.scalars(select(Meeting).where(Meeting.group_id==obj.id,Meeting.status=='scheduled').order_by(Meeting.id)):
            remove(db,lock(db,Meeting,meeting.id))
        for member in db.scalars(select(Membership).where(Membership.group_id==obj.id)):
            member.active=False
        obj.status='archived'
    elif isinstance(obj, Meeting):
        confirm_meeting(db,obj.id,0,{},cancelled=True,reason='Удаление занятия: возврат списанных минут')
    obj.deleted=True
    db.flush()


def restore(db, obj):
    if not obj.deleted:
        return
    if isinstance(obj,Group):
        parent=db.scalar(select(Course).where(Course.id==obj.course_id))
        if parent is None:
            raise ValueError('Сначала восстановите курс этой группы.')
    if isinstance(obj,Meeting) and obj.group_id:
        if db.scalar(select(Group).where(Group.id==obj.group_id)) is None:
            raise ValueError('Сначала восстановите группу этого занятия.')
    obj.deleted=False
    if isinstance(obj,Meeting):
        obj.status='scheduled'
        obj.actual_duration=None
    # Do not silently re-enroll pupils, republish courses or re-charge restored meetings.
    db.flush()
