from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi import Request
from jwt import InvalidTokenError, PyJWKClient

from fraud_platform.auth.permissions import (
    ROLE_ALIASES,
    ROLE_PERMISSIONS,
    Permission,
    Principal,
    permissions_for_roles,
)
from fraud_platform.config import Settings
from fraud_platform.database.repository import DecisionRepository


class AuthenticationError(Exception):
    """A caller did not present a valid identity credential."""


class AuthenticationService:
    """Resolve a tenant-bound principal from a local-demo credential or verified JWT.

    OIDC validation intentionally happens in the API service, not in browser code.
    The configured issuer/audience/JWKS are mandatory outside development/test.
    """

    def __init__(self, settings: Settings, repository: DecisionRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.jwks = PyJWKClient(settings.oidc_jwks_url) if settings.oidc_jwks_url else None

    async def authenticate(self, request: Request) -> Principal:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return await self._api_key_principal(api_key)
        if self.settings.auth_mode == "demo":
            return self._demo_principal(request)
        return self._oidc_principal(request)

    async def _api_key_principal(self, raw_key: str) -> Principal:
        """Validate only a SHA-256 verifier; raw API keys are never persisted."""
        parts = raw_key.split("_", 2)
        if len(parts) != 3 or parts[0] != "sfk" or not parts[1] or not parts[2]:
            raise AuthenticationError("Malformed API key")
        prefix = f"{parts[0]}_{parts[1]}"
        record = await self.repository.api_key_by_prefix(prefix)
        if record is None or record.revoked_at is not None:
            raise AuthenticationError("Unknown or revoked API key")
        if record.expires_at and record.expires_at <= datetime.now(UTC):
            raise AuthenticationError("Expired API key")
        candidate_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(record.key_hash, candidate_hash):
            raise AuthenticationError("Unknown or revoked API key")
        try:
            granted = frozenset(Permission(value) for value in record.permissions)
        except ValueError as exc:
            raise AuthenticationError("API key has invalid configured scopes") from exc
        await self.repository.touch_api_key(record.id)
        return Principal(
            subject=f"api_key:{record.id}",
            organization_id=record.organization_id,
            roles=frozenset({"integration_service"}),
            permissions=granted,
            authentication_method="api_key",
            api_key_id=record.id,
        )

    def _demo_principal(self, request: Request) -> Principal:
        if not self.settings.demo_auth_enabled or self.settings.environment not in {
            "development",
            "test",
        }:
            raise AuthenticationError("Demo authentication is disabled")
        requested_role = request.headers.get("X-Demo-Role", "viewer").lower()
        role = ROLE_ALIASES.get(requested_role, requested_role)
        if role not in ROLE_PERMISSIONS:
            raise AuthenticationError("Unknown demo role")
        return Principal(
            subject=f"demo:{role}",
            organization_id=self.settings.demo_organization_id,
            roles=frozenset({role}),
            permissions=permissions_for_roles({role}),
            authentication_method="demo",
        )

    def _oidc_principal(self, request: Request) -> Principal:
        token = self._bearer_token(request)
        if self.jwks is None or not self.settings.oidc_issuer or not self.settings.oidc_audience:
            raise AuthenticationError("OIDC is not configured")
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                audience=self.settings.oidc_audience,
                issuer=self.settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except InvalidTokenError as exc:
            raise AuthenticationError("Invalid or expired bearer token") from exc
        organization = claims.get(self.settings.oidc_organization_claim)
        if not isinstance(organization, str) or not organization:
            raise AuthenticationError("Token has no organization context")
        roles = self._roles(claims)
        if not roles:
            raise AuthenticationError("Token has no recognized SentinelFlow role")
        return Principal(
            subject=str(claims["sub"]),
            organization_id=organization,
            roles=frozenset(roles),
            permissions=permissions_for_roles(roles),
            authentication_method="oidc",
        )

    @staticmethod
    def _bearer_token(request: Request) -> str:
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthenticationError("A bearer token is required")
        return token

    def _roles(self, claims: dict[str, Any]) -> set[str]:
        raw: Any = claims.get(self.settings.oidc_roles_claim, [])
        if isinstance(raw, str):
            values: Iterable[Any] = raw.split()
        elif isinstance(raw, list):
            values = raw
        else:
            values = []
        roles = {ROLE_ALIASES.get(str(value), str(value)) for value in values}
        return {role for role in roles if role in ROLE_PERMISSIONS}
