import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session as ORMSession, with_loader_criteria
from sqlalchemy.types import TypeDecorator, DateTime


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError('Дата должна содержать часовой пояс')
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


def now():
    return datetime.now(timezone.utc)


url = os.getenv('DATABASE_URL', 'sqlite:///./local.db')
engine = create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {}, pool_pre_ping=True)
if url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_fk(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
Session = sessionmaker(engine, expire_on_commit=False)


@event.listens_for(ORMSession, 'do_orm_execute')
def hide_deleted(state):
    if state.is_select and not state.execution_options.get('include_deleted', False):
        from .models import SoftDelete
        state.statement = state.statement.options(
            with_loader_criteria(SoftDelete, lambda model: model.deleted == False, include_aliases=True))


def get_db():
    with Session() as db:
        yield db
