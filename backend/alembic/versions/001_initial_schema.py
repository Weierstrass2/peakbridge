"""Initial schema — devices, sensor_readings, alerts, control_logs, energy_savings, users."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("device_type", sa.String(32), nullable=False),
        sa.Column("building_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="offline"),
        sa.Column("registered_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_devices_device_id", "devices", ["device_id"])
    op.create_index("ix_devices_building_id", "devices", ["building_id"])

    op.create_table(
        "sensor_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.device_id"), nullable=False),
        sa.Column("sensor_type", sa.String(32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sensor_readings_device_id", "sensor_readings", ["device_id"])
    op.create_index("ix_sensor_readings_recorded_at", "sensor_readings", ["recorded_at"])
    op.create_index(
        "ix_sensor_readings_device_recorded",
        "sensor_readings",
        ["device_id", "recorded_at"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("building_id", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("grid_current", sa.Float(), nullable=False),
        sa.Column("ess_soc", sa.Float(), nullable=False),
        sa.Column("reduction_percent", sa.Float(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_alerts_building_id", "alerts", ["building_id"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    op.create_table(
        "control_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("building_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("triggered_by", sa.String(16), nullable=False),
        sa.Column("ess_soc_before", sa.Float(), nullable=False),
        sa.Column("ess_soc_after", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_control_logs_building_id", "control_logs", ["building_id"])

    op.create_table(
        "energy_savings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("building_id", sa.String(64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("saved_kwh", sa.Float(), server_default="0"),
        sa.Column("saved_won", sa.Float(), server_default="0"),
        sa.Column("co2_reduced_kg", sa.Float(), server_default="0"),
        sa.Column("peak_count", sa.Integer(), server_default="0"),
        sa.UniqueConstraint("building_id", "date", name="uq_energy_saving_building_date"),
    )
    op.create_index("ix_energy_savings_building_id", "energy_savings", ["building_id"])
    op.create_index("ix_energy_savings_date", "energy_savings", ["date"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), server_default="viewer"),
        sa.Column("building_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("energy_savings")
    op.drop_table("control_logs")
    op.drop_table("alerts")
    op.drop_table("sensor_readings")
    op.drop_table("devices")
