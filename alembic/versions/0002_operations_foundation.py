"""tenant-aware operations foundation

Revision ID: 0002_operations_foundation
Revises: 0001_initial
Create Date: 2026-08-31

The migration preserves the original physical transaction primary-key name while
adding a tenant-scoped external identifier. Existing development rows are assigned
to the synthetic demo organization during upgrade.
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_operations_foundation"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.execute("INSERT INTO organizations (id, name, status) VALUES ('org_demo', 'SentinelFlow Synthetic Demo', 'active')")

    # New writes never use the legacy float amount. It remains for backwards read
    # compatibility while amount_minor + ISO currency is authoritative.
    op.add_column("transaction_decisions", sa.Column("organization_id", sa.String(length=80), nullable=False, server_default="org_demo"))
    op.add_column("transaction_decisions", sa.Column("external_transaction_id", sa.String(length=120), nullable=True))
    op.execute("UPDATE transaction_decisions SET external_transaction_id = transaction_id WHERE external_transaction_id IS NULL")
    op.add_column("transaction_decisions", sa.Column("program_id", sa.String(length=80), nullable=False, server_default="default"))
    op.add_column("transaction_decisions", sa.Column("channel", sa.String(length=16), nullable=False, server_default="unknown"))
    op.add_column("transaction_decisions", sa.Column("location", sa.String(length=32), nullable=False, server_default="UNKNOWN"))
    op.add_column("transaction_decisions", sa.Column("amount_minor", sa.BigInteger(), nullable=False, server_default="0"))
    op.execute("UPDATE transaction_decisions SET amount_minor = CAST(ROUND(amount * 100) AS BIGINT) WHERE amount_minor = 0")
    op.add_column("transaction_decisions", sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"))
    op.add_column("transaction_decisions", sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.add_column("transaction_decisions", sa.Column("policy_version", sa.String(length=80), nullable=False, server_default="legacy-unversioned"))
    op.add_column("transaction_decisions", sa.Column("request_fingerprint", sa.String(length=64), nullable=False, server_default="legacy-unverified"))
    op.add_column("transaction_decisions", sa.Column("client_id", sa.String(length=120), nullable=False, server_default="legacy"))
    op.create_foreign_key("fk_decision_organization", "transaction_decisions", "organizations", ["organization_id"], ["id"], ondelete="RESTRICT")
    op.create_unique_constraint("uq_decision_org_external_transaction", "transaction_decisions", ["organization_id", "external_transaction_id"])
    op.create_index("ix_decisions_org_created", "transaction_decisions", ["organization_id", "created_at"])
    op.create_index("ix_decisions_org_decision_created", "transaction_decisions", ["organization_id", "decision", "created_at"])
    op.create_index("ix_decisions_org_customer_created", "transaction_decisions", ["organization_id", "customer_id", "created_at"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("endpoint", sa.String(length=160), nullable=False),
        sa.Column("client_id", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("transaction_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transaction_decisions.transaction_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "endpoint", "client_id", "idempotency_key", name="uq_idempotency_scope"),
    )
    op.create_table(
        "cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("transaction_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("queue", sa.String(length=80), nullable=False, server_default="risk-review"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("assigned_to", sa.String(length=160)),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transaction_decisions.transaction_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_cases_org_queue_opened", "cases", ["organization_id", "queue", "status", "opened_at"])
    op.create_table(
        "case_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_case_events_org_case_created", "case_events", ["organization_id", "case_id", "created_at"])
    op.create_table(
        "review_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("advisory_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_review_actions_org_case_created", "review_actions", ["organization_id", "case_id", "created_at"])
    op.create_table(
        "outcomes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("transaction_id", sa.String(length=80), nullable=False),
        sa.Column("confirmed_fraud", sa.Boolean(), nullable=False),
        sa.Column("maturity_state", sa.String(length=24), nullable=False, server_default="observed"),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("recorded_by", sa.String(length=160), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transaction_decisions.transaction_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "transaction_id", name="uq_outcome_transaction"),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("transaction_id", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_error", sa.Text()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transaction_decisions.transaction_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_outbox_org_status_available", "outbox_events", ["organization_id", "status", "available_at"])
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_api_keys_organization_status", "api_keys", ["organization_id", "revoked_at"])

    op.add_column("audit_events", sa.Column("organization_id", sa.String(length=80), nullable=False, server_default="org_demo"))
    op.add_column("audit_events", sa.Column("case_id", sa.String(length=36), nullable=True))
    op.add_column("audit_events", sa.Column("actor_id", sa.String(length=160), nullable=False, server_default="legacy"))
    op.add_column("audit_events", sa.Column("request_id", sa.String(length=80), nullable=True))
    op.create_index("ix_audit_events_org_created", "audit_events", ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_org_created", table_name="audit_events")
    op.drop_column("audit_events", "request_id")
    op.drop_column("audit_events", "actor_id")
    op.drop_column("audit_events", "case_id")
    op.drop_column("audit_events", "organization_id")
    op.drop_index("ix_api_keys_organization_status", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_outbox_org_status_available", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_table("outcomes")
    op.drop_index("ix_review_actions_org_case_created", table_name="review_actions")
    op.drop_table("review_actions")
    op.drop_index("ix_case_events_org_case_created", table_name="case_events")
    op.drop_table("case_events")
    op.drop_index("ix_cases_org_queue_opened", table_name="cases")
    op.drop_table("cases")
    op.drop_table("idempotency_records")
    op.drop_index("ix_decisions_org_customer_created", table_name="transaction_decisions")
    op.drop_index("ix_decisions_org_decision_created", table_name="transaction_decisions")
    op.drop_index("ix_decisions_org_created", table_name="transaction_decisions")
    op.drop_constraint("uq_decision_org_external_transaction", "transaction_decisions", type_="unique")
    op.drop_constraint("fk_decision_organization", "transaction_decisions", type_="foreignkey")
    for column in ["client_id", "request_fingerprint", "policy_version", "ingested_at", "currency", "amount_minor", "location", "channel", "program_id", "external_transaction_id", "organization_id"]:
        op.drop_column("transaction_decisions", column)
    op.drop_table("organizations")
