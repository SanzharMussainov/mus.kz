"""Recoverable removal and user avatars."""
from alembic import op
import sqlalchemy as sa

revision = 'af631c094243'
down_revision = '9e521b083132'
branch_labels = None
depends_on = None
TABLES = ('users','courses','groups','meetings','leads','message_templates')


def upgrade():
    for table in TABLES:
        op.add_column(table,sa.Column('deleted',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('users',sa.Column('avatar_path',sa.String(100),nullable=False,server_default=''))
    op.add_column('settings',sa.Column('teacher_photo',sa.String(100),nullable=False,server_default=''))


def downgrade():
    op.drop_column('settings','teacher_photo')
    op.drop_column('users','avatar_path')
    for table in TABLES:
        op.drop_column(table,'deleted')
