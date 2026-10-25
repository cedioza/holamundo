"""add shifts and administration fields

Revision ID: b7c41d9a2e30
Revises: 2045266188de
Create Date: 2026-10-21 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c41d9a2e30'
down_revision: Union[str, Sequence[str], None] = '2045266188de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'shifts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('parking_lot_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('starts_at', sa.Time(), nullable=False),
        sa.Column('ends_at', sa.Time(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.String(length=240), nullable=False),
        sa.ForeignKeyConstraint(['parking_lot_id'], ['parking_lots.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('employees') as batch_op:
        batch_op.add_column(sa.Column('shift_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_employees_shift_id', 'shifts', ['shift_id'], ['id'])
    with op.batch_alter_table('parking_lots') as batch_op:
        batch_op.add_column(sa.Column('city', sa.String(length=80), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('address', sa.String(length=160), nullable=False, server_default=''))
    with op.batch_alter_table('zones') as batch_op:
        batch_op.add_column(sa.Column('code', sa.String(length=20), nullable=False, server_default=''))
    with op.batch_alter_table('monthly_tariffs') as batch_op:
        batch_op.add_column(sa.Column('note', sa.String(length=240), nullable=False, server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('monthly_tariffs') as batch_op:
        batch_op.drop_column('note')
    with op.batch_alter_table('zones') as batch_op:
        batch_op.drop_column('code')
    with op.batch_alter_table('parking_lots') as batch_op:
        batch_op.drop_column('address')
        batch_op.drop_column('city')
    with op.batch_alter_table('employees') as batch_op:
        batch_op.drop_constraint('fk_employees_shift_id', type_='foreignkey')
        batch_op.drop_column('shift_id')
    op.drop_table('shifts')
