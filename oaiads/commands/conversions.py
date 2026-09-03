"""Commands: pixels, pixel-create, capi-key-create, event-settings, event-setting-create, conversion-events."""

from __future__ import annotations

from oaiads import api, lint
from oaiads.formatting import _die, _err, _output_json, print_table, _truncate
from oaiads.commands.common import emit, parse_csv, print_plan, run_write

STANDARD_EVENTS = ["appointment_scheduled", "checkout_started", "contents_viewed", "items_added", "lead_created",
                   "order_created", "page_viewed", "registration_completed", "subscription_created", "trial_started",
                   "app_installed", "app_opened"]


def cmd_pixels(args) -> None:
    rows = api._fetch_all("/conversions/pixels", max_items=args.max_items)
    emit(rows, args, lambda items: print_table(
        [[p.get("id"), p.get("name"), p.get("client_type"), p.get("pixel_id")] for p in items],
        ["Source ID (for event settings)", "Name", "Type", "Pixel ID (for the JS pixel / CAPI)"]))


def cmd_pixel_create(args) -> None:
    findings: list = []
    lint.lint_name(args.name, "Pixel", findings)
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    resp = run_write("POST", "/conversions/pixels", {"name": args.name, "client_type": "web"}, args, "",
                     idempotent=False, note="Requires pixel management enabled for the account (404 otherwise).")
    if resp is not None and not args.json:
        print(f"Pixel created: source id {resp.get('id')}  pixel_id {resp.get('pixel_id')}  ({resp.get('name')})")
        print("Use the source id in event-setting-create --source-id; the pixel_id in the website snippet / CAPI.")


def cmd_capi_key_create(args) -> None:
    findings: list = []
    lint.lint_name(args.name, "CAPI key", findings)
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    if not args.confirm:
        print_plan("POST", "/conversions/api_keys", {"name": args.name}, args,
                   note="Creates a server-side Conversions API key. Shown ONCE; store it in a secret manager.")
        return
    resp = api._api_call("POST", "/conversions/api_keys", json_body={"name": args.name}, idempotent=False)
    if args.json:
        _output_json(resp)
    else:
        print(f"Conversions API key '{resp.get('name')}' (shown ONCE):\n{resp.get('api_key')}")
    _err("⚠ Server-side only. Never put it in browser code, NEXT_PUBLIC_/VITE_ env vars, logs or git.")


def cmd_event_settings(args) -> None:
    rows = api._fetch_all("/conversions/event_settings", max_items=args.max_items)
    if not args.all:
        rows = [r for r in rows if not r.get("archived")]
    emit(rows, args, lambda items: print_table(
        [[e.get("id"), _truncate(e.get("name"), 30), e.get("event_type"), e.get("custom_event_name") or "",
          e.get("attribution_window_days"), ",".join(s.get("id", "") for s in e.get("sources") or []),
          len(e.get("campaigns") or []), "yes" if e.get("archived") else "no"] for e in items],
        ["ID", "Name", "Event", "Custom name", "Window d", "Sources", "Campaigns", "Archived"]))


def cmd_event_setting_create(args) -> None:
    findings: list = []
    body = {"name": args.name, "event_type": args.event_type, "attribution_window_days": args.attribution_window,
            "source_ids": parse_csv(args.source_id)}
    if args.event_type == "custom":
        if not args.custom_event_name:
            findings.append(("error", "--custom-event-name is required for event_type=custom."))
        body["custom_event_name"] = args.custom_event_name
        findings.append(("warn", "custom events can be measured but NOT used as oCPC optimization goals."))
    elif args.event_type not in STANDARD_EVENTS:
        findings.append(("warn", f"'{args.event_type}' is not in the documented standard event list {STANDARD_EVENTS}."))
    if len(body["source_ids"]) != 1:
        findings.append(("error", "exactly one --source-id (conversion source id from pixels) is required."))
    if args.attribution_window != 30:
        findings.append(("warn", "docs say: use attribution_window_days=30."))
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    resp = run_write("POST", "/conversions/event_settings", body, args, "", idempotent=False,
                     note="Last step people forget: LINK the event to campaigns (campaign-update --conversion-event-setting-id), "
                          "otherwise it collects data the campaigns never see.")
    if resp is not None and not args.json:
        print(f"Event setting created: {resp.get('id')} \"{resp.get('name')}\" ({resp.get('event_type')}).")
        print(f"Next: campaign-update --campaign-id <id> --conversion-event-setting-id {resp.get('id')} --confirm  (reporting link; "
              "for oCPC pass it to campaign-create --bidding-type conversions).")


def cmd_conversion_events(args) -> None:
    data = api._api_call("GET", "/conversions/events", [("pid", args.pid), ("limit", min(max(args.limit, 1), 50))])
    rows = data.get("data", [])

    def human(items):
        if not items:
            print("No pixel events in the last ~15 minutes for this pixel id. (Debug stream, not attribution.)")
            return
        width = 400 if getattr(args, "wide", False) else 60
        print_table([[e.get("event_type"), e.get("custom_event_name") or "", e.get("action_source"), e.get("api_channel"),
                      e.get("event_timestamp_ms"), _truncate(e.get("event_data_json"), width)] for e in items],
                    ["Event", "Custom", "Source", "Channel", "Event ts (ms)", "Data"])
        if not getattr(args, "wide", False):
            print("(Data truncated — --wide or --json for the full event_data_json, e.g. contents[0].id with the landing query)")
        print(f"\n{len(items)} recent event(s) (max 50, last 15 min). Requires the event stream enabled on the account.")

    emit(rows, args, human)


# ---------------------------------------------------------------------------
# conversion-check — measurement health: pixel → event setting → campaign link → recent events
# ---------------------------------------------------------------------------

def cmd_conversion_check(args) -> None:
    from oaiads.commands.common import brief_error
    pixels = api._api_call("GET", "/conversions/pixels", [("limit", 500)], soft=True)
    settings = api._api_call("GET", "/conversions/event_settings", [("limit", 500)], soft=True)
    campaigns = [c for c in api._fetch_all("/campaigns") if c.get("status") != "archived"]
    findings: list = []
    result: dict = {"pixels": None, "event_settings": None, "campaigns": [], "recent_events": {}, "errors": {}}

    if brief_error(pixels):
        result["errors"]["pixels"] = brief_error(pixels)
        findings.append(("error", f"pixels unavailable ({brief_error(pixels)}) — pixel management may not be enabled for this account; create the pixel in Ads Manager → Tools → Conversions."))
        pixel_rows = []
    else:
        pixel_rows = pixels.get("data", [])
        result["pixels"] = pixel_rows
        if not pixel_rows:
            findings.append(("error", "no conversion source (pixel) — nothing can measure conversions. pixel-create or Ads Manager → Tools → Conversions."))

    if brief_error(settings):
        result["errors"]["event_settings"] = brief_error(settings)
        setting_rows = []
    else:
        setting_rows = [e for e in settings.get("data", []) if not e.get("archived")]
        result["event_settings"] = setting_rows
        if not setting_rows:
            findings.append(("error", "no conversion event settings — define at least one (event-setting-create), e.g. order_created / lead_created."))
        elif not [e for e in setting_rows if e.get("event_type") != "custom"]:
            findings.append(("warn", "only custom event settings exist — custom events cannot be oCPC optimization goals."))

    setting_ids = {e.get("id") for e in setting_rows}
    for c in campaigns:
        linked = [i for i in (c.get("conversion_event_setting_ids") or [])]
        unknown = [i for i in linked if setting_ids and i not in setting_ids]
        result["campaigns"].append({"id": c.get("id"), "name": c.get("name"), "status": c.get("status"),
                                    "bidding_type": c.get("bidding_type"), "conversion_event_setting_ids": linked})
        if not linked and setting_rows:
            findings.append(("warn", f"campaign {c.get('id')} \"{c.get('name')}\" ({c.get('status')}) has NO conversion event linked — "
                                     f"it reports clicks only. campaign-update --campaign-id {c.get('id')} --conversion-event-setting-id <ces_id>"))
        if unknown:
            findings.append(("warn", f"campaign {c.get('id')} links unknown/archived event setting(s) {unknown}."))

    if args.events:
        for p in pixel_rows:
            pid = p.get("pixel_id")
            ev = api._api_call("GET", "/conversions/events", [("pid", pid), ("limit", 50)], soft=True)
            if brief_error(ev):
                result["recent_events"][pid] = {"error": brief_error(ev)}
            else:
                rows = ev.get("data", [])
                result["recent_events"][pid] = {"count": len(rows), "types": sorted({r.get("event_type") for r in rows})}
                if not rows:
                    findings.append(("warn", f"pixel {pid} ({p.get('name')}) received no events in the last ~15 min — fire a test event on the site and re-run."))

    result["findings"] = [{"level": lvl, "message": m} for lvl, m in findings]

    def human(r):
        print("Conversion measurement check")
        if r["pixels"] is not None:
            print(f"  pixels: {len(r['pixels'])}" + "".join(f"\n    {p.get('id')}  pixel_id {p.get('pixel_id')}  {p.get('name')}" for p in r["pixels"]))
        if r["event_settings"] is not None:
            print(f"  event settings (active): {len(r['event_settings'])}" + "".join(
                f"\n    {e.get('id')}  {e.get('event_type')}{'/' + e.get('custom_event_name') if e.get('custom_event_name') else ''}  \"{e.get('name')}\"  "
                f"sources {[s.get('id') for s in e.get('sources') or []]}  campaigns {len(e.get('campaigns') or [])}" for e in r["event_settings"]))
        print(f"  campaigns (non-archived): {len(r['campaigns'])}, linked to a conversion event: "
              f"{sum(1 for c in r['campaigns'] if c['conversion_event_setting_ids'])}")
        for pid, info in r["recent_events"].items():
            print(f"  recent pixel events {pid}: {info}")
        if not findings:
            print("✅ Pixel → event setting → campaign link all present.")
        else:
            lint.report(findings, strict=False)
        print("Order in Ads Manager: data source (pixel) → conversion event → site implementation (consent + CSP!) → LINK event to campaign.")

    emit(result, args, human)
