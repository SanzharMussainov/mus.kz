from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, UTCDateTime, now
from datetime import datetime


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default='student')
    phone: Mapped[str] = mapped_column(String(40), default='')
    parent_contact: Mapped[str] = mapped_column(String(300), default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_requested: Mapped[bool] = mapped_column(Boolean, default=False)


class Course(Base):
    __tablename__ = 'courses'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    direction: Mapped[str] = mapped_column(String(100), default='Школьная математика')
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str] = mapped_column(String(100), default='Базовый')
    public: Mapped[bool] = mapped_column(Boolean, default=False)


class Topic(Base):
    __tablename__ = 'topics'
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=1)


class Lesson(Base):
    __tablename__ = 'lessons'
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default='')
    position: Mapped[int] = mapped_column(Integer, default=1)


class Group(Base):
    __tablename__ = 'groups'
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'))
    title: Mapped[str] = mapped_column(String(200))
    schedule: Mapped[str] = mapped_column(Text, default='')
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='recruiting')


class Membership(Base):
    __tablename__ = 'memberships'
    __table_args__ = (UniqueConstraint('group_id', 'user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey('groups.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CourseAccess(Base):
    __tablename__ = 'course_access'
    __table_args__ = (UniqueConstraint('course_id', 'user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))
    answer: Mapped[str] = mapped_column(Text)
    options: Mapped[str] = mapped_column(Text, default='')
    tolerance: Mapped[str] = mapped_column(String(30), default='0')
    ordered: Mapped[bool] = mapped_column(Boolean, default=False)
    exact_form: Mapped[bool] = mapped_column(Boolean, default=False)
    solution: Mapped[str] = mapped_column(Text, default='')
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    topic: Mapped[str] = mapped_column(String(200), default='')
    difficulty: Mapped[str] = mapped_column(String(50), default='Базовая')
    status: Mapped[str] = mapped_column(String(20), default='draft')


class HomeworkTemplate(Base):
    __tablename__ = 'homework_templates'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    task_ids: Mapped[str] = mapped_column(Text, default='')


class Assignment(Base):
    __tablename__ = 'assignments'
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey('groups.id'))
    template_id: Mapped[int] = mapped_column(ForeignKey('homework_templates.id'))
    title: Mapped[str] = mapped_column(String(200))
    opens_at: Mapped[datetime] = mapped_column(UTCDateTime)
    deadline: Mapped[datetime] = mapped_column(UTCDateTime)
    solutions_at: Mapped[datetime] = mapped_column(UTCDateTime)
    allow_late: Mapped[bool] = mapped_column(Boolean, default=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default='draft')
    snapshot: Mapped[list] = mapped_column(JSON, default=list)


class Attempt(Base):
    __tablename__ = 'attempts'
    __table_args__ = (UniqueConstraint('user_id', 'assignment_id', 'task_index', 'number'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    assignment_id: Mapped[int] = mapped_column(ForeignKey('assignments.id'))
    task_index: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    answer: Mapped[str] = mapped_column(Text)
    correct: Mapped[bool] = mapped_column(Boolean)
    late: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class GradeCorrection(Base):
    __tablename__ = 'grade_corrections'
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey('attempts.id'))
    correct: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Meeting(Base):
    __tablename__ = 'meetings'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    group_id: Mapped[int | None] = mapped_column(ForeignKey('groups.id'), nullable=True)
    is_event: Mapped[bool] = mapped_column(Boolean, default=False)
    audience: Mapped[str] = mapped_column(String(20), default='all')
    audience_groups: Mapped[str] = mapped_column(Text, default='')
    audience_users: Mapped[str] = mapped_column(Text, default='')
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    duration: Mapped[int] = mapped_column(Integer, default=60)
    actual_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meet_url: Mapped[str] = mapped_column(String(500), default='')
    material: Mapped[str] = mapped_column(Text, default='')
    payment_mode: Mapped[str] = mapped_column(String(20), default='subscription')
    cancel_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='scheduled')


class Registration(Base):
    __tablename__ = 'registrations'
    __table_args__ = (UniqueConstraint('meeting_id', 'user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey('meetings.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)


class RegistrationHistory(Base):
    __tablename__ = 'registration_history'
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey('meetings.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Attendance(Base):
    __tablename__ = 'attendance'
    __table_args__ = (UniqueConstraint('meeting_id', 'user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey('meetings.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(30))
    charged_minutes: Mapped[int] = mapped_column(Integer, default=0)


class Ledger(Base):
    __tablename__ = 'ledger'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey('meetings.id'), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('ledger.id'), nullable=True)
    minutes: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Lead(Base):
    __tablename__ = 'leads'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    contact: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(30), default='new')
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Settings(Base):
    __tablename__ = 'settings'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    title: Mapped[str] = mapped_column(String(200), default='mus.kz')
    headline: Mapped[str] = mapped_column(String(300), default='Математика становится понятной')
    about: Mapped[str] = mapped_column(Text, default='Онлайн-занятия по школьной математике. Знакомимся, определяем уровень и выбираем подходящую группу.')
    teacher: Mapped[str] = mapped_column(Text, default='Информация о преподавателе скоро появится здесь.')
    contact: Mapped[str] = mapped_column(String(200), default='Контакты уточняются. Оставьте заявку — преподаватель свяжется с вами.')
    whatsapp: Mapped[str] = mapped_column(String(30), default='')


class File(Base):
    __tablename__ = 'files'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey('lessons.id'), nullable=True)
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey('assignments.id'), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey('tasks.id'), nullable=True)
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey('meetings.id'), nullable=True)
    name: Mapped[str] = mapped_column(String(250))
    path: Mapped[str] = mapped_column(String(100), unique=True)
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)


class LoginFailure(Base):
    __tablename__ = 'login_failures'
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(300), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
