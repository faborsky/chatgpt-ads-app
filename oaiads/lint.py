"""Preflight lint — local checks before a write leaves the machine.

Hard limits come from the OpenAPI spec (rejected with an error). Policy
checks come from OpenAI's Ad policies (https://openai.com/policies/ad-policies/,
v1.5, 2026-08-31) and produce WARNINGS: the reviewer is an LLM + classifier
pipeline, so these are heuristics that catch the common rejection causes,
not a guarantee of approval.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

TITLE_MIN, TITLE_MAX = 3, 50
BODY_MAX = 100
# Help Center ("Ads in ChatGPT: The Basics") recommends ~16 chars for the headline and
# ~32 for the description — the spec maximum is far above what the unit shows untruncated.
TITLE_RECOMMENDED = 16
BODY_RECOMMENDED = 32
PRICE_MAX = 100
URL_MAX = 2048
NAME_MIN, NAME_MAX = 3, 1000
CONTEXT_HINTS_MAX = 2000
LOCATION_IDS_MAX = 2500
NEGATIVE_KEYWORDS_MAX = 100
NEGATIVE_KEYWORD_LEN_MAX = 100
BUDGET_MIN_MICROS = 1_000_000
BID_MULTIPLIER_MIN, BID_MULTIPLIER_MAX = 100_000, 10_000_000
STARTERS_MAX = 12
LEAD_FIELDS_MIN, LEAD_FIELDS_MAX = 3, 5

# Terms that map to categories the policy disallows or restricts (warn only).
_POLICY_TERMS = {
    "alcohol/tobacco (disallowed)": r"\b(beer|wine|vodka|whisk(e)?y|alcohol|pivo|víno|vino|cigaret|vap(e|ing)|nicotin|nikotin|tobacco|tabák)\b",
    "gambling (disallowed)": r"\b(casino|kasino|betting|sázk\w*|sazk\w*|poker|lotter\w*|loterie|jackpot|wager)\b",
    "adult/dating (disallowed)": r"\b(dating|seznamk\w*|erotic\w*|sex\w*|nud(e|ity)|escort|onlyfans)\b",
    "recreational drugs (disallowed)": r"\b(cannabis|marijuana|weed|thc|psychedelic|psilocybin|magic mushrooms|konopí)\b",
    "financial services (restricted, US only)": r"\b(loan|půjčk\w*|pujck\w*|mortgage|hypoték\w*|credit card|kreditní kart\w*|crypto\w*|bitcoin|forex|investment|invest\w*|trading|insurance|pojištění|pojisteni)\b",
    "health/medical (restricted, US only)": r"\b(cure|léčb\w*|lecb\w*|treatment|diagnos\w*|therapy|terapie|clinic|klinik\w*|supplement|doplněk stravy|weight loss|hubnutí|hubnuti|detox|diet pill)\b",
    "legal services (restricted, US only)": r"\b(lawyer|attorney|advokát\w*|právník\w*|pravnik\w*|legal services|právní služb\w*)\b",
    "political content (disallowed)": r"\b(election|volby|vote|hlasuj\w*|candidate|kandidát\w*|referendum|political party|politick\w*)\b",
    "jobs/housing listings (disallowed)": r"\b(hiring|we are hiring|job opening|volná pozice|nabídka práce|for rent|k pronájmu|for sale.*(apartment|house|byt|dům))\b",
    "weapons (disallowed)": r"\b(gun|firearm|rifle|pistol|ammo|ammunition|zbraň\w*|zbran\w*|střelivo)\b",
}

_MISLEADING_TERMS = r"\b(guaranteed|guarantee|zaručen\w*|garantovan\w*|#1|no\.?\s?1|the best|nejlepší na (světě|trhu)|100 ?%|risk[- ]free|bez rizika|free money|zbohatn\w*|get rich|miracle|zázrač\w*)\b"
_INTERFACE_TERMS = r"\b(chatgpt|openai|gpt-?\d|sponsored by openai|official chatgpt)\b"
_RESERVED_QUERY_PREFIXES = ("oai", "openai", "oppref", "obref")


def _add(findings: list, level: str, msg: str) -> None:
    findings.append((level, msg))


def lint_name(name: str | None, what: str, findings: list) -> None:
    if name is None:
        return
    if not (NAME_MIN <= len(name) <= NAME_MAX) or not name.strip():
        _add(findings, "error", f"{what} name must be {NAME_MIN}–{NAME_MAX} chars with a non-space character (got {len(name)}).")


def lint_url(url: str | None, findings: list, what: str = "target_url") -> None:
    if url is None:
        return
    if len(url) > URL_MAX:
        _add(findings, "error", f"{what} exceeds {URL_MAX} chars.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        _add(findings, "error", f"{what} must be an absolute http(s) URL (got '{url[:80]}').")
        return
    if parsed.scheme == "http":
        _add(findings, "warn", f"{what} uses http:// — landing pages are crawled for review; https is expected in practice.")
    for pair in parsed.query.split("&"):
        key = pair.split("=")[0].lower()
        if key and key.startswith(_RESERVED_QUERY_PREFIXES):
            _add(findings, "error", f"{what} carries a reserved query parameter '{key}' (serving issue "
                                    "reserved_query_params_present). OpenAI appends its own click params.")
    if re.search(r"\{\{|\}\}", url):
        _add(findings, "warn", f"{what} contains template braces — only product_ad_template creatives get feed values.")


def _policy_scan(text: str, findings: list, where: str) -> None:
    low = text.lower()
    for label, pattern in _POLICY_TERMS.items():
        if re.search(pattern, low, flags=re.IGNORECASE):
            _add(findings, "warn", f"{where} mentions a {label} theme — check openai.com/policies/ad-policies before submitting.")
    if re.search(_MISLEADING_TERMS, low, flags=re.IGNORECASE):
        _add(findings, "warn", f"{where} contains superlative/guarantee wording — 'misleading or deceptive ads' is a baseline rejection reason.")
    if re.search(_INTERFACE_TERMS, low, flags=re.IGNORECASE):
        _add(findings, "warn", f"{where} references ChatGPT/OpenAI — ads must not imitate or imply affiliation with the product (interface imitation policy).")
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > 0.6:
        _add(findings, "warn", f"{where} is mostly UPPERCASE — reads as shouting; reviewers treat it as low quality.")
    if re.search(r"[!?]{2,}", text):
        _add(findings, "warn", f"{where} has repeated punctuation (!!, ??).")
    if re.search(r"[\U0001F300-\U0001FAFF☀-➿]", text):
        _add(findings, "warn", f"{where} contains emoji — keep chat-card copy plain and professional.")
    if re.search(r"\b(click here|klikni zde|klikněte zde)\b", low):
        _add(findings, "warn", f"{where} uses 'click here' — weak, generic CTA copy.")


def lint_creative(creative: dict, findings: list | None = None) -> list:
    """Lint a CreateAdCreativeParams payload. Returns [(level, message)]."""
    findings = findings if findings is not None else []
    ctype = creative.get("type")
    if ctype not in ("chat_card", "product_ad_template"):
        _add(findings, "error", f"creative.type must be chat_card or product_ad_template (got {ctype!r}).")
    title = creative.get("title")
    body = creative.get("body")
    if title is None or not str(title).strip():
        _add(findings, "error", "creative.title is required.")
    elif not (TITLE_MIN <= len(title) <= TITLE_MAX):
        _add(findings, "error", f"creative.title must be {TITLE_MIN}–{TITLE_MAX} chars (got {len(title)}).")
    elif len(title) > TITLE_RECOMMENDED:
        _add(findings, "warn", f"creative.title is {len(title)} chars — OpenAI recommends ~{TITLE_RECOMMENDED}; longer headlines get truncated in some placements.")
    if body is None:
        _add(findings, "error", "creative.body is required.")
    elif len(body) > BODY_MAX:
        _add(findings, "error", f"creative.body must be ≤ {BODY_MAX} chars (got {len(body)}).")
    elif len(body) > BODY_RECOMMENDED:
        _add(findings, "warn", f"creative.body is {len(body)} chars — OpenAI recommends ~{BODY_RECOMMENDED}; keep one concrete benefit, not a slogan.")
    price = creative.get("price")
    if price is not None and len(str(price)) > PRICE_MAX:
        _add(findings, "error", f"creative.price must be ≤ {PRICE_MAX} chars.")
    if ctype == "chat_card":
        if not creative.get("target_url"):
            _add(findings, "error", "chat_card needs creative.target_url.")
        else:
            lint_url(creative["target_url"], findings)
        if not creative.get("file_id"):
            _add(findings, "error", "chat_card needs creative.file_id (upload with image-upload first).")
        if creative.get("image_crop"):
            crop = creative["image_crop"]
            for k in ("x", "y", "width", "height"):
                v = crop.get(k)
                if not isinstance(v, (int, float)) or not (0 <= v <= 1):
                    _add(findings, "error", f"image_crop.{k} must be a fraction 0–1.")
            if isinstance(crop.get("width"), (int, float)) and isinstance(crop.get("height"), (int, float)) \
                    and abs(crop["width"] - crop["height"]) > 1e-6:
                _add(findings, "warn", "image_crop is documented as a *square* crop — width and height differ.")
    if ctype == "product_ad_template":
        if creative.get("file_id") or creative.get("image_crop"):
            _add(findings, "error", "product_ad_template takes image and URL from the feed item — drop file_id/image_crop.")
        if creative.get("target_url"):
            _add(findings, "warn", "product_ad_template ignores target_url (the feed item supplies it).")
        for field in ("title", "body", "price"):
            val = creative.get(field)
            if val and "{{" not in str(val):
                _add(findings, "warn", f"product_ad_template {field} has no {{{{product.*}}}} token — every product will show the same {field}.")
    for field in ("title", "body"):
        if creative.get(field):
            _policy_scan(str(creative[field]), findings, f"creative.{field}")
    return findings


def lint_context_hints(hints: list[str] | None, findings: list) -> None:
    if hints is None:
        return
    if len(hints) > CONTEXT_HINTS_MAX:
        _add(findings, "error", f"context_hints max {CONTEXT_HINTS_MAX} items (got {len(hints)}).")
    if any(not h.strip() for h in hints):
        _add(findings, "error", "context_hints contains an empty item.")
    if not hints:
        _add(findings, "warn", "No context_hints — hints tell ChatGPT when the ad is useful; ad groups without them rely on the model alone.")


def lint_negative_keywords(keywords: list[str], findings: list) -> None:
    if len(keywords) > NEGATIVE_KEYWORDS_MAX:
        _add(findings, "error", f"negative_keywords max {NEGATIVE_KEYWORDS_MAX} (got {len(keywords)}).")
    for kw in keywords:
        if not (1 <= len(kw) <= NEGATIVE_KEYWORD_LEN_MAX):
            _add(findings, "error", f"negative keyword '{kw[:30]}' must be 1–{NEGATIVE_KEYWORD_LEN_MAX} chars.")
    dupes = {k for k in keywords if keywords.count(k) > 1}
    if dupes:
        _add(findings, "warn", f"duplicate negative keywords: {sorted(dupes)[:5]}")


def lint_budget(budget: dict | None, findings: list) -> None:
    if not budget:
        _add(findings, "error", "budget is required (--lifetime-budget and/or --daily-budget).")
        return
    for k, v in budget.items():
        if v is not None and v < BUDGET_MIN_MICROS:
            _add(findings, "error", f"budget.{k} minimum is {BUDGET_MIN_MICROS} micros (1 currency unit).")


def lint_times(start: int | None, end: int | None, findings: list) -> None:
    for label, v in (("start_time", start), ("end_time", end)):
        if v is not None and not (946684800 <= v <= 4102444800):
            _add(findings, "error", f"{label} must be a unix timestamp between 2000-01-01 and 2100-01-01.")
    if start and end and end <= start:
        _add(findings, "error", "end_time must be after start_time.")


def report(findings: list, strict: bool = True) -> bool:
    """Print findings to stderr. Returns True when there are errors."""
    from oaiads.formatting import _err
    errors = [m for lvl, m in findings if lvl == "error"]
    warns = [m for lvl, m in findings if lvl == "warn"]
    for m in errors:
        _err(f"✗ {m}")
    for m in warns:
        _err(f"⚠ {m}")
    return bool(errors) if strict else False
