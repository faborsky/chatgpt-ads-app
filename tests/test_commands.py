"""Command wiring tests through the real argparse parser with a faked API layer (offline)."""

import json

import pytest

from oaiads import api
from oaiads.cli import build_parser


@pytest.fixture
def fake_api(monkeypatch):
    """Replace api._api_call: record calls, answer from a dict of path → response (or list queue)."""
    calls = []
    answers = {}

    def _call(method, path, params=None, json_body=None, files=None, data=None, extra_headers=None,
              idempotent=False, idempotency_key=None, timeout=60, soft=False, _attempt=0):
        calls.append({"method": method, "path": path, "params": params, "json": json_body,
                      "idempotency_key": idempotency_key, "idempotent": idempotent, "soft": soft, "data": data})
        key = f"{method} {path}"
        if key in answers:
            val = answers[key]
            return val.pop(0) if isinstance(val, list) else val
        for k, v in answers.items():
            if k.endswith("*") and key.startswith(k[:-1]):
                return v
        return {}

    monkeypatch.setattr(api, "_api_call", _call)

    def _meta(refresh=False):
        calls.append({"method": "META", "path": "/ad_account", "params": None, "json": None,
                      "idempotency_key": None, "idempotent": False, "soft": True, "data": None})
        return {"id": "adacct_1", "currency_code": "USD", "timezone": "Europe/Prague"}

    monkeypatch.setattr(api, "account_meta", _meta)
    return calls, answers


def run(argv):
    args = build_parser().parse_args(argv)
    api.set_account(args.account)
    args.func(args)
    return args


def writes(calls):
    return [c for c in calls if c["method"] not in ("GET", "META")]


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

def test_campaign_create_dry_run_sends_nothing_and_prints_plan(fake_api, capsys):
    calls, _ = fake_api
    run(["campaign-create", "--name", "Spring launch", "--lifetime-budget", "250", "--countries", "cz,sk",
         "--bidding-type", "clicks", "--json"])
    assert not calls
    out = json.loads(capsys.readouterr().out)
    assert out["executed"] is False
    body = out["plan"]["body"]
    assert body["status"] == "paused"
    assert body["budget"] == {"lifetime_spend_limit_micros": 250_000_000}
    assert body["targeting"]["locations"]["countries"] == ["CZ", "SK"]
    assert body["bidding_type"] == "clicks"


def test_campaign_create_confirm_posts_with_idempotency(fake_api):
    calls, answers = fake_api
    answers["POST /campaigns"] = {"id": "cmpn_1", "name": "X", "status": "paused", "bidding_type": "impressions"}
    run(["campaign-create", "--name", "Spring launch", "--daily-budget", "20", "--confirm"])
    w = writes(calls)
    assert len(w) == 1 and w[0]["path"] == "/campaigns"
    assert w[0]["json"]["budget"] == {"daily_spend_limit_micros": 20_000_000}
    assert w[0]["idempotency_key"].startswith("oaiads-")


def test_campaign_create_budget_below_minimum_blocked(fake_api, capsys):
    calls, _ = fake_api
    with pytest.raises(SystemExit):
        run(["campaign-create", "--name", "Spring launch", "--lifetime-budget", "0.5", "--confirm"])
    assert not calls


def test_campaign_create_ocpc_requires_event_setting(fake_api, capsys):
    with pytest.raises(SystemExit):
        run(["campaign-create", "--name", "Spring launch", "--lifetime-budget", "5", "--bidding-type", "conversions"])
    assert "conversion-event-setting-id" in capsys.readouterr().err


def test_campaign_create_event_setting_on_cpc_is_a_reporting_link(fake_api, capsys):
    run(["campaign-create", "--name", "Spring launch", "--daily-budget", "20", "--bidding-type", "clicks",
         "--conversion-event-setting-id", "ces_1,ces_2", "--json"])
    body = json.loads(capsys.readouterr().out)["plan"]["body"]
    assert body["bidding_type"] == "clicks" and body["conversion_event_setting_ids"] == ["ces_1", "ces_2"]


def test_campaign_create_without_event_setting_warns(fake_api, capsys):
    run(["campaign-create", "--name", "Spring launch", "--daily-budget", "20", "--bidding-type", "clicks"])
    assert "No conversion event setting linked" in capsys.readouterr().err


def test_conversion_check_flags_unlinked_campaigns(fake_api, capsys):
    _, answers = fake_api
    answers["GET /conversions/pixels"] = {"data": [{"id": "clidsrc_1", "pixel_id": "px1", "name": "Web"}]}
    answers["GET /conversions/event_settings"] = {"data": [{"id": "ces_1", "event_type": "order_created", "name": "Purchases", "archived": False, "sources": [], "campaigns": []}]}
    answers["GET /campaigns"] = {"data": [{"id": "c1", "name": "Linked", "status": "active", "conversion_event_setting_ids": ["ces_1"]},
                                          {"id": "c2", "name": "Unlinked", "status": "active", "conversion_event_setting_ids": []}], "has_more": False}
    run(["conversion-check", "--json"])
    out = json.loads(capsys.readouterr().out)
    msgs = " ".join(f["message"] for f in out["findings"])
    assert "c2" in msgs and "c1" not in msgs


def test_conversion_check_gated_pixels(fake_api, capsys):
    _, answers = fake_api
    answers["GET /conversions/pixels"] = {"_error": {"status": 404, "message": "Not found"}}
    answers["GET /conversions/event_settings"] = {"data": []}
    answers["GET /campaigns"] = {"data": [], "has_more": False}
    run(["conversion-check", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["errors"]["pixels"].startswith("HTTP 404")
    assert any("no conversion event settings" in f["message"] for f in out["findings"])


def test_campaign_update_merges_targeting_ids_only(fake_api):
    calls, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "targeting": {"locations": {"include": [
        {"id": "2000043", "name": "California", "type": "region", "country_code": "US"}]}}}
    run(["campaign-update", "--campaign-id", "cmpn_1", "--countries", "CZ", "--confirm"])
    body = writes(calls)[0]["json"]
    assert body["targeting"]["locations"]["include"] == [{"id": "2000043"}]
    assert body["targeting"]["locations"]["countries"] == ["CZ"]


def test_campaign_archive_refuses_active_without_force(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "status": "active", "name": "Live"}
    with pytest.raises(SystemExit):
        run(["campaign-archive", "--campaign-id", "cmpn_1", "--confirm"])
    assert not writes(calls)
    assert "refusing to archive" in capsys.readouterr().err


def test_campaign_archive_paused_with_confirm(fake_api):
    calls, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "status": "paused", "name": "Old"}
    run(["campaign-archive", "--campaign-id", "cmpn_1", "--confirm"])
    assert writes(calls)[0]["path"] == "/campaigns/cmpn_1/archive"


def test_campaign_activate_dry_run_makes_no_call(fake_api, capsys):
    calls, _ = fake_api
    run(["campaign-activate", "--campaign-id", "cmpn_1"])
    assert not calls
    assert "starts delivery" in capsys.readouterr().out


def test_campaigns_hide_archived_by_default(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /campaigns"] = {"data": [{"id": "a", "status": "active", "name": "A", "budget": {}},
                                          {"id": "b", "status": "archived", "name": "B", "budget": {}}], "has_more": False}
    run(["campaigns", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["a"]


# ---------------------------------------------------------------------------
# Ad groups
# ---------------------------------------------------------------------------

def test_adgroup_create_infers_billing_and_converts_cpm(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "bidding_type": "impressions"}
    run(["adgroup-create", "--campaign-id", "cmpn_1", "--name", "US English", "--max-cpm", "60",
         "--hints", "productivity, team collaboration", "--json"])
    out = json.loads(capsys.readouterr().out)
    bc = out["plan"]["body"]["bidding_config"]
    assert bc == {"billing_event_type": "impression", "max_bid_micros": 60_000}
    assert out["plan"]["body"]["context_hints"] == ["productivity", "team collaboration"]
    assert not writes(calls)
    assert [c["method"] for c in calls] == ["GET"], "dry-run reads the campaign only; no account-meta fetch"


def test_adgroup_create_click_campaign_rejects_impression_billing(fake_api, capsys):
    _, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "bidding_type": "clicks"}
    with pytest.raises(SystemExit):
        run(["adgroup-create", "--campaign-id", "cmpn_1", "--name", "Grp", "--billing-event", "impression", "--max-bid", "0.5"])
    assert "billing_event_type=click" in capsys.readouterr().err


def test_adgroup_update_sends_full_bidding_config(fake_api):
    calls, answers = fake_api
    answers["GET /ad_groups/adgrp_1"] = {"id": "adgrp_1", "bidding_config": {"billing_event_type": "click", "max_bid_micros": 500000, "strategy": "fixed_bid"}}
    run(["adgroup-update", "--ad-group-id", "adgrp_1", "--max-bid", "0.75", "--confirm"])
    body = writes(calls)[0]["json"]
    assert body["bidding_config"] == {"billing_event_type": "click", "max_bid_micros": 750_000, "strategy": "fixed_bid"}


def test_product_filter_parsing(fake_api, capsys):
    _, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "bidding_type": "impressions", "mode": "product_feed", "product_feed_id": "feed_1"}
    run(["adgroup-create", "--campaign-id", "cmpn_1", "--name", "Nike", "--max-cpm", "50", "--product-feed-id", "feed_1",
         "--product-filter", "brand:in:Nike|Adidas", "--product-filter", "price:lte:100", "--json"])
    ps = json.loads(capsys.readouterr().out)["plan"]["body"]["product_set"]
    assert ps["filters"][0] == {"field": "brand", "operator": "in", "values": ["Nike", "Adidas"]}
    assert ps["filters"][1]["values"] == ["100"]


# ---------------------------------------------------------------------------
# Ads
# ---------------------------------------------------------------------------

def test_ad_create_lint_blocks_long_title(fake_api, capsys):
    calls, _ = fake_api
    with pytest.raises(SystemExit):
        run(["ad-create", "--ad-group-id", "adgrp_1", "--name", "Card", "--title", "x" * 51, "--body", "ok",
             "--target-url", "https://example.com", "--file-id", "file_1", "--confirm"])
    assert not calls
    assert "3–50" in capsys.readouterr().err


def test_ad_create_dry_run_plan_and_confirm_body(fake_api, capsys):
    calls, answers = fake_api
    run(["ad-create", "--ad-group-id", "adgrp_1", "--name", "Card", "--title", "Try the planner", "--body", "Tasks in one place.",
         "--target-url", "https://example.com/p", "--file-id", "file_1", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["plan"]["body"]["creative"] == {"type": "chat_card", "title": "Try the planner", "body": "Tasks in one place.",
                                               "target_url": "https://example.com/p", "file_id": "file_1"}
    assert out["plan"]["body"]["status"] == "paused"
    answers["POST /ads"] = {"id": "ad_1", "name": "Card", "status": "paused", "review_status": "in_review"}
    run(["ad-create", "--ad-group-id", "adgrp_1", "--name", "Card", "--title", "Try the planner", "--body", "Tasks in one place.",
         "--target-url", "https://example.com/p", "--file-id", "file_1", "--confirm"])
    assert writes(calls)[0]["idempotency_key"]


def test_ad_create_image_url_uploads_only_on_confirm(fake_api, monkeypatch, capsys):
    calls, answers = fake_api
    uploaded = []
    monkeypatch.setattr("oaiads.commands.ads.upload_image", lambda url=None, path=None, purpose=None: uploaded.append(url) or {"file_id": "file_9"})
    run(["ad-create", "--ad-group-id", "adgrp_1", "--name", "Card", "--title", "Try the planner", "--body", "ok",
         "--target-url", "https://example.com/p", "--image-url", "https://cdn/x.png"])
    assert not uploaded and not calls
    answers["POST /ads"] = {"id": "ad_1"}
    run(["ad-create", "--ad-group-id", "adgrp_1", "--name", "Card", "--title", "Try the planner", "--body", "ok",
         "--target-url", "https://example.com/p", "--image-url", "https://cdn/x.png", "--confirm"])
    assert uploaded == ["https://cdn/x.png"]
    assert writes(calls)[0]["json"]["creative"]["file_id"] == "file_9"


def test_ad_update_merges_current_creative(fake_api):
    calls, answers = fake_api
    answers["GET /ads/ad_1"] = {"id": "ad_1", "creative": {"type": "chat_card", "title": "Old", "body": "B", "target_url": "https://e.com", "file_id": "f1", "image_url": "https://cdn/x"}}
    run(["ad-update", "--ad-id", "ad_1", "--title", "New title", "--confirm"])
    cr = writes(calls)[0]["json"]["creative"]
    assert cr == {"type": "chat_card", "title": "New title", "body": "B", "target_url": "https://e.com", "file_id": "f1"}


def test_ad_review_flags_unapproved(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ads"] = {"data": [{"id": "ad_1", "review_status": "approved", "status": "active", "serving_issues": []},
                                    {"id": "ad_2", "review_status": "rejected", "status": "active", "review": {"reason": "missing_favicon"}},
                                    {"id": "ad_3", "review_status": "approved", "status": "active",
                                     "serving_issues": [{"code": "campaign_not_active"}]}], "has_more": False}
    run(["ad-review", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in rows] == ["ad_2"], "paused-hierarchy codes are not attention items"


def test_raw_list_params_get_array_suffix(fake_api):
    calls, _ = fake_api
    run(["raw", "GET", "/campaigns/c1", "--params", '{"include": ["serving_issues"], "limit": 5}'])
    assert calls[0]["params"] == [("include[]", "serving_issues"), ("limit", 5)]


# ---------------------------------------------------------------------------
# Account: negative keywords, spend limits
# ---------------------------------------------------------------------------

def test_negative_keywords_add_is_read_modify_write(fake_api):
    calls, answers = fake_api
    answers["GET /ad_account"] = {"negative_keywords": ["casino"]}
    run(["negative-keywords-add", "--keywords", "betting, casino", "--confirm"])
    assert writes(calls)[0]["json"] == {"negative_keywords": ["casino", "betting"]}


def test_spend_limit_create_body_and_exclusive_end(fake_api, capsys):
    calls, _ = fake_api
    run(["spend-limit-create", "--start", "2099-01-01", "--end", "2099-02-01", "--amount", "500", "--name", "Q1 cap", "--json"])
    assert not calls, "dry-run must not touch the API (not even account meta)"
    body = json.loads(capsys.readouterr().out)["plan"]["body"]
    assert body == {"start_date": "2099-01-01", "end_date": "2099-02-01", "amount_micros": 500_000_000, "name": "Q1 cap"}
    with pytest.raises(SystemExit):
        run(["spend-limit-create", "--start", "2099-02-01", "--end", "2099-01-01", "--amount", "5"])


# ---------------------------------------------------------------------------
# Insights & pulse
# ---------------------------------------------------------------------------

def test_insights_params_use_array_suffix_and_account_tz(fake_api):
    calls, answers = fake_api
    answers["GET /ad_account/insights"] = {"data": [], "has_more": False}
    run(["insights", "--since", "2026-08-01", "--until", "2026-08-07", "--json"])
    params = next(c for c in calls if c["method"] == "GET")["params"]
    keys = [k for k, _ in params]
    assert "fields[]" in keys and "time_ranges[]" in keys
    assert ("aggregation_level", "campaign") in params
    tr = json.loads(dict(params)["time_ranges[]"])
    assert tr == {"type": "date_range", "since": "2026-08-01", "until": "2026-08-07", "timezone": "Europe/Prague"}


def test_insights_level_requires_object_id(fake_api):
    with pytest.raises(SystemExit):
        run(["insights", "--level", "campaign"])


def test_insights_aggregation_above_scope_rejected(fake_api):
    with pytest.raises(SystemExit):
        run(["insights", "--level", "ad", "--object-id", "ad_1", "--aggregation-level", "campaign"])


def test_pulse_survives_partial_failures(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ad_account"] = {"id": "adacct_1", "name": "Acme", "status": "active", "review": {"status": "approved"}}
    answers["GET /ad_account/spend_limit_windows"] = {"data": []}
    answers["GET /ad_account/insights"] = [
        {"data": [{"campaign_id": "c1", "campaign_name": "A", "impressions": 100, "clicks": 10, "spend": 5.0}]},
        {"data": [{"campaign_id": "c1", "campaign_name": "A", "impressions": 50, "clicks": 4, "spend": 2.0}]},
    ]
    answers["POST /conversions/insights"] = {"_error": {"status": 403, "message": "not enabled"}}
    answers["GET /ads"] = {"data": []}
    answers["GET /conversions/event_settings"] = {"data": [{"id": "ces_1", "archived": False}]}
    answers["GET /campaigns"] = {"data": [{"id": "c1", "name": "A", "status": "active", "conversion_event_setting_ids": []}]}
    run(["pulse"])
    out = capsys.readouterr().out
    assert "PULSE" in out and "Spend" in out and "NONE active" in out and "conversions: HTTP 403" in out
    assert "no conversion event linked" in out


# ---------------------------------------------------------------------------
# Audiences, raw, bulk
# ---------------------------------------------------------------------------

def test_audience_add_inline_identifiers_and_revision(fake_api):
    calls, answers = fake_api
    answers["GET /custom_audiences/caud_1"] = {"id": "caud_1", "status": "ready", "membership_revision": 4}
    run(["audience-add", "--audience-id", "caud_1", "--identifiers", "email:a@b.cz, gaid:38400000-8cf0-11bd-b23e-10b96e40000d", "--confirm"])
    w = writes(calls)[0]
    assert w["json"]["expected_revision"] == 4
    assert w["json"]["identifiers"][1] == {"identifier_type": "gaid", "identifier": "38400000-8cf0-11bd-b23e-10b96e40000d"}
    assert w["idempotency_key"]


def test_audience_merge_needs_two_ids(fake_api):
    with pytest.raises(SystemExit):
        run(["audience-merge", "--name", "All", "--ids", "caud_1"])


def test_raw_write_requires_confirm(fake_api, capsys):
    calls, _ = fake_api
    run(["raw", "POST", "/campaigns/c/pause"])
    assert not calls
    run(["raw", "GET", "campaigns", "--params", '{"limit": 5, "include": ["serving_issues"]}'])
    assert calls[0]["params"] == [("limit", 5), ("include[]", "serving_issues")]


def test_bulk_submit_validates_ops(fake_api, tmp_path, capsys):
    f = tmp_path / "ops.json"
    f.write_text(json.dumps({"operations": [{"operation_id": "a", "type": "campaign.create", "input": {"name": "x"}}]}))
    with pytest.raises(SystemExit):
        run(["bulk-submit", "--file", str(f)])
    assert "idempotency_key" in capsys.readouterr().err


def test_bulk_submit_dry_run_uses_validate_only(fake_api, tmp_path, monkeypatch):
    calls, answers = fake_api
    monkeypatch.setattr(api, "bulk_budget_wait_and_record", lambda: None)
    f = tmp_path / "ops.json"
    f.write_text(json.dumps([{"operation_id": "a", "type": "campaign.create", "idempotency_key": "k", "input": {"name": "x", "max_budget_micros": 1000000}}]))
    answers["POST /bulk_mutation_jobs"] = {"id": "blk_1", "status": "pending", "operation_count": 1}
    run(["bulk-submit", "--file", str(f)])
    assert writes(calls)[0]["json"]["validate_only"] is True
    run(["bulk-submit", "--file", str(f), "--confirm"])
    assert writes(calls)[1]["json"]["validate_only"] is False


# ---------------------------------------------------------------------------
# landing-check helpers (pure functions)
# ---------------------------------------------------------------------------

def test_robots_blocks_oai_adsbot_and_star():
    from oaiads.commands.account import _robots_blocks
    txt = "User-agent: *\nAllow: /\nDisallow: /objednavka\n\nUser-agent: OAI-AdsBot\nDisallow: /\n"
    assert _robots_blocks(txt, "/kurz") == ["OAI-AdsBot"]
    assert set(_robots_blocks(txt, "/objednavka")) == {"OAI-AdsBot", "*"}
    assert _robots_blocks("User-agent: *\nAllow: /\n", "/x") == []
    assert _robots_blocks("User-agent: OAI-SearchBot\nDisallow: /private\n", "/private/a") == ["OAI-SearchBot"]


def test_oppref_survives_helper():
    from oaiads.commands.account import oppref_survives
    assert oppref_survives("https://www.example.com/?oppref=oaiads-test123")
    assert oppref_survives("https://www.example.com/kurz?utm=1&oppref=oaiads-test123")
    assert not oppref_survives("https://www.example.com/kurz")
    assert not oppref_survives("https://www.example.com/?oppref=other")


# ---------------------------------------------------------------------------
# 1.2.0 — findings from the first live write session
# ---------------------------------------------------------------------------

def test_negative_keywords_unavailable_when_field_absent(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /ad_account"] = {"id": "adacct_1", "name": "X"}  # no negative_keywords key at all
    run(["negative-keywords"])
    assert "not available on this account" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        run(["negative-keywords-add", "--keywords", "casino", "--confirm"])
    assert not writes(calls)


def test_negative_keywords_set_explains_404(fake_api, capsys):
    _, answers = fake_api
    answers["POST /ad_account/negative_keywords"] = {"_error": {"status": 404, "message": "Invalid URL (POST /v1/ad_account/negative_keywords)"}}
    with pytest.raises(SystemExit):
        run(["negative-keywords-set", "--keywords", "casino", "--confirm"])
    err = capsys.readouterr().err
    assert "HTTP 404" in err and "not available on this account" in err


def test_campaign_detail_tree_fetches_ads(fake_api, capsys):
    _, answers = fake_api
    answers["GET /campaigns/c1"] = {"id": "c1", "name": "C", "status": "paused", "budget": {}}
    answers["GET /ad_groups"] = {"data": [{"id": "g1", "name": "G", "status": "active", "bidding_config": {}}], "has_more": False}
    answers["GET /ads"] = {"data": [{"id": "a1", "name": "A", "status": "active", "review_status": "approved", "creative": {"title": "T"}}], "has_more": False}
    run(["campaign-detail", "--campaign-id", "c1", "--with-children", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["_ad_groups"][0]["_ads"][0]["id"] == "a1"


def test_campaign_update_verifies_via_detail(fake_api, capsys):
    calls, answers = fake_api
    answers["POST /campaigns/cmpn_1"] = {"id": "cmpn_1", "name": "Old"}
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "name": "New", "status": "paused"}
    run(["campaign-update", "--campaign-id", "cmpn_1", "--name", "New", "--confirm"])
    methods = [(c["method"], c["path"]) for c in calls]
    assert methods.index(("POST", "/campaigns/cmpn_1")) < methods.index(("GET", "/campaigns/cmpn_1"))
    captured = capsys.readouterr()
    assert "Verified via detail" in captured.out and "lag a few seconds" in captured.err


def test_ad_review_splits_waiting_from_problems(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ads"] = {"data": [
        {"id": "ad_1", "name": "fresh", "review_status": "in_review", "status": "paused", "serving_issues": []},
        {"id": "ad_2", "name": "bad", "review_status": "rejected", "status": "paused", "review": {"reason": "robots_txt"}},
        {"id": "ad_3", "name": "ok", "review_status": "approved", "status": "paused", "serving_issues": [{"code": "campaign_not_active"}]},
    ], "has_more": False}
    run(["ad-review"])
    out = capsys.readouterr().out
    assert "Problems (1)" in out and "Waiting for review (1)" in out and "1 problem(s), 1 in review, 1 fine" in out


def test_pulse_warns_on_foreign_country_targeting(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ad_account"] = {"id": "adacct_1", "name": "Acme", "status": "active", "review": {"status": "approved"}}
    answers["GET /ad_account/spend_limit_windows"] = {"_error": {"status": 404, "message": "Invalid URL"}}
    answers["GET /ad_account/insights"] = {"data": []}
    answers["POST /conversions/insights"] = {"data": []}
    answers["GET /ads"] = {"data": []}
    answers["GET /conversions/event_settings"] = {"data": []}
    answers["GET /campaigns"] = {"data": [{"id": "c1", "name": "Recommended", "status": "paused", "conversion_event_setting_ids": [],
                                          "targeting": {"locations": {"include": [{"id": "1000232", "type": "country", "country_code": "US"}]}}}]}
    run(["pulse"])
    out = capsys.readouterr().out
    assert "targets ['US']" in out and "endpoint unavailable" in out


# ---------------------------------------------------------------------------
# plan-apply
# ---------------------------------------------------------------------------

def _write_plan(tmp_path, campaign=None, extra=None):
    (tmp_path / "card.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "hints-A.txt").write_text("marketér chce postavit appku bez kódu\n# comment\nchce si automatizovat reporting\n", encoding="utf-8")
    plan = {
        "campaign": campaign or {"name": "Podzim", "bidding_type": "clicks", "daily_budget": 15, "end": "2099-01-01",
                                 "location_ids": ["1000055"], "conversion_event_setting_ids": ["ces_1"]},
        "image_file": "card.png",
        "defaults": {"ad_group": {"max_bid": 1}, "ad": {"target_url": "https://www.example.com/"}},
        "ad_groups": [
            {"key": "A", "name": "A situace", "hints_file": "hints-A.txt", "query_string_template": "utm_content=A",
             "ads": [{"name": "A1 čas", "title": "Kurz práce s AI", "body": "Postav si appku bez kódování."},
                     {"title": "AI v praxi", "body": "Praktický videokurz."}]},
            {"key": "G", "name": "G kontrola", "hints": ["kurz AI", "vibe coding"],
             "ads": [{"name": "G1 čas", "title": "Kurz práce s AI", "body": "Postav si appku bez kódování."}]},
        ],
    }
    if extra:
        plan.update(extra)
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return p


def test_plan_apply_dry_run_sends_nothing(fake_api, tmp_path, capsys, monkeypatch):
    calls, _ = fake_api
    uploads = []
    monkeypatch.setattr("oaiads.commands.plan.upload_image", lambda url=None, path=None, purpose=None: uploads.append(path) or {"file_id": "file_9"})
    p = _write_plan(tmp_path)
    run(["plan-apply", "--file", str(p), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["executed"] is False and out["plan"]["writes_remaining"] == 1 + 2 + 3
    assert out["plan"]["campaign"]["budget"] == {"daily_spend_limit_micros": 15_000_000}
    assert out["plan"]["ad_groups"][0]["body"]["context_hints"] == ["marketér chce postavit appku bez kódu", "chce si automatizovat reporting"]
    assert out["plan"]["ad_groups"][0]["body"]["landing_page_configuration"] == {"query_string_template": "utm_content=A"}
    assert out["plan"]["ad_groups"][0]["body"]["bidding_config"] == {"billing_event_type": "click", "max_bid_micros": 1_000_000}
    assert out["plan"]["ad_groups"][0]["ads"][1]["body"]["name"] == "A/1 · AI v praxi", "missing ad name is derived"
    assert not calls and not uploads
    assert not (tmp_path / "plan.state.json").exists()


def test_plan_apply_confirm_creates_tree_with_keys_and_state(fake_api, tmp_path, capsys, monkeypatch):
    calls, answers = fake_api
    uploads = []
    monkeypatch.setattr("oaiads.commands.plan.upload_image", lambda url=None, path=None, purpose=None: uploads.append(path) or {"file_id": "file_9"})
    answers["POST /campaigns"] = {"id": "cmpn_1", "name": "Podzim", "status": "paused"}
    answers["POST /ad_groups"] = [{"id": "adgrp_A", "name": "A"}, {"id": "adgrp_G", "name": "G"}]
    answers["POST /ads"] = [{"id": "ad_1", "review_status": "in_review"}, {"id": "ad_2", "review_status": "in_review"}, {"id": "ad_3", "review_status": "in_review"}]
    p = _write_plan(tmp_path)
    run(["plan-apply", "--file", str(p), "--confirm"])
    w = writes(calls)
    assert [c["path"] for c in w] == ["/campaigns", "/ad_groups", "/ads", "/ads", "/ad_groups", "/ads"]
    assert all(c["idempotency_key"] for c in w)
    assert w[1]["json"]["campaign_id"] == "cmpn_1" and w[2]["json"]["ad_group_id"] == "adgrp_A" and w[5]["json"]["ad_group_id"] == "adgrp_G"
    assert w[2]["json"]["creative"]["file_id"] == "file_9" and len(uploads) == 1, "shared image uploaded once"
    state = json.loads((tmp_path / "plan.state.json").read_text())
    assert state["created"]["campaign"] == "cmpn_1" and state["created"]["ad_groups"] == {"A": "adgrp_A", "G": "adgrp_G"}
    assert set(state["created"]["ads"]) == {"A/0", "A/1", "G/0"}
    # second run: everything exists → no writes
    calls.clear()
    run(["plan-apply", "--file", str(p), "--confirm"])
    assert not writes(calls)


def test_plan_apply_resumes_after_failure_reusing_key(fake_api, tmp_path, monkeypatch):
    calls, answers = fake_api
    monkeypatch.setattr("oaiads.commands.plan.upload_image", lambda url=None, path=None, purpose=None: {"file_id": "file_9"})
    answers["POST /campaigns"] = {"id": "cmpn_1"}
    answers["POST /ad_groups"] = [{"id": "adgrp_A"}, {"id": "adgrp_G"}]
    boom = {"n": 0}
    real_call = api._api_call

    def flaky(method, path, *a, **kw):
        if method == "POST" and path == "/ads":
            boom["n"] += 1
            calls.append({"method": method, "path": path, "params": None, "json": kw.get("json_body"),
                          "idempotency_key": kw.get("idempotency_key"), "idempotent": True, "soft": False, "data": None})
            if boom["n"] == 2:
                raise SystemExit(1)  # the CLI exits on an API error
            return {"id": f"ad_{boom['n']}"}
        return real_call(method, path, *a, **kw)

    monkeypatch.setattr(api, "_api_call", flaky)
    p = _write_plan(tmp_path)
    with pytest.raises(SystemExit):
        run(["plan-apply", "--file", str(p), "--confirm"])
    state = json.loads((tmp_path / "plan.state.json").read_text())
    assert state["created"]["ads"] == {"A/0": "ad_1"} and state["keys"]["ads"]["A/1"], "key for the failed ad was saved before the call"
    saved_key = state["keys"]["ads"]["A/1"]
    calls.clear()
    run(["plan-apply", "--file", str(p), "--confirm"])
    paths = [c["path"] for c in writes(calls)]
    assert paths == ["/ads", "/ad_groups", "/ads"], "campaign and group A are not recreated"
    assert writes(calls)[0]["idempotency_key"] == saved_key


def test_plan_apply_lint_blocks_and_attach_mode(fake_api, tmp_path, capsys):
    calls, answers = fake_api
    p = _write_plan(tmp_path, campaign={"id": "cmpn_existing"})
    answers["GET /campaigns/cmpn_existing"] = {"id": "cmpn_existing", "bidding_type": "impressions"}
    with pytest.raises(SystemExit):  # impressions campaign + max_bid → billing impression fine, but chat_card ads need file: shared image ok → why exit? title ok… make a real lint error:
        bad = json.loads(p.read_text(encoding="utf-8"))
        bad["ad_groups"][0]["ads"][0]["title"] = "x" * 51
        p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        run(["plan-apply", "--file", str(p), "--confirm"])
    assert not writes(calls)
    assert "3–50" in capsys.readouterr().err
    good = json.loads(p.read_text(encoding="utf-8"))
    good["ad_groups"][0]["ads"][0]["title"] = "Kurz práce s AI"
    p.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
    run(["plan-apply", "--file", str(p), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["plan"]["campaign"] == {"existing_id": "cmpn_existing"}
    assert out["plan"]["ad_groups"][0]["body"]["bidding_config"]["billing_event_type"] == "impression"
