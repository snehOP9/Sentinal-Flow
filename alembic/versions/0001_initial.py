"""initial audit schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transaction_decisions",
        sa.Column("transaction_id", sa.String(length=80), primary_key=True),
        sa.Column("customer_id", sa.String(length=80), nullable=False), sa.Column("card_id", sa.String(length=80), nullable=False),
        sa.Column("merchant_id", sa.String(length=100), nullable=False), sa.Column("merchant_category", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False), sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_probability", sa.Float(), nullable=False), sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False), sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False), sa.Column("feature_snapshot", sa.JSON(), nullable=False),
        sa.Column("explanations", sa.JSON(), nullable=False), sa.Column("state_update_status", sa.String(length=24), nullable=False),
        sa.Column("confirmed_fraud", sa.Boolean(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_decisions_created_at", "transaction_decisions", ["created_at"])
    op.create_index("ix_decisions_decision_created", "transaction_decisions", ["decision", "created_at"])
    op.create_index("ix_decisions_customer_created", "transaction_decisions", ["customer_id", "created_at"])
    op.create_table("audit_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("transaction_id", sa.String(length=80), nullable=False), sa.Column("event_type", sa.String(length=64), nullable=False), sa.Column("detail", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index("ix_audit_events_transaction_id", "audit_events", ["transaction_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("transaction_decisions")
