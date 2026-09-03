# ChatGPT Ads App — CLI for the OpenAI Advertiser API (ChatGPT Ads)

Python CLI for ads in ChatGPT via the **OpenAI Advertiser API v1** (`https://api.ads.openai.com/v1`, OpenAPI spec 2.3.0). Version 1.3.2, 96 commands covering all 88 spec operations + the Bulk API (limited preview) + a `raw` escape hatch. Czech user docs in [README.md](README.md).

## Current phase (2026-09-02)

**Live-verified read AND write** on the author's self-serve account (EUR): the first pilot created 1 campaign / 7 ad groups / 18 ads through the CLI — facts in [docs/api-notes.md → Živě ověřeno](docs/api-notes.md). Not deployed on self-serve accounts (404 "Invalid URL"): `spend_limit_windows`, `negative_keywords`; Business Agent tools 403. Lists are eventually consistent — verify with details. Ads Manager's auto-generated campaign targets **United States**.

**When something misbehaves in real use**: append to `docs/api-notes.md` → „Poznámky z ostrého provozu" (date, command, `x-request-id`, actual vs expected), fix the code, add a test, bump the version, CHANGELOG. Lint warnings go to **stderr** (dry-run included) — look there before reporting "no warning".

## Setup

```bash
<APP_DIR>/run.sh <command> [flags]        # activates .venv automatically
# or: source <APP_DIR>/.venv/bin/activate && python <APP_DIR>/chatgpt_ads_cli.py <command>
```

Credentials in `.env`: `OPENAI_ADS_API_KEY` (issued in Ads Manager → Settings → API keys; scoped to ONE ad account) or, for several accounts, one **named key per account** `OPENAI_ADS_API_KEY_<NAME>` + global flag `--account <name>` (before the subcommand). **Guard:** with 2+ configured accounts and no `--account` (nor `OPENAI_ADS_DEFAULT_ACCOUNT`) `check_config()` refuses to run; a single configured account is auto-selected; the active account is echoed to stderr as `[account: …]`. The project → account mapping is private (the operator's `my-accounts.md` / project docs), never in this repo. `OPENAI_ADS_AD_ACCOUNT` sets the `OpenAI-Ad-Account` header — OAuth tokens only, never with API keys.

## Code structure

- `chatgpt_ads_cli.py` — thin entrypoint (+ re-exports `_api_call`, `_fetch_all`, `account_meta`)
- `oaiads/api.py` — engine: env/accounts, `_api_call` (Bearer auth, redacted errors, retry policy), cross-invocation **request budget** (`.usage/ratelimit_<account>.json`, 80 % of 600/min per endpoint & 1 200/min overall), `Idempotency-Key` generation, cursor paging `_fetch_all`, account meta cache (currency/timezone), `mutate()` dry-run gate
- `oaiads/formatting.py` — output helpers, **micros ⇄ currency** (Decimal), tables
- `oaiads/lint.py` — preflight: spec limits (title 3–50, body ≤100, URL ≤2048 + reserved params, names 3–1000, hints ≤2000, budget ≥1 unit) + **ad-policy heuristics** (warn-only)
- `oaiads/cli.py` — argparse wiring; `_cmd()` = parser/dispatch parity by construction
- `oaiads/commands/*.py` — one module per domain: account, campaigns, adgroups, ads, files, insights (+pulse), targeting, audiences, conversions, feeds, leads, agents, bulk, partner, raw, **plan** (`plan-apply`: whole tree from JSON, resumable via `<plan>.state.json`); `common.py` = shared plan/write/state-change flows (`run_write(verify_path=…)` re-reads the detail after an update)
- `scripts/check_docs_consistency.py` — CLI ↔ README ↔ CLAUDE.md ↔ skill gate
- `tests/` — offline pytest suite (no credentials, no network): `.venv/bin/python -m pytest tests/`

## Commands (96, grouped)

- **Account**: `account`, `accounts`, `brand-update`, `negative-keywords`, `negative-keywords-set`, `negative-keywords-add`, `negative-keywords-remove`, `spend-limits`, `spend-limit-create`, `spend-limit-update`, `spend-limit-delete`, `account-pause`, `account-activate`, `api-limits`, `api-key-create`, `landing-check`
- **Campaigns**: `campaigns`, `campaign-detail`, `campaign-create`, `campaign-update`, `campaign-activate`, `campaign-pause`, `campaign-archive`, `plan-apply`
- **Ad groups**: `adgroups`, `adgroup-detail`, `adgroup-create`, `adgroup-update`, `adgroup-activate`, `adgroup-pause`, `adgroup-archive`
- **Ads**: `ads`, `ad-detail`, `ad-review`, `ad-create`, `ad-update`, `ad-preview`, `ad-activate`, `ad-pause`, `ad-archive`
- **Files**: `image-upload`, `file-upload`
- **Insights**: `insights`, `conversion-insights`, `pulse`
- **Targeting**: `geo-search`
- **Audiences**: `audiences`, `audience-detail`, `audience-create`, `audience-add`, `audience-remove`, `audience-replace`, `audience-merge`, `audience-archive`, `audience-operation`
- **Conversions**: `conversion-check`, `pixels`, `pixel-create`, `capi-key-create`, `event-settings`, `event-setting-create`, `conversion-events`
- **Product feeds**: `feeds`, `feed-create`, `feed-archive`, `feed-uploads`, `feed-products`, `feed-products-patch`, `feed-sftp`, `feed-sftp-create`, `feed-sftp-activate`, `feed-sftp-pause`
- **Lead forms & sync**: `lead-forms`, `lead-form-detail`, `lead-form-create`, `lead-form-update`, `lead-form-publish`, `lead-form-archive`, `lead-form-test`, `lead-syncs`, `lead-sync-create`, `lead-sync-detail`, `lead-sync-delete`
- **Business agents**: `business-agents`, `business-agent-detail`, `business-agent-tools`, `business-agent-create`, `business-agent-update`, `business-agent-preview`, `business-agent-publish`
- **Bulk API**: `bulk-submit`, `bulk-job`, `bulk-operations`
- **Partner data**: `partner-data-upload-create`, `partner-data-upload`
- **Escape hatch**: `raw`

Full flags: README.md command tables, or `--help` per command.

## Safety

- **Writes default to dry-run** — the API has no `validate_only` for single objects, so the dry-run is local lint + the exact request plan; nothing is sent. `--confirm` executes. Exceptions: `image-upload`/`file-upload` write directly (media only, no spend), `bulk-submit` dry-run sends a server-side `validate_only` job (documented, changes nothing).
- **Everything starts `paused`** (`--status` default). Activation only via `*-activate` / `--status active` with `--confirm`.
- **Archive is irreversible** (no delete, no restore). `*-archive` refuses non-paused objects without `--force`.
- **Creates carry an `Idempotency-Key`** (auto-generated, printed) → transient failures are retried safely; writes without one are never auto-retried (the CLI says the write may have landed).
- **Spend limit windows** (`spend-limit-create`) are the account-level fuse where available — on self-serve accounts the endpoint currently returns 404, so the fuse is campaign daily budgets (spend can hit 2×/day) + `end_time`, watched via `pulse`.
- Preflight lint blocks spec violations and warns on ad-policy risks (categories, superlatives, ChatGPT/OpenAI mentions, caps/emoji) and on copy above the Help-Center recommendation (~16-char title, ~32-char body). `landing-check` tests reachability for browser AND bot UA (WAF), robots.txt for **OAI-AdsBot**/OAI-SearchBot, favicon and whether `?oppref=` survives redirects — the top rejection and attribution-loss causes.
- Listings hide `archived` rows by default. Always use `--json` when parsing programmatically (errors → stderr, stdout stays empty).

## ⚠️ Critical for automation (read before scripting writes)

- **Money is in micros** (1 000 000 = 1 unit of ACCOUNT currency). CLI flags take currency units; `max_bid_micros` is PER EVENT — a $60 CPM = `60000` micros per impression (`--max-cpm 60` does the ÷1000). For oCPC, `max_bid` is the CPA bid while billing stays per click. Check `account` for `currency_code` before interpreting spend (likely USD, not CZK).
- **Immutable after create**: campaign `bidding_type`, `mode`, and the oCPC `conversion_event_setting_ids`. Wrong type → new campaign.
- **Full-object replace on update**: `budget`, `bidding_config`, `creative`, `product_set`, `context_hints`, `negative_keywords`. The CLI reads current values and merges flags; when scripting `raw`, send the whole object.
- **Ad group billing must match the campaign**: `impression` for `impressions` campaigns, `click` for `clicks`/`conversions`.
- **Ad review is automatic and re-runs on any creative change**; `review_status` in_review → approved/rejected typically within minutes. Serving needs the ad, ad group AND campaign active, review approved, account brand review approved (favicon!), and a payment method.
- **Rate limits**: 600 req/min per endpoint, 1 200/min overall, per account AND per IP; bulk job creates 10/10 s. Usage is not exposed by the API — the CLI keeps its own sliding-window count in `.usage/` and paces at 80 %. Never fan out parallel invocations; `api-limits` shows the local count. Override: `OAIADS_IGNORE_RATE_BUDGET=1`.
- **Insights**: query arrays go as `fields[]=` (docs convention); default window = last 7 complete days ending yesterday (today's attribution is preliminary, future bounds are rejected); canonical field names (`campaign.spend`) come back as flat wire keys (`spend` / `campaign_spend`) — use `metric()` in insights.py, never hardcode one key.
- **Custom audiences are async and revisioned**: every membership op needs its own `Idempotency-Key`, `expected_revision` from a fresh read, and polling via `audience-operation`. Not available for EEA/Switzerland targeting. Inclusion needs ~25 000 matched users; exclusion works with tiny audiences.
- **`conversion_event_setting_ids` on a campaign = reporting link on CPM/CPC (link every campaign, or it reports clicks only) and the immutable optimization goal on oCPC (exactly one standard setting).** `conversion-check` audits pixel → setting → link; `pulse` warns.
- **Conversion features are gated per account** (pixels/CAPI keys → 404 „Not found", oCPC → 403 „Conversion bidding is not enabled", delta feeds → 403 `product_feed_delta_api_disabled`, Bulk API → 404). The CLI maps these; escalation = OpenAI partner rep, not a retry loop.
- **Secrets shown once**: `api-key-create`, `capi-key-create`, `feed-sftp-create` (rotates!), `lead-sync-create` (signing secret). Never retried, never cached in `.usage/`.
- API details, verified quirks and open questions: [docs/api-notes.md](docs/api-notes.md).

## Release checklist

Bump `__version__` in `oaiads/__init__.py` → update README (version line, 🆕 section, command tables), CLAUDE.md (command count/index), CHANGELOG.md (new `## [x.y.z] — YYYY-MM-DD` entry), bundled skill → `python scripts/check_docs_consistency.py` (must pass) → `.venv/bin/python -m pytest tests/` (must pass) → commit → tag `vX.Y.Z` → GitHub Release once the repo is public.

## Documentation map

- [README.md](README.md) — Czech user docs: setup, access walkthrough, command tables
- [docs/api-notes.md](docs/api-notes.md) — how the Advertiser API behaves (spec + docs research, live-verification TODOs)
- [CHANGELOG.md](CHANGELOG.md) — Keep a Changelog, SemVer
- [skill/chatgpt-ads/](skill/chatgpt-ads/) — bundled operator skill (`SKILL.md`, `chatgpt-ads-campaign-playbook.md` = prerequisites gate + how campaigns are meant to be built, `chatgpt-ads-policies.md`); [skill/INSTALL.md](skill/INSTALL.md)
