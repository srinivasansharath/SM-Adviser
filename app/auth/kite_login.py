"""Kite access-token management for the daily headless run.

Kite's access_token expires every morning. This module obtains and caches one per day:

  1. Official path (default, ToS-compliant): you obtain a `request_token` via the Kite
     login redirect once, then `exchange_request_token()` swaps it for an access_token.
  2. Automated path (opt-in): `fetch_request_token()` drives Kite's internal web login
     endpoints (/api/login -> /api/twofa -> /connect/login) with your TOTP secret to get
     a request_token with no human in the loop — this is what enables the unattended cron.

WARNING: the automated path uses Kite's *internal* web endpoints and automates 2FA, which
is against Zerodha's API ToS / exchange rules. Use it only for your own personal account.
If uncomfortable, leave KITE_USER_ID/PASSWORD/TOTP_SECRET unset and refresh the token
manually via exchange_request_token().
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from ..config import REPO_ROOT, Settings, get_settings

KITE_LOGIN_URL = "https://kite.zerodha.com/api/login"
KITE_TWOFA_URL = "https://kite.zerodha.com/api/twofa"
KITE_CONNECT_LOGIN_URL = "https://kite.zerodha.com/connect/login"


class AutoLoginError(RuntimeError):
    pass


def _request_token_from(url: str | None) -> str | None:
    if not url:
        return None
    tok = parse_qs(urlparse(url).query).get("request_token")
    return tok[0] if tok else None


def _safe_json(resp) -> dict:
    """Kite's login endpoints occasionally return an empty/non-JSON body on a transient hiccup.
    Treat that as 'no data' so the caller raises a clear AutoLoginError (and retries) instead of
    crashing with a raw JSONDecodeError."""
    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def fetch_request_token(
    *,
    api_key: str,
    user_id: str,
    password: str,
    totp_secret: str,
    client=None,
    totp_now: Callable[[], str] | None = None,
    max_redirects: int = 10,
    retries: int = 3,
    retry_delay: float = 2.0,
    sleep: Callable[[float], None] | None = None,
) -> str:
    """Headless login via Kite's internal web flow. Returns a request_token.

    The headless TOTP login is the daily run's flakiest external step, so a transient blip (empty
    body, network wobble, momentary Kite 5xx) is retried up to `retries` times with linear backoff,
    regenerating the TOTP each attempt. `client`, `totp_now`, and `sleep` are injectable for tests.
    """
    close = False
    if client is None:  # pragma: no cover - real network path
        import httpx

        client = httpx.Client(
            timeout=15,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0", "X-Kite-Version": "3"},
        )
        close = True
    if totp_now is None:  # pragma: no cover - real TOTP path
        import pyotp

        totp_now = lambda: pyotp.TOTP(totp_secret).now()  # noqa: E731
    if sleep is None:
        sleep = time.sleep

    def _attempt() -> str:
        r1 = client.post(KITE_LOGIN_URL, data={"user_id": user_id, "password": password})
        request_id = (_safe_json(r1).get("data") or {}).get("request_id")
        if not request_id:
            raise AutoLoginError(
                f"login step returned no request_id (status "
                f"{getattr(r1, 'status_code', '?')}): {getattr(r1, 'text', r1)!r}"
            )

        r2 = client.post(
            KITE_TWOFA_URL,
            data={
                "user_id": user_id,
                "request_id": request_id,
                "twofa_value": totp_now(),
                "twofa_type": "totp",
                "skip_session": "true",
            },
        )
        if getattr(r2, "status_code", 200) != 200:
            raise AutoLoginError(f"2FA step failed: {getattr(r2, 'status_code', '?')}")

        url = f"{KITE_CONNECT_LOGIN_URL}?api_key={api_key}&v=3"
        for _ in range(max_redirects):
            resp = client.get(url, follow_redirects=False)
            location = resp.headers.get("location")
            token = _request_token_from(location) or _request_token_from(str(getattr(resp, "url", "")))
            if token:
                return token
            if not location:
                break
            url = location
        raise AutoLoginError("no request_token found in the login redirect chain")

    try:
        last: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                return _attempt()
            except Exception as e:  # transient Kite/network failure — back off and retry
                last = e
                if attempt < retries:
                    sleep(retry_delay * attempt)  # linear backoff: 2s, 4s, ...
        raise AutoLoginError(
            f"headless login failed after {retries} attempts; last error: {last}"
        ) from last
    finally:
        if close:  # pragma: no cover
            client.close()


def exchange_request_token(api_key: str, api_secret: str, request_token: str, kite=None) -> str:
    """Official ToS-compliant swap: request_token -> access_token via generate_session."""
    if kite is None:  # pragma: no cover - real SDK path
        from kiteconnect import KiteConnect

        kite = KiteConnect(api_key=api_key)
    session = kite.generate_session(request_token, api_secret=api_secret)
    return session["access_token"]


@dataclass
class TokenStore:
    """Caches the day's access_token on disk (gitignored; chmod 600)."""

    path: Path

    def load_today(self, today: date) -> str | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return data.get("access_token") if data.get("date") == today.isoformat() else None

    def save(self, today: date, access_token: str) -> None:
        self.path.write_text(json.dumps({"date": today.isoformat(), "access_token": access_token}))
        try:
            self.path.chmod(0o600)
        except OSError:  # pragma: no cover
            pass


def _default_store() -> TokenStore:
    return TokenStore(REPO_ROOT / "kite_token.json")


def get_access_token(
    settings: Settings | None = None,
    *,
    today: date | None = None,
    store: TokenStore | None = None,
    kite=None,
    http_client=None,
) -> str:
    """Return today's cached access_token, or obtain one via automated login and cache it."""
    s = settings or get_settings()
    today = today or date.today()
    store = store or _default_store()

    cached = store.load_today(today)
    if cached:
        return cached

    if not (s.kite_api_key and s.kite_api_secret):
        raise AutoLoginError("KITE_API_KEY / KITE_API_SECRET not set — cannot obtain an access token")
    if not (s.kite_user_id and s.kite_password and s.kite_totp_secret):
        raise AutoLoginError(
            "No cached token for today and automated-login creds are missing. Either set "
            "KITE_USER_ID/KITE_PASSWORD/KITE_TOTP_SECRET for headless login, or call "
            "exchange_request_token() manually with a fresh request_token."
        )

    request_token = fetch_request_token(
        api_key=s.kite_api_key,
        user_id=s.kite_user_id,
        password=s.kite_password,
        totp_secret=s.kite_totp_secret,
        client=http_client,
    )
    access_token = exchange_request_token(s.kite_api_key, s.kite_api_secret, request_token, kite=kite)
    store.save(today, access_token)
    return access_token
