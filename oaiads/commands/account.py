"""Commands: account, accounts, brand-update, negative-keywords*, spend-limit*, account-pause/activate,
api-limits, api-key-create, landing-check."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

import requests

from oaiads import api, lint
from oaiads.formatting import _die, _err, _output_json, fmt_money, print_table
from oaiads.commands.common import (
    emit, money_flag, parse_csv, parse_iso_date, print_plan, run_write,
)


# ---------------------------------------------------------------------------
# account / accounts
# ---------------------------------------------------------------------------

def cmd_account(args) -> None:
    acct = api._api_call("GET", "/ad_account")
    windows = api._api_call("GET", "/ad_account/spend_limit_windows", soft=True)
    if isinstance(windows, dict) and "_error" not in windows:
        acct["_spend_limit_windows"] = windows.get("data", windows)
    elif isinstance(windows, dict):
        acct["_spend_limit_windows_error"] = windows["_error"]
    api.account_meta(refresh=True)

    def human(a):
        review = a.get("review") or {}
        integ = (a.get("account_integrity_review") or {}).get("review") or {}
        print(f"Account:   {a.get('name')} ({a.get('id')})")
        print(f"URL:       {a.get('url')}   favicon: {'yes' if a.get('preview_url') else 'MISSING'}")
        print(f"Status:    {a.get('status')}   currency: {a.get('currency_code')}   timezone: {a.get('timezone')}")
        print(f"Brand review:     {review.get('status')}" + (f" — {review.get('reason')}" if review.get("reason") else ""))
        if integ:
            print(f"Integrity review: {integ.get('status')}" + (f" — {integ.get('reason')}" if integ.get("reason") else ""))
        if "negative_keywords" in a:
            nk = a.get("negative_keywords") or []
            print(f"Negative keywords: {len(nk)}" + (f" — {', '.join(nk[:8])}{'…' if len(nk) > 8 else ''}" if nk else ""))
        else:
            print("Negative keywords: not available on this account (field absent; POST → 404)")
        wins = a.get("_spend_limit_windows")
        if a.get("_spend_limit_windows_error"):
            e = a["_spend_limit_windows_error"]
            print(f"Spend limit windows: endpoint unavailable on this account (HTTP {e.get('status')}: {e.get('message')}) — "
                  "no account-level cap via API; use daily budgets + end dates on campaigns.")
        if isinstance(wins, list):
            if not wins:
                print("Spend limit windows: NONE — consider `spend-limit-create` before automating writes.")
            else:
                print("Spend limit windows:")
                for w in wins:
                    print(f"  {w.get('window_id')}  {w.get('start_date')} → {w.get('end_date')}  "
                          f"{fmt_money(w.get('amount_micros'), a.get('currency_code'))}  spent "
                          f"{fmt_money(w.get('spent_micros'), a.get('currency_code'))}  [{w.get('status')}]"
                          + (f"  {w.get('name')}" if w.get("name") else ""))
        if review.get("status") != "approved":
            _err("⚠ Account brand review is not approved — the account cannot serve ads until it is.")

    emit(acct, args, human)


def cmd_accounts(args) -> None:
    rows = api._fetch_all("/ad_accounts", max_items=args.max_items)

    def human(items):
        print_table([[a.get("id"), a.get("name"), a.get("status"), a.get("currency_code"), a.get("timezone"),
                      (a.get("review") or {}).get("status")] for a in items],
                    ["ID", "Name", "Status", "Currency", "Timezone", "Review"])
        print(f"\nLocal .env accounts: {', '.join(api.configured_accounts()) or '(none)'} — active: {api.ACTIVE_ACCOUNT}")

    emit(rows, args, human)


# ---------------------------------------------------------------------------
# brand
# ---------------------------------------------------------------------------

def cmd_brand_update(args) -> None:
    body: dict = {}
    if args.name:
        body["name"] = args.name
    if args.url:
        findings: list = []
        lint.lint_url(args.url, findings, what="url")
        if lint.report(findings):
            _die("Lint errors — fix them first.")
        body["url"] = args.url
    if args.favicon_file_id:
        body["favicon_file_id"] = args.favicon_file_id
    if not body:
        _die("ERROR: give at least one of --name, --url, --favicon-file-id.")
    run_write("POST", "/ad_account/brand", body, args,
              "Brand metadata updated — a new brand review started. Poll `account` until review.status=approved.",
              idempotent=True,
              note="Starts a NEW brand review; the account cannot serve until it is approved again.")


# ---------------------------------------------------------------------------
# negative keywords (account level — replace semantics on the API)
# ---------------------------------------------------------------------------

NEGATIVE_KEYWORDS_UNAVAILABLE = ("Account-level negative keywords are not available on this account: GET /ad_account has no "
                                 "`negative_keywords` field and POST /ad_account/negative_keywords answers 404 'Invalid URL' "
                                 "(self-serve, verified 2026-09-02). Steer context with ad-group hints instead.")


def _current_negative_keywords() -> list[str] | None:
    """None when the account resource does not expose the field at all (feature not deployed)."""
    acct = api._api_call("GET", "/ad_account")
    if "negative_keywords" not in acct:
        return None
    return list(acct.get("negative_keywords") or [])


def _write_negative_keywords(keywords: list[str], args, msg: str) -> None:
    findings: list = []
    lint.lint_negative_keywords(keywords, findings)
    if lint.report(findings):
        _die("Lint errors — fix them first.")
    if not args.confirm:
        print_plan("POST", "/ad_account/negative_keywords", {"negative_keywords": keywords}, args,
                   note="The API REPLACES the whole list with what is sent.")
        return
    resp = api._api_call("POST", "/ad_account/negative_keywords", json_body={"negative_keywords": keywords},
                         idempotent=True, soft=True)
    if isinstance(resp, dict) and "_error" in resp:
        e = resp["_error"]
        if e.get("status") == 404:
            _die(f"ERROR: HTTP 404 {e.get('message')}\n  {NEGATIVE_KEYWORDS_UNAVAILABLE}")
        _die(f"ERROR: HTTP {e.get('status')} {e.get('code') or ''}: {e.get('message')}")
    if args.json:
        _output_json(resp)
    else:
        print(msg)


def cmd_negative_keywords(args) -> None:
    kws = _current_negative_keywords()
    if kws is None:
        if args.json:
            _output_json({"available": False, "negative_keywords": None, "note": NEGATIVE_KEYWORDS_UNAVAILABLE})
        else:
            print(NEGATIVE_KEYWORDS_UNAVAILABLE)
        return
    emit(kws, args, lambda k: print("\n".join(k) if k else "(no negative keywords)"))


def cmd_negative_keywords_set(args) -> None:
    kws = parse_csv(args.keywords)
    if args.keywords_file:
        with open(args.keywords_file, encoding="utf-8") as f:
            kws += [line.strip() for line in f if line.strip() and not line.startswith("#")]
    _write_negative_keywords(kws, args, f"Negative keywords replaced ({len(kws)}).")


def cmd_negative_keywords_add(args) -> None:
    current = _current_negative_keywords()
    if current is None:
        _die(f"ERROR: {NEGATIVE_KEYWORDS_UNAVAILABLE}")
    new = [k for k in parse_csv(args.keywords) if k not in current]
    if not new:
        print("Nothing to add — all keywords already present.")
        return
    _write_negative_keywords(current + new, args, f"Added {len(new)} negative keyword(s); total {len(current) + len(new)}.")


def cmd_negative_keywords_remove(args) -> None:
    current = _current_negative_keywords()
    if current is None:
        _die(f"ERROR: {NEGATIVE_KEYWORDS_UNAVAILABLE}")
    drop = set(parse_csv(args.keywords))
    remaining = [k for k in current if k not in drop]
    if len(remaining) == len(current):
        print("Nothing to remove — none of the keywords are present.")
        return
    _write_negative_keywords(remaining, args, f"Removed {len(current) - len(remaining)}; total {len(remaining)}.")


# ---------------------------------------------------------------------------
# spend limit windows — the account-level safety fuse
# ---------------------------------------------------------------------------

SPEND_LIMIT_FALLBACK = ("Spend limit windows are not available on this account (the endpoint answers 404 'Invalid URL' — "
                        "it is in the OpenAPI spec but not deployed for self-serve accounts as of 2026-09-02). Fallback fuse: "
                        "campaign daily budgets (spend can reach 2× on a day) + campaign end_time, and `pulse` to watch spend.")


def cmd_spend_limits(args) -> None:
    data = api._api_call("GET", "/ad_account/spend_limit_windows", soft=True)
    if isinstance(data, dict) and "_error" in data:
        e = data["_error"]
        if e.get("status") == 404:
            if args.json:
                _output_json({"available": False, "error": e, "fallback": SPEND_LIMIT_FALLBACK})
            else:
                _err(f"⚠ HTTP 404: {e.get('message')}")
                print(SPEND_LIMIT_FALLBACK)
            return
        _die(f"ERROR: HTTP {e.get('status')} {e.get('code') or ''}: {e.get('message')}")
    rows = data.get("data", data) if isinstance(data, dict) else data
    cur = api.account_currency()

    def human(items):
        if not items:
            print("No spend limit windows. Create one with spend-limit-create (start inclusive, end exclusive).")
            return
        print_table([[w.get("window_id"), w.get("start_date"), w.get("end_date"), fmt_money(w.get("amount_micros"), cur),
                      fmt_money(w.get("spent_micros"), cur), w.get("status"), w.get("name") or "",
                      "yes" if w.get("can_edit") else "no", "yes" if w.get("can_delete") else "no"]
                     for w in items],
                    ["Window", "Start", "End (excl.)", "Limit", "Spent", "Status", "Name", "Editable", "Deletable"])

    emit(rows, args, human)


def _window_body(args, create: bool) -> dict:
    body: dict = {}
    if args.start:
        body["start_date"] = parse_iso_date(args.start, "--start").isoformat()
    if args.end:
        body["end_date"] = parse_iso_date(args.end, "--end").isoformat()
    if args.amount is not None:
        body["amount_micros"] = money_flag(args.amount, "--amount", minimum_micros=0)
    if args.name is not None:
        body["name"] = args.name
    if getattr(args, "io_id", None) is not None:
        body["io_id"] = args.io_id
    if create:
        for k in ("start_date", "end_date", "amount_micros"):
            if k not in body:
                _die(f"ERROR: --start, --end and --amount are required (missing {k}).")
    if "start_date" in body and "end_date" in body and body["end_date"] <= body["start_date"]:
        _die("ERROR: --end must be after --start (end date is exclusive).")
    if "end_date" in body and body["end_date"] <= date.today().isoformat():
        _err("⚠ --end is not in the future — the window would already be over.")
    return body


def cmd_spend_limit_create(args) -> None:
    body = _window_body(args, create=True)
    run_write("POST", "/ad_account/spend_limit_windows", body, args,
              lambda: f"Spend limit window created: {body['start_date']} → {body['end_date']} "
                      f"{fmt_money(body['amount_micros'], api.account_currency())}.", idempotent=True)


def cmd_spend_limit_update(args) -> None:
    body = _window_body(args, create=False)
    if not body:
        _die("ERROR: nothing to update.")
    run_write("POST", f"/ad_account/spend_limit_windows/{args.window_id}", body, args,
              f"Spend limit window {args.window_id} updated.", idempotent=True)


def cmd_spend_limit_delete(args) -> None:
    run_write("POST", f"/ad_account/spend_limit_windows/{args.window_id}/delete", None, args,
              f"Spend limit window {args.window_id} deleted — the account has one fewer spend cap.",
              idempotent=True, note="Removes a spend cap. Make sure another guard exists.")


# ---------------------------------------------------------------------------
# account state
# ---------------------------------------------------------------------------

def cmd_account_pause(args) -> None:
    run_write("POST", "/ad_account/pause", None, args, "Ad account paused — nothing delivers.", idempotent=True)


def cmd_account_activate(args) -> None:
    run_write("POST", "/ad_account/activate", None, args, "Ad account activated.", idempotent=True,
              note="Re-enables delivery for every active campaign in the account.")


# ---------------------------------------------------------------------------
# api-limits / api-key-create
# ---------------------------------------------------------------------------

def cmd_api_limits(args) -> None:
    snap = api.budget_snapshot()
    snap["account"] = api.ACTIVE_ACCOUNT
    snap["documented"] = {
        "per_endpoint_per_minute": api.RATE_LIMIT_PER_ENDPOINT,
        "overall_per_minute": api.RATE_LIMIT_OVERALL,
        "scope": "per ad account AND per IP address",
        "bulk_job_creates": f"{api.BULK_CREATE_LIMIT} per {api.BULK_CREATE_WINDOW_SECS}s per ad account",
    }

    def human(s):
        print(f"Account '{s['account']}' — local sliding-window usage (last {s['window_secs']} s):")
        print(f"  overall: {s['overall_calls']} / {s['overall_limit']} (pacing starts at {int(s['soft_factor'] * 100)} %)")
        for fam, n in sorted(s["per_endpoint_calls"].items(), key=lambda x: -x[1]):
            print(f"  {n:4d} / {s['per_endpoint_limit']}  {fam}")
        print("Documented: 600 req/min per endpoint, 1 200 req/min overall (account AND IP); "
              "bulk job creates 10 / 10 s. Usage is not exposed by the API — this is the CLI's own count.")

    emit(snap, args, human)


def cmd_api_key_create(args) -> None:
    body = {"key_name": args.name} if args.name else {}
    if not args.confirm:
        print_plan("POST", "/api_keys", body, args,
                   note="Creates a NEW API key scoped to this ad account. The key is shown once.")
        return
    resp = api._api_call("POST", "/api_keys", json_body=body, idempotent=False)
    if args.json:
        _output_json(resp)
    else:
        print(f"New API key created (organization {resp.get('api_organization_id')}, "
              f"service account {resp.get('service_account_id')}).")
        print(f"API key (shown ONCE — store it in .env / a secret manager now):\n{resp.get('api_key')}")
    _err("⚠ Never commit this key. Revoke unused keys in Ads Manager → Settings.")


# ---------------------------------------------------------------------------
# landing-check — the cheapest fix for the most common review rejection
# ---------------------------------------------------------------------------

# OAI-AdsBot must be allowed (it reviews the landing page and feeds relevance);
# OAI-SearchBot is recommended; '*' rules apply to both when no specific group exists.
_CRAWLER_UAS = ("OAI-AdsBot", "OAI-SearchBot", "*")
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
# Best-effort imitation of the reviewer's crawler UA string (the exact string is not published).
_BOT_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-AdsBot/1.0; +https://openai.com/bots"
OPPREF_PROBE = "oaiads-test123"


def oppref_survives(final_url: str, probe: str = OPPREF_PROBE) -> bool:
    """True when the click-attribution param is still in the URL after redirects/routing."""
    q = urlparse(final_url).query
    return any(p.split("=", 1) == ["oppref", probe] for p in q.split("&") if p)


def cmd_landing_check(args) -> None:
    """Local reachability + WAF + robots + favicon + oppref check for a landing page."""
    url = args.url
    findings: list = []
    lint.lint_url(url, findings)
    result: dict = {"url": url, "checks": {}}
    parsed = urlparse(url)
    checks = result["checks"]

    def get(u, ua, **kw):
        return requests.get(u, headers={"User-Agent": ua}, timeout=20, allow_redirects=True, **kw)

    # 1) browser view + favicon
    html = ""
    try:
        r = get(url, _BROWSER_UA)
        checks["status"] = r.status_code
        checks["final_url"] = r.url
        checks["content_type"] = r.headers.get("Content-Type", "")
        if r.status_code >= 400:
            findings.append(("error", f"landing page returned HTTP {r.status_code} (review reason crawler_{r.status_code})."))
        if "text/html" not in checks["content_type"]:
            findings.append(("warn", f"content-type is {checks['content_type'] or 'unknown'} — reviewers expect an HTML page (unsupported_content_type)."))
        html = r.text[:400_000].lower()
        has_favicon = bool(re.search(r'<link[^>]+rel=["\'](?:shortcut )?icon', html))
        checks["favicon_link"] = has_favicon
        if not has_favicon:
            fav = get(f"{parsed.scheme}://{parsed.netloc}/favicon.ico", _BROWSER_UA)
            has_favicon = fav.status_code == 200
            checks["favicon_ico"] = fav.status_code
        if not has_favicon:
            findings.append(("warn", "no favicon found — `missing_favicon` is a documented review reason (account favicon: image-upload --purpose account_favicon + brand-update)."))
        if re.search(r"captcha|cf-challenge|just a moment", html):
            findings.append(("warn", "page looks like a bot challenge/captcha (crawler_captcha)."))
        if re.search(r'<meta[^>]+name=["\']robots["\'][^>]+noindex', html):
            findings.append(("warn", "meta robots noindex present — the reviewer's crawler may skip the page."))
    except requests.RequestException as e:
        findings.append(("error", f"landing page not reachable: {str(e)[:160]} (crawl_failed)."))

    # 2) bot view — WAF/CDN/anti-bot layers (Cloudflare, Akamai, rate limiting) often 403/429 crawlers
    try:
        rb = get(url, _BOT_UA)
        checks["bot_status"] = rb.status_code
        if rb.status_code in (401, 403, 429, 503) and checks.get("status", 0) < 400:
            findings.append(("error", f"a crawler-like User-Agent gets HTTP {rb.status_code} while a browser gets {checks['status']} — "
                                      "WAF/CDN/anti-bot blocks OAI-AdsBot; allow it (crawler_bot_blocked)."))
        elif re.search(r"captcha|cf-challenge|just a moment|access denied", rb.text[:200_000].lower()) and "captcha" not in html:
            findings.append(("error", "the crawler-like User-Agent hits a challenge page — allow OAI-AdsBot in the WAF/CDN."))
    except requests.RequestException as e:
        checks["bot_status"] = None
        findings.append(("warn", f"bot-UA request failed: {str(e)[:120]}"))

    # 3) oppref — OpenAI appends ?oppref=<click ref>; redirects/routing must keep it for attribution
    try:
        sep = "&" if parsed.query else "?"
        ro = get(f"{url}{sep}oppref={OPPREF_PROBE}", _BROWSER_UA)
        checks["oppref_final_url"] = ro.url
        checks["oppref_survives"] = oppref_survives(ro.url)
        if not checks["oppref_survives"]:
            findings.append(("error", "the oppref query parameter is stripped by a redirect/router — the Pixel cannot store the click "
                                      "reference (__oppref cookie) and click attribution is silently lost. Preserve query params on "
                                      "www/https/locale/consent redirects."))
    except requests.RequestException:
        checks["oppref_survives"] = None

    # 4) robots.txt
    try:
        rr = get(f"{parsed.scheme}://{parsed.netloc}/robots.txt", _BROWSER_UA)
        checks["robots_status"] = rr.status_code
        if rr.status_code == 200:
            blocked = _robots_blocks(rr.text, parsed.path or "/")
            checks["robots_blocks"] = blocked
            for ua in blocked:
                level = "warn" if ua == "OAI-SearchBot" else "error"
                findings.append((level, f"robots.txt disallows '{ua}' for this path — review reason robots_txt / crawler_bot_blocked"
                                        + (" (OAI-AdsBot is MANDATORY for ads)." if ua in ("OAI-AdsBot", "*") else " (recommended for relevance).")))
    except requests.RequestException:
        checks["robots_status"] = None

    result["findings"] = [{"level": lvl, "message": m} for lvl, m in findings]
    if args.json:
        _output_json(result)
    else:
        print(f"Landing check: {url}")
        for k, v in checks.items():
            print(f"  {k}: {v}")
        if not findings:
            print("✅ No issues found (reachable for browser and bot UA, HTML, favicon present, oppref survives, robots ok).")
        else:
            lint.report(findings, strict=False)
        if checks.get("robots_blocks") or checks.get("robots_status") != 200:
            print("Recommended robots.txt:\n  User-agent: OAI-AdsBot\n  Allow: /\n  User-agent: OAI-SearchBot\n  Allow: /")


def _robots_blocks(text: str, path: str) -> list[str]:
    """Which of the relevant UA tokens are disallowed for `path` (specific group wins over '*')."""
    groups: dict[str, list[str]] = {}
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line or ":" not in line:
            continue
        key, val = [p.strip() for p in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            if current and any(groups.get(c) for c in current):
                current = []
            current.append(val)
            groups.setdefault(val, [])
        elif key in ("disallow", "allow") and current:
            for ua in current:
                groups.setdefault(ua, []).append((key, val))

    def rules_for(ua: str):
        for g, r in groups.items():
            if g.lower() == ua.lower():
                return r
        return None

    def blocked_by(rules, p: str) -> bool:
        best = None  # longest matching rule wins; allow beats disallow on ties
        for kind, pattern in rules:
            if not pattern:
                continue
            prefix = pattern.rstrip("*").rstrip("$")
            if p.startswith(prefix):
                if best is None or len(prefix) > len(best[1]) or (len(prefix) == len(best[1]) and kind == "allow"):
                    best = (kind, prefix)
        return best is not None and best[0] == "disallow"

    blocked = []
    star = rules_for("*")
    for ua in _CRAWLER_UAS:
        rules = rules_for(ua)
        if ua != "*" and rules is None:
            continue  # falls under '*', reported once there
        if rules is None:
            continue
        if blocked_by(rules, path):
            blocked.append(ua)
    return blocked
