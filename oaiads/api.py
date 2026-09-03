"""API engine: config, accounts, auth, request runner, rate budget, retries, paging.

All mutable module state lives here and changes only through the setters
(``set_account``). Command modules read it via the ``api`` module — never
``from oaiads.api import ACTIVE_ACCOUNT`` (that would copy a stale value).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid

import requests
from dotenv import load_dotenv

from oaiads.formatting import _die, _err

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.getenv("OAIADS_NO_DOTENV"):  # tests/CI: keep the developer's .env out of the process
    load_dotenv(os.path.join(BASE_DIR, ".env"))

API_HOST = "https://api.ads.openai.com"
API_BASE = f"{API_HOST}/v1"
USAGE_DIR = os.path.join(BASE_DIR, ".usage")

ENV_KEY = "OPENAI_ADS_API_KEY"           # default account
ENV_KEY_PREFIX = "OPENAI_ADS_API_KEY_"    # named accounts: OPENAI_ADS_API_KEY_<NAME>
ENV_AD_ACCOUNT = "OPENAI_ADS_AD_ACCOUNT"  # optional OpenAI-Ad-Account header (OAuth tokens only)
PLACEHOLDER_KEY = "your-ads-api-key-here"

ACTIVE_ACCOUNT = "default"
ACCOUNT_EXPLICIT = False          # True when --account was given (or OPENAI_ADS_DEFAULT_ACCOUNT applies)
ENV_DEFAULT_ACCOUNT = "OPENAI_ADS_DEFAULT_ACCOUNT"  # opt-in: which named account bare calls use

# Documented limits (developers.openai.com/ads/api-overview): per ad account
# AND per IP address, both must hold.
RATE_LIMIT_PER_ENDPOINT = 600   # requests / minute / endpoint
RATE_LIMIT_OVERALL = 1200       # requests / minute overall
RATE_SOFT_FACTOR = 0.8          # start pacing at 80 % of the documented limit
RATE_WINDOW_SECS = 60
BULK_CREATE_LIMIT = 10          # bulk job creates / 10 s / ad account
BULK_CREATE_WINDOW_SECS = 10

DEFAULT_TIMEOUT = 60
# Query-array convention used throughout the official docs (fields[]=a&fields[]=b).
ARRAY_SUFFIX = "[]"
_TRANSIENT_DELAYS = [2, 5, 15]   # seconds, for GET / idempotent writes
_RATE_LIMIT_DELAYS = [5, 15, 60]  # seconds, for HTTP 429 without Retry-After
MAX_RETRY_AFTER_WAIT = 120        # never sleep longer than this on one 429

# Endpoints whose successful response carries a secret (shown once, never
# retried, never cached) or which rotate credentials as a side effect.
_NEVER_RETRY_PATHS = ("/api_keys", "/conversions/api_keys", "/sftp_access", "/lead_sync_subscriptions")

# Secrets never belong in error output.
_SECRET_RE = re.compile(
    r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}"
    r"|(\"(?:api_key|signing_secret|password|Authorization)\"\s*:\s*\")[^\"]+"
    r"|\b(sk-[A-Za-z0-9_-]{8,})"
    r"|\b(whsec_[A-Za-z0-9+/=]{8,})",
)


def _redact(text: str) -> str:
    """Replace bearer tokens / api keys / secrets in arbitrary text with REDACTED."""
    def repl(m: re.Match) -> str:
        if m.group(1):
            return f"{m.group(1)}REDACTED"
        if m.group(2):
            return f"{m.group(2)}REDACTED"
        return "REDACTED"
    return _SECRET_RE.sub(repl, text)


# ---------------------------------------------------------------------------
# Accounts & auth
# ---------------------------------------------------------------------------

def set_account(name: str | None) -> None:
    """Select the account for this run.

    Resolution: --account <name> → OPENAI_ADS_DEFAULT_ACCOUNT → the single configured account
    (if exactly one) → "default" (OPENAI_ADS_API_KEY). With 2+ accounts and none of the first
    two, check_config() refuses to run: an agent must never act on a guessed client account.
    """
    global ACTIVE_ACCOUNT, ACCOUNT_EXPLICIT
    if name:
        ACTIVE_ACCOUNT, ACCOUNT_EXPLICIT = name.lower(), True
        return
    env_default = os.getenv(ENV_DEFAULT_ACCOUNT)
    if env_default:
        ACTIVE_ACCOUNT, ACCOUNT_EXPLICIT = env_default.lower(), True
        return
    known = configured_accounts()
    if len(known) == 1:
        ACTIVE_ACCOUNT, ACCOUNT_EXPLICIT = known[0], False
        return
    ACTIVE_ACCOUNT, ACCOUNT_EXPLICIT = "default", False


def configured_accounts() -> list[str]:
    """Account names discovered from the environment (no names hardcoded)."""
    names = []
    if os.getenv(ENV_KEY):
        names.append("default")
    for key in os.environ:
        if key.startswith(ENV_KEY_PREFIX) and os.environ[key]:
            names.append(key[len(ENV_KEY_PREFIX):].lower())
    return sorted(set(names))


def _env_var_for(account: str) -> str:
    return ENV_KEY if account == "default" else f"{ENV_KEY_PREFIX}{account.upper()}"


def api_key() -> str:
    return os.getenv(_env_var_for(ACTIVE_ACCOUNT), "")


def check_config() -> None:
    """Validate credentials for the active account (called before any API call)."""
    known = configured_accounts()
    if not ACCOUNT_EXPLICIT and len(known) > 1:
        _die(f"ERROR: {len(known)} accounts are configured ({', '.join(known)}) — say which one:\n"
             f"  --account <name>   (global flag, before the subcommand)\n"
             f"  or set {ENV_DEFAULT_ACCOUNT}=<name> in .env for a default.\n"
             "  Refusing to guess: a write on the wrong client account is not undoable.")
    key = api_key()
    var = _env_var_for(ACTIVE_ACCOUNT)
    if not key or key == PLACEHOLDER_KEY:
        hint = f"  Configured accounts: {', '.join(known)} (use --account <name>)" if known else \
            "  Copy .env.example to .env and paste the key from Ads Manager → Settings → API keys."
        _die(f"ERROR: {var} not set (account '{ACTIVE_ACCOUNT}').\n{hint}")


def _auth_headers() -> dict:
    headers = {"Authorization": f"Bearer {api_key()}", "Accept": "application/json"}
    ad_account = os.getenv(ENV_AD_ACCOUNT)
    if ad_account:
        # Only meaningful with OAuth tokens; API keys are already account-scoped.
        headers["OpenAI-Ad-Account"] = ad_account
    return headers


def new_idempotency_key() -> str:
    return f"oaiads-{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# Persistent state helpers (.usage/) — never store secrets here
# ---------------------------------------------------------------------------

def _write_json_atomic(path: str, data: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _read_json(path: str, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _safe_account_slug() -> str:
    return re.sub(r"[^a-z0-9_-]", "_", ACTIVE_ACCOUNT)


# ---------------------------------------------------------------------------
# Cross-invocation request budget (rate limiting)
# ---------------------------------------------------------------------------

def _budget_file() -> str:
    return os.path.join(USAGE_DIR, f"ratelimit_{_safe_account_slug()}.json")


# Resource ids look like cmpn_101 / adgrp_301 / blkmtnjob_6a2b… (a digit after the last
# underscore) or are bare digits / hex blobs; route words (ad_account, lead_forms) never do.
_ID_SEGMENT_RE = re.compile(r"^[a-z]+_[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*$|^\d+$|^[0-9a-f]{16,}$")


def endpoint_family(method: str, path: str) -> str:
    """Normalise '/campaigns/cmpn_1/insights' → 'GET /campaigns/{id}/insights'.

    The documented per-endpoint limit is per route, so ids collapse to {id}.
    """
    parts = []
    for seg in path.split("?")[0].strip("/").split("/"):
        parts.append("{id}" if _ID_SEGMENT_RE.match(seg) else seg)
    return f"{method.upper()} /" + "/".join(parts)


def _load_budget() -> dict:
    data = _read_json(_budget_file(), {})
    now = time.time()
    calls = [c for c in data.get("calls", []) if now - c[0] < RATE_WINDOW_SECS]
    return {"calls": calls}


def budget_snapshot() -> dict:
    """Current usage in the sliding 60 s window (for api-limits)."""
    calls = _load_budget()["calls"]
    per_family: dict[str, int] = {}
    for _, fam in calls:
        per_family[fam] = per_family.get(fam, 0) + 1
    return {
        "window_secs": RATE_WINDOW_SECS,
        "overall_calls": len(calls),
        "overall_limit": RATE_LIMIT_OVERALL,
        "per_endpoint_limit": RATE_LIMIT_PER_ENDPOINT,
        "soft_factor": RATE_SOFT_FACTOR,
        "per_endpoint_calls": per_family,
    }


def _budget_wait_and_record(family: str) -> None:
    """Pace requests so we stay under the soft caps; persist the call."""
    if os.getenv("OAIADS_IGNORE_RATE_BUDGET"):
        return
    data = _load_budget()
    calls = data["calls"]
    now = time.time()
    overall_cap = int(RATE_LIMIT_OVERALL * RATE_SOFT_FACTOR)
    family_cap = int(RATE_LIMIT_PER_ENDPOINT * RATE_SOFT_FACTOR)
    family_calls = [c for c in calls if c[1] == family]
    wait = 0.0
    if len(calls) >= overall_cap:
        wait = max(wait, RATE_WINDOW_SECS - (now - calls[0][0]))
    if len(family_calls) >= family_cap:
        wait = max(wait, RATE_WINDOW_SECS - (now - family_calls[0][0]))
    if wait > 0:
        _err(f"⏳ Local rate budget: pacing {wait:.1f}s before {family} "
             f"({len(calls)}/{RATE_LIMIT_OVERALL} calls in the last 60 s).")
        time.sleep(min(wait, RATE_WINDOW_SECS) + 0.05)
        data = _load_budget()
        calls = data["calls"]
    calls.append([time.time(), family])
    try:
        _write_json_atomic(_budget_file(), {"calls": calls})
    except OSError:
        pass  # budget is best-effort; never break the actual call


def bulk_budget_wait_and_record() -> None:
    """Separate 10 creates / 10 s budget for POST /bulk_mutation_jobs."""
    path = os.path.join(USAGE_DIR, f"bulk_{_safe_account_slug()}.json")
    now = time.time()
    stamps = [t for t in _read_json(path, []) if now - t < BULK_CREATE_WINDOW_SECS]
    if len(stamps) >= BULK_CREATE_LIMIT:
        wait = BULK_CREATE_WINDOW_SECS - (now - stamps[0]) + 0.05
        _err(f"⏳ Bulk job budget: waiting {wait:.1f}s (10 creates / 10 s).")
        time.sleep(wait)
    stamps.append(time.time())
    try:
        _write_json_atomic(path, stamps)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

_STATUS_HINTS = {
    400: "Validation error — check field names, types and limits (see docs/api-notes.md).",
    401: "API key missing/invalid/revoked. Issue a new key in Ads Manager → Settings and update .env.",
    403: "Not permitted for this ad account — the feature may not be enabled (conversion bidding, "
         "brand updates, delta feeds…) or the key lacks scope. Contact your OpenAI partner rep.",
    404: "Not found — wrong ID, or the endpoint/feature is not available for this account "
         "('Invalid URL' = endpoint not deployed for you; e.g. spend_limit_windows, pixels, CAPI keys).",
    409: "Conflict — a concurrent audience/membership operation or stale revision. Re-read the "
         "object and retry the intended change.",
    413: "Payload too large (request body limit: 16 MiB).",
    422: "Unprocessable — the payload shape is wrong for this endpoint.",
    429: "Rate limited (600 req/min/endpoint, 1 200 req/min overall, per account and per IP).",
}


def _extract_error(resp) -> tuple[str, str | None]:
    """(message, code) from an error response.

    Verified live (2026-09-02): the Ads API uses the Platform-API envelope
    {"error": {"message", "type", "param", "code"}} — e.g. type invalid_request_error,
    code integer_above_max_value, param "limit". Unknown shapes still degrade gracefully.
    """
    try:
        body = resp.json()
    except ValueError:
        return (resp.text[:400] or f"HTTP {resp.status_code}"), None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("detail") or json.dumps(err, ensure_ascii=False)[:400]
            parts = [str(err[k]) for k in ("type", "code") if err.get(k)]
            if err.get("param"):
                parts.append(f"param={err['param']}")
            return str(msg), ("/".join(parts) if parts else None)
        if isinstance(err, str):
            return err, body.get("code")
        msg = body.get("message") or body.get("detail") or body.get("error_description")
        if msg:
            return str(msg), (str(body.get("code")) if body.get("code") else None)
        return json.dumps(body, ensure_ascii=False)[:400], None
    return str(body)[:400], None


def _fail_response(resp, method: str, path: str) -> None:
    message, code = _extract_error(resp)
    request_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-Id")
    code_txt = f" [{code}]" if code else ""
    _err(f"ERROR: HTTP {resp.status_code}{code_txt} on {method} {_redact(path)}: {_redact(message)}")
    hint = _STATUS_HINTS.get(resp.status_code)
    if resp.status_code >= 500:
        hint = "Server error on OpenAI's side."
    if hint:
        _err(f"  Hint: {hint}")
    if request_id:
        _err(f"  Request ID (for support): {request_id}")
    sys.exit(1)


def _retry_after_seconds(resp) -> float | None:
    ra = resp.headers.get("Retry-After")
    if not ra:
        return None
    try:
        return float(ra)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Request runner
# ---------------------------------------------------------------------------

def _api_call(
    method: str,
    path: str,
    params=None,
    json_body: dict | list | None = None,
    files: dict | None = None,
    data: dict | None = None,
    extra_headers: dict | None = None,
    idempotent: bool = False,
    idempotency_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    soft: bool = False,
    _attempt: int = 0,
):
    """Call the Advertiser API and return the parsed JSON body.

    method: GET / POST / PATCH / DELETE
    path: '/campaigns' or '/campaigns/cmpn_1' (relative to API_BASE)
    params: query params — dict or list of (key, value) tuples (repeatable keys)
    json_body: JSON payload; files/data: multipart upload
    idempotent: allow transient-error retries on a write. Creates get an
        Idempotency-Key automatically (idempotency_key), so re-sending them is
        safe; updates and state changes are idempotent by nature. Writes
        without either are NOT retried — the write may have landed.
    soft: return {"_error": {...}} instead of exiting on an HTTP error
        (for optional/best-effort calls such as pulse sections).

    The key travels in the Authorization header, never in the URL.
    """
    if path.startswith("http"):
        if not path.startswith(API_HOST):
            _die(f"ERROR: refusing to call a non-Ads-API URL: {_redact(path)}")
        url = path
    else:
        url = f"{API_BASE}{path if path.startswith('/') else '/' + path}"

    headers = _auth_headers()
    if extra_headers:
        headers.update(extra_headers)
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
        idempotent = True
    if any(p in path for p in _NEVER_RETRY_PATHS) and method != "GET":
        idempotent = False

    family = endpoint_family(method, path)
    _budget_wait_and_record(family)

    try:
        resp = requests.request(
            method, url, params=params, json=json_body, files=files, data=data,
            headers=headers, timeout=timeout,
        )
    except requests.exceptions.Timeout:
        return _retry_or_die(method, path, params, json_body, files, data, extra_headers, idempotent,
                             idempotency_key, timeout, soft, _attempt,
                             reason=f"request timed out ({timeout}s)")
    except requests.exceptions.ConnectionError as e:
        return _retry_or_die(method, path, params, json_body, files, data, extra_headers, idempotent,
                             idempotency_key, timeout, soft, _attempt,
                             reason=f"connection failed: {_redact(str(e))[:200]}")

    if resp.status_code == 429:
        # A rejection — nothing was written, so retrying is safe for every method.
        if _attempt < len(_RATE_LIMIT_DELAYS):
            delay = _retry_after_seconds(resp) or _RATE_LIMIT_DELAYS[_attempt]
            if delay > MAX_RETRY_AFTER_WAIT:
                _die(f"ERROR: rate limited; server asks to wait {delay:.0f}s. Try again later "
                     "(check pacing with: api-limits).")
            _err(f"Rate limited (429), waiting {delay:.0f}s (retry {_attempt + 1}/{len(_RATE_LIMIT_DELAYS)})…")
            time.sleep(delay)
            return _api_call(method, path, params, json_body, files, data, extra_headers, idempotent,
                             idempotency_key, timeout, soft, _attempt + 1)
        if soft:
            return {"_error": {"status": 429, "message": "rate limited after retries"}}
        _fail_response(resp, method, path)

    if resp.status_code >= 500:
        if method == "GET" or idempotent:
            return _retry_or_die(method, path, params, json_body, files, data, extra_headers, idempotent,
                                 idempotency_key, timeout, soft, _attempt,
                                 reason=f"HTTP {resp.status_code}", resp=resp)
        if soft:
            msg, code = _extract_error(resp)
            return {"_error": {"status": resp.status_code, "message": msg, "code": code}}
        _err(f"ERROR: HTTP {resp.status_code} from OpenAI on {method} {_redact(path)}.")
        _die("  Not retrying automatically — the write MAY have landed despite the error.\n"
             "  Check with the matching list command before retrying.")

    if resp.status_code >= 400:
        if soft:
            msg, code = _extract_error(resp)
            return {"_error": {"status": resp.status_code, "message": msg, "code": code}}
        _fail_response(resp, method, path)

    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        _err(f"ERROR: Non-JSON response from {method} {path} (HTTP {resp.status_code})")
        _die(_redact(resp.text[:500]))


def _retry_or_die(method, path, params, json_body, files, data, extra_headers, idempotent,
                  idempotency_key, timeout, soft, attempt, reason: str, resp=None):
    can_retry = method == "GET" or idempotent
    if can_retry and attempt < len(_TRANSIENT_DELAYS):
        delay = _TRANSIENT_DELAYS[attempt]
        _err(f"Transient error ({reason}), retrying in {delay}s…")
        time.sleep(delay)
        return _api_call(method, path, params, json_body, files, data, extra_headers, idempotent,
                         idempotency_key, timeout, soft, attempt + 1)
    if soft:
        return {"_error": {"status": getattr(resp, "status_code", 0), "message": reason}}
    if resp is not None and can_retry:
        _fail_response(resp, method, path)
    _err(f"ERROR: {reason} for {method} {_redact(path)}")
    if not can_retry:
        _die("  Not retrying automatically — the write MAY have landed despite the error.\n"
             "  Check with the matching list command before retrying.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Pagination (cursor based: after / has_more / last_id)
# ---------------------------------------------------------------------------

LIST_HARD_CAP = 5000  # the API caps accounts at 5 000 non-archived objects anyway


def _fetch_all(path: str, params=None, max_items: int = LIST_HARD_CAP, page_size: int = 500,
               item_key: str = "data") -> list:
    """Walk cursor pages to the end (or max_items). Never silently truncates."""
    items: list = []
    base = list(params.items()) if isinstance(params, dict) else list(params or [])
    after = None
    while True:
        page_params = [p for p in base if p[0] not in ("limit", "after")]
        page_params.append(("limit", min(page_size, max_items - len(items))))
        if after:
            page_params.append(("after", after))
        data = _api_call("GET", path, page_params)
        page = data.get(item_key, []) if isinstance(data, dict) else []
        items.extend(page)
        has_more = bool(data.get("has_more")) if isinstance(data, dict) else False
        after = data.get("last_id") if isinstance(data, dict) else None
        if not has_more or not page or not after:
            break
        if len(items) >= max_items:
            _err(f"⚠ Listing stopped at {max_items} items (--max-items to raise). More rows exist.")
            break
    return items


# ---------------------------------------------------------------------------
# Account metadata cache (currency / timezone) — no secrets
# ---------------------------------------------------------------------------

def _accounts_cache_file() -> str:
    return os.path.join(USAGE_DIR, "accounts.json")


def account_meta(refresh: bool = False) -> dict:
    """{id, name, currency_code, timezone} for the active account, cached 24 h."""
    cache = _read_json(_accounts_cache_file(), {})
    entry = cache.get(ACTIVE_ACCOUNT) or {}
    if not refresh and entry.get("currency_code") and time.time() - entry.get("ts", 0) < 86400:
        return entry
    data = _api_call("GET", "/ad_account", soft=True)
    if not isinstance(data, dict) or "_error" in data:
        return entry
    entry = {
        "id": data.get("id"), "name": data.get("name"),
        "currency_code": data.get("currency_code"), "timezone": data.get("timezone"),
        "ts": time.time(),
    }
    cache[ACTIVE_ACCOUNT] = entry
    try:
        _write_json_atomic(_accounts_cache_file(), cache)
    except OSError:
        pass
    return entry


def account_currency() -> str:
    return account_meta().get("currency_code") or ""


def cached_currency() -> str:
    """Currency from the local cache only — never a network call (safe in dry-runs)."""
    entry = _read_json(_accounts_cache_file(), {}).get(ACTIVE_ACCOUNT) or {}
    return entry.get("currency_code") or ""


def account_timezone() -> str:
    return account_meta().get("timezone") or "UTC"


# ---------------------------------------------------------------------------
# Mutations: dry-run by default
# ---------------------------------------------------------------------------

def mutate(method: str, path: str, body: dict | list | None, confirm: bool, *,
           create: bool = False, idempotent: bool = False, idempotency_key: str | None = None,
           extra_headers: dict | None = None):
    """Run a write; without confirm make NO call and return (None, False).

    The single-object endpoints have no server-side validate_only, so the
    dry-run is local: the caller lints the payload and prints the plan.
    Creates always carry an Idempotency-Key (generated unless given) so a
    transient failure can be retried without duplicating the object.
    Returns (response, executed).
    """
    if not confirm:
        return None, False
    key = idempotency_key
    if create and not key:
        key = new_idempotency_key()
    resp = _api_call(method, path, json_body=body, idempotent=idempotent or create,
                     idempotency_key=key, extra_headers=extra_headers)
    if key and isinstance(resp, dict):
        resp.setdefault("_idempotency_key", key)
    return resp, True
