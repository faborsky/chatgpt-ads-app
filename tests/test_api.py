"""Engine tests: secret hygiene, headers, retries, idempotency, rate budget, paging, error handling."""

import json

import pytest
import requests

from oaiads import api


# ---------------------------------------------------------------------------
# Secret hygiene
# ---------------------------------------------------------------------------

def test_redact_bearer_and_keys():
    text = ('Authorization: Bearer sk-abcdefghijklmnop "api_key": "sk-secret12345678" '
            '"signing_secret": "whsec_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG=" plain=ok')
    red = api._redact(text)
    assert "sk-abcdefghijklmnop" not in red
    assert "sk-secret12345678" not in red
    assert "whsec_abcdefghijklmnopqrstuvwxyz" not in red
    assert "plain=ok" in red


def test_api_call_sends_bearer_header_not_query(capture_requests, dummy_resp):
    calls, queue = capture_requests
    queue.append(dummy_resp({"data": []}))
    api._api_call("GET", "/campaigns", [("limit", 5)])
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-FAKETESTKEY1234567890"
    assert "OpenAI-Ad-Account" not in calls[0]["headers"]
    assert calls[0]["url"] == "https://api.ads.openai.com/v1/campaigns"
    assert ("limit", 5) in calls[0]["params"]


def test_ad_account_header_only_when_env_set(capture_requests, dummy_resp, monkeypatch):
    calls, queue = capture_requests
    monkeypatch.setenv("OPENAI_ADS_AD_ACCOUNT", "adacct_9")
    queue.append(dummy_resp({}))
    api._api_call("GET", "/ad_account")
    assert calls[0]["headers"]["OpenAI-Ad-Account"] == "adacct_9"


def test_non_api_url_refused(capture_requests, capsys):
    calls, _ = capture_requests
    with pytest.raises(SystemExit):
        api._api_call("GET", "https://evil.example.com/steal")
    assert not calls


def test_connection_error_message_redacted(monkeypatch, capsys):
    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("failed Bearer sk-SUPERSECRETKEY12345")
    monkeypatch.setattr(api.requests, "request", boom)
    with pytest.raises(SystemExit):
        api._api_call("GET", "/ad_account")
    err = capsys.readouterr().err
    assert "sk-SUPERSECRETKEY12345" not in err


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def test_named_accounts_discovered(monkeypatch):
    monkeypatch.setenv("OPENAI_ADS_API_KEY_CLIENTX", "sk-client")
    assert "clientx" in api.configured_accounts()
    api.set_account("ClientX")
    assert api.api_key() == "sk-client"


def test_check_config_fails_on_placeholder(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_ADS_API_KEY", api.PLACEHOLDER_KEY)
    with pytest.raises(SystemExit):
        api.check_config()
    assert "OPENAI_ADS_API_KEY not set" in capsys.readouterr().err


def test_unknown_named_account_lists_configured(monkeypatch, capsys):
    api.set_account("nope")
    with pytest.raises(SystemExit):
        api.check_config()
    err = capsys.readouterr().err
    assert "OPENAI_ADS_API_KEY_NOPE" in err and "default" in err


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

def test_get_retries_on_5xx_then_succeeds(capture_requests, dummy_resp):
    calls, queue = capture_requests
    queue += [dummy_resp({"error": "x"}, status_code=503), dummy_resp({"ok": True})]
    assert api._api_call("GET", "/campaigns") == {"ok": True}
    assert len(calls) == 2


def test_post_without_idempotency_not_retried_on_5xx(capture_requests, dummy_resp, capsys):
    calls, queue = capture_requests
    queue += [dummy_resp({"error": {"message": "boom"}}, status_code=502)]
    with pytest.raises(SystemExit):
        api._api_call("POST", "/upload", json_body={"image_url": "x"})
    assert len(calls) == 1
    assert "MAY have landed" in capsys.readouterr().err


def test_post_with_idempotency_key_retries(capture_requests, dummy_resp):
    calls, queue = capture_requests
    queue += [dummy_resp({}, status_code=500), dummy_resp({"id": "cmpn_1"})]
    out = api._api_call("POST", "/campaigns", json_body={"name": "x"}, idempotency_key="k1")
    assert out == {"id": "cmpn_1"}
    assert len(calls) == 2
    assert all(c["headers"]["Idempotency-Key"] == "k1" for c in calls)


def test_429_retried_for_writes_and_honours_retry_after(capture_requests, dummy_resp, monkeypatch):
    slept = []
    monkeypatch.setattr(api.time, "sleep", lambda s: slept.append(s))
    calls, queue = capture_requests
    queue += [dummy_resp({}, status_code=429, headers={"Retry-After": "7"}), dummy_resp({"id": "ad_1"})]
    assert api._api_call("POST", "/ads", json_body={}) == {"id": "ad_1"}
    assert 7 in slept and len(calls) == 2


def test_429_gives_up_after_retries(capture_requests, dummy_resp):
    calls, queue = capture_requests
    queue += [dummy_resp({}, status_code=429)] * 4
    with pytest.raises(SystemExit):
        api._api_call("GET", "/campaigns")
    assert len(calls) == len(api._RATE_LIMIT_DELAYS) + 1


def test_never_retry_paths_even_with_key(capture_requests, dummy_resp):
    calls, queue = capture_requests
    queue += [dummy_resp({}, status_code=500)]
    with pytest.raises(SystemExit):
        api._api_call("POST", "/conversions/api_keys", json_body={"name": "k"}, idempotency_key="k1")
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_error_message_and_request_id_shown(capture_requests, dummy_resp, capsys):
    _, queue = capture_requests
    queue.append(dummy_resp({"error": {"message": "Conversion bidding is not enabled", "code": "forbidden"}},
                            status_code=403, headers={"x-request-id": "req_123"}))
    with pytest.raises(SystemExit):
        api._api_call("POST", "/campaigns", json_body={})
    err = capsys.readouterr().err
    assert "HTTP 403" in err and "Conversion bidding is not enabled" in err and "req_123" in err
    assert "forbidden" in err


def test_error_line_shows_type_code_and_param(capture_requests, dummy_resp, capsys):
    _, queue = capture_requests
    queue.append(dummy_resp({"error": {"message": "Invalid 'limit'", "type": "invalid_request_error",
                                       "param": "limit", "code": "integer_above_max_value"}}, status_code=400))
    with pytest.raises(SystemExit):
        api._api_call("GET", "/campaigns", [("limit", 9999)])
    err = capsys.readouterr().err
    assert "invalid_request_error/integer_above_max_value/param=limit" in err


def test_soft_error_returns_dict(capture_requests, dummy_resp):
    _, queue = capture_requests
    queue.append(dummy_resp({"error": {"message": "nope"}}, status_code=404))
    out = api._api_call("GET", "/bulk_mutation_jobs/x", soft=True)
    assert out["_error"]["status"] == 404 and out["_error"]["message"] == "nope"


def test_empty_body_returns_empty_dict(capture_requests, dummy_resp):
    _, queue = capture_requests
    queue.append(dummy_resp(None, status_code=200))
    assert api._api_call("POST", "/campaigns/c/pause") == {}


# ---------------------------------------------------------------------------
# Rate budget
# ---------------------------------------------------------------------------

def test_endpoint_family_collapses_ids():
    assert api.endpoint_family("get", "/campaigns/cmpn_101/insights") == "GET /campaigns/{id}/insights"
    assert api.endpoint_family("POST", "/ad_account/spend_limit_windows/12345/delete") == "POST /ad_account/spend_limit_windows/{id}/delete"
    assert api.endpoint_family("GET", "/ads?limit=5") == "GET /ads"


def test_budget_records_and_paces(capture_requests, dummy_resp, monkeypatch):
    calls, queue = capture_requests
    slept = []
    monkeypatch.setattr(api.time, "sleep", lambda s: slept.append(s))
    cap = int(api.RATE_LIMIT_PER_ENDPOINT * api.RATE_SOFT_FACTOR)
    for _ in range(cap):
        queue.append(dummy_resp({}))
        api._api_call("GET", "/campaigns")
    assert api.budget_snapshot()["per_endpoint_calls"]["GET /campaigns"] == cap
    queue.append(dummy_resp({}))
    api._api_call("GET", "/campaigns")
    assert slept, "should have paced at the soft cap"


def test_budget_override_env(capture_requests, dummy_resp, monkeypatch):
    monkeypatch.setenv("OAIADS_IGNORE_RATE_BUDGET", "1")
    _, queue = capture_requests
    queue.append(dummy_resp({}))
    api._api_call("GET", "/campaigns")
    assert api.budget_snapshot()["overall_calls"] == 0


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_fetch_all_follows_cursor(capture_requests, dummy_resp):
    calls, queue = capture_requests
    queue += [dummy_resp({"data": [{"id": "a"}, {"id": "b"}], "has_more": True, "last_id": "b"}),
              dummy_resp({"data": [{"id": "c"}], "has_more": False, "last_id": "c"})]
    rows = api._fetch_all("/campaigns", [("name", "abc")])
    assert [r["id"] for r in rows] == ["a", "b", "c"]
    assert ("after", "b") in calls[1]["params"]
    assert ("name", "abc") in calls[1]["params"]


def test_fetch_all_stops_at_cap_and_warns(capture_requests, dummy_resp, capsys):
    _, queue = capture_requests
    queue += [dummy_resp({"data": [{"id": str(i)} for i in range(3)], "has_more": True, "last_id": "2"})]
    rows = api._fetch_all("/campaigns", max_items=3)
    assert len(rows) == 3
    assert "stopped at 3" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# mutate
# ---------------------------------------------------------------------------

def test_mutate_without_confirm_makes_no_call(capture_requests):
    calls, _ = capture_requests
    resp, executed = api.mutate("POST", "/campaigns", {"name": "x"}, confirm=False, create=True)
    assert resp is None and executed is False and not calls


def test_mutate_create_generates_idempotency_key(capture_requests, dummy_resp):
    calls, queue = capture_requests
    queue.append(dummy_resp({"id": "cmpn_1"}))
    resp, executed = api.mutate("POST", "/campaigns", {"name": "x"}, confirm=True, create=True)
    assert executed and resp["id"] == "cmpn_1"
    key = calls[0]["headers"]["Idempotency-Key"]
    assert key.startswith("oaiads-") and resp["_idempotency_key"] == key


def test_usage_files_never_contain_key(capture_requests, dummy_resp):
    _, queue = capture_requests
    queue.append(dummy_resp({"id": "adacct_1", "currency_code": "USD", "timezone": "Europe/Prague"}))
    api.account_meta(refresh=True)
    import glob, os
    for path in glob.glob(os.path.join(api.USAGE_DIR, "*.json")):
        assert "FAKETESTKEY" not in open(path).read()


# ---------------------------------------------------------------------------
# Multi-account guard (agencies: never act on a guessed account)
# ---------------------------------------------------------------------------

def test_two_accounts_without_flag_refused(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_ADS_API_KEY_ACME", "sk-a")
    monkeypatch.setenv("OPENAI_ADS_API_KEY_BRANDX", "sk-d")
    monkeypatch.delenv("OPENAI_ADS_API_KEY", raising=False)
    api.set_account(None)
    with pytest.raises(SystemExit):
        api.check_config()
    err = capsys.readouterr().err
    assert "2 accounts are configured" in err and "acme" in err and "brandx" in err and "--account" in err


def test_two_accounts_explicit_flag_ok(monkeypatch):
    monkeypatch.setenv("OPENAI_ADS_API_KEY_ACME", "sk-a")
    monkeypatch.setenv("OPENAI_ADS_API_KEY_BRANDX", "sk-d")
    api.set_account("BrandX")
    api.check_config()
    assert api.ACTIVE_ACCOUNT == "brandx" and api.api_key() == "sk-d"


def test_default_account_env_selects(monkeypatch):
    monkeypatch.setenv("OPENAI_ADS_API_KEY_ACME", "sk-a")
    monkeypatch.setenv("OPENAI_ADS_API_KEY_BRANDX", "sk-d")
    monkeypatch.setenv("OPENAI_ADS_DEFAULT_ACCOUNT", "acme")
    api.set_account(None)
    api.check_config()
    assert api.ACTIVE_ACCOUNT == "acme"


def test_single_named_account_auto_selected(monkeypatch):
    monkeypatch.delenv("OPENAI_ADS_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_ADS_API_KEY_ACME", "sk-a")
    api.set_account(None)
    api.check_config()
    assert api.ACTIVE_ACCOUNT == "acme" and api.api_key() == "sk-a"
