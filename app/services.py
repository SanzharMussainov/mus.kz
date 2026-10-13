from sqlalchemy import select, func
from .models import *
from .db import now
from .grading import check


def ids(value):
    try:
        return [int(x.strip()) for x in value.split(',') if x.strip()]
    except ValueError:
        raise ValueError('Укажите номера через запятую.')


def lock(db, model, pk):
    obj = db.scalar(select(model).where(model.id == pk).with_for_update())
    if obj is None:
        raise ValueError('Запись не найдена.')
    return obj


def group_ids(db, user_id):
    return list(db.scalars(select(Membership.group_id).where(Membership.user_id == user_id, Membership.active == True)))


def course_ids(db, user_id):
    groups = group_ids(db, user_id)
    return set(db.scalars(select(Group.course_id).where(Group.id.in_(groups)))) | set(db.scalars(select(CourseAccess.course_id).where(CourseAccess.user_id == user_id, CourseAccess.active == True)))


def accessible(db, assignment, user_id, at=None):
    return assignment.group_id in group_ids(db, user_id) and assignment.status == 'published' and assignment.opens_at <= (at or now())


def publish(db, assignment):
    if not assignment.snapshot:
        template = db.get(HomeworkTemplate, assignment.template_id)
        task_ids = ids(template.task_ids)
        if not task_ids or len(task_ids) != len(set(task_ids)):
            raise ValueError('Шаблон должен содержать неповторяющиеся задания.')
        snapshot = []
        for pk in task_ids:
            t = db.get(Task, pk)
            if not t or t.status != 'ready':
                raise ValueError(f'Задание №{pk} отсутствует или не готово.')
            item = {c.name: getattr(t, c.name) for c in Task.__table__.columns}
            check(item, item['answer'])
            item['file_ids'] = list(db.scalars(select(File.id).where(File.task_id == t.id)))
            snapshot.append(item)
        assignment.snapshot = snapshot
    assignment.status = 'published'


def submit(db, assignment_id, user_id, task_index, value, at=None):
    at = at or now()
    # Serializes submissions for this issuance, also enforcing the attempt limit.
    a = lock(db, Assignment, assignment_id)
    if not accessible(db, a, user_id, at):
        raise ValueError('Работа пока недоступна.')
    if at >= a.solutions_at:
        raise ValueError('Приём ответов завершён: решения уже открыты.')
    if at > a.deadline and not a.allow_late:
        raise ValueError('Срок сдачи истёк.')
    if not 0 <= task_index < len(a.snapshot):
        raise ValueError('Задание не найдено.')
    count = db.scalar(select(func.count()).select_from(Attempt).where(Attempt.user_id == user_id, Attempt.assignment_id == a.id, Attempt.task_index == task_index))
    if count >= a.max_attempts:
        raise ValueError('Попытки закончились.')
    correct = check(a.snapshot[task_index], value)
    attempt = Attempt(user_id=user_id, assignment_id=a.id, task_index=task_index, number=count+1, answer=value, correct=correct, late=at > a.deadline, created_at=at)
    db.add(attempt)
    db.flush()
    return attempt


def balance(db, user_id):
    return db.scalar(select(func.coalesce(func.sum(Ledger.minutes), 0)).where(Ledger.user_id == user_id))


def eligible(db, meeting, user_id):
    return meeting.audience == 'all' or user_id in ids(meeting.audience_users) or bool(set(group_ids(db, user_id)) & set(ids(meeting.audience_groups)))


def registration(db, meeting_id, user_id):
    return db.scalar(select(Registration).where(Registration.meeting_id == meeting_id, Registration.user_id == user_id))


def meeting_access(db, m, user_id):
    r = registration(db, m.id, user_id)
    if m.is_event:
        return eligible(db, m, user_id) or bool(r)
    return m.group_id in group_ids(db, user_id) or bool(r)


def participates(db, m, user_id):
    r = registration(db, m.id, user_id)
    return bool(r and r.active) if m.is_event or not m.group_id else m.group_id in group_ids(db, user_id)


def register(db, meeting_id, user_id, active=True, admin=False, at=None):
    at = at or now()
    m = lock(db, Meeting, meeting_id)
    if not admin and (not m.is_event or not eligible(db, m, user_id)):
        raise ValueError('Запись недоступна для вашей группы.')
    if not admin and (m.status != 'scheduled' or at >= m.starts_at):
        raise ValueError('Запись на событие закрыта.')
    if not active and not admin and at >= (m.cancel_until or m.starts_at):
        raise ValueError('Срок самостоятельной отмены истёк. Свяжитесь с преподавателем.')
    r = registration(db, m.id, user_id)
    if not r:
        if not active:
            return
        r = Registration(meeting_id=m.id, user_id=user_id, active=True)
        db.add(r)
    elif r.active == active:
        return
    else:
        r.active = active
    db.add(RegistrationHistory(meeting_id=m.id, user_id=user_id, action=('admin:' if admin else 'student:') + ('registered' if active else 'cancelled')))
    db.flush()
    if admin and not active and m.status == 'held':
        record_attendance(db, m, user_id, 'warned', 'Участник снят преподавателем')


def record_attendance(db, m, user_id, status, reason):
    if status not in ('present', 'warned', 'absent', 'trial', 'cancelled'):
        raise ValueError('Неизвестный статус посещаемости.')
    row = db.scalar(select(Attendance).where(Attendance.meeting_id == m.id, Attendance.user_id == user_id))
    if not row:
        row = Attendance(meeting_id=m.id, user_id=user_id, status=status, charged_minutes=0)
        db.add(row)
    target = (m.actual_duration or 0) if m.status == 'held' and m.payment_mode == 'subscription' and status in ('present', 'absent') else 0
    refunds = db.scalar(select(func.coalesce(func.sum(Ledger.minutes), 0)).where(Ledger.meeting_id == m.id, Ledger.user_id == user_id, Ledger.kind == 'refund'))
    target = max(0, target-refunds)
    difference = target - row.charged_minutes
    if difference:
        db.add(Ledger(user_id=user_id, meeting_id=m.id, minutes=-difference, kind='charge' if difference > 0 else 'attendance_correction', reason=reason))
    row.status = status
    row.charged_minutes = target


def confirm_meeting(db, meeting_id, actual_duration, statuses, cancelled=False, reason='Подтверждение занятия', at=None):
    m = lock(db, Meeting, meeting_id)
    if not cancelled and m.starts_at > (at or now()):
        raise ValueError('Нельзя подтвердить ещё не начавшееся занятие.')
    if not cancelled and not 1 <= actual_duration <= 1440:
        raise ValueError('Фактическая длительность: от 1 до 1440 минут.')
    participants = set(db.scalars(select(Registration.user_id).where(Registration.meeting_id == m.id, Registration.active == True)))
    if not m.is_event and m.group_id:
        participants |= set(db.scalars(select(Membership.user_id).where(Membership.group_id == m.group_id, Membership.active == True)))
    participants |= set(db.scalars(select(Attendance.user_id).where(Attendance.meeting_id == m.id)))
    if not cancelled and set(statuses) != participants:
        raise ValueError('Отметьте посещаемость всех участников.')
    m.status = 'cancelled' if cancelled else 'held'
    m.actual_duration = 0 if cancelled else actual_duration
    for user_id in sorted(participants):
        lock(db, User, user_id)
        record_attendance(db, m, user_id, 'cancelled' if cancelled else statuses[user_id], reason)
    db.flush()
    for user_id in participants:
        refresh_notice(db, user_id)


def refund(db, ledger_id, minutes, reason):
    original = db.get(Ledger, ledger_id)
    if not original:
        raise ValueError('Операция не найдена.')
    if original.meeting_id:
        lock(db, Meeting, original.meeting_id)
    original = lock(db, Ledger, ledger_id)
    if original.minutes >= 0 or original.kind != 'charge' or minutes <= 0 or not reason.strip():
        raise ValueError('Выберите списание, положительное количество минут и укажите причину.')
    # Attendance changes and manual returns cannot collectively exceed the current debit.
    lock(db, User, original.user_id)
    returned = db.scalar(select(func.coalesce(func.sum(Ledger.minutes), 0)).where(Ledger.parent_id == original.id))
    net = db.scalar(select(func.coalesce(func.sum(Ledger.minutes), 0)).where(Ledger.meeting_id == original.meeting_id, Ledger.user_id == original.user_id))
    if minutes > min(-original.minutes-returned, max(0, -net)):
        raise ValueError('Возврат превышает невозвращённое списание.')
    db.add(Ledger(user_id=original.user_id, meeting_id=original.meeting_id, parent_id=original.id, minutes=minutes, kind='refund', reason=reason))
    # Track net charge so subsequent attendance reconciliation preserves ledger correctness.
    row = db.scalar(select(Attendance).where(Attendance.meeting_id == original.meeting_id, Attendance.user_id == original.user_id))
    if row:
        row.charged_minutes -= minutes
    db.flush()
    refresh_notice(db, original.user_id)


def next_meeting(db, user_id):
    for m in db.scalars(select(Meeting).where(Meeting.status == 'scheduled', Meeting.starts_at > now(), Meeting.payment_mode == 'subscription').order_by(Meeting.starts_at)):
        if participates(db, m, user_id):
            return m


def payment_notice(db, user_id):
    minutes = balance(db, user_id)
    upcoming = next_meeting(db, user_id)
    return {'balance': minutes, 'meeting': upcoming} if minutes <= 0 or upcoming and minutes < upcoming.duration else None


def refresh_notice(db, user_id):
    if not payment_notice(db, user_id):
        db.get(User, user_id).payment_requested = False


def payment(db, user_id, minutes, amount, reason, at=None, adjustment=False):
    lock(db, User, user_id)
    if not reason.strip() or amount < 0 or (not adjustment and minutes <= 0):
        raise ValueError('Укажите минуты, неотрицательную сумму и комментарий.')
    db.add(Ledger(user_id=user_id, minutes=minutes, amount=amount, kind='adjustment' if adjustment else 'payment', reason=reason, created_at=at or now()))
    db.flush()
    refresh_notice(db, user_id)
