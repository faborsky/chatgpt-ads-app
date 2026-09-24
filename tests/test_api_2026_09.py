"""API changes 2026-09 (spec/docs re-check 2026-09-24): daily account spending limit, granular web platforms,
audience operation list/cancel/resume, Maximize Results rules, bid_too_low, platform insights segment,
documented UTM precedence, deprecated endpoints. Offline, through the real parser."""

import json
from datetime import date, timedelta

import pytest

from oaiads.commands.insights import retention_warnings
from tests.test_commands import _write_plan, fake_api, run, writes  # noqa: F401  (fixture re-export)


# ---------------------------------------------------------------------------
# Account spending limits (daily limit: 2026-09-09)
# ---------------------------------------------------------------------------

def test_spend_limits_403_is_a_clean_fallback(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ad_account/spend_limit_windows"] = {"_error": {"status": 403, "message": "403: Only ad account admins can perform this action."}}
    run(["spend-limits", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is False and "billing" in out["fallback"]


def test_spend_limits_shows_daily_limit_and_revision(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ad_account/spend_limit_windows"] = {
        "object": "list", "data": [], "revision": 12, "can_create_daily_limit": False,
        "daily_limit": {"amount_micros": 100_000_000, "start_date": "2026-10-01", "end_date": None, "status": "active",
                        "spent_micros": 40_000_000, "remaining_micros": 60_000_000}}
    run(["spend-limits"])
    out = capsys.readouterr().out
    assert "100.00 USD/day from 2026-10-01, no end date [active]" in out and "remaining 60.00 USD" in out
    assert "Revision: 12" in out


def test_daily_spend_limit_set_reads_revision_and_is_not_auto_retried(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /ad_account/spend_limit_windows"] = {"data": [], "revision": 7, "daily_limit": None}
    answers["POST /ad_account/daily_spend_limit"] = {"spend_limits": {"revision": 8}}
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    run(["daily-spend-limit-set", "--amount", "150", "--start", tomorrow, "--no-end", "--confirm"])
    w = writes(calls)
    assert w[0]["path"] == "/ad_account/daily_spend_limit"
    assert w[0]["json"] == {"amount_micros": 150_000_000, "expected_revision": 7, "start_date": tomorrow, "end_date": None}
    assert w[0]["idempotent"] is False  # 503 = may have landed → re-read, never blind retry


def test_daily_spend_limit_delete_uses_explicit_revision_without_reading(fake_api, capsys):
    calls, _ = fake_api
    run(["daily-spend-limit-delete", "--expected-revision", "13", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["plan"]["body"] == {"expected_revision": 13} and out["executed"] is False
    assert not calls


def test_daily_spend_limit_set_dies_when_limits_unreadable(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ad_account/spend_limit_windows"] = {"_error": {"status": 403, "message": "Only ad account admins"}}
    with pytest.raises(SystemExit):
        run(["daily-spend-limit-set", "--amount", "100"])
    assert "billing" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Platform targeting (2026-09-10)
# ---------------------------------------------------------------------------

def test_campaign_create_accepts_granular_web_platforms(fake_api, capsys):
    run(["campaign-create", "--name", "Mobile web", "--daily-budget", "20", "--platforms", "android_web,ios_web", "--json"])
    body = json.loads(capsys.readouterr().out)["plan"]["body"]
    assert body["targeting"]["platforms"] == {"included": ["android_web", "ios_web"]}


def test_platforms_validation(fake_api, capsys):
    with pytest.raises(SystemExit):
        run(["campaign-create", "--name", "X campaign", "--daily-budget", "20", "--platforms", "tv_app"])
    with pytest.raises(SystemExit):  # empty list = HTTP 400 on the API
        run(["campaign-create", "--name", "X campaign", "--daily-budget", "20", "--platforms", ","])
    capsys.readouterr()
    run(["campaign-create", "--name", "X campaign", "--daily-budget", "20", "--platforms", "web,desktop_web", "--json"])
    assert "redundant" in capsys.readouterr().err


def test_campaign_update_platform_only_sends_just_platforms(fake_api, capsys):
    calls, _ = fake_api
    run(["campaign-update", "--campaign-id", "cmpn_1", "--platforms", "ios_app,android_app", "--json"])
    body = json.loads(capsys.readouterr().out)["plan"]["body"]
    assert body == {"targeting": {"platforms": {"included": ["ios_app", "android_app"]}}}
    assert not [c for c in calls if c["method"] == "GET"]  # no read-modify-write of audiences/locations


def test_campaign_update_clear_platforms_sends_null(fake_api, capsys):
    run(["campaign-update", "--campaign-id", "cmpn_1", "--clear-platforms", "--json"])
    assert json.loads(capsys.readouterr().out)["plan"]["body"] == {"targeting": {"platforms": None}}


def test_plan_rejects_unknown_platform(fake_api, tmp_path, capsys):
    p = _write_plan(tmp_path, campaign={"name": "Podzim", "bidding_type": "clicks", "daily_budget": 15, "end": "2099-01-01",
                                        "location_ids": ["1000055"], "conversion_event_setting_ids": ["ces_1"],
                                        "platforms": ["desktop_web", "smart_tv"]})
    with pytest.raises(SystemExit):
        run(["plan-apply", "--file", str(p)])
    assert "smart_tv" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Budgets & Maximize Results
# ---------------------------------------------------------------------------

def test_campaign_create_rejects_both_budget_types(fake_api):
    with pytest.raises(SystemExit):
        run(["campaign-create", "--name", "Two budgets", "--daily-budget", "20", "--lifetime-budget", "500"])


def test_campaign_update_daily_to_lifetime_is_blocked(fake_api, capsys):
    _, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "budget": {"daily_spend_limit_micros": 20_000_000}}
    with pytest.raises(SystemExit):
        run(["campaign-update", "--campaign-id", "cmpn_1", "--lifetime-budget", "500"])
    assert "cannot be switched back to lifetime" in capsys.readouterr().err


def test_adgroup_create_maximize_clicks_omits_bid(fake_api, capsys):
    _, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "bidding_type": "clicks", "budget": {"daily_spend_limit_micros": 20_000_000}}
    run(["adgroup-create", "--campaign-id", "cmpn_1", "--name", "Auto bid", "--strategy", "maximize_clicks", "--json"])
    bc = json.loads(capsys.readouterr().out)["plan"]["body"]["bidding_config"]
    assert bc == {"billing_event_type": "click", "strategy": "maximize_clicks"}


@pytest.mark.parametrize("campaign, needle", [
    ({"bidding_type": "clicks", "budget": {"lifetime_spend_limit_micros": 500_000_000}}, "DAILY campaign budget"),
    ({"bidding_type": "impressions", "budget": {"daily_spend_limit_micros": 20_000_000}}, "needs a clicks campaign"),
])
def test_adgroup_create_maximize_incompatible_campaign(fake_api, capsys, campaign, needle):
    _, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", **campaign}
    with pytest.raises(SystemExit):
        run(["adgroup-create", "--campaign-id", "cmpn_1", "--name", "Auto bid", "--strategy", "maximize_clicks",
             "--billing-event", "click"])
    assert needle in capsys.readouterr().err


def test_adgroup_maximize_with_bid_is_rejected(fake_api):
    _, answers = fake_api
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "bidding_type": "clicks", "budget": {"daily_spend_limit_micros": 1}}
    with pytest.raises(SystemExit):
        run(["adgroup-create", "--campaign-id", "cmpn_1", "--name", "Auto bid", "--strategy", "maximize_clicks", "--max-bid", "2"])


def test_adgroup_update_to_maximize_drops_bid_and_clears_multipliers(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ad_groups/adgrp_1"] = {"id": "adgrp_1", "campaign_id": "cmpn_1", "bidding_config": {
        "billing_event_type": "click", "strategy": "fixed_bid", "max_bid_micros": 2_000_000,
        "custom_audience_bid_multipliers": [{"custom_audience_id": "caud_1", "bid_multiplier_micros": 2_000_000}]}}
    answers["GET /campaigns/cmpn_1"] = {"id": "cmpn_1", "bidding_type": "clicks", "budget": {"daily_spend_limit_micros": 20_000_000}}
    run(["adgroup-update", "--ad-group-id", "adgrp_1", "--strategy", "maximize_clicks", "--json"])
    bc = json.loads(capsys.readouterr().out)["plan"]["body"]["bidding_config"]
    assert bc == {"billing_event_type": "click", "strategy": "maximize_clicks", "custom_audience_bid_multipliers": []}


def test_adgroup_update_back_to_fixed_bid_needs_explicit_bid(fake_api):
    _, answers = fake_api
    answers["GET /ad_groups/adgrp_1"] = {"id": "adgrp_1", "campaign_id": "cmpn_1",
                                         "bidding_config": {"billing_event_type": "click", "strategy": "maximize_clicks"}}
    with pytest.raises(SystemExit):
        run(["adgroup-update", "--ad-group-id", "adgrp_1", "--strategy", "fixed_bid"])


# ---------------------------------------------------------------------------
# bid_too_low (documented 2026-09, live-verified on detail AND list)
# ---------------------------------------------------------------------------

def test_adgroup_detail_requests_and_shows_bid_too_low(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /ad_groups/adgrp_1"] = {"id": "adgrp_1", "name": "G", "status": "active", "bid_too_low": True,
                                         "bidding_config": {"billing_event_type": "click", "max_bid_micros": 500_000}}
    run(["adgroup-detail", "--ad-group-id", "adgrp_1"])
    assert ("include[]", "bid_too_low") in calls[0]["params"]
    assert "bid_too_low" in capsys.readouterr().out


def test_adgroups_bid_check_column(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /ad_groups"] = {"data": [{"id": "g1", "name": "A", "status": "active", "bid_too_low": True},
                                          {"id": "g2", "name": "B", "status": "active", "bid_too_low": False}], "has_more": False}
    run(["adgroups", "--bid-check"])
    out = capsys.readouterr().out
    assert "Bid too low" in out and "bid_too_low: 1 of 2" in out
    assert ("include[]", "bid_too_low") in calls[0]["params"]


# ---------------------------------------------------------------------------
# Custom audience operations: list / cancel / resume
# ---------------------------------------------------------------------------

def test_audience_operations_follows_next_cursor(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /custom_audiences/caud_1/operations"] = [
        {"data": [{"operation_id": "op1", "operation": "add", "status": "succeeded"}], "has_more": True, "next_cursor": "c2"},
        {"data": [], "has_more": True, "next_cursor": "c3"},  # empty page but has_more → keep going (docs)
        {"data": [{"operation_id": "op2", "operation": "remove", "status": "processing"}], "has_more": False, "next_cursor": None},
    ]
    run(["audience-operations", "--audience-id", "caud_1", "--json"])
    assert [o["operation_id"] for o in json.loads(capsys.readouterr().out)] == ["op1", "op2"]
    assert ("cursor", "c3") in calls[2]["params"]


@pytest.mark.parametrize("action", ["cancel", "resume"])
def test_audience_operation_actions_send_no_body_and_no_key(fake_api, capsys, action):
    calls, answers = fake_api
    answers[f"POST /custom_audiences/caud_1/operations/op1/{action}"] = {"operation_id": "op1", "operation": "add", "status": "failed"}
    run([f"audience-operation-{action}", "--audience-id", "caud_1", "--operation-id", "op1", "--confirm"])
    w = writes(calls)[0]
    assert w["path"].endswith(f"/op1/{action}") and w["json"] is None and w["idempotency_key"] is None


def test_audience_operation_recovery_required_points_to_resume(fake_api, capsys):
    _, answers = fake_api
    answers["GET /custom_audiences/caud_1/operations/op1"] = {"_error": {
        "status": 409, "code": "custom_audience_operation_recovery_required", "message": "recover"}}
    with pytest.raises(SystemExit):
        run(["audience-operation", "--audience-id", "caud_1", "--operation-id", "op1"])
    assert "audience-operation-resume --audience-id caud_1 --operation-id op1" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Insights: platform segment, retention
# ---------------------------------------------------------------------------

def test_insights_platform_segment_fields_and_label(fake_api, capsys):
    calls, answers = fake_api
    answers["GET /ad_account/insights"] = {"data": [{"platform": "ios_app", "impressions": 100, "clicks": 5, "spend": 3.0}]}
    run(["insights", "--segment", "platform", "--granularity", "none"])
    params = next(c["params"] for c in calls if c["path"] == "/ad_account/insights")
    assert ("segments[]", "platform") in params and ("fields[]", "platform") in params and ("fields[]", "platform.clicks") in params
    out = capsys.readouterr().out
    assert "ios_app" in out and "Platform" in out and "not split retroactively" in out


def test_retention_warnings():
    old = date.today() - timedelta(days=40)
    assert retention_warnings(old, "hourly", None) and retention_warnings(old, "daily", "product")
    assert not retention_warnings(old, "daily", None)
    assert retention_warnings(date.today() - timedelta(days=400), "daily", None)


# ---------------------------------------------------------------------------
# pulse: origin country, bid_too_low, daily limit
# ---------------------------------------------------------------------------

def test_pulse_uses_origin_country_and_reports_bid_too_low(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ad_account"] = {"id": "adacct_1", "name": "Acme", "status": "active", "review": {"status": "approved"},
                                  "origin_country_code": "SK"}
    answers["GET /ad_account/spend_limit_windows"] = {"data": [], "revision": 1, "daily_limit": {
        "amount_micros": 50_000_000, "start_date": "2026-10-01", "end_date": None, "status": "upcoming"}}
    answers["GET /ad_account/insights"] = {"data": []}
    answers["POST /conversions/insights"] = {"data": []}
    answers["GET /ads"] = {"data": []}
    answers["GET /ad_groups"] = {"data": [{"id": "g1", "name": "A", "status": "active", "bid_too_low": True},
                                          {"id": "g2", "name": "B", "status": "paused", "bid_too_low": True}]}
    answers["GET /conversions/event_settings"] = {"data": []}
    answers["GET /campaigns"] = {"data": [{"id": "c1", "name": "CZ only", "status": "paused", "conversion_event_setting_ids": [],
                                          "targeting": {"locations": {"countries": ["CZ"]}}}]}
    run(["pulse"])
    out = capsys.readouterr().out
    assert "targets ['CZ']" in out and "is SK" in out          # origin_country_code beats the timezone map
    assert "1 active ad group(s) flagged bid_too_low (g1)" in out
    assert "daily account limit: 50.00 USD/day" in out


# ---------------------------------------------------------------------------
# Deprecated (removed from the public spec)
# ---------------------------------------------------------------------------

def test_deprecated_commands_warn_on_stderr(fake_api, capsys):
    _, answers = fake_api
    answers["GET /ad_account"] = {"id": "adacct_1"}
    run(["negative-keywords", "--json"])
    assert "removed from the public OpenAPI spec" in capsys.readouterr().err


def test_campaign_ended_is_an_expected_state_not_a_problem():
    from oaiads.commands.common import ad_attention
    assert ad_attention({"review_status": "approved", "serving_issues": [{"code": "campaign_ended"}]}) is None
    assert ad_attention({"review_status": "rejected", "serving_issues": [{"code": "review_not_approved"}]}) == "problem"
