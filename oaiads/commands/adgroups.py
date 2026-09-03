"""Commands: adgroups, adgroup-detail, adgroup-create/update, adgroup-activate/pause/archive."""

from __future__ import annotations

from decimal import Decimal

from oaiads import api, lint
from oaiads.formatting import _die, _err, amount_to_micros, fmt_money, fmt_ts, print_table, _truncate
from oaiads.commands.common import (
    drop_archived, emit, issues_str, money_flag, parse_csv, parse_json_arg, qarr, run_write, state_change, trunc,
)

BILLING_EVENTS = ["impression", "click"]
STRATEGIES = ["fixed_bid", "maximize_clicks", "maximize_conversions"]
PRODUCT_FILTER_OPS = ["in", "not_in", "gt", "gte", "lt", "lte", "contains", "not_contains", "starts_with"]
PRODUCT_FILTER_FIELDS = ["title", "body", "item_id", "offer_id", "price", "target_url", "image_url",
                         "product_category", "brand", "seller_name", "external_seller_id", "star_rating",
                         "condition", "age_group"]


def _list_params(args) -> list:
    params = []
    if getattr(args, "campaign_id", None):
        params.append(("campaign_id", args.campaign_id))
    if getattr(args, "name", None):
        if len(args.name) < 3:
            _die("ERROR: --name filter needs at least 3 characters.")
        params.append(("name", args.name))
    if getattr(args, "include_issues", False):
        params.append((qarr("include"), "serving_issues"))
    if getattr(args, "order", None):
        params.append(("order", args.order))
    return params


def cmd_adgroups(args) -> None:
    rows = drop_archived(api._fetch_all("/ad_groups", _list_params(args), max_items=args.max_items),
                         args.status, args.all)
    cur = api.account_currency()

    def human(items):
        print_table([[g.get("id"), trunc(g.get("name"), args), g.get("status"),
                      (g.get("bidding_config") or {}).get("billing_event_type"),
                      (g.get("bidding_config") or {}).get("strategy") or "",
                      fmt_money((g.get("bidding_config") or {}).get("max_bid_micros"), cur),
                      len(g.get("context_hints") or []), _truncate(issues_str(g), 40)] for g in items],
                    ["ID", "Name", "Status", "Billing", "Strategy", "Max bid/event", "Hints", "Issues"])
        print(f"\n{len(items)} ad group(s)" + ("" if args.all or args.status else " (archived hidden — use --all)"))

    emit(rows, args, human)


def cmd_adgroup_detail(args) -> None:
    g = api._api_call("GET", f"/ad_groups/{args.ad_group_id}", [(qarr("include"), "serving_issues")])
    if args.with_children:
        g["_ads"] = api._fetch_all("/ads", [("ad_group_id", args.ad_group_id), (qarr("include"), "serving_issues")])
    cur = api.account_currency()

    def human(g):
        bc = g.get("bidding_config") or {}
        print(f"Ad group {g.get('id')} — {g.get('name')}   status {g.get('status')}")
        print(f"  bidding: {bc.get('billing_event_type')}  strategy {bc.get('strategy')}  max bid {fmt_money(bc.get('max_bid_micros'), cur)} per event"
              + (f" (= {fmt_money((bc.get('max_bid_micros') or 0) * 1000, cur)} CPM)" if bc.get("billing_event_type") == "impression" and bc.get("max_bid_micros") else ""))
        for m in bc.get("custom_audience_bid_multipliers") or []:
            print(f"    audience {m.get('custom_audience_id')} × {Decimal(m.get('bid_multiplier_micros', 0)) / 1_000_000}")
        hints = g.get("context_hints") or []
        print(f"  context hints ({len(hints)}): {', '.join(hints[:15])}{'…' if len(hints) > 15 else ''}")
        if g.get("description"):
            print(f"  description: {g['description']}")
        if g.get("product_set"):
            print(f"  product set: {g['product_set']}")
        if g.get("landing_page_configuration"):
            print(f"  landing page config: {g['landing_page_configuration']}")
        print(f"  created {fmt_ts(g.get('created_at'))}  updated {fmt_ts(g.get('updated_at'))}")
        print(f"  serving issues: {issues_str(g) or 'none'}")
        if "_ads" in g:
            print(f"\n  Ads ({len(g['_ads'])}):")
            for a in g["_ads"]:
                cr = a.get("creative") or {}
                print(f"    {a.get('id')}  {_truncate(a.get('name'), 32)}  {a.get('status')}  review {a.get('review_status')}  "
                      f"\"{_truncate(cr.get('title'), 30)}\"  {issues_str(a)}")

    emit(g, args, human)


def _hints_from_args(args) -> list[str] | None:
    hints: list[str] = []
    given = False
    for h in getattr(args, "hints", None) or []:
        hints += parse_csv(h)
        given = True
    if getattr(args, "hints_file", None):
        with open(args.hints_file, encoding="utf-8") as f:
            hints += [line.strip() for line in f if line.strip() and not line.startswith("#")]
        given = True
    return hints if given else None


def _product_set_from_args(args) -> dict | None:
    if getattr(args, "product_set_json", None):
        return parse_json_arg(args.product_set_json, "--product-set-json")
    if not getattr(args, "product_feed_id", None) and not getattr(args, "product_filter", None):
        return None
    if not getattr(args, "product_feed_id", None):
        _die("ERROR: --product-filter needs --product-feed-id (must match the campaign's feed).")
    ps: dict = {"product_feed_id": args.product_feed_id}
    filters = []
    seen = set()
    for spec in getattr(args, "product_filter", None) or []:
        parts = spec.split(":", 2)
        if len(parts) != 3:
            _die(f"ERROR: --product-filter format is field:operator:value1|value2 (got '{spec}').")
        field, op, values = parts
        if field not in PRODUCT_FILTER_FIELDS:
            _err(f"⚠ product filter field '{field}' is not in the documented list {PRODUCT_FILTER_FIELDS}.")
        if op not in PRODUCT_FILTER_OPS:
            _die(f"ERROR: operator '{op}' not in {PRODUCT_FILTER_OPS}.")
        if op in ("gt", "gte", "lt", "lte") and field not in ("price", "star_rating"):
            _die("ERROR: gt/gte/lt/lte are only valid for price or star_rating.")
        if field in seen:
            _die(f"ERROR: field '{field}' repeated — one filter per field in a product set.")
        seen.add(field)
        filters.append({"field": field, "operator": op, "values": [v for v in values.split("|") if v]})
    if filters:
        ps["filters"] = filters
    return ps


def _bidding_from_args(args, current: dict | None, campaign_bidding_type: str | None) -> dict | None:
    """BiddingConfigParams from flags (merged into `current`, which is sent whole)."""
    flags = ("billing_event", "max_bid", "max_cpm", "strategy", "audience_multiplier")
    if not any(getattr(args, f, None) is not None for f in flags):
        return None
    bc: dict = dict(current or {})
    if args.billing_event:
        bc["billing_event_type"] = args.billing_event
    elif not bc.get("billing_event_type"):
        # Infer from the campaign: impressions → impression; clicks/conversions → click.
        if campaign_bidding_type == "impressions":
            bc["billing_event_type"] = "impression"
        elif campaign_bidding_type in ("clicks", "conversions"):
            bc["billing_event_type"] = "click"
        else:
            _die("ERROR: --billing-event is required (impression|click).")
    if args.max_bid is not None and args.max_cpm is not None:
        _die("ERROR: give --max-bid (per event) OR --max-cpm (per 1 000 impressions), not both.")
    if args.max_cpm is not None:
        if bc["billing_event_type"] != "impression":
            _die("ERROR: --max-cpm only makes sense with billing_event_type=impression.")
        bc["max_bid_micros"] = int(amount_to_micros(args.max_cpm) / 1000)
    if args.max_bid is not None:
        bc["max_bid_micros"] = money_flag(args.max_bid, "--max-bid", 1)
    if args.strategy:
        bc["strategy"] = args.strategy
    if args.audience_multiplier is not None:
        mults = []
        for spec in args.audience_multiplier:
            if "=" not in spec:
                _die("ERROR: --audience-multiplier format is caud_id=2.0")
            aid, mult = spec.split("=", 1)
            micros = int(Decimal(mult) * 1_000_000)
            if not (lint.BID_MULTIPLIER_MIN <= micros <= lint.BID_MULTIPLIER_MAX):
                _die("ERROR: bid multiplier must be 0.1–10.0 (×).")
            mults.append({"custom_audience_id": aid.strip(), "bid_multiplier_micros": micros})
        bc["custom_audience_bid_multipliers"] = mults
    if not bc.get("max_bid_micros") and bc.get("strategy", "fixed_bid") == "fixed_bid":
        _die("ERROR: --max-bid (or --max-cpm) is required.")
    return bc


def cmd_adgroup_create(args) -> None:
    findings: list = []
    lint.lint_name(args.name, "Ad group", findings)
    campaign = api._api_call("GET", f"/campaigns/{args.campaign_id}")
    bidding = _bidding_from_args(args, None, campaign.get("bidding_type"))
    if bidding is None:
        _die("ERROR: --max-bid (per event) or --max-cpm is required.")
    if campaign.get("bidding_type") == "impressions" and bidding["billing_event_type"] != "impression":
        findings.append(("error", "impression campaign needs billing_event_type=impression."))
    if campaign.get("bidding_type") in ("clicks", "conversions") and bidding["billing_event_type"] != "click":
        findings.append(("error", f"{campaign.get('bidding_type')} campaign needs billing_event_type=click."))
    if campaign.get("bidding_type") == "conversions":
        findings.append(("warn", "oCPC campaign: max_bid is the CPA bid (billing stays per click)."))
    hints = _hints_from_args(args)
    lint.lint_context_hints(hints if hints is not None else [], findings)
    body: dict = {"campaign_id": args.campaign_id, "name": args.name, "status": args.status, "bidding_config": bidding}
    if args.description:
        body["description"] = args.description
    if hints:
        body["context_hints"] = hints
    ps = _product_set_from_args(args)
    if ps:
        if campaign.get("mode") != "product_feed":
            findings.append(("error", "product_set only applies to product_feed campaigns."))
        if campaign.get("product_feed_id") and ps.get("product_feed_id") != campaign.get("product_feed_id"):
            findings.append(("error", f"product_set.product_feed_id must match the campaign feed {campaign.get('product_feed_id')}."))
        body["product_set"] = ps
    if args.query_string_template:
        body["landing_page_configuration"] = {"query_string_template": args.query_string_template}
    if args.status == "active":
        findings.append(("warn", "Creating the ad group ACTIVE (default paused)."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    def note():
        cur = api.cached_currency()  # cache only: a dry-run must not call the API
        txt = f"max_bid_micros {bidding.get('max_bid_micros')} = {fmt_money(bidding.get('max_bid_micros'), cur)} per {bidding['billing_event_type']}"
        if bidding["billing_event_type"] == "impression" and bidding.get("max_bid_micros"):
            txt += f" (CPM {fmt_money(bidding['max_bid_micros'] * 1000, cur)})"
        return txt

    resp = run_write("POST", "/ad_groups", body, args, "", create=True, note=note)
    if resp is not None and not args.json:
        print(f"Ad group created: {resp.get('id')} \"{resp.get('name')}\" status {resp.get('status')}.")


def cmd_adgroup_update(args) -> None:
    findings: list = []
    body: dict = {}
    current = api._api_call("GET", f"/ad_groups/{args.ad_group_id}")
    if args.name is not None:
        lint.lint_name(args.name, "Ad group", findings)
        body["name"] = args.name
    if args.description is not None:
        body["description"] = args.description or None
    if args.status:
        body["status"] = args.status
    hints = _hints_from_args(args)
    if hints is not None:
        lint.lint_context_hints(hints, findings)
        body["context_hints"] = hints
    bidding = _bidding_from_args(args, current.get("bidding_config"), None)
    if bidding is not None:
        body["bidding_config"] = bidding
    ps = _product_set_from_args(args)
    if ps is not None:
        body["product_set"] = ps
    if args.query_string_template is not None:
        body["landing_page_configuration"] = {"query_string_template": args.query_string_template} if args.query_string_template else None
    if not body:
        _die("ERROR: nothing to update.")
    if body.get("status") == "archived":
        findings.append(("warn", "status=archived is IRREVERSIBLE. Prefer adgroup-archive."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    run_write("POST", f"/ad_groups/{args.ad_group_id}", body, args, f"Ad group {args.ad_group_id} updated.",
              idempotent=True, note="bidding_config is sent as the full merged object; context_hints replace the list.",
              verify_path=f"/ad_groups/{args.ad_group_id}")


def cmd_adgroup_activate(args) -> None:
    state_change("Ad group", "/ad_groups", args.ad_group_id, "activate", args)


def cmd_adgroup_pause(args) -> None:
    state_change("Ad group", "/ad_groups", args.ad_group_id, "pause", args)


def cmd_adgroup_archive(args) -> None:
    state_change("Ad group", "/ad_groups", args.ad_group_id, "archive", args)
