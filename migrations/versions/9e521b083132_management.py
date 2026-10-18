"""Lightweight tutoring management; retain legacy history for safe restore."""
from alembic import op
import sqlalchemy as sa

revision = '9e521b083132'
down_revision = '7cf0113a6b20'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('courses', sa.Column('stepik_url', sa.String(500), nullable=False, server_default=''))
    op.add_column('meetings', sa.Column('planned_topics', sa.Text(), nullable=False, server_default=''))
    op.add_column('meetings', sa.Column('covered_topics', sa.Text(), nullable=False, server_default=''))
    with op.batch_alter_table('leads') as batch:
        batch.add_column(sa.Column('group_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_lead_group', 'groups', ['group_id'], ['id'])
    op.create_table('message_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False))
    table = sa.table('message_templates', sa.column('title'), sa.column('body'))
    op.bulk_insert(table, [
        {'title': 'Продление абонемента', 'body': 'Здравствуйте! У {student} осталось {balance}. Для продолжения занятий нужно пополнить абонемент. {contact}'},
        {'title': 'Напоминание о занятии', 'body': 'Здравствуйте, {student}! {next_lesson}\nСсылка на встречу: {meet_url}'},
        {'title': 'Недельный отчёт', 'body': 'Здравствуйте! Отчёт по занятиям: {student}.\n{weekly_report}\nОстаток абонемента сейчас: {balance}.'},
        {'title': 'Добро пожаловать', 'body': 'Здравствуйте, {student}! Вы занимаетесь в группе: {groups}.\nРасписание: {schedule}\nМатериалы: {stepik_url}\nКонтакт преподавателя: {contact}'}])


def downgrade():
    op.drop_table('message_templates')
    with op.batch_alter_table('leads') as batch:
        batch.drop_constraint('fk_lead_group', type_='foreignkey')
        batch.drop_column('group_id')
    op.drop_column('meetings', 'covered_topics')
    op.drop_column('meetings', 'planned_topics')
    op.drop_column('courses', 'stepik_url')
