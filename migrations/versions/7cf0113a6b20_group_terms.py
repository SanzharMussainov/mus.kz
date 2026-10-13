"""Group pricing, size and private default meeting link."""
from alembic import op
import sqlalchemy as sa

revision = '7cf0113a6b20'
down_revision = '381b997c7bbf'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('groups', sa.Column('hourly_price', sa.Integer(), nullable=True))
    op.add_column('groups', sa.Column('min_students', sa.Integer(), nullable=True))
    op.add_column('groups', sa.Column('max_students', sa.Integer(), nullable=True))
    op.add_column('groups', sa.Column('meet_url', sa.String(500), nullable=True))


def downgrade():
    op.drop_column('groups', 'meet_url')
    op.drop_column('groups', 'max_students')
    op.drop_column('groups', 'min_students')
    op.drop_column('groups', 'hourly_price')
