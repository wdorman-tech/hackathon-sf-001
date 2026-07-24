"""Auth + webhook-signature gating.

These cover the fail-open cases, which are the ones that actually bite: the app
is meant to run wide open locally (so `/simulate` and the dashboard need no
setup) and locked down in production. The tests pin the boundary between those
two, since getting it wrong in the quiet direction is invisible until someone
reads another user's deals.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest
from fastapi import HTTPException


def _auth(monkeypatch, **env):
    """Reload app.auth with a specific environment (module reads env at import)."""
    for k in ("CLERK_ISSUER", "CLERK_JWKS_URL", "CLERK_AUTHORIZED_PARTIES",
              "DEV_AUTH", "DEV_USER_ID", "VERCEL_ENV"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.auth as auth
    return importlib.reload(auth)


@pytest.fixture(autouse=True)
def _restore():
    yield
    import app.auth
    importlib.reload(app.auth)          # leave the module as the rest of the suite expects


# ── the dev bypass ───────────────────────────────────────────────────────────
def test_local_unconfigured_falls_back_to_dev_user(monkeypatch):
    auth = _auth(monkeypatch)
    assert asyncio.run(auth.require_user(None, None)) == "demo_user"


def test_production_without_clerk_fails_closed(monkeypatch):
    """The important one: a prod deploy that forgot the Clerk vars must not
    authenticate everyone as whoever they claim to be."""
    auth = _auth(monkeypatch, VERCEL_ENV="production")
    with pytest.raises(HTTPException) as e:
        asyncio.run(auth.require_user(None, "victim_user_id"))
    assert e.value.status_code == 503


def test_production_with_explicit_dev_auth_still_opens(monkeypatch):
    """Explicitly asking for an open deployment is allowed — it just can't happen
    by accident."""
    auth = _auth(monkeypatch, VERCEL_ENV="production", DEV_AUTH="true")
    assert asyncio.run(auth.require_user(None, "whoever")) == "whoever"


def test_dev_user_header_picks_the_identity_locally(monkeypatch):
    auth = _auth(monkeypatch)
    assert asyncio.run(auth.require_user(None, "alice")) == "alice"


# ── clerk_enabled() ──────────────────────────────────────────────────────────
def test_jwks_without_issuer_does_not_enable_clerk(monkeypatch):
    """Without an issuer we can't verify `iss`, so this config is not 'enabled'."""
    auth = _auth(monkeypatch, CLERK_JWKS_URL="https://x.clerk.accounts.dev/jwks")
    assert not auth.clerk_enabled()


def test_issuer_alone_enables_clerk_and_derives_jwks(monkeypatch):
    auth = _auth(monkeypatch, CLERK_ISSUER="https://x.clerk.accounts.dev")
    assert auth.clerk_enabled()
    assert auth.CLERK_JWKS_URL == "https://x.clerk.accounts.dev/.well-known/jwks.json"


def test_dev_auth_disables_clerk_even_when_configured(monkeypatch):
    auth = _auth(monkeypatch, CLERK_ISSUER="https://x.clerk.accounts.dev", DEV_AUTH="true")
    assert not auth.clerk_enabled()


def test_configured_clerk_rejects_missing_bearer(monkeypatch):
    auth = _auth(monkeypatch, CLERK_ISSUER="https://x.clerk.accounts.dev")
    with pytest.raises(HTTPException) as e:
        asyncio.run(auth.require_user(None, "alice"))      # X-Dev-User must not help here
    assert e.value.status_code == 401


def test_configured_clerk_rejects_garbage_token(monkeypatch):
    auth = _auth(monkeypatch, CLERK_ISSUER="https://x.clerk.accounts.dev")
    with pytest.raises(HTTPException) as e:
        asyncio.run(auth.require_user("Bearer not.a.jwt", None))
    assert e.value.status_code == 401


# ── authorized parties ───────────────────────────────────────────────────────
def test_token_without_azp_is_rejected_when_parties_configured(monkeypatch):
    """A session minted for another front-end on the same Clerk instance has no
    azp we recognise — it used to pass."""
    auth = _auth(monkeypatch, CLERK_ISSUER="https://x.clerk.accounts.dev",
                 CLERK_AUTHORIZED_PARTIES="https://closer.vercel.app")
    monkeypatch.setattr(auth, "_client", lambda: _FakeJWKS())
    monkeypatch.setattr("jwt.decode", lambda *a, **kw: {"sub": "u1"})
    with pytest.raises(HTTPException) as e:
        auth._verify("t")
    assert e.value.detail == "unauthorized party"


def test_token_with_wrong_azp_is_rejected(monkeypatch):
    auth = _auth(monkeypatch, CLERK_ISSUER="https://x.clerk.accounts.dev",
                 CLERK_AUTHORIZED_PARTIES="https://closer.vercel.app")
    monkeypatch.setattr(auth, "_client", lambda: _FakeJWKS())
    monkeypatch.setattr("jwt.decode", lambda *a, **kw: {"sub": "u1", "azp": "https://evil.com"})
    with pytest.raises(HTTPException):
        auth._verify("t")


def test_token_with_right_azp_passes(monkeypatch):
    auth = _auth(monkeypatch, CLERK_ISSUER="https://x.clerk.accounts.dev",
                 CLERK_AUTHORIZED_PARTIES="https://closer.vercel.app")
    monkeypatch.setattr(auth, "_client", lambda: _FakeJWKS())
    monkeypatch.setattr("jwt.decode",
                        lambda *a, **kw: {"sub": "u1", "azp": "https://closer.vercel.app"})
    assert auth._verify("t") == "u1"


class _FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": "fake"})()


# ── webhook signatures ───────────────────────────────────────────────────────
def _linq(monkeypatch, **env):
    for k in ("VERIFY_LINQ_SIGNATURES", "LINQ_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.linq as linq
    return importlib.reload(linq)


def test_no_secret_no_flag_is_unverified_demo_default(monkeypatch):
    linq = _linq(monkeypatch)
    assert linq.verify_signature(b"{}", None) is True


def test_configured_secret_is_enforced_without_the_flag(monkeypatch):
    """Setting a secret but forgetting VERIFY_LINQ_SIGNATURES used to leave the
    webhook open to anyone who knew the URL."""
    linq = _linq(monkeypatch, LINQ_WEBHOOK_SECRET="s3cret")
    assert linq.signatures_enforced()
    assert linq.verify_signature(b"{}", None) is False
    assert linq.verify_signature(b"{}", "sha256=deadbeef") is False


def test_valid_signature_accepted(monkeypatch):
    import hashlib
    import hmac
    linq = _linq(monkeypatch, LINQ_WEBHOOK_SECRET="s3cret")
    body = b'{"event_type":"message.received"}'
    sig = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert linq.verify_signature(body, f"sha256={sig}") is True
    assert linq.verify_signature(body + b" ", f"sha256={sig}") is False


def test_flag_without_secret_fails_closed(monkeypatch):
    linq = _linq(monkeypatch, VERIFY_LINQ_SIGNATURES="true")
    assert linq.verify_signature(b"{}", "sha256=whatever") is False
