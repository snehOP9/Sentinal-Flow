from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Permission(StrEnum):
    TRANSACTION_READ = "transaction.read"
    TRANSACTION_SCORE = "transaction.score"
    CASE_READ = "case.read"
    CASE_ASSIGN = "case.assign"
    CASE_DECIDE = "case.decide"
    OUTCOME_WRITE = "outcome.write"
    POLICY_READ = "policy.read"
    POLICY_PROPOSE = "policy.propose"
    POLICY_APPROVE = "policy.approve"
    MODEL_READ = "model.read"
    MODEL_PROMOTE = "model.promote"
    MONITORING_READ = "monitoring.read"
    AUDIT_READ = "audit.read"
    INTEGRATION_MANAGE = "integration.manage"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "platform_admin": frozenset(Permission),
    "tenant_admin": frozenset(Permission),
    "risk_manager": frozenset(
        {
            Permission.TRANSACTION_READ,
            Permission.CASE_READ,
            Permission.CASE_ASSIGN,
            Permission.CASE_DECIDE,
            Permission.OUTCOME_WRITE,
            Permission.POLICY_READ,
            Permission.POLICY_PROPOSE,
            Permission.POLICY_APPROVE,
            Permission.MODEL_READ,
            Permission.MONITORING_READ,
            Permission.AUDIT_READ,
        }
    ),
    "analyst": frozenset(
        {
            Permission.TRANSACTION_READ,
            Permission.TRANSACTION_SCORE,
            Permission.CASE_READ,
            Permission.CASE_ASSIGN,
            Permission.CASE_DECIDE,
            Permission.OUTCOME_WRITE,
            Permission.POLICY_READ,
            Permission.MODEL_READ,
            Permission.MONITORING_READ,
        }
    ),
    "reviewer": frozenset(
        {
            Permission.TRANSACTION_READ,
            Permission.CASE_READ,
            Permission.CASE_DECIDE,
            Permission.OUTCOME_WRITE,
            Permission.POLICY_READ,
            Permission.MODEL_READ,
            Permission.MONITORING_READ,
        }
    ),
    "viewer": frozenset(
        {
            Permission.TRANSACTION_READ,
            Permission.CASE_READ,
            Permission.POLICY_READ,
            Permission.MODEL_READ,
            Permission.MONITORING_READ,
        }
    ),
    "model_operator": frozenset(
        {
            Permission.TRANSACTION_READ,
            Permission.MODEL_READ,
            Permission.MODEL_PROMOTE,
            Permission.MONITORING_READ,
            Permission.AUDIT_READ,
        }
    ),
    "integration_service": frozenset(
        {
            Permission.TRANSACTION_READ,
            Permission.TRANSACTION_SCORE,
            Permission.OUTCOME_WRITE,
        }
    ),
}

# Kept only for continuity with the local demo labels from the previous version.
ROLE_ALIASES = {"admin": "tenant_admin"}


@dataclass(frozen=True)
class Principal:
    subject: str
    organization_id: str
    roles: frozenset[str]
    permissions: frozenset[Permission]
    authentication_method: str
    api_key_id: str | None = None

    def allows(self, permission: Permission) -> bool:
        return permission in self.permissions


def permissions_for_roles(roles: set[str] | list[str]) -> frozenset[Permission]:
    normalized = {ROLE_ALIASES.get(role, role) for role in roles}
    return frozenset().union(*(ROLE_PERMISSIONS.get(role, frozenset()) for role in normalized))
