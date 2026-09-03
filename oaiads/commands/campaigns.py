"""Commands: campaigns, campaign-detail, campaign-create/update, campaign-activate/pause/archive."""

from __future__ import annotations

from oaiads import api, lint
from oaiads.formatting import _die, _err, fmt_money, fmt_ts, print_table, _truncate
from oaiads.commands.common import (
    drop_archived, emit, issues_str, money_flag, parse_csv, parse_json_arg, parse_time_to_unix,
    print_plan, qarr, run_write, state_change, trunc,
)

BIDDING_TYPES = ["impressions", "clicks", "conversions"]
OBJECTIVES = ["reach", "clicks", "conversions"]
PLATFORMS = ["web", "ios_app", "android_app"]
MODES = ["product_feed", "business_agent"]


def _list_params(args) -> list:
    params = []
    if getattr(args, "name", None):
        if len(args.name) < 3:
            _die("ERROR: --name filter needs at least 3 characters.")
        params.append(("name", args.name))
    if getattr(args, "include_issues", False):
        params.append((qarr("include"), "serving_issues"))
    if getattr(args, "order", None):
        params.append(("order", args.order))
    return params


def cmd_campaigns(args) -> None:
    rows = drop_archived(api._fetch_all("/campaigns", _list_params(args), max_items=args.max_items),
                         args.status, args.all)
    cur = api.account_currency()

    def human(items):
        table = []
        for c in items:
            b = c.get("budget") or {}
            budget = fmt_money(b.get("lifetime_spend_limit_micros"), cur) if b.get("lifetime_spend_limit_micros") \
                else (f"{fmt_money(b.get('daily_spend_limit_micros'), cur)}/day" if b.get("daily_spend_limit_micros") else "---")
            table.append([c.get("id"), trunc(c.get("name"), args), c.get("status"), c.get("bidding_type"),
                          c.get("mode") or "", budget, fmt_ts(c.get("start_time"))[:10], fmt_ts(c.get("end_time"))[:10],
                          _truncate(issues_str(c), 40)])
        print_table(table, ["ID", "Name", "Status", "Bidding", "Mode", "Budget", "Start", "End", "Issues"])
        print(f"\n{len(items)} campaign(s)" + ("" if args.all or args.status else " (archived hidden — use --all)"))

    emit(rows, args, human)


def cmd_campaign_detail(args) -> None:
    c = api._api_call("GET", f"/campaigns/{args.campaign_id}", [(qarr("include"), "serving_issues")])
    if args.with_children:
        c["_ad_groups"] = api._fetch_all("/ad_groups", [("campaign_id", args.campaign_id), (qarr("include"), "serving_issues")])
        for g in c["_ad_groups"]:
            g["_ads"] = api._fetch_all("/ads", [("ad_group_id", g["id"]), (qarr("include"), "serving_issues")])
    cur = api.account_currency()

    def human(c):
        b = c.get("budget") or {}
        print(f"Campaign {c.get('id')} — {c.get('name')}")
        print(f"  status: {c.get('status')}   bidding: {c.get('bidding_type')}   objective: {c.get('objective')}   "
              f"billing: {c.get('billing_event_type')}   mode: {c.get('mode')}")
        print(f"  budget: lifetime {fmt_money(b.get('lifetime_spend_limit_micros'), cur)}  daily {fmt_money(b.get('daily_spend_limit_micros'), cur)}")
        print(f"  time:   {fmt_ts(c.get('start_time'))} → {fmt_ts(c.get('end_time'))}   created {fmt_ts(c.get('created_at'))}")
        if c.get("description"):
            print(f"  description: {c['description']}")
        t = c.get("targeting") or {}
        if t:
            locs = (t.get("locations") or {})
            inc = locs.get("include") or []
            print(f"  targeting: countries={locs.get('countries') or []} locations={[(l.get('name') or l.get('id')) for l in inc]}"
                  f" excluded={[(l.get('name') or l.get('id')) for l in ((t.get('excluded_locations') or {}).get('include') or [])]}"
                  f" audiences={(t.get('custom_audiences') or {}).get('ids') or []} excl_audiences={(t.get('excluded_custom_audiences') or {}).get('ids') or []}"
                  f" platforms={(t.get('platforms') or {}).get('included') if t.get('platforms') else 'all'}")
        if c.get("conversion_event_setting_ids"):
            print(f"  conversion event settings: {c['conversion_event_setting_ids']}")
        if c.get("product_feed_id"):
            print(f"  product feed: {c['product_feed_id']}")
        if c.get("business_agent_id"):
            print(f"  business agent: {c['business_agent_id']}")
        if c.get("landing_page_configuration"):
            print(f"  landing page config: {c['landing_page_configuration']}")
        iss = issues_str(c)
        print(f"  serving issues: {iss or 'none'}")
        if "_ad_groups" in c:
            total_ads = sum(len(g.get("_ads") or []) for g in c["_ad_groups"])
            print(f"\n  Tree: {len(c['_ad_groups'])} ad group(s), {total_ads} ad(s)")
            for g in c["_ad_groups"]:
                bc = g.get("bidding_config") or {}
                bid = fmt_money(bc.get("max_bid_micros"), cur) if bc.get("max_bid_micros") else (bc.get("strategy") or "auto")
                print(f"  ├─ {g.get('id')}  {_truncate(g.get('name'), 40)}  [{g.get('status')}]  {bc.get('billing_event_type')} {bid}  "
                      f"hints {len(g.get('context_hints') or [])}  {issues_str(g)}")
                for a in g.get("_ads") or []:
                    cr = a.get("creative") or {}
                    print(f"  │    {a.get('id')}  {_truncate(a.get('name'), 30)}  [{a.get('status')}]  review {a.get('review_status')}  "
                          f"\"{_truncate(cr.get('title'), 28)}\"  {issues_str(a)}")

    emit(c, args, human)


def _targeting_from_args(args, current: dict | None = None) -> dict | None:
    """Build TargetingParams from flags; None when no targeting flag was given."""
    if getattr(args, "targeting_json", None):
        return parse_json_arg(args.targeting_json, "--targeting-json")
    t: dict = dict(current or {}) if current else {}
    touched = False
    if getattr(args, "countries", None) is not None:
        t.setdefault("locations", {})["countries"] = [c.upper() for c in parse_csv(args.countries)]
        touched = True
    if getattr(args, "location_ids", None) is not None:
        ids = parse_csv(args.location_ids)
        if len(ids) > lint.LOCATION_IDS_MAX:
            _die(f"ERROR: max {lint.LOCATION_IDS_MAX} location ids.")
        t.setdefault("locations", {})["include"] = [{"id": i} for i in ids]
        touched = True
    if getattr(args, "exclude_location_ids", None) is not None:
        t["excluded_locations"] = {"include": [{"id": i} for i in parse_csv(args.exclude_location_ids)]}
        touched = True
    if getattr(args, "audience_ids", None) is not None:
        t["custom_audiences"] = {"ids": parse_csv(args.audience_ids)}
        touched = True
    if getattr(args, "exclude_audience_ids", None) is not None:
        t["excluded_custom_audiences"] = {"ids": parse_csv(args.exclude_audience_ids)}
        touched = True
    if getattr(args, "platforms", None) is not None:
        plats = parse_csv(args.platforms)
        bad = [p for p in plats if p not in PLATFORMS]
        if bad:
            _die(f"ERROR: unknown platform(s) {bad}; use {PLATFORMS}.")
        t["platforms"] = {"included": plats}
        touched = True
    if current is not None:
        # Strip server-expanded location metadata so we only send ids back.
        for key in ("locations", "excluded_locations"):
            inc = (t.get(key) or {}).get("include")
            if inc:
                t[key]["include"] = [{"id": l["id"]} for l in inc if isinstance(l, dict) and l.get("id")]
    inc_ids = set((t.get("custom_audiences") or {}).get("ids") or [])
    exc_ids = set((t.get("excluded_custom_audiences") or {}).get("ids") or [])
    if inc_ids & exc_ids:
        _die(f"ERROR: audience(s) both included and excluded: {sorted(inc_ids & exc_ids)}")
    return t if touched else None


def _budget_from_args(args) -> dict | None:
    budget: dict = {}
    lifetime = money_flag(getattr(args, "lifetime_budget", None), "--lifetime-budget", lint.BUDGET_MIN_MICROS)
    daily = money_flag(getattr(args, "daily_budget", None), "--daily-budget", lint.BUDGET_MIN_MICROS)
    if lifetime is not None:
        budget["lifetime_spend_limit_micros"] = lifetime
    if daily is not None:
        budget["daily_spend_limit_micros"] = daily
    return budget or None


def cmd_campaign_create(args) -> None:
    findings: list = []
    lint.lint_name(args.name, "Campaign", findings)
    budget = _budget_from_args(args)
    lint.lint_budget(budget, findings)
    start = parse_time_to_unix(args.start, "--start")
    end = parse_time_to_unix(args.end, "--end")
    lint.lint_times(start, end, findings)

    body: dict = {"name": args.name, "status": args.status, "budget": budget}
    if args.description:
        body["description"] = args.description
    if start:
        body["start_time"] = start
    if end:
        body["end_time"] = end
    if args.bidding_type:
        body["bidding_type"] = args.bidding_type
    if args.objective:
        body["objective"] = args.objective
    if args.billing_event_type:
        body["billing_event_type"] = args.billing_event_type
    if args.mode:
        body["mode"] = args.mode
    if args.product_feed_id:
        body["product_feed_id"] = args.product_feed_id
        body.setdefault("mode", "product_feed")
    if args.business_agent_id:
        body["business_agent_id"] = args.business_agent_id
        body.setdefault("mode", "business_agent")
    if args.conversion_event_setting_id:
        ids = parse_csv(args.conversion_event_setting_id)
        body["conversion_event_setting_ids"] = ids
        if body.get("bidding_type") == "conversions" and len(ids) != 1:
            findings.append(("error", "oCPC needs exactly ONE active STANDARD conversion event setting id."))
    if body.get("bidding_type") == "conversions" and not body.get("conversion_event_setting_ids"):
        findings.append(("error", "bidding_type=conversions requires --conversion-event-setting-id (one active standard event setting)."))
    if body.get("bidding_type") != "conversions" and not body.get("conversion_event_setting_ids"):
        findings.append(("warn", "No conversion event setting linked — the campaign will report clicks only. Link one with "
                                 "--conversion-event-setting-id (see event-settings) so conversions/CPA show up and oCPC data accrues."))
    targeting = _targeting_from_args(args)
    if targeting is not None:
        body["targeting"] = targeting
    if args.query_string_template:
        body["landing_page_configuration"] = {"query_string_template": args.query_string_template}
    if args.status == "active":
        findings.append(("warn", "Creating the campaign ACTIVE — it delivers as soon as ad groups/ads are approved. Default is paused."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    resp = run_write("POST", "/campaigns", body, args, "", create=True,
                     note="bidding_type and mode cannot be changed after creation (nor the oCPC event).")
    if resp is not None and not args.json:
        print(f"Campaign created: {resp.get('id')} \"{resp.get('name')}\" status {resp.get('status')} "
              f"bidding {resp.get('bidding_type')}.")


def cmd_campaign_update(args) -> None:
    findings: list = []
    body: dict = {}
    if args.name is not None:
        lint.lint_name(args.name, "Campaign", findings)
        body["name"] = args.name
    if args.description is not None:
        body["description"] = args.description or None
    if args.status:
        body["status"] = args.status
    budget = _budget_from_args(args)
    if budget:
        lint.lint_budget(budget, findings)
        body["budget"] = budget
    start = parse_time_to_unix(args.start, "--start")
    end = parse_time_to_unix(args.end, "--end")
    lint.lint_times(start, end, findings)
    if start:
        body["start_time"] = start
    if end:
        body["end_time"] = end
    if args.clear_end_time:
        body["end_time"] = None
    if args.clear_targeting:
        body["targeting"] = None
    else:
        needs_current = any(getattr(args, k, None) is not None for k in
                            ("countries", "location_ids", "exclude_location_ids", "audience_ids",
                             "exclude_audience_ids", "platforms"))
        current = api._api_call("GET", f"/campaigns/{args.campaign_id}").get("targeting") if needs_current else None
        targeting = _targeting_from_args(args, current)
        if targeting is not None:
            body["targeting"] = targeting
    if args.conversion_event_setting_id is not None:
        body["conversion_event_setting_ids"] = parse_csv(args.conversion_event_setting_id)
        findings.append(("warn", "Links conversion event setting(s) for reporting. On a conversion-optimized campaign the "
                                 "selected event cannot change (API rejects)."))
    if args.query_string_template is not None:
        body["landing_page_configuration"] = {"query_string_template": args.query_string_template} if args.query_string_template else None
    if not body:
        _die("ERROR: nothing to update.")
    if body.get("status") == "archived":
        findings.append(("warn", "status=archived is IRREVERSIBLE. Prefer campaign-archive (has the paused-only brake)."))
    if body.get("status") == "active":
        findings.append(("warn", "Setting ACTIVE starts delivery/spend."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    run_write("POST", f"/campaigns/{args.campaign_id}", body, args,
              f"Campaign {args.campaign_id} updated.", idempotent=True,
              note="budget is replaced as a whole object; targeting merges your flags into the current spec.",
              verify_path=f"/campaigns/{args.campaign_id}")


def cmd_campaign_activate(args) -> None:
    state_change("Campaign", "/campaigns", args.campaign_id, "activate", args)


def cmd_campaign_pause(args) -> None:
    state_change("Campaign", "/campaigns", args.campaign_id, "pause", args)


def cmd_campaign_archive(args) -> None:
    state_change("Campaign", "/campaigns", args.campaign_id, "archive", args)
