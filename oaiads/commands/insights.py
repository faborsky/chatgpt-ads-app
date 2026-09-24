"""Commands: insights, conversion-insights, pulse."""

from __future__ import annotations

import json
from datetime import date, timedelta

from oaiads import api
from oaiads.formatting import _die, _err, fmt_delta, fmt_money, fmt_num, print_table, _truncate
from oaiads.commands.common import ad_attention, brief_error, date_window, emit, parse_csv, parse_json_arg, qarr

LEVELS = ["account", "campaign", "ad_group", "ad"]
LEVEL_WIRE = {"account": "ad_account", "campaign": "campaign", "ad_group": "ad_group", "ad": "ad"}
GRANULARITIES = ["hourly", "daily", "monthly", "none"]
SEGMENTS = ["product", "country", "device", "platform"]  # platform: 2026-09-10 (apps + desktop/iOS/Android web)
INCLUDES = ["zero_impression_items", "zero_impression_products"]
METRICS = ["impressions", "clicks", "spend", "ctr", "cpc", "cpm"]
DEFAULT_CHILD = {"account": "campaign", "campaign": "ad_group", "ad_group": "ad", "ad": "ad"}
LIST_PATH = {"campaign": "/campaigns", "ad_group": "/ad_groups", "ad": "/ads"}


# Coarse timezone → home country map for the "targets a foreign country" guard (pulse).
_TZ_COUNTRY = {
    "Europe/Prague": "CZ", "Europe/Bratislava": "SK", "Europe/Vienna": "AT", "Europe/Berlin": "DE", "Europe/Warsaw": "PL",
    "Europe/Budapest": "HU", "Europe/Paris": "FR", "Europe/Madrid": "ES", "Europe/Rome": "IT", "Europe/Amsterdam": "NL",
    "Europe/Brussels": "BE", "Europe/Lisbon": "PT", "Europe/Dublin": "IE", "Europe/London": "GB", "Europe/Stockholm": "SE",
    "Europe/Copenhagen": "DK", "Europe/Oslo": "NO", "Europe/Helsinki": "FI", "Europe/Zurich": "CH", "Europe/Athens": "GR",
    "Europe/Bucharest": "RO", "Europe/Sofia": "BG", "Europe/Zagreb": "HR", "Europe/Ljubljana": "SI", "Europe/Vilnius": "LT",
    "Europe/Riga": "LV", "Europe/Tallinn": "EE", "Australia/Sydney": "AU", "Asia/Tokyo": "JP", "America/Toronto": "CA",
}


def home_country_for_timezone(tz: str | None) -> str | None:
    if not tz:
        return None
    if tz in _TZ_COUNTRY:
        return _TZ_COUNTRY[tz]
    if tz.startswith("America/") and tz not in ("America/Toronto", "America/Vancouver", "America/Mexico_City", "America/Sao_Paulo"):
        return "US"
    return None


def campaign_countries(c: dict) -> set:
    """Country codes a campaign's location targeting resolves to (empty = all locations)."""
    t = c.get("targeting") or {}
    locs = t.get("locations") or {}
    out = {str(x).upper() for x in (locs.get("countries") or [])}
    for loc in locs.get("include") or []:
        if isinstance(loc, dict) and loc.get("country_code"):
            out.add(str(loc["country_code"]).upper())
    return out


def _scope_path(level: str, object_id: str | None) -> str:
    if level == "account":
        return "/ad_account/insights"
    if not object_id:
        _die(f"ERROR: --object-id is required for --level {level}.")
    return {"campaign": "/campaigns", "ad_group": "/ad_groups", "ad": "/ads"}[level] + f"/{object_id}/insights"


def time_range_param(since, until, tz: str | None) -> str:
    rng = {"type": "date_range", "since": since.isoformat(), "until": until.isoformat()}
    if tz:
        rng["timezone"] = tz
    return json.dumps(rng, separators=(",", ":"))


def default_fields(agg: str, granularity: str, segment: str | None) -> list[str]:
    wire = LEVEL_WIRE[agg]
    fields = []
    if granularity != "none":
        fields.append("metadata.readable_time")
    fields += [f"{wire}.id", f"{wire}.name"]
    if agg in ("campaign", "ad_group", "ad"):
        fields.append(f"{wire}.status")
    if agg == "ad":
        fields.append("ad.review_status")
    if segment:
        # `platform` is the canonical field itself (valid only with segments[]=platform); metrics come back as flat
        # wire keys (clicks, spend) — live-verified 2026-09-24.
        seg_meta = {"product": ["product.item_id", "product.title"], "country": ["country.name"], "device": ["device.type"],
                    "platform": ["platform"]}
        fields += seg_meta[segment]
        fields += [f"{segment}.{m}" for m in METRICS]
    else:
        fields += [f"{wire}.{m}" for m in METRICS]
    return fields


def metric(row: dict, agg: str, name: str, segment: str | None = None):
    """Read a metric from a row regardless of flat vs prefixed wire key."""
    wire = LEVEL_WIRE[agg]
    for key in ((f"{segment}_{name}",) if segment else ()) + (name, f"{wire}_{name}"):
        if key in row and row[key] is not None:
            return row[key]
    return None


def build_params(args, agg: str, since, until) -> list:
    tz = args.timezone or api.account_timezone()
    params: list = [("time_granularity", args.granularity), ("aggregation_level", LEVEL_WIRE[agg]),
                    ("limit", min(max(args.limit, 1), 2000))]
    params.append((qarr("time_ranges"), time_range_param(since, until, tz)))
    fields = parse_csv(args.fields) if args.fields else default_fields(agg, args.granularity, args.segment)
    for f in fields:
        params.append((qarr("fields"), f))
    for flt in args.filter or []:
        params.append((qarr("filters"), json.dumps(parse_json_arg(flt, "--filter"), separators=(",", ":"))))
    for s in args.sort or []:
        if s.startswith("{"):
            params.append((qarr("sort"), json.dumps(parse_json_arg(s, "--sort"), separators=(",", ":"))))
        else:
            field, _, direction = s.partition(":")
            params.append((qarr("sort"), json.dumps({"field": field, "direction": direction or "desc"}, separators=(",", ":"))))
    if args.segment:
        params.append((qarr("segments"), args.segment))
        if args.segment_first:
            params.append((qarr("override_segment_group_order"), args.segment))
            params.append((qarr("override_segment_group_order"), LEVEL_WIRE[agg]))
    if args.include:
        params.append((qarr("includes"), args.include))
    return params


# Reporting retention (docs → Reporting → Historical availability, 2026-09).
RETENTION_DAYS = {"hourly": 30, "product": 30, "default": 365}


def retention_warnings(since, granularity: str, segment: str | None) -> list[str]:
    age = (date.today() - since).days
    out = []
    if granularity == "hourly" and age > RETENTION_DAYS["hourly"]:
        out.append(f"hourly reporting keeps ~{RETENTION_DAYS['hourly']} days — --since {since} is older; expect missing rows.")
    if segment == "product" and age > RETENTION_DAYS["product"]:
        out.append(f"product reporting keeps ~{RETENTION_DAYS['product']} days — --since {since} is older; expect missing rows.")
    if age > RETENTION_DAYS["default"]:
        out.append(f"delivery reporting keeps the most recent {RETENTION_DAYS['default']} days — --since {since} is older.")
    return out


def fetch_insights(path: str, params: list, fetch_all: bool, max_items: int) -> list:
    if not fetch_all:
        data = api._api_call("GET", path, params)
        rows = data.get("data", [])
        if data.get("has_more"):
            _err(f"⚠ More rows exist beyond --limit {len(rows)} (has_more=true). Use --all or raise --limit.")
        return rows
    return api._fetch_all(path, params, max_items=max_items, page_size=min(2000, max_items))


def cmd_insights(args) -> None:
    agg = args.aggregation_level or DEFAULT_CHILD[args.level]
    if LEVELS.index(agg) < LEVELS.index(args.level):
        _die(f"ERROR: --aggregation-level {agg} is above the endpoint scope {args.level}.")
    if args.segment and args.granularity == "hourly":
        _die("ERROR: segmented requests support none/daily/monthly only.")
    since, until = date_window(args.days, args.since, args.until)
    for msg in retention_warnings(since, args.granularity, args.segment):
        _err(f"⚠ {msg}")
    path = _scope_path(args.level, args.object_id)
    params = build_params(args, agg, since, until)
    rows = fetch_insights(path, params, args.all, args.max_items)
    cur = api.account_currency()

    def human(items):
        wire = LEVEL_WIRE[agg]
        seg = args.segment
        # Segmented rows are entity × segment — show the entity too, or rows of different campaigns look duplicated.
        with_entity = bool(seg) and agg != "account"
        headers = (["Time"] if args.granularity != "none" else []) + \
                  ([_truncate(agg, 12)] if with_entity else []) + \
                  ([{"product": "Product", "country": "Country", "device": "Device", "platform": "Platform"}[seg]] if seg else [f"{agg} id", "Name"]) + \
                  ["Impr", "Clicks", "CTR %", "CPC", "CPM", "Spend"]
        table = []
        for r in items:
            row = []
            if args.granularity != "none":
                row.append(r.get("readable_time", ""))
            if with_entity:
                row.append(_truncate(r.get(f"{wire}_name") or r.get(f"{wire}_id") or "", 30))
            if seg:
                label = (r.get("product_title") or r.get("item_id") or r.get("country_name") or r.get("device_type")
                         or r.get("platform") or "")
                row.append(_truncate(label, 36))
            else:
                row += [r.get(f"{wire}_id") or r.get("id", ""), _truncate(r.get(f"{wire}_name") or r.get("name"), 36)]
            impr = metric(r, agg, "impressions", seg) or 0
            clicks = metric(r, agg, "clicks", seg) or 0
            spend = metric(r, agg, "spend", seg) or 0
            ctr = metric(r, agg, "ctr", seg)
            row += [fmt_num(impr, 0), fmt_num(clicks, 0),
                    fmt_num((ctr * 100) if ctr is not None else (clicks / impr * 100 if impr else 0), 2),
                    fmt_num(metric(r, agg, "cpc", seg) or (spend / clicks if clicks else 0), 3),
                    fmt_num(metric(r, agg, "cpm", seg) or (spend / impr * 1000 if impr else 0), 2),
                    f"{fmt_num(spend, 2)} {cur}"]
            table.append(row)
        print(f"Insights {since} → {until} ({api.account_timezone()}), scope {args.level}"
              f"{' ' + args.object_id if args.object_id else ''}, rows by {agg}, granularity {args.granularity}")
        print_table(table, headers)
        if seg == "platform":
            print("Platform rows: historical 'web' keeps combined web totals (not split retroactively); conversions are not "
                  "available per platform.")
        tot_s = sum((metric(r, agg, 'spend', seg) or 0) for r in items)
        tot_i = sum((metric(r, agg, 'impressions', seg) or 0) for r in items)
        tot_c = sum((metric(r, agg, 'clicks', seg) or 0) for r in items)
        print(f"\nΣ {len(items)} rows: {fmt_num(tot_i, 0)} impr, {fmt_num(tot_c, 0)} clicks, {fmt_num(tot_s, 2)} {cur}"
              + (" — spend is in ACCOUNT currency" if cur else ""))

    emit(rows, args, human)


# ---------------------------------------------------------------------------
# conversion-insights (POST /conversions/insights)
# ---------------------------------------------------------------------------

def cmd_conversion_insights(args) -> None:
    since, until = date_window(args.days, args.since, args.until)
    tz = args.timezone or api.account_timezone()
    body: dict = {"aggregation_level": LEVEL_WIRE[args.level],
                  "time_ranges": [time_range_param(since, until, tz)],
                  "time_granularity": args.granularity}
    # Verified live 2026-09-07: the server defaults group_by_entity to TRUE and then rejects the call
    # with 400 "entity_ids must be provided when group_by_entity is true". So: ids given (or asked for
    # via --group-by-entity → we list the level's non-archived objects) → one row per entity;
    # otherwise group_by_entity=false → ONE total row (entity_id = the ad account).
    ids = parse_csv(args.ids)
    if args.group_by_entity and not ids and args.level != "account":
        ids = [o["id"] for o in api._fetch_all(LIST_PATH[args.level], []) if o.get("status") != "archived" and o.get("id")]
        if not ids:
            _die(f"ERROR: --group-by-entity: no non-archived {args.level} objects to group by (pass --ids).")
    body["group_by_entity"] = bool(ids)
    if ids:
        body["entity_ids"] = ids
    if args.breakdown:
        body["breakdown"] = args.breakdown
    if args.include_zero:
        body["include_zero_rows"] = True
    data = api._api_call("POST", "/conversions/insights", json_body=body, idempotent=True)
    rows = data.get("data", []) if isinstance(data, dict) else data

    def human(items):
        scope = f"{len(ids)} {args.level}(s)" if ids else "whole account (one total row; --ids or --group-by-entity for per-entity rows)"
        print(f"Conversions {since} → {until} ({tz}), level {args.level}, granularity {args.granularity}, {scope}")
        print_table([[r.get("entity_id"), r.get("date") or "", r.get("device") or r.get("country") or "",
                      r.get("conversions"), r.get("click_through_conversions"), r.get("view_through_conversions")]
                     for r in items],
                    ["Entity", "Date", "Breakdown", "Conversions", "Click-through", "View-through"])
        print("\nconversions == click_through_conversions; view-through is a separate, reporting-only metric (1-day window).")

    emit(rows, args, human)


# ---------------------------------------------------------------------------
# pulse — account digest
# ---------------------------------------------------------------------------

def cmd_pulse(args) -> None:
    days = args.days
    since, until = date_window(days, None, None)
    prev_until = since - timedelta(days=1)
    prev_since = prev_until - timedelta(days=days - 1)
    tz = api.account_timezone()
    cur = api.account_currency()

    from oaiads.commands.account import fetch_spend_limits, fmt_daily_limit
    acct = api._api_call("GET", "/ad_account", soft=True)
    windows = fetch_spend_limits()

    def campaign_rows(s, u):
        params = [("time_granularity", "none"), ("aggregation_level", "campaign"), ("limit", 500),
                  (qarr("time_ranges"), time_range_param(s, u, tz))]
        for f in ["campaign.id", "campaign.name", "campaign.status", "campaign.impressions", "campaign.clicks",
                  "campaign.spend", "campaign.ctr", "campaign.cpc", "campaign.cpm"]:
            params.append((qarr("fields"), f))
        data = api._api_call("GET", "/ad_account/insights", params, soft=True)
        if brief_error(data):
            return None, brief_error(data)
        return data.get("data", []), None

    cur_rows, err_cur = campaign_rows(since, until)
    prev_rows, err_prev = campaign_rows(prev_since, prev_until)

    # group_by_entity=false → one account-total row; the server default (true) needs entity_ids and
    # answered 400 in every pulse run (seen live 2026-09-07).
    conv = api._api_call("POST", "/conversions/insights", json_body={
        "aggregation_level": "campaign", "time_granularity": "none",
        "time_ranges": [time_range_param(since, until, tz)], "group_by_entity": False}, soft=True, idempotent=True)

    settings = api._api_call("GET", "/conversions/event_settings", [("limit", 500)], soft=True)
    campaigns_all = api._api_call("GET", "/campaigns", [("limit", 500)], soft=True)
    unlinked = []
    if isinstance(settings, dict) and "_error" not in settings and isinstance(campaigns_all, dict) and "_error" not in campaigns_all:
        if [e for e in settings.get("data", []) if not e.get("archived")]:
            unlinked = [c for c in campaigns_all.get("data", []) if c.get("status") == "active"
                        and not c.get("conversion_event_setting_ids")]

    home = ((acct.get("origin_country_code") if isinstance(acct, dict) else None) or home_country_for_timezone(tz))
    foreign = []
    if home and isinstance(campaigns_all, dict) and "_error" not in campaigns_all:
        for c in campaigns_all.get("data", []):
            if c.get("status") == "archived":
                continue
            countries = campaign_countries(c)
            if countries and home not in countries:
                foreign.append({"id": c.get("id"), "name": c.get("name"), "status": c.get("status"), "countries": sorted(countries)})

    groups = api._api_call("GET", "/ad_groups", [(qarr("include"), "bid_too_low"), ("limit", 500)], soft=True)
    bid_low = []
    if isinstance(groups, dict) and "_error" not in groups:
        bid_low = [{"id": g.get("id"), "name": g.get("name")} for g in groups.get("data", [])
                   if g.get("bid_too_low") and g.get("status") == "active"]

    ads = api._api_call("GET", "/ads", [(qarr("include"), "serving_issues"), ("limit", 500)], soft=True)
    flagged, waiting, paused_only = [], [], []
    if isinstance(ads, dict) and "_error" not in ads:
        live_ads = [a for a in ads.get("data", []) if a.get("status") != "archived"]
        # Same classification as ad-review: paused-hierarchy / in-review codes are intended states.
        flagged = [a for a in live_ads if ad_attention(a) == "problem"]
        waiting = [a for a in live_ads if ad_attention(a) == "waiting"]
        paused_only = [a for a in live_ads if not ad_attention(a) and a.get("serving_issues")]

    def agg(rows):
        t = {"impressions": 0, "clicks": 0, "spend": 0.0}
        for r in rows or []:
            for k in t:
                t[k] += metric(r, "campaign", k) or 0
        return t

    tot, prev = agg(cur_rows), agg(prev_rows)
    conv_total = None
    if isinstance(conv, dict) and "_error" not in conv:
        conv_total = sum(int(r.get("conversions") or 0) for r in conv.get("data", []))

    result = {
        "window": {"since": str(since), "until": str(until), "previous_since": str(prev_since),
                   "previous_until": str(prev_until), "timezone": tz, "currency": cur},
        "account": acct if isinstance(acct, dict) else None,
        "spend_limit_windows": (windows.get("data") or [] if "_error" not in windows else None),
        "daily_spend_limit": (windows.get("daily_limit") if "_error" not in windows else None),
        "ad_groups_bid_too_low": bid_low,
        "totals": tot, "previous_totals": prev, "conversions": conv_total,
        "campaigns": cur_rows, "previous_campaigns": prev_rows,
        "ads_needing_attention": flagged,
        "ads_waiting_for_review": waiting,
        "ads_paused_only": len(paused_only),
        "active_campaigns_without_conversion_event": [{"id": c.get("id"), "name": c.get("name")} for c in unlinked],
        "campaigns_targeting_foreign_country": foreign,
        "errors": {k: v for k, v in (("insights", err_cur or err_prev), ("conversions", brief_error(conv)),
                                    ("ads", brief_error(ads)), ("account", brief_error(acct)),
                                    ("ad_groups", brief_error(groups)),
                                    ("spend_limits", brief_error(windows))) if v},
    }

    def human(r):
        a = r["account"] or {}
        review = (a.get("review") or {}).get("status")
        print(f"PULSE — {a.get('name', '?')} ({a.get('id', '?')})  {since} → {until} vs {prev_since} → {prev_until}  [{tz}]")
        print(f"  account status {a.get('status')}  brand review {review}" + (
            "  ⚠ NOT APPROVED — cannot serve" if review and review != "approved" else ""))
        wins = r["spend_limit_windows"]
        if wins is None and r["errors"].get("spend_limits"):
            print(f"  account spending limits: not readable ({r['errors']['spend_limits']}) — rely on campaign daily budgets/end dates.")
        if wins is not None:
            if r["daily_spend_limit"]:
                print(f"  daily account limit: {fmt_daily_limit(r['daily_spend_limit'], cur)}")
            active = [w for w in wins if str(w.get("status", "")).lower() in ("active", "upcoming")]
            if not active and not r["daily_spend_limit"]:
                print("  account spending limits: NONE — no account-level cap (daily-spend-limit-set / spend-limit-create).")
            for w in active:
                print(f"  spend cap {w.get('start_date')}→{w.get('end_date')}: "
                      f"{fmt_money(w.get('spent_micros'), cur)} of {fmt_money(w.get('amount_micros'), cur)} [{w.get('status')}]")
        if r["errors"].get("insights"):
            print(f"  insights unavailable: {r['errors']['insights']}")
        else:
            t, p = r["totals"], r["previous_totals"]
            ctr = (t["clicks"] / t["impressions"] * 100) if t["impressions"] else 0
            pctr = (p["clicks"] / p["impressions"] * 100) if p["impressions"] else 0
            cpc = t["spend"] / t["clicks"] if t["clicks"] else 0
            pcpc = p["spend"] / p["clicks"] if p["clicks"] else 0
            print(f"\n  Spend   {fmt_delta(t['spend'], p['spend'])} {cur}")
            print(f"  Impr    {fmt_delta(t['impressions'], p['impressions'])}")
            print(f"  Clicks  {fmt_delta(t['clicks'], p['clicks'])}")
            print(f"  CTR %   {fmt_delta(ctr, pctr, pct=True)}")
            print(f"  CPC     {fmt_delta(cpc, pcpc, pct=True)} {cur}")
            if r["conversions"] is not None:
                cpa = (t["spend"] / r["conversions"]) if r["conversions"] else 0
                print(f"  Conv    {r['conversions']}   CPA {fmt_num(cpa, 2)} {cur}")
            prev_by = {row.get("campaign_id"): row for row in (r["previous_campaigns"] or [])}
            rows = sorted(r["campaigns"] or [], key=lambda x: -(metric(x, "campaign", "spend") or 0))
            if rows:
                print("\n  Campaigns (by spend):")
                table = []
                for c in rows[:15]:
                    pc = prev_by.get(c.get("campaign_id"), {})
                    sp, psp = metric(c, "campaign", "spend") or 0, metric(pc, "campaign", "spend") or 0
                    cl, pcl = metric(c, "campaign", "clicks") or 0, metric(pc, "campaign", "clicks") or 0
                    im = metric(c, "campaign", "impressions") or 0
                    table.append([c.get("campaign_id"), _truncate(c.get("campaign_name"), 34), c.get("campaign_status") or "",
                                  fmt_num(im, 0), fmt_delta(cl, pcl), fmt_num(cl / im * 100 if im else 0, 2),
                                  fmt_delta(sp, psp)])
                print_table(table, ["ID", "Campaign", "Status", "Impr", "Clicks", "CTR %", f"Spend {cur}"])
            else:
                print("\n  No delivery in the window.")
        for c in r["campaigns_targeting_foreign_country"]:
            print(f"\n  ⚠ campaign {c['id']} \"{c['name']}\" [{c['status']}] targets {c['countries']} while the account's home country "
                  f"(origin_country_code / timezone {tz}) is {home} — Ads Manager's auto-generated campaigns default to US. campaign-update --location-ids <country id>")
        if r["active_campaigns_without_conversion_event"]:
            names = ", ".join(c["id"] for c in r["active_campaigns_without_conversion_event"][:5])
            print(f"\n  ⚠ {len(r['active_campaigns_without_conversion_event'])} active campaign(s) with no conversion event linked ({names}) — "
                  "clicks only, no CPA. See conversion-check.")
        if r["ad_groups_bid_too_low"]:
            names = ", ".join(g["id"] for g in r["ad_groups_bid_too_low"][:5])
            print(f"\n  ⚠ {len(r['ad_groups_bid_too_low'])} active ad group(s) flagged bid_too_low ({names}) — OpenAI's guidance that "
                  "the bid may be too low for reliable delivery (adgroups --bid-check). Not a block; check impressions first.")
        if r["ads_needing_attention"]:
            print(f"\n  ⚠ {len(r['ads_needing_attention'])} ad(s) rejected / with serving issues — run ad-review.")
        elif not r["errors"].get("ads"):
            print("\n  ✅ No rejected ads, no serving issues"
                  + (f" ({r['ads_paused_only']} not serving only because the campaign/ad group/ad is paused)" if r["ads_paused_only"] else "")
                  + ".")
        if r["ads_waiting_for_review"]:
            print(f"  ℹ {len(r['ads_waiting_for_review'])} ad(s) waiting for review — normal for minutes after create/edit.")
        for k, v in r["errors"].items():
            if k not in ("insights", "spend_limits"):
                print(f"  ({k}: {v})")

    emit(result, args, human)
