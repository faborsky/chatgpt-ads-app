"""Shared fixtures: no test may ever touch the real API, .env or .usage/."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oaiads import api  # noqa: E402


class DummyResp:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload=None, headers=None, status_code=200, text=""):
        self._payload = {} if payload is None else payload
        self.headers = headers or {}
        self.status_code = status_code
        self.text = text or ("" if payload is None else "x")
        self.content = b"x" if payload is not None else b""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def dummy_resp():
    return DummyResp


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Redirect persistent state to a temp dir, fake credentials, never sleep."""
    monkeypatch.setattr(api, "USAGE_DIR", str(tmp_path / ".usage"))
    for var in list(os.environ):
        if var.startswith("OPENAI_ADS_") or var.startswith("OAIADS_"):
            monkeypatch.delenv(var, raising=False)   # the developer's .env must not leak into tests
    monkeypatch.setenv("OPENAI_ADS_API_KEY", "sk-FAKETESTKEY1234567890")
    api.set_account(None)
    monkeypatch.setattr(api.time, "sleep", lambda s: None)


@pytest.fixture
def capture_requests(monkeypatch, dummy_resp):
    """Record every outgoing request and answer from a queue of DummyResp."""
    calls = []
    queue = []

    def fake_request(method, url, params=None, json=None, files=None, data=None, headers=None, timeout=None):
        calls.append({"method": method, "url": url, "params": params, "json": json, "files": files,
                      "data": data, "headers": headers, "timeout": timeout})
        if queue:
            return queue.pop(0)
        return dummy_resp({})

    monkeypatch.setattr(api.requests, "request", fake_request)
    return calls, queue
