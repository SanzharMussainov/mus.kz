from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, UTCDateTime, now
from datetime import datetime


class SoftDelete:
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class User(SoftDelete, Base):
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
    avatar_path: Mapped[str] = mapped_column(String(100), default='')


class Course(SoftDelete, Base):
    __tablename__ = 'courses'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    direction: Mapped[str] = mapped_column(String(100), default='Школьная математика')
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str] = mapped_column(String(100), default='Базовый')
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    stepik_url: Mapped[str] = mapped_column(String(500), default='')






class Group(SoftDelete, Base):
    __tablename__ = 'groups'
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'))
    title: Mapped[str] = mapped_column(String(200))
    schedule: Mapped[str] = mapped_column(Text, default='')
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='recruiting')
    hourly_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_students: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_students: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meet_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Membership(Base):
    __tablename__ = 'memberships'
    __table_args__ = (UniqueConstraint('group_id', 'user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey('groups.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)














class Meeting(SoftDelete, Base):
    __tablename__ = 'meetings'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    planned_topics: Mapped[str] = mapped_column(Text, default='')
    covered_topics: Mapped[str] = mapped_column(Text, default='')
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


class Lead(SoftDelete, Base):
    __tablename__ = 'leads'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    contact: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default='')
    group_id: Mapped[int | None] = mapped_column(ForeignKey('groups.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='new')
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class MessageTemplate(SoftDelete, Base):
    __tablename__ = 'message_templates'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)


class Settings(Base):
    __tablename__ = 'settings'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    title: Mapped[str] = mapped_column(String(200), default='mus.kz')
    headline: Mapped[str] = mapped_column(String(300), default='Математика становится понятной')
    about: Mapped[str] = mapped_column(Text, default='Онлайн-занятия по школьной математике. Знакомимся, определяем уровень и выбираем подходящую группу.')
    teacher: Mapped[str] = mapped_column(Text, default='Информация о преподавателе скоро появится здесь.')
    contact: Mapped[str] = mapped_column(String(200), default='Контакты уточняются. Оставьте заявку — преподаватель свяжется с вами.')
    whatsapp: Mapped[str] = mapped_column(String(30), default='')
    teacher_photo: Mapped[str] = mapped_column(String(100), default='')


class File(Base):
    __tablename__ = 'files'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
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
