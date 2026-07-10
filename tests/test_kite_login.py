from datetime import date

import pytest

from app.auth import kite_login
from app.auth.kite_login import (
    AutoLoginError,
    TokenStore,
    exchange_request_token,
    fetch_request_token,
    get_access_token,
)
from app.config import Settings


# --- fakes for the headless HTTP flow -------------------------------------------------
class FakeResponse:
    def __init__(self, *, json_data=None, status_code=200, location=None, url=""):
        self._json = json_data or {}
        self.status_code = status_code
        self.headers = {"location": location} if location else {}
        self.url = url

    def json(self):
        return self._json


class FakeClient:
    """Simulates /api/login -> /api/twofa -> /connect/login redirect chain."""

    def __init__(self):
        self.calls = []

    def post(self, url, data=None):
        self.calls.append(("POST", url))
        if url == kite_login.KITE_LOGIN_URL:
            return FakeResponse(json_data={"data": {"request_id": "REQ1"}})
        if url == kite_login.KITE_TWOFA_URL:
            return FakeResponse(status_code=200)
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url, follow_redirects=False):
        self.calls.append(("GET", url))
        # First hop: no token yet, redirect onward. Second hop: token present.
        if "connect/login" in url and "request_token" not in url:
            return FakeResponse(status_code=302, location="https://kite.zerodha.com/connect/finish?sess=1")
        return FakeResponse(
            status_code=302, location="https://myapp.local/redirect?request_token=RT_ABC&action=login"
        )


class FakeKite:
    def __init__(self):
        self.exchanged = None

    def generate_session(self, request_token, api_secret):
        self.exchanged = (request_token, api_secret)
        return {"access_token": "AT_XYZ"}


# --- tests ----------------------------------------------------------------------------
def test_token_store_roundtrip(tmp_path):
    store = TokenStore(tmp_path / "kite_token.json")
    today = date(2026, 7, 10)
    assert store.load_today(today) is None
    store.save(today, "AT_123")
    assert store.load_today(today) == "AT_123"
    # A different day must not return yesterday's token.
    assert store.load_today(date(2026, 7, 11)) is None


def test_get_access_token_returns_cached(tmp_path):
    store = TokenStore(tmp_path / "kite_token.json")
    today = date(2026, 7, 10)
    store.save(today, "CACHED")
    s = Settings(kite_api_key="k", kite_api_secret="s")
    assert get_access_token(s, today=today, store=store) == "CACHED"


def test_get_access_token_missing_creds_raises(tmp_path):
    store = TokenStore(tmp_path / "kite_token.json")
    s = Settings(kite_api_key="k", kite_api_secret="s")  # no user/password/totp
    with pytest.raises(AutoLoginError):
        get_access_token(s, today=date(2026, 7, 10), store=store)


def test_fetch_request_token_flow():
    client = FakeClient()
    token = fetch_request_token(
        api_key="k",
        user_id="AB1234",
        password="pw",
        totp_secret="BASE32SECRET",
        client=client,
        totp_now=lambda: "123456",
    )
    assert token == "RT_ABC"
    assert ("POST", kite_login.KITE_TWOFA_URL) in client.calls


def test_exchange_request_token():
    kite = FakeKite()
    at = exchange_request_token("k", "secret", "RT_ABC", kite=kite)
    assert at == "AT_XYZ"
    assert kite.exchanged == ("RT_ABC", "secret")
