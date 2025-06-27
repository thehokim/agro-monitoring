"""alter maydon to string

Revision ID: d9513a3c9117
Revises: 306eeaf7d0bc
Create Date: 2025-06-27 15:13:20.309235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# revision identifiers
revision = 'd9513a3c9117'
down_revision = '306eeaf7d0bc'
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column(
        'agro_data',
        'maydon',
        existing_type=sa.Integer(),
        type_=sa.Numeric(18, 4),
        postgresql_using="trim(maydon::text)::numeric(18,4)"
    )

def downgrade():
    op.alter_column(
        'agro_data',
        'maydon',
        existing_type=sa.Numeric(18,4),
        type_=sa.Integer(),
        postgresql_using='maydon::integer'
    )

