"""Only prepare messages; sending stays an explicit teacher action."""
from string import Formatter
from sqlalchemy import select
from .models import Course, Group, Settings, Meeting
from .services import group_ids, balance, participates
from .db import now
from .reports import weekly_report, ZONE

FIELDS = ('student', 'balance', 'groups', 'schedule', 'next_lesson', 'meet_url', 'stepik_url', 'weekly_report', 'contact')


def validate_template(body):
    if not body.strip() or len(body) > 10000:
        raise ValueError('Введите текст сообщения, не более 10000 символов.')
    try:
        for _, field, spec, conversion in Formatter().parse(body):
            if field is not None and (field not in FIELDS or spec or conversion):
                raise ValueError('Допустимы только переменные: ' + ', '.join('{'+f+'}' for f in FIELDS))
    except ValueError as error:
        raise ValueError('Проверьте переменные и фигурные скобки в шаблоне. ' + str(error)) from error


def message_context(db, student, week=None):
    groups = db.scalars(select(Group).where(Group.id.in_(group_ids(db, student.id))).order_by(Group.title)).all()
    courses = db.scalars(select(Course).where(Course.id.in_([g.course_id for g in groups]))).all()
    meeting = next((m for m in db.scalars(select(Meeting).where(Meeting.status=='scheduled', Meeting.starts_at>now()).order_by(Meeting.starts_at)) if participates(db,m,student.id)), None)
    minutes = balance(db, student.id)
    settings = db.get(Settings, 1)
    return dict(student=student.name,
        balance=('−' if minutes < 0 else '') + f'{abs(minutes)//60} ч {abs(minutes)%60:02d} мин',
        groups=', '.join(g.title for g in groups) or 'Группа ещё не назначена',
        schedule='; '.join(g.schedule for g in groups if g.schedule) or 'Уточняется',
        next_lesson=f'{meeting.title} — {meeting.starts_at.astimezone(ZONE):%d.%m.%Y %H:%M} (Asia/Qyzylorda)' if meeting else 'Следующее занятие ещё не назначено',
        meet_url=meeting.meet_url if meeting and meeting.meet_url else 'Ссылка появится в кабинете',
        stepik_url='\n'.join(c.stepik_url for c in courses if c.stepik_url) or 'Ссылки на Stepik преподаватель добавит позже',
        weekly_report=weekly_report(db, student.id, week)['text'],
        contact=settings.contact if settings else '')
