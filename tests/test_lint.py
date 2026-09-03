"""Lint: hard limits from the spec + policy heuristics."""

from oaiads import lint
from oaiads.formatting import amount_to_micros, micros_to_amount, fmt_money


def _levels(findings):
    return {lvl for lvl, _ in findings}


def test_chat_card_valid():
    f = lint.lint_creative({"type": "chat_card", "title": "Try the planner", "body": "Tasks and docs in one place.",
                            "target_url": "https://example.com/p", "file_id": "file_1"})
    assert not [m for lvl, m in f if lvl == "error"]


def test_chat_card_limits():
    f = lint.lint_creative({"type": "chat_card", "title": "ab", "body": "x" * 101, "target_url": "ftp://x", "file_id": None})
    msgs = " ".join(m for _, m in f)
    assert "3–50" in msgs and "≤ 100" in msgs and "http(s)" in msgs and "file_id" in msgs


def test_reserved_query_params_error():
    f = []
    lint.lint_url("https://example.com/?oppref=abc&utm_source=x", f)
    assert any("reserved" in m for lvl, m in f if lvl == "error")
    f2 = []
    lint.lint_url("https://example.com/?utm_source=x", f2)
    assert not [m for lvl, m in f2 if lvl == "error"]


def test_policy_warnings_do_not_block():
    f = lint.lint_creative({"type": "chat_card", "title": "Best casino bonus!!!", "body": "GUARANTEED WINS EVERY DAY",
                            "target_url": "https://example.com", "file_id": "file_1"})
    assert not [m for lvl, m in f if lvl == "error"]
    warns = " ".join(m for lvl, m in f if lvl == "warn")
    assert "gambling" in warns and "superlative" in warns and "punctuation" in warns


def test_interface_imitation_warning():
    f = lint.lint_creative({"type": "chat_card", "title": "Official ChatGPT partner", "body": "ok",
                            "target_url": "https://example.com", "file_id": "f"})
    assert any("imitate" in m for _, m in f)


def test_product_template_rules():
    f = lint.lint_creative({"type": "product_ad_template", "title": "{{product.title}}", "body": "Static body",
                            "file_id": "f"})
    msgs = " ".join(m for _, m in f)
    assert "drop file_id" in msgs and "no {{product.*}} token" in msgs


def test_negative_keywords_limits():
    f = []
    lint.lint_negative_keywords(["a"] * 101, f)
    assert any("max 100" in m for lvl, m in f if lvl == "error")


def test_budget_minimum():
    f = []
    lint.lint_budget({"lifetime_spend_limit_micros": 999_999}, f)
    assert any("minimum" in m for lvl, m in f if lvl == "error")


def test_money_conversion_is_exact():
    assert amount_to_micros("0.07") == 70_000
    assert amount_to_micros("12.5") == 12_500_000
    assert str(micros_to_amount(60_000)) == "0.06"
    assert fmt_money(25_000_000, "USD") == "25.00 USD"


def test_recommended_lengths_warn_but_pass():
    f = lint.lint_creative({"type": "chat_card", "title": "Try the new workspace planner", "body": "Coordinate tasks, docs, and meetings in one place.",
                            "target_url": "https://example.com/p", "file_id": "file_1"})
    assert not [m for lvl, m in f if lvl == "error"]
    warns = " ".join(m for lvl, m in f if lvl == "warn")
    assert "recommends ~16" in warns and "recommends ~32" in warns
    f2 = lint.lint_creative({"type": "chat_card", "title": "Kurz vibe coding", "body": "Postav si appku bez kódování.",
                             "target_url": "https://example.com/p", "file_id": "file_1"})
    assert not [m for lvl, m in f2 if "recommends" in m]
