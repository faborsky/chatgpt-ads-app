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
    """--json → raw JSON; otherwise the human renderer (or JSON as fallback)."""
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


def run_write(method: str, path: str, body, args, done_msg: str, *, create: bool = False,
              idempotent: bool = False, note: str | None = None, extra_headers: dict | None = None,
              verify_path: str | None = None):
    """Dry-run or execute a write and print the standard output. Returns response or None.

    verify_path: after an executed update, GET this path and attach it as `_verified` (lists are
    eventually consistent — verified live 2026-09-02 — so the detail is the source of truth).
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
        detail = api._api_call("GET", verify_path, soft=True)
        if isinstance(detail, dict) and "_error" not in detail:
            resp["_verified"] = detail
    print_result(resp, args, done_msg() if callable(done_msg) else done_msg)
    if verify_path and not getattr(args, "json", False):
        v = resp.get("_verified") if isinstance(resp, dict) else None
        if v:
            summary = {k: v.get(k) for k in ("name", "status", "budget", "bidding_type", "end_time", "review_status") if k in v}
            print(f"  Verified via detail: {json.dumps(summary, ensure_ascii=False, default=str)}")
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
              verify_path=f"{path_prefix}/{object_id}")


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


def issues_str(obj: dict) -> str:
    issues = obj.get("serving_issues") or []
    return ", ".join(i.get("code", "?") if isinstance(i, dict) else str(i) for i in issues) or ""
