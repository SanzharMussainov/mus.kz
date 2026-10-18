"""Remove retired homework subsystem. Back up database and files before upgrade."""
from alembic import op
import sqlalchemy as sa
revision = 'b3a410'
down_revision = 'af631c094243'
branch_labels = None
depends_on = None

def upgrade():
    op.execute(sa.text('DELETE FROM files WHERE meeting_id IS NULL AND (lesson_id IS NOT NULL OR assignment_id IS NOT NULL OR task_id IS NOT NULL)'))
    with op.batch_alter_table('files') as batch:
        for column in ('lesson_id','assignment_id','task_id'):
            batch.drop_column(column)
    for table in ('grade_corrections','attempts','assignments','homework_templates','tasks','lessons','topics','course_access'):
        op.drop_table(table)

def downgrade():
    raise RuntimeError('Restore the pre-upgrade database and files backup; deleted learning data cannot be recreated by a downgrade.')
