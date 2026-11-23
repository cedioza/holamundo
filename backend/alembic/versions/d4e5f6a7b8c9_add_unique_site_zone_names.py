"""Nombres únicos de sedes y zonas.

Impide registrar dos sedes con el mismo nombre en un parqueadero y dos zonas
con el mismo nombre dentro de una misma sede. La validación amable (HTTP 409 con
el motivo) vive en los endpoints; esta restricción protege la integridad incluso
si se escribiera directamente en la base de datos.

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-11-23
"""
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_site_name_per_parking", "sites", ["parking_lot_id", "name"])
    op.create_unique_constraint("uq_zone_name_per_site", "zones", ["site_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_zone_name_per_site", "zones", type_="unique")
    op.drop_constraint("uq_site_name_per_parking", "sites", type_="unique")
