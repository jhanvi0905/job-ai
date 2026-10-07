"""Supabase Auth, verified in FastAPI.

Sign-up, login, password reset, magic links and OAuth all happen in the browser
against Supabase. Every API request carries `Authorization: Bearer <Supabase
access token>`; this module verifies it locally (JWKS, cached; or the legacy
HS256 project secret) and maps `sub` to our own `users` row, creating it on
first sight (just-in-time provisioning). Every other service takes a `user_id`
— only `get_current_user` turns a token into one.
"""
from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from jobai.product import observability
from jobai.product.api.deps import get_session
from jobai.product.db.models import ErasedAccount, User
from jobai.product.services import ratelimit

log = logging.getLogger(__name__)

AUDIENCE = "authenticated"
ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]
LEGACY_ALGORITHMS = ["HS256"]
JWKS_CACHE_SECONDS = 600
LEEWAY_SECONDS = 30  # clock skew between Supabase and us

TokenVerifier = Callable[[str], dict[str, Any]]


class AuthError(Exception):
    pass


class EmailConflict(Exception):
    """A verified token's email already belongs to a row linked to a different Supabase identity."""


def app_env() -> str:
    return os.environ.get("APP_ENV", "dev").strip().lower()


def is_dev() -> bool:
    return app_env() in ("dev", "development", "test")


def is_prod() -> bool:
    return app_env() in ("prod", "production")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


# ------------------------------------------------------------- verification
class SupabaseVerifier:
    """Callable `token -> claims`. Accepts ES256/RS256 tokens whose key is in the
    project's JWKS, or HS256 tokens when the legacy `jwt_secret` is configured.
    Always checks signature, `exp`, `aud == "authenticated"` and
    `iss == {SUPABASE_URL}/auth/v1`.

    `key_resolver(token) -> key` replaces the JWKS lookup (tests use a local
    keypair so nothing touches the network)."""

    def __init__(self, base_url: str, jwt_secret: str | None = None,
                 key_resolver: Callable[[str], Any] | None = None):
        base_url = base_url.rstrip("/")
        self.issuer = f"{base_url}/auth/v1"
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        self.jwt_secret = jwt_secret or None
        self._key_resolver = key_resolver
        self._jwks: jwt.PyJWKClient | None = None

    def _asymmetric_key(self, token: str):
        if self._key_resolver is not None:
            return self._key_resolver(token)
        if self._jwks is None:  # lazy: no network at startup; keys cached for JWKS_CACHE_SECONDS
            self._jwks = jwt.PyJWKClient(self.jwks_url, cache_keys=True, lifespan=JWKS_CACHE_SECONDS, timeout=5)
        return self._jwks.get_signing_key_from_jwt(token).key

    def __call__(self, token: str) -> dict[str, Any]:
        try:
            alg = jwt.get_unverified_header(token).get("alg")
            if alg in LEGACY_ALGORITHMS:
                if not self.jwt_secret:
                    raise AuthError("HS256 token but SUPABASE_JWT_SECRET is not configured")
                key, algorithms = self.jwt_secret, LEGACY_ALGORITHMS
            elif alg in ASYMMETRIC_ALGORITHMS:
                key, algorithms = self._asymmetric_key(token), ASYMMETRIC_ALGORITHMS
            else:
                raise AuthError(f"unsupported token algorithm {alg!r}")
            return jwt.decode(
                token, key, algorithms=algorithms, audience=AUDIENCE, issuer=self.issuer, leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWKClientError as exc:  # JWKS unreachable or kid unknown
            log.warning("JWKS lookup failed: %s", exc)
            raise AuthError("could not resolve signing key") from exc
        except jwt.PyJWTError as exc:
            raise AuthError(f"invalid token: {exc}") from exc


def verifier_from_env() -> TokenVerifier | None:
    url = supabase_url()
    if not url:
        return None
    return SupabaseVerifier(url, jwt_secret=os.environ.get("SUPABASE_JWT_SECRET") or None)


def check_auth_config(verifier: TokenVerifier | None) -> None:
    """Called at app startup: outside dev, refuse to run without a way to verify tokens."""
    if verifier is not None:
        return
    if is_dev():
        log.warning("SUPABASE_URL is not set: every authenticated endpoint will return 401")
        return
    raise RuntimeError("SUPABASE_URL must be set when APP_ENV is not dev")


# ------------------------------------------------------------- provisioning
def _by_auth_id(session: Session, auth_id: uuid.UUID) -> User | None:
    return session.scalar(select(User).where(User.auth_id == auth_id))


def provision_user(session: Session, claims: dict[str, Any]) -> User:
    """Map verified claims to a `users` row, creating or linking it on first sight.

    Order: existing row for `sub` → legacy row with the same email and no
    auth_id (linked, not duplicated) → new free-plan row. Concurrent first
    requests race on the unique `auth_id`/`email` indexes; the loser rolls back
    its savepoint and re-reads the winner's row."""
    try:
        auth_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthError("token subject is not a user id") from exc
    if claims.get("is_anonymous"):
        raise AuthError("anonymous sessions are not accepted")

    user = _by_auth_id(session, auth_id)
    if user is not None:
        if user.deleted_at is not None:
            raise AuthError("account deleted")
        return user
    if session.get(ErasedAccount, auth_id) is not None:
        raise AuthError("account deleted")

    email = normalize_email(str(claims.get("email") or ""))
    if "@" not in email or len(email) > 320:
        raise AuthError("token has no usable email")

    for _ in range(2):
        existing = session.scalar(select(User).where(User.email == email))
        if existing is not None:
            if existing.auth_id is not None and existing.auth_id != auth_id:
                raise EmailConflict(email)
            if existing.deleted_at is not None:
                raise AuthError("account deleted")
            existing.auth_id = auth_id  # link the legacy (pre-Supabase) row
            session.flush()
            return existing
        try:
            with session.begin_nested():
                user = User(email=email, auth_id=auth_id, plan="free")
                session.add(user)
            return user
        except IntegrityError:
            # Another request provisioned this identity (or email) between our read and insert.
            user = _by_auth_id(session, auth_id)
            if user is not None:
                return user
    raise AuthError("could not provision user")


# ---------------------------------------------------------------- dependency
_bearer = HTTPBearer(auto_error=False)
LAST_SEEN_RESOLUTION = timedelta(hours=1)  # write users.last_seen_at at most hourly


def _touch(user: User) -> None:
    now = datetime.now(UTC)
    seen = user.last_seen_at
    if seen is not None and seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    if seen is None or now - seen > LAST_SEEN_RESOLUTION:
        user.last_seen_at = now


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    unauth = HTTPException(status_code=401, detail="not authenticated", headers={"WWW-Authenticate": "Bearer"})
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if creds is None or verifier is None:
        raise unauth
    try:
        user = provision_user(session, verifier(creds.credentials))
    except AuthError:
        raise unauth from None
    except EmailConflict:
        raise HTTPException(409, "this email is linked to a different sign-in; contact support") from None
    observability.bind(user_id=user.id)
    request.state.user_id = user.id
    _touch(user)
    if request.method in ratelimit.WRITE_METHODS:  # every authenticated write: 60/min/user
        ratelimit.check(request, "write", user.id)
    return user


# ------------------------------------------------------------ admin (erasure)
class SupabaseAdmin:
    """Service-role calls to the Supabase Auth Admin API. Backend-only secret."""

    def __init__(self, base_url: str, service_role_key: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._key = service_role_key
        self._client = client or httpx.Client(timeout=10)

    @classmethod
    def from_env(cls) -> SupabaseAdmin | None:
        url, key = supabase_url(), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        return cls(url, key) if url and key else None

    def delete_user(self, auth_id: uuid.UUID) -> None:
        """Hard-delete the auth user. 404 (already gone) counts as success."""
        r = self._client.delete(
            f"{self.base_url}/auth/v1/admin/users/{auth_id}",
            headers={"apikey": self._key, "Authorization": f"Bearer {self._key}"},
        )
        if r.status_code != 404:
            r.raise_for_status()
