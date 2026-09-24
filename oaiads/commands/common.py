"""Helpers shared across command modules."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from oaiads import api
from oaiads.formatting import _die, _err, _output_json, amount_to_micros

# Archiving is irreversible on OpenAI Ads (there is no delete/restore). The
# brake: only PAUSED entities may be archived without --force.
ARCHIVABLE_STATUSES = ("paused",)

STATUS_CREATE = ["active", "paused"]
STATUS_UPDATE = ["active", "paused", "archived"]


def parse_json_arg(value: str | None, flag: str):
    """json.loads a CLI flag value (or @file) with a clean error instead of a traceback."""
    if value is None:
        return None
    text = value
    if value.startswith("@"):
        try:
            with open(value[1:], encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            _die(f"ERROR: cannot read {flag} file {value[1:]}: {e}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        _die(f"ERROR: {flag} is not valid JSON ({e}).\n  Got: {text[:120]}")


def parse_csv(value: str | None) -> list[str]:
    """'a, b,c' → ['a', 'b', 'c'] (empty items dropped)."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def parse_time_to_unix(value: str | None, flag: str = "--time") -> int | None:
    """Accept unix seconds, YYYY-MM-DD or ISO 8601 and return unix seconds (UTC)."""
    if value is None:
        return None
    if value.isdigit():
        return int(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    _die(f"ERROR: cannot parse {flag} '{value}' (use unix seconds, YYYY-MM-DD or ISO 8601)")
    return None


def parse_iso_date(value: str, flag: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        _die(f"ERROR: {flag} must be YYYY-MM-DD (got '{value}')")
    return date.today()  # unreachable


def date_window(days: int, since: str | None, until: str | None) -> tuple[date, date]:
    """Resolve --since/--until/--days into (since, until) inclusive dates.

    Default until = yesterday (complete days; the API rejects future bounds and
    today's attribution numbers are preliminary).
    """
    if until:
        end = date.today() if until == "today" else parse_iso_date(until, "--until")
    else:
        end = date.today() - timedelta(days=1)
    start = parse_iso_date(since, "--since") if since else end - timedelta(days=max(days, 1) - 1)
    if start > end:
        _die(f"ERROR: --since {start} is after --until {end}")
    return start, end


def money_flag(value: str | None, flag: str, minimum_micros: int | None = None) -> int | None:
    """Currency amount flag → micros, with the documented minimum."""
    if value is None:
        return None
    micros = amount_to_micros(value)
    if minimum_micros is not None and micros < minimum_micros:
        unit = api.cached_currency() or "unit(s) of account currency"
        _die(f"ERROR: {flag} must be at least {minimum_micros / 1_000_000:g} {unit} "
             f"({minimum_micros} micros); got {value}.")
    return micros


def emit(data, args, human_fn=None) -> None:
    """--json → raw JSON; otherwise the human renderer (or JSON as fallback).

    Listings accept --limit N (dest list_limit): a client-side cap on the rows shown after the local
    filters — paging is always automatic (--max-items caps how many rows are fetched).
    """
    cap = getattr(args, "list_limit", None)
    if cap and isinstance(data, list) and len(data) > cap:
        _err(f"(showing the first {cap} of {len(data)} rows — --limit; paging itself is automatic)")
        data = data[:cap]
    if getattr(args, "json", False) or human_fn is None:
        _output_json(data)
    else:
        human_fn(data)


def print_plan(method: str, path: str, body, args, note: str | None = None) -> None:
    """Dry-run output: the exact request that --confirm would send."""
    if getattr(args, "json", False):
        _output_json({"executed": False, "plan": {"method": method, "path": path, "body": body},
                      "note": note or "Dry-run: nothing was sent. Add --confirm to execute."})
        return
    print(f"DRY-RUN — would send {method} {path}")
    if body is not None:
        print(json.dumps(body, indent=2, ensure_ascii=False))
    if note:
        print(f"Note: {note}")
    print("Nothing was sent. Add --confirm to execute.")


def print_result(resp, args, done_msg: str) -> None:
    """Standard output after an executed write."""
    if getattr(args, "json", False):
        _output_json(resp)
        return
    print(done_msg)
    if isinstance(resp, dict) and resp.get("_idempotency_key"):
        _err(f"  Idempotency-Key used: {resp['_idempotency_key']} (reuse with --idempotency-key to retry safely)")


STALE_LIST_HINT = "Lists (campaigns/adgroups/ads) can lag a few seconds after a write — trust *-detail, not the list."

# The detail itself is eventually consistent too: seen live 2026-09-07, `adgroup-pause` returned OK and
# the immediate re-read still said `status: active` — the old "Verified via detail" line then read as a
# failed write. So: re-read up to VERIFY_READS times with a pause, and say "verified" only when the
# fields we expect actually match; otherwise say plainly that the detail still shows the old state.
VERIFY_READS = 3
VERIFY_DELAY_SECS = 1.5
_VERIFY_SUMMARY_KEYS = ("name", "status", "budget", "bidding_type", "end_time", "review_status")


def _verify_after_write(verify_path: str, expect: dict | None) -> tuple[dict | None, bool]:
    """Re-read the detail until `expect` (subset of top-level fields) matches. Returns (detail, matched)."""
    detail = None
    for attempt in range(VERIFY_READS):
        d = api._api_call("GET", verify_path, soft=True)
        if isinstance(d, dict) and "_error" not in d:
            detail = d
            if not expect or all(d.get(k) == v for k, v in expect.items()):
                return d, bool(expect)
        if attempt < VERIFY_READS - 1:
            api.time.sleep(VERIFY_DELAY_SECS)
    return detail, False


def run_write(method: str, path: str, body, args, done_msg: str, *, create: bool = False,
              idempotent: bool = False, note: str | None = None, extra_headers: dict | None = None,
              verify_path: str | None = None, expect: dict | None = None):
    """Dry-run or execute a write and print the standard output. Returns response or None.

    verify_path: after an executed update, re-read this detail and attach it as `_verified` plus
    `_verified_matches` (True only when `expect` — default: the body's name/status — matches). Lists AND
    details are eventually consistent (seen live 2026-09-02 / 2026-09-07), hence the retries and the
    careful wording.
    """
    key = getattr(args, "idempotency_key", None)
    # done_msg / note may be callables so a dry-run never triggers side effects
    # (e.g. fetching the account currency) just to format a message.
    if not args.confirm:
        print_plan(method, path, body, args, note() if callable(note) else note)
        return None
    resp, _ = api.mutate(method, path, body, True, create=create, idempotent=idempotent,
                         idempotency_key=key, extra_headers=extra_headers)
    if verify_path and isinstance(resp, dict):
        if expect is None and isinstance(body, dict):
            expect = {k: body[k] for k in ("name", "status") if body.get(k) is not None}
        detail, matched = _verify_after_write(verify_path, expect)
        if detail is not None:
            resp["_verified"] = detail
            resp["_verified_matches"] = matched
            resp["_verified_expect"] = expect or {}
    print_result(resp, args, done_msg() if callable(done_msg) else done_msg)
    if verify_path and not getattr(args, "json", False):
        v = resp.get("_verified") if isinstance(resp, dict) else None
        if v:
            summary = json.dumps({k: v.get(k) for k in _VERIFY_SUMMARY_KEYS if k in v}, ensure_ascii=False, default=str)
            if resp.get("_verified_matches"):
                print(f"  Verified via detail ({', '.join(resp['_verified_expect'])} match): {summary}")
            elif not resp.get("_verified_expect"):
                print(f"  Detail right after the write (may still lag a few seconds): {summary}")
            else:
                print(f"  ⚠ Detail still shows the OLD state after {VERIFY_READS} reads (~{VERIFY_DELAY_SECS * (VERIFY_READS - 1):g} s): {summary}")
                print("    The write itself returned OK — the API is eventually consistent. Re-check with the *-detail command in a few seconds "
                      "before retrying anything.")
        _err(f"  ℹ {STALE_LIST_HINT}")
    return resp


def trunc(text, args, n: int = 36) -> str:
    """Table cell: truncate unless --wide."""
    from oaiads.formatting import _truncate
    return _truncate(text, 200) if getattr(args, "wide", False) else _truncate(text, n)


def state_change(kind: str, path_prefix: str, object_id: str, action: str, args) -> None:
    """Shared activate/pause/archive flow with the archive brake."""
    path = f"{path_prefix}/{object_id}/{action}"
    if action == "archive":
        current = api._api_call("GET", f"{path_prefix}/{object_id}")
        status = str(current.get("status", "?"))
        name = current.get("name", "---")
        if not args.confirm:
            print_plan("POST", path, None, args,
                       note=f"{kind} {object_id} \"{name}\" is {status}. ARCHIVING IS IRREVERSIBLE "
                            "(no unarchive, no delete). Pause instead if unsure.")
            return
        if status not in ARCHIVABLE_STATUSES and not getattr(args, "force", False):
            _die(f"ERROR: {kind} {object_id} \"{name}\" is {status} — refusing to archive a non-paused "
                 f"object. Pause it first, or use --force.")
    if action == "activate" and not args.confirm:
        print_plan("POST", path, None, args,
                   note=f"Activating starts delivery (and spend) as soon as review/parents allow.")
        return
    run_write("POST", path, None, args, f"{kind} {object_id}: {action} done.", idempotent=True,
              verify_path=f"{path_prefix}/{object_id}",
              expect={"status": {"activate": "active", "pause": "paused", "archive": "archived"}[action]})


def brief_error(resp) -> str | None:
    """For soft calls: return a short error string or None."""
    if isinstance(resp, dict) and "_error" in resp:
        e = resp["_error"]
        return f"HTTP {e.get('status')} {e.get('code') or ''} {e.get('message') or ''}".strip()
    return None


def qarr(name: str) -> str:
    """Query-array key: 'fields' → 'fields[]' (the docs' convention)."""
    return f"{name}{api.ARRAY_SUFFIX}"


def drop_archived(rows: list, status_arg: str | None, show_all: bool = False) -> list:
    """Hide archived rows unless asked for (--status archived / --all); apply --status filter."""
    if status_arg:
        return [r for r in rows if str(r.get("status", "")).lower() == status_arg.lower()]
    if show_all:
        return rows
    return [r for r in rows if str(r.get("status", "")).lower() != "archived"]


def issue_codes(obj: dict) -> list[str]:
    return [i.get("code", "?") if isinstance(i, dict) else str(i) for i in (obj.get("serving_issues") or [])]


def issues_str(obj: dict) -> str:
    return ", ".join(issue_codes(obj))


# Serving-issue codes that describe an INTENDED or transient state, not a fault: something in the
# hierarchy is paused / not started yet (the CLI itself creates everything paused), or the ad is
# still in review. ad-review and pulse must not count them as problems (false alarms seen live
# 2026-09-04/07: `ad_group_not_active` on a deliberately paused ad group, `ad_in_review` minutes
# after ad-create).
# `campaign_ended` (campaign past its end_time) seen live 2026-09-24 on ads of a finished campaign — an intended
# end state, not a fault.
PAUSED_CODES = frozenset({"campaign_not_active", "ad_group_not_active", "ad_not_active", "campaign_not_started",
                          "campaign_ended"})
REVIEW_CODES = frozenset({"ad_in_review"})
EXPECTED_ISSUE_CODES = PAUSED_CODES | REVIEW_CODES


def real_issues(obj: dict) -> list[str]:
    """Serving-issue codes that need a human: everything except the expected paused/in-review codes."""
    return [c for c in issue_codes(obj) if c not in EXPECTED_ISSUE_CODES]


def ad_attention(a: dict) -> str | None:
    """'problem' (rejected / real serving issue / appeal), 'waiting' (in review, nothing else wrong) or None (fine)."""
    if a.get("review_status") == "rejected" or real_issues(a) or a.get("appeal"):
        return "problem"
    if a.get("review_status") == "in_review":
        return "waiting"
    return None
