"""Clerk authentication for the dashboard API.

The dashboard (built by a teammate, hosted on Vercel) sends the Clerk session JWT
as `Authorization: Bearer <token>`. We verify it against Clerk's JWKS and return
the Clerk user id (`sub`). When Clerk isn't configured — local dev, the /simulate
demo — we fall back to a dev user so nothing is blocked.

Env:
  CLERK_ISSUER               e.g. https://your-app.clerk.accounts.dev
  CLERK_JWKS_URL             optional; defaults to {issuer}/.well-known/jwks.json
  CLERK_AUTHORIZED_PARTIES   optional CSV of allowed `azp` values (your domains)
  DEV_AUTH=true              force the dev-user bypass even if Clerk is configured
  DEV_USER_ID                dev user id (default: demo_user)
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException

CLERK_ISSUER = os.getenv("CLERK_ISSUER", "").rstrip("/")
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "") or (
    f"{CLERK_ISSUER}/.well-known/jwks.json" if CLERK_ISSUER else "")
CLERK_AUTHORIZED_PARTIES = [p.strip() for p in
                            os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",") if p.strip()]
DEV_AUTH = os.getenv("DEV_AUTH", "").lower() in ("1", "true", "yes")
DEV_USER_ID = os.getenv("DEV_USER_ID", "demo_user")

_jwks_client = None


def clerk_enabled() -> bool:
    return bool(CLERK_JWKS_URL) and not DEV_AUTH


def _client():
    global _jwks_client
    if _jwks_client is None:
        from jwt import PyJWKClient
        _jwks_client = PyJWKClient(CLERK_JWKS_URL)
    return _jwks_client


def _verify(token: str) -> str:
    import jwt
    key = _client().get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token, key, algorithms=["RS256"],
        issuer=CLERK_ISSUER or None,
        options={"verify_aud": False, "verify_iss": bool(CLERK_ISSUER)},
    )
    if CLERK_AUTHORIZED_PARTIES:
        azp = claims.get("azp")
        if azp and azp not in CLERK_AUTHORIZED_PARTIES:
            raise HTTPException(status_code=401, detail="unauthorized party")
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token has no subject")
    return sub


async def require_user(authorization: Optional[str] = Header(default=None),
                       x_dev_user: Optional[str] = Header(default=None)) -> str:
    """FastAPI dependency → the authenticated Clerk user id (or the dev user)."""
    if not clerk_enabled():
        return x_dev_user or DEV_USER_ID
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return _verify(token)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — any verify failure is a 401
        raise HTTPException(status_code=401, detail=f"invalid token: {e}")
