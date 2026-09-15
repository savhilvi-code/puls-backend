from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

from app.database.supabase import (
    SupabaseOperationError,
    SupabaseUnavailableError,
    create_user_record,
    find_user_by_fields,
    get_auth_user_from_bearer,
)
from app.schemas.user import UserRecord
from app.services.subscription_service import ensure_user_subscription


@dataclass(frozen=True)
class AuthIdentity:
    auth_user_id: str = ""
    email: str = ""
    name: str = ""
    is_verified: bool = False


def _bearer_token(request: Request | None) -> str:
    if request is None:
        return ""
    header = str(request.headers.get("authorization") or "").strip()
    if not header.lower().startswith("bearer "):
        return ""
    return header.split(" ", 1)[1].strip()


def _dev_identity_allowed() -> bool:
    return os.getenv("PULS_ALLOW_UNVERIFIED_DEV_AUTH", "").strip().lower() in {"1", "true", "yes"}


def resolve_identity(request: Request | None = None, payload: dict[str, Any] | None = None) -> AuthIdentity:
    token = _bearer_token(request)
    if token:
        verified = get_auth_user_from_bearer(token)
        return AuthIdentity(
            auth_user_id=verified.get("auth_user_id", ""),
            email=verified.get("email", ""),
            is_verified=True,
        )

    payload = payload or {}
    if _dev_identity_allowed():
        return AuthIdentity(
            auth_user_id=str(payload.get("auth_user_id") or "").strip(),
            email=str(payload.get("email") or "").strip().lower(),
            name=str(payload.get("username") or payload.get("first_name") or "").strip(),
            is_verified=False,
        )
    return AuthIdentity()


def transient_user(identity: AuthIdentity | None = None, *, language: str = "en") -> UserRecord:
    identity = identity or AuthIdentity()
    return UserRecord(
        id=None,
        auth_user_id=identity.auth_user_id,
        email=identity.email,
        username=identity.name,
        language=language or "en",
    )


async def get_or_create_profile(
    *,
    request: Request | None = None,
    payload: dict[str, Any] | None = None,
    require_auth: bool = False,
) -> UserRecord:
    payload = payload or {}
    identity = resolve_identity(request, payload)
    language = str(payload.get("language") or "en")
    if not identity.auth_user_id and not identity.email:
        if require_auth:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return transient_user(identity, language=language)

    try:
        existing = find_user_by_fields(auth_user_id=identity.auth_user_id, email=identity.email)
        if existing is not None:
            ensure_user_subscription(user_id=existing.id)
            return existing

        created = create_user_record(
            {
                "auth_user_id": identity.auth_user_id or None,
                "email": identity.email or None,
                "name": identity.name,
                "language": language,
                "source": "web",
            }
        )
        ensure_user_subscription(user_id=created.id)
        return created
    except (SupabaseUnavailableError, SupabaseOperationError) as exc:
        if require_auth:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return transient_user(identity, language=language)
