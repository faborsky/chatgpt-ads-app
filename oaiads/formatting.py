"""Output & formatting helpers. No API logic here."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MICROS = Decimal(1_000_000)


def _err(msg: str) -> None:
    """Print a warning/notice to stderr."""
    print(msg, file=sys.stderr)


def _die(msg: str, code: int = 1) -> None:
    """Print an error to stderr and exit."""
    print(msg, file=sys.stderr)
    sys.exit(code)


def _output_json(data: object) -> None:
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# Money: the API uses micros (1 000 000 micros = 1 unit of account currency)
# ---------------------------------------------------------------------------

def amount_to_micros(value: str | float | int | Decimal) -> int:
    """Convert an amount in account currency (e.g. '12.50') to integer micros.

    Uses Decimal so 0.07 does not become 69999 micros. Rejects negatives.
    """
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        _die(f"ERROR: '{value}' is not a valid amount.")
    if dec < 0:
        _die(f"ERROR: amount must not be negative (got {value}).")
    return int((dec * MICROS).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def micros_to_amount(micros: int | str | None) -> Decimal | None:
    """Convert integer micros to a Decimal amount in account currency."""
    if micros is None or micros == "":
        return None
    return (Decimal(int(micros)) / MICROS).quantize(Decimal("0.000001")).normalize()


def fmt_money(micros: int | str | None, currency: str = "") -> str:
    """Format micros as '12.50 USD' (always labelled with the currency)."""
    amount = micros_to_amount(micros)
    if amount is None:
        return "---"
    text = f"{amount:,.2f}" if amount == amount.quantize(Decimal("0.01")) else f"{amount:,f}"
    return f"{text} {currency}".strip()


def fmt_num(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "---"
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer() and decimals == 0):
        return f"{int(value):,}"
    return f"{value:,.{decimals}f}"


def fmt_ts(unix: int | str | None) -> str:
    """Unix seconds → 'YYYY-MM-DD HH:MM UTC'."""
    if unix in (None, "", 0):
        return "---"
    try:
        return datetime.fromtimestamp(int(unix), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, OverflowError, TypeError):
        return str(unix)


def _truncate(text: str | None, max_len: int = 40) -> str:
    """Truncate text for table display."""
    if text is None or text == "":
        return "---"
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def fmt_delta(cur: float, prev: float, pct: bool = False) -> str:
    """Format a current-vs-previous delta as '12.3 (+15%)'."""
    if prev:
        change = (cur - prev) / prev * 100
        arrow = "+" if change >= 0 else ""
        suffix = f" ({arrow}{change:.0f}%)"
    elif cur:
        suffix = " (new)"
    else:
        suffix = ""
    val = f"{cur:.2f}" if pct or cur != int(cur) else f"{int(cur):,}"
    return f"{val}{suffix}"


def print_table(rows: list[list[str]], headers: list[str]) -> None:
    """Minimal fixed-width table (no third-party deps)."""
    if not rows:
        print("(no rows)")
        return
    widths = [len(h) for h in headers]
    str_rows = [[str(c) for c in r] for r in rows]
    for r in str_rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in str_rows:
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)))
