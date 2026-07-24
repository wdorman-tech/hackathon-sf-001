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
# Vercel sets VERCEL_ENV=production on a prod deployment. We refuse to fail open there.
IS_PRODUCTION = os.getenv("VERCEL_ENV", "").lower() == "production"

_jwks_client = None


def clerk_enabled() -> bool:
    # Issuer is required, not optional: without it we can't verify `iss`, and a
    # token from any other Clerk instance would only need to be signed by a key
    # our configured JWKS endpoint happens to serve.
    return bool(CLERK_JWKS_URL and CLERK_ISSUER) and not DEV_AUTH


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
        token, key, algorithms=["RS256"],       # never "none", never HS* (key confusion)
        issuer=CLERK_ISSUER,
        options={"verify_aud": False, "verify_iss": True, "require": ["exp", "iss", "sub"]},
    )
    if CLERK_AUTHORIZED_PARTIES:
        # A token with NO azp used to sail through this check — meaning a session
        # minted for a different front-end on the same Clerk instance was accepted.
        azp = claims.get("azp")
        if not azp or azp not in CLERK_AUTHORIZED_PARTIES:
            raise HTTPException(status_code=401, detail="unauthorized party")
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token has no subject")
    return sub


async def require_user(authorization: Optional[str] = Header(default=None),
                       x_dev_user: Optional[str] = Header(default=None)) -> str:
    """FastAPI dependency → the authenticated Clerk user id (or the dev user).

    The dev path is a real bypass — `X-Dev-User` lets the caller name whatever user
    id it likes, which is total access to every other user's deals. So it is gated:
    unconfigured Clerk falls back to the dev user LOCALLY, but on a production
    deployment it is a 503, not an open door. Shipping to prod with the Clerk env
    vars unset should break loudly, never silently authenticate the world.
    """
    if not clerk_enabled():
        if IS_PRODUCTION and not DEV_AUTH:
            raise HTTPException(status_code=503,
                                detail="auth not configured (set CLERK_ISSUER, or "
                                       "DEV_AUTH=true to intentionally run open)")
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
