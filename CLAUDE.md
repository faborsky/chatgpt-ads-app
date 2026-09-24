# ChatGPT Ads App — CLI for the OpenAI Advertiser API (ChatGPT Ads)

Python CLI for ads in ChatGPT via the **OpenAI Advertiser API v1** (`https://api.ads.openai.com/v1`, OpenAPI spec 2.3.0). Version 1.5.0, 101 commands covering all 78 operations of the current spec (re-checked 2026-09-24) + the Bulk API (limited preview) + a `raw` escape hatch; 18 commands target endpoints OpenAI removed from the spec (negative keywords, lead forms, Business Agents) and are deprecated (stderr notice, removal in 2.0). Czech user docs in [README.md](README.md).

## Current phase (2026-09-24)

**1.5.0** caught up with the API changes after 2026-09-02 (spec re-diffed, full docs re-read, reads live-verified): daily account spending limit, granular web platforms + `platform` insights segment, `bid_too_low`, audience operation list/resume/cancel, Maximize Results rules, one budget type, documented UTM precedence (templates combine), `campaign_ended` as an expected state, `origin_country_code`; deprecated the endpoints that left the spec. Details: [docs/api-notes.md → Změny API 2026-09](docs/api-notes.md).

**1.4.0** fixed the first week of live-use findings (state file crash on relative `plan-apply` paths, false alarms in `pulse`/`ad-review`, conversions 400) and added `plan-apply --update-existing`; **1.4.1** (same day, after a plan with hundreds of objects) made verify-after-write honest (details are eventually consistent too — retry reads, say "verified" only on a match), folded repeated lint warnings, put a summary + run-time estimate before the dry-run tree and added `--limit` on listings; details in [CHANGELOG.md](CHANGELOG.md) and [docs/api-notes.md → Poznámky z ostrého provozu](docs/api-notes.md).

**Live-verified read AND write** on the author's self-serve account (EUR): the first pilot created 1 campaign / 7 ad groups / 18 ads through the CLI — facts in [docs/api-notes.md → Živě ověřeno](docs/api-notes.md). Account spending limits (`spend_limit_windows`, `daily_spend_limit`) → 403 "Only ad account admins" with a self-serve key (postpaid invoice billing + billing permission only; was 404 before 2026-09-09); `negative_keywords` 404 and Business Agents / lead forms 403 — both left the public spec. Lists are eventually consistent — verify with details. Ads Manager's auto-generated campaign targets **United States**.

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
- `oaiads/lint.py` — preflight: spec limits (title 3–50, body ≤100, URL ≤2048 + reserved params, names 3–1000, hints ≤2000, budget ≥1 unit) + **ad-policy heuristics** (warn-only); `report(collapse=True)` folds ≥3 warnings of one kind into a counted line (errors never)
- `oaiads/cli.py` — argparse wiring; `_cmd()` = parser/dispatch parity by construction
- `oaiads/commands/*.py` — one module per domain: account, campaigns, adgroups, ads, files, insights (+pulse), targeting, audiences, conversions, feeds, leads, agents, bulk, partner, raw, **plan** (`plan-apply`: whole tree from JSON, resumable via `<plan>.state.json`; re-runs diff the plan against live details and `--update-existing` syncs everything except `status`); `common.py` = shared plan/write/state-change flows (`run_write(verify_path=…, expect=…)` re-reads the detail up to 3× and reports "verified" only when the expected fields match; `emit()` applies the listings' `--limit`) and the serving-issue classification (`ad_attention`: `PAUSED_CODES` + `ad_in_review` are expected states, shared by `ad-review` and `pulse`)
- `scripts/check_docs_consistency.py` — CLI ↔ README ↔ CLAUDE.md ↔ skill gate
- `tests/` — offline pytest suite (no credentials, no network): `.venv/bin/python -m pytest tests/`

## Commands (101, grouped)

- **Account**: `account`, `accounts`, `brand-update`, `negative-keywords`, `negative-keywords-set`, `negative-keywords-add`, `negative-keywords-remove` (deprecated), `spend-limits`, `daily-spend-limit-set`, `daily-spend-limit-delete`, `spend-limit-create`, `spend-limit-update`, `spend-limit-delete`, `account-pause`, `account-activate`, `api-limits`, `api-key-create`, `landing-check`
- **Campaigns**: `campaigns`, `campaign-detail`, `campaign-create`, `campaign-update`, `campaign-activate`, `campaign-pause`, `campaign-archive`, `plan-apply`
- **Ad groups**: `adgroups`, `adgroup-detail`, `adgroup-create`, `adgroup-update`, `adgroup-activate`, `adgroup-pause`, `adgroup-archive`
- **Ads**: `ads`, `ad-detail`, `ad-review`, `ad-create`, `ad-update`, `ad-preview`, `ad-activate`, `ad-pause`, `ad-archive`
- **Files**: `image-upload`, `file-upload`
- **Insights**: `insights`, `conversion-insights`, `pulse`
- **Targeting**: `geo-search`
- **Audiences**: `audiences`, `audience-detail`, `audience-create`, `audience-add`, `audience-remove`, `audience-replace`, `audience-merge`, `audience-archive`, `audience-operation`, `audience-operations`, `audience-operation-resume`, `audience-operation-cancel`
- **Conversions**: `conversion-check`, `pixels`, `pixel-create`, `capi-key-create`, `event-settings`, `event-setting-create`, `conversion-events`
- **Product feeds**: `feeds`, `feed-create`, `feed-archive`, `feed-uploads`, `feed-products`, `feed-products-patch`, `feed-sftp`, `feed-sftp-create`, `feed-sftp-activate`, `feed-sftp-pause`
- **Lead forms & sync** (lead forms deprecated; lead sync is in the spec): `lead-forms`, `lead-form-detail`, `lead-form-create`, `lead-form-update`, `lead-form-publish`, `lead-form-archive`, `lead-form-test`, `lead-syncs`, `lead-sync-create`, `lead-sync-detail`, `lead-sync-delete`
- **Business agents** (deprecated): `business-agents`, `business-agent-detail`, `business-agent-tools`, `business-agent-create`, `business-agent-update`, `business-agent-preview`, `business-agent-publish`
- **Bulk API**: `bulk-submit`, `bulk-job`, `bulk-operations`
- **Partner data**: `partner-data-upload-create`, `partner-data-upload`
- **Escape hatch**: `raw`

Full flags: README.md command tables, or `--help` per command.

## Safety

- **Writes default to dry-run** — the API has no `validate_only` for single objects, so the dry-run is local lint + the exact request plan; nothing is sent. `--confirm` executes. Exceptions: `image-upload`/`file-upload` write directly (media only, no spend), `bulk-submit` dry-run sends a server-side `validate_only` job (documented, changes nothing).
- **Everything starts `paused`** (`--status` default). Activation only via `*-activate` / `--status active` with `--confirm`.
- **Archive is irreversible** (no delete, no restore). `*-archive` refuses non-paused objects without `--force`.
- **Creates carry an `Idempotency-Key`** (auto-generated, printed) → transient failures are retried safely; writes without one are never auto-retried (the CLI says the write may have landed).
- **Account spending limits** — daily (`daily-spend-limit-set`, renews at midnight, guarded by `expected_revision`, never auto-retried: 503 = may have landed) or date-range windows (`spend-limit-create`) — are the account-level fuse where available: postpaid invoice billing + a key with billing permission. A self-serve key gets 403 (CLI treats 403/404 as "no account cap via API"), so the fuse is campaign daily budgets (spend can hit 2×/day) + `end_time`, watched via `pulse`.
- Preflight lint blocks spec violations and warns on ad-policy risks (categories, superlatives, ChatGPT/OpenAI mentions, caps/emoji) and on copy above the Help-Center recommendation (~16-char title, ~32-char body). `landing-check` tests reachability for browser AND bot UA (WAF), robots.txt for **OAI-AdsBot**/OAI-SearchBot, favicon and whether `?oppref=` survives redirects — the top rejection and attribution-loss causes.
- Listings hide `archived` rows by default. Always use `--json` when parsing programmatically (errors → stderr, stdout stays empty); listings/insights return a **bare JSON array**, details/`pulse` an object (README → Použití). `--ad-group-id` has the alias `--adgroup-id`; listings take `--limit N` (client-side cap).
- **Details are eventually consistent too** (seen live: pause → immediate re-read still `active`). `run_write` re-reads up to 3× (1.5 s apart) and prints "Verified via detail" only on a match, else "still shows the OLD state" — never retry a write because of that line.
- `ad-review` and `pulse` treat `campaign_not_active` / `ad_group_not_active` / `ad_not_active` / `campaign_not_started` / `campaign_ended` / `ad_in_review` as intended states, never as problems (false alarms seen live). `pulse` reports ⚠ rejected/real issues, ℹ waiting for review, and "not serving only because paused" separately.

## ⚠️ Critical for automation (read before scripting writes)

- **Money is in micros** (1 000 000 = 1 unit of ACCOUNT currency). CLI flags take currency units; `max_bid_micros` is PER EVENT — a $60 CPM = `60000` micros per impression (`--max-cpm 60` does the ÷1000). For oCPC, `max_bid` is the CPA bid while billing stays per click. Check `account` for `currency_code` before interpreting spend (likely USD, not CZK).
- **Immutable after create**: campaign `bidding_type`, `mode`, and the oCPC `conversion_event_setting_ids`. Wrong type → new campaign.
- **Full-object replace on update**: `budget`, `bidding_config`, `creative`, `product_set`, `context_hints`, `conversion_event_setting_ids`. The CLI reads current values and merges flags; when scripting `raw`, send the whole object. Exception: `targeting.platforms` alone — a platform-only update keeps locations/audiences (`null` clears only platforms; `{}`/`[]` = 400).
- **Budget = exactly one type** (daily OR lifetime); lifetime → daily is allowed, daily → lifetime never. **Maximize Results** (`maximize_clicks` ↔ clicks campaign, `maximize_conversions` ↔ conversions campaign) needs a daily budget, click billing, NO `max_bid_micros` and no audience multipliers; back to `fixed_bid` needs an explicit bid (`check_maximize` in adgroups.py).
- **UTM templates combine** across ad account / campaign / ad group / ad; a duplicate key comes from the most specific level (destination URL > ad > ad group > campaign > account) — documented 2026-09, lint warns only on duplicate keys.
- **Ad group billing must match the campaign**: `impression` for `impressions` campaigns, `click` for `clicks`/`conversions`.
- **Ad review is automatic and re-runs on any creative change**; `review_status` in_review → approved/rejected typically within minutes. Serving needs the ad, ad group AND campaign active, review approved, account brand review approved (favicon!), and a payment method.
- **Rate limits**: 600 req/min per endpoint, 1 200/min overall, per account AND per IP; bulk job creates 10/10 s. Usage is not exposed by the API — the CLI keeps its own sliding-window count in `.usage/` and paces at 80 %. Never fan out parallel invocations; `api-limits` shows the local count. Override: `OAIADS_IGNORE_RATE_BUDGET=1`.
- **Conversions insights** (`POST /conversions/insights`): the server defaults `group_by_entity` to true and then demands `entity_ids` (400). The CLI sends `group_by_entity: false` (one account total) unless ids are given; `time_ranges` are JSON *strings*.
- **Insights**: query arrays go as `fields[]=` (docs convention); default window = last 7 complete days ending yesterday (today's attribution is preliminary, future bounds are rejected); canonical field names (`campaign.spend`) come back as flat wire keys (`spend` / `campaign_spend`; live 2026-09-24: flat `spend`/`clicks`, also for `platform.*` segment fields) — use `metric()` in insights.py, never hardcode one key. Segments `product|country|device|platform` (one per request; platform has no conversions; historical `web` rows are not split). Retention: hourly ~30 d, product ~30 d, other 365 d.
- **Custom audiences are async and revisioned**: every membership op needs its own `Idempotency-Key`, `expected_revision` from a fresh read, and polling via `audience-operation` (`409 …recovery_required` → `audience-operation-resume`; add/remove can be cancelled before they apply). Not available for EEA/Switzerland targeting. Inclusion needs ~25 000 matched users; exclusion works with tiny audiences.
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
