"""Attendance is the source of truth, not enrollment or billing."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .db import now
from .models import Meeting, Attendance

ZONE = ZoneInfo('Asia/Qyzylorda')


def week_start(value=None):
    day = date.fromisoformat(value) if value else now().astimezone(ZONE).date()
    return day - timedelta(days=day.weekday())


def weekly_report(db, user_id, week=None):
    start = week_start(week)
    end = start + timedelta(days=7)
    lower = datetime.combine(start, time.min, ZONE)
    upper = datetime.combine(end, time.min, ZONE)
    rows = db.execute(select(Meeting, Attendance).join(Attendance, Attendance.meeting_id == Meeting.id).where(
        Attendance.user_id == user_id, Meeting.status == 'held',
        Meeting.starts_at >= lower, Meeting.starts_at < upper,
        Meeting.starts_at <= now()).order_by(Meeting.starts_at, Meeting.id)).all()
    attended = [(m, a) for m, a in rows if a.status in ('present', 'trial')]
    topics = list(dict.fromkeys(line.strip() for m, _ in attended for line in m.covered_topics.splitlines() if line.strip()))
    minutes = sum(m.actual_duration or 0 for m, _ in attended)
    missing = sum(not m.covered_topics.strip() for m, _ in attended)
    label = f'{start:%d.%m.%Y} — {end-timedelta(days=1):%d.%m.%Y}'
    text = f'Неделя {label}.\nПосещено занятий: {len(attended)}. Время на занятиях: {minutes // 60} ч {minutes % 60:02d} мин.'
    text += '\nТемы посещённых занятий:\n' + ('\n'.join('• '+t for t in topics) if topics else 'Пока нет отмеченных тем.')
    if missing:
        text += f'\nПреподаватель ещё уточняет темы для {missing} занятий.'
    return dict(start=start, end=end, label=label, rows=rows, attended=len(attended),
                minutes=minutes, topics=topics, missing=missing, text=text,
                previous=(start-timedelta(days=7)).isoformat(), following=end.isoformat(),
                current=start==week_start())
