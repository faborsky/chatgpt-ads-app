# ChatGPT Ads App

**🇬🇧 English** · [🇨🇿 Čeština](README.cs.md) · [🇪🇸 Español](i18n/README.es.md) · [🇧🇷 Português](i18n/README.pt-BR.md) · [🇩🇪 Deutsch](i18n/README.de.md) · [🇫🇷 Français](i18n/README.fr.md) · [🇨🇳 简体中文](i18n/README.zh-CN.md) · [🇯🇵 日本語](i18n/README.ja.md) · [🇸🇪 Svenska](i18n/README.sv.md) · [🇳🇴 Norsk](i18n/README.nb.md) · [🇩🇰 Dansk](i18n/README.da.md)

A CLI for creating and monitoring ads in ChatGPT from the terminal or through an AI agent, without clicking around Ads Manager. For marketers and agencies who advertise on ChatGPT Ads and want to build and evaluate campaigns with Claude Code or their own scripts.

**Version 1.5.0** · Python CLI for ads in ChatGPT via the **OpenAI Advertiser API v1** (OpenAPI spec 2.3.0, as of 2026-09-24): 101 commands, all 78 operations of the current spec + the Bulk API + `plan-apply` + a `raw` escape hatch (+ 18 commands for endpoints OpenAI removed from the spec, kept as deprecated). Built to be orchestrated by an AI agent (Claude Code) and for your own automations: `--json` output, dry-run writes, idempotency, its own rate-limit budget.

Author: [Jindřich Fáborský](https://www.faborsky.com)

Follow new releases via **Watch → Custom → Releases** on GitHub; the changelog is in [CHANGELOG.md](CHANGELOG.md).

> ✅ **Status:** reads and writes (campaign, ad groups, ads, upload, preview) verified in live use on a self-serve account (2026-09-02). Still to verify: [docs/api-notes.md → Neověřeno živě](docs/api-notes.md) (Czech). A dry-run (without `--confirm`) sends nothing.

> [!TIP]
> **The app is free and it's yours.** Clone it, use it, rebuild it your way.
>
> Want to build tools like this for your own marketing? That's what I teach: **[faborsky.com](https://www.faborsky.com)**.

## 🆕 What's new (1.5.0)

The app checked against what OpenAI added to the API after 2026-09-02 (changelog of September 9 and 10, reworked docs, a new spec build under the same number 2.3.0). Details in [CHANGELOG.md](CHANGELOG.md) and [docs/api-notes.md](docs/api-notes.md#změny-api-2026-09-srovnání-2026-09-24).

- **Daily account spending limit** (`daily-spend-limit-set` / `daily-spend-limit-delete`): a shared daily cap across all campaigns, renewed at midnight in the account timezone. `spend-limits`, `account` and `pulse` show the daily limit next to the date-range windows. Only for invoice-billed (postpaid invoice) accounts and a key with billing permission. On a self-serve key the endpoint now returns 403 "Only ad account admins" (404 before); the CLI reports it as "no account cap via API" and does not crash.
- **Web split into platforms**: `--platforms` takes `desktop_web`, `ios_web`, `android_web` (plus `web` = all web platforms, `ios_app`, `android_app`); `--clear-platforms` removes only the platform restriction. A platform-only change sends only `platforms` (locations and audiences stay as they are). `insights --segment platform` breaks performance down by platform.
- **`bid_too_low`**: OpenAI now flags ad groups whose bid is probably too low for reliable delivery. Shown by `adgroup-detail`, `adgroups --bid-check` (column) and `pulse` (number of active ad groups).
- **Maximize Results per the new docs**: `--strategy maximize_clicks|maximize_conversions` works without `--max-bid`; the CLI checks that the campaign has the matching goal and a **daily** budget, and drops the bid and audience multipliers on the switch. Back to `fixed_bid` only with an explicit bid. A campaign always has one budget (daily OR lifetime), and daily cannot be switched back to lifetime.
- **UTM templates combine**: OpenAI documented that templates on the campaign, ad group and ad are merged, and on a duplicate key the more specific level wins (URL > ad > ad group > campaign > account). Lint warns only on duplicate keys.
- **Audience operations**: `audience-operations` (list), `audience-operation-resume` (finishes an interrupted add/remove), `audience-operation-cancel` (cancels an add/remove before it applies); polling on `409 recovery_required` suggests resume right away.
- **Fixed**: `campaign_ended` (campaign past its end) is no longer a "problem" in `pulse`/`ad-review` (seen live, most of the reported "problems"); segmented insights also show the campaign (rows looked duplicated); `pulse` detects the home country from the new `origin_country_code` field.
- **Deprecated**: negative keywords, lead forms and Business Agents disappeared from the public spec. The commands stay, print a notice on stderr and will be removed in 2.0. Lead sync is still in the spec.

### 1.4.1

- **Verify-after-write no longer misleads**: right after a write the detail is briefly stale (ad group paused → re-read still said `active`). The CLI now reads it up to 3× with a pause and prints "Verified via detail" only when the expected state matches; otherwise it says the detail still shows the old state and to check `*-detail` in a few seconds.
- **`plan-apply` for hundreds of objects**: the summary (counts, writes, run-time estimate) comes **before** the tree, repeated lint warnings fold into one line with a count (`--verbose-lint` expands them).
- `--limit N` on the `campaigns` / `adgroups` / `ads` listings; the README describes the shape of `--json` output (listings = array, details = object).

### 1.4.0

- **Fixes from a week of live use**: `plan-apply --file plan.json --confirm` no longer crashes on a relative path (the state was written to `plan.state.json` without a directory and failed only in the live run, before the campaign was created); `pulse` no longer raises a false alarm for ads in a deliberately paused ad group, and `ad-review` no longer lists freshly created ads (`ad_in_review`) under "Problems" (both share one classification: a pause in the hierarchy and review are expected states, not problems); conversions in `pulse` no longer return HTTP 400 (the server defaults to `group_by_entity=true` and wants `entity_ids`).
- **`plan-apply --update-existing`**: a repeated run compares the plan with the live objects and lists the differences (↻); with the flag it syncs them (name, budget/end/targeting, bidding, hints, UTM, creative → new review). It never changes `status`. Without the flag it only reports how many objects differ. Before, plan changes were silently ignored.
- `conversion-insights`: without `--ids`, one total row for the account; `--group-by-entity` lists the objects itself; alias `--adgroup-id`; lint warns on a UTM template on both campaign and ad group. Playbook: the whole UTM template on the ad group; a 3–5 USD bid is a US calibration, on the CZ/SK market ~1 EUR delivers too.

### 1.3.1

- **Context hints in four styles.** OpenAI describes hints in two help articles in three ways (product description "what / for whom / when" · topic or intent of the ad group · "conversations, topics, or keywords"). Playbook §2 quotes this verbatim and derives styles **P** (product description), **S** (situation), **C** (question in a conversation), **K** (topics/keywords); the skill asks the user which way to go, or proposes testing the styles against each other (same ads, one ad group per style, its own `utm_content`, always a control K ad group).

### 1.3.0

- **Renamed to `chatgpt-ads-app`** (repo, folder, entrypoint `chatgpt_ads_cli.py`, skill `/chatgpt-ads`, placeholder `<CHATGPT_ADS_APP_DIR>`). The product is called ChatGPT Ads; "OpenAI" stays only where it is the API's name. The `OPENAI_ADS_API_KEY*` variables and the `oaiads` package **do not change**, so `.env` and scripts need no edits. If you installed the skill under the old name: `mv ~/.claude/skills/openai-ads ~/.claude/skills/chatgpt-ads` and repeat step 2 of `skill/INSTALL.md`.

### 1.2.1

- **Multiple accounts without mistakes**: with 2+ configured keys the CLI **refuses calls without `--account`** (a write to the wrong client account cannot be undone); a single configured account is selected automatically; `OPENAI_ADS_DEFAULT_ACCOUNT` sets a default. The active account is printed to stderr (`[account: …]`). See [Multiple accounts (agencies)](#multiple-accounts-agencies), the rule in the skill and the template for the private `my-accounts.md` file in `skill/INSTALL.md`.

### 1.2.0

- **`plan-apply`**: a whole campaign (campaign → ad groups with hints and UTM → ads with a shared image) from **one JSON**: the dry-run prints the tree with text lengths and lint, `--confirm` creates everything sequentially with an Idempotency-Key and writes the IDs to `plan.state.json`, so you resume an interrupted run with the same command. Template: [docs/plan-example.json](docs/plan-example.json). Replaces the 25 separate calls from the first pilot.
- **Verified live after writing**: `campaign-create/update`, `adgroup-create` (the UTM template on the ad group persists), `image-upload`, 18× `ad-create` (review within ~3 min), `ad-preview`. Listings are stale for a few seconds after a write → `*-update` now fetches the detail and says so.
- `campaign-detail --with-children` = the whole tree including ads and review; `ad-review` separates "waiting for review" from problems; `--wide` on listings and `conversion-events`; `pulse` warns when a campaign targets a different country than the account timezone suggests (the auto-generated campaign trap = USA).
- **Negative keywords do not exist on a self-serve account** (`POST` → 404, `GET /ad_account` does not return the field). The CLI says so explicitly instead of showing an empty list. Playbook: budget only on the campaign (more situations = more ad groups), the API enforces no minimum bid, image = a small square thumbnail without text, UTM conventions, pixel client-side → verify via `conversion-events`.

### 1.1.1

- **First verified against a live account** (read-only): `fields[]` syntax, error shape + `x-request-id`, gating (spend limit windows 404, Business Agents 403), CZ geo ids incl. postal codes, what a campaign generated by Ads Manager looks like (**targets the USA by default**, check `campaign-detail`). Details in [docs/api-notes.md → Živě ověřeno](docs/api-notes.md) (Czech).
- `ad-review` tells "not delivering because paused" apart from real problems; `raw --params` supports array parameters.

### 1.1.0

- **`conversion-check`**: measurement audit pixel → event setting → link to the campaign → latest pixel events (`--events`); explains the gating (404 = pixels not enabled).
- `--conversion-event-setting-id` on a campaign now has the right semantics: on CPM/CPC = linking the event for reporting (the last step people forget), on oCPC exactly one standard setting. `campaign-create` warns when nothing is linked, `pulse` reports active campaigns without an event.
- Playbook: why to measure conversions on CPC too, consent hook + CSP for the pixel, the "no permission to create ad accounts in your tenant" trap and the way around it via a company e-mail + invitation.

### 1.0.0

- Full API coverage: account + spend limit windows + negative keywords, campaigns / ad groups / ads, insights (4 scopes + conversions), geo lookup, custom audiences, conversions (pixel, CAPI, event settings), product feeds (SFTP, Delta Feeds), lead forms + webhooks, Business Agents, Bulk API, partner data.
- Safety model for an agent: dry-run by default, everything starts `paused`, irreversible archiving with a brake, automatic `Idempotency-Key`, local rate-limit budget, lint against spec limits and Ad policies, `landing-check` for the most common rejection reasons.
- Bundled `/chatgpt-ads` skill for Claude Code.

## Two ways to use the app

**A) Orchestration through Claude Code (recommended)**: an AI agent drives the app and you give it tasks in plain language. Copy this prompt into Claude Code:

> Clone the repo `https://github.com/faborsky/chatgpt-ads-app.git` into `~/dev/chatgpt-ads-app`, run `./setup.sh`, install the skill per `skill/INSTALL.md` and walk me through filling in `.env` (I need an API key from OpenAI Ads Manager; the steps are in the README under "Getting access"). Then check that it works with `./run.sh account`.

The `/chatgpt-ads` skill then handles the create / optimize / analyze / review-check / audiences / conversions / feeds scenarios with built-in safety rules (plan → approval → write, paused starts, dry-run, policy checklist).

**B) Your own automations**: the CLI has stable `--json` output, dry-run by default, a rate-limit budget and retry logic, so it is safe to call from scripts, crons or your own agents:

```bash
./run.sh campaigns --json | jq '.[].name'
./run.sh insights --days 7 --aggregation-level campaign --json
./run.sh campaign-create --name "Test" --lifetime-budget 50 --bidding-type clicks            # dry-run: prints the plan
./run.sh campaign-create --name "Test" --lifetime-budget 50 --bidding-type clicks --confirm  # write (paused)
```

## Requirements

- Python 3.9+
- An advertiser account in [OpenAI Ads Manager](https://ads.openai.com) with an approved brand review and a payment method
- An API key issued in Ads Manager (Settings → API keys), scoped to one ad account

## Installation

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see below)
./run.sh account    # smoke test
```

### Windows

The `setup.sh`/`run.sh` scripts are bash. On Windows use **Git Bash** (part of [Git for Windows](https://git-scm.com/download/win)) or **WSL** and the steps above work unchanged. Alternatively, plain PowerShell:

```powershell
git clone https://github.com/faborsky/chatgpt-ads-app.git; cd chatgpt-ads-app
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # fill in the key
python chatgpt_ads_cli.py account
```

## Getting access step by step

### 0) Advertiser account (one-time)

1. Create an account at [ads.openai.com](https://ads.openai.com) (Ads Manager). You go through business verification and **brand review**. The account does not serve until its name, URL and **favicon** (min. 128 × 128 px) are approved. Add a payment method.
2. Check that your category is allowed ([Ad policies](https://openai.com/policies/ad-policies/)): in the first phase consumer goods, local services, travel and experiences, digital products and education. Finance / health / legal only for approved advertisers in the US; alcohol, gambling, dating, politics, weapons and individual job/housing listings are prohibited. Summary for the operator: [skill/chatgpt-ads/chatgpt-ads-policies.md](skill/chatgpt-ads/chatgpt-ads-policies.md).

### 1) API key

Ads Manager → **Settings → API keys** → issue a key. The key is scoped to **one ad account** (more accounts need more keys).

### 2) .env

```
OPENAI_ADS_API_KEY=<key>                       # one account
# several accounts: OPENAI_ADS_API_KEY_<NAME>=<key>  →  ./run.sh --account <name> <command>   (see Multiple accounts)
```

`.env` has 600 permissions and is in `.gitignore`. The key never travels in a URL, only in the `Authorization` header.

### 3) Check and safety cap

```bash
./run.sh account            # name, currency, timezone, brand review, spend caps
./run.sh spend-limits       # no window? →
./run.sh spend-limit-create --start 2026-09-02 --end 2026-10-01 --amount 500 --name "September cap" --confirm
```

**The account spending limit caps spend for the whole account**: daily (`daily-spend-limit-set`, renews at midnight) or per period (`spend-limit-create`, start inclusive, end exclusive). Set it before you let an agent loose on the account. **Note:** limits are only for invoice-billed (postpaid invoice) accounts and a key with billing permission; a self-serve key gets 403 "Only ad account admins" (2026-09-24). In that case the safety net is the campaign daily budget (spend can reach 2× per day) + `--end`, and `pulse` for monitoring.

## Prerequisites before the first campaign

A ChatGPT Ads campaign depends on the technical integration of your website and measurement. Before you launch anything, these must be in place: approved brand review + payment method, an **account spending limit** (where available, otherwise a daily budget + campaign end), a landing page reachable for **OAI-AdsBot** (robots.txt and WAF/CDN), **oppref surviving redirects**, measurement in place (pixel and/or Conversions API with a shared event id, consent hook, CSP) **linked to the campaign** (on CPC too, otherwise you compare CPC instead of cost per customer), and for e-shops a feed with `is_ads_eligible` and automatic sync (items expire after 14 days).

Watch out when creating the account: a personal account has no permission to create ad accounts in the tenant. A company e-mail + invitation works (see playbook §7). Everything except measurement is checked by `./run.sh landing-check --url …` and `./run.sh account`. The full checklist, rules for context hints (describe situations, not keywords), recommended text lengths (~16 / ~32 characters), bidding and billing traps: [skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md](skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md).

## Multiple accounts (agencies)

One ad account = one legal entity, country and currency, so an agency or a company with several brands has **several accounts and several keys**. A convention that prevents the worst mistake (writing to someone else's account):

1. **One named key per account** in `.env`: `OPENAI_ADS_API_KEY_ACME=…`, `OPENAI_ADS_API_KEY_BRANDX=…`. Name = slug of the client/brand. No "bare" `OPENAI_ADS_API_KEY`, so no account is implicit.
2. **Every call names the account**: `./run.sh --account acme campaigns`. With 2+ configured accounts the CLI **refuses** a call without `--account` and lists what is available. A single configured account is selected automatically; for a default, set `OPENAI_ADS_DEFAULT_ACCOUNT=acme`. With several accounts the active one is printed to stderr as `[account: acme]`.
3. **The project → account mapping does not belong in the repo or in the shared skill** (it is client data). It lives in a private layer: a `my-accounts.md` file next to the skill (template in [skill/INSTALL.md](skill/INSTALL.md)) or in the client's project docs. The skill looks there, and when a project has no row, it **asks** and never guesses.
4. **Run `account` before the first write**: the account name, currency and timezone in the response must match the client. Local state (`.usage/`) is per account, so one client's rate budget does not block another's.
5. A new client account: the client creates it on their own entity and invites the manager (see playbook §7); issues a key in that account's Ads Manager; the manager stores it as another `OPENAI_ADS_API_KEY_<NAME>` and adds a row to `my-accounts.md`.

## A campaign from one file (`plan-apply`)

```bash
cp docs/plan-example.json plan.json        # edit: budget, end, location_ids, event setting, hints, texts, image
./run.sh plan-apply --file plan.json       # dry-run: summary (counts, writes, run-time estimate) + campaign tree + lint, nothing is sent
./run.sh plan-apply --file plan.json --confirm   # creates campaign → ad groups → ads (paused), resume via plan.state.json
./run.sh campaign-detail --campaign-id cmpn_… --with-children   # check the tree + review
./run.sh plan-apply --file plan.json                    # after editing the plan: ↻ shows what differs from the live objects
./run.sh plan-apply --file plan.json --confirm --update-existing   # and syncs it (never status; creative → new review)
```

A plan also supports `"campaign": {"id": "cmpn_existing"}` (only add ad groups and ads to an existing campaign), `defaults` for ad groups/ads, `hints_file` (one hint per line), a shared `image_file` or `image_url`, and a UTM template via `query_string_template` on both campaign and ad group: templates **combine** and on a duplicate key the ad group wins (lint shows duplicate keys). Both work: the whole template on the ad group (verified in live use) and splitting `utm_source/medium/campaign` on the campaign + `utm_content` on the ad group (per the docs, not yet verified live).

**Large plans** (hundreds of objects): the summary comes before the tree, repeated lint warnings of one kind fold into one line with a count and maximum (`--verbose-lint` prints each one). Errors against spec limits stay with their object.

**Repeated run** (same `plan.json` + `plan.state.json`): objects from the state are not created again; the CLI reads their details, compares them with the plan and lists the differences (↻). Without `--update-existing` nothing existing changes (report only); with it, name, budget/end/targeting/linked events, bidding (the whole object, live keys stay), hints, UTM template and creative (merged with the live one; a new image is uploaded once) are synced. `status` is never synced: activation and pausing are always an explicit `*-activate` / `*-pause`. A key removed from the plan is not deleted from the object.

## Usage conventions

- **Writes are dry-run by default**: the command prints the exact request it would send and sends nothing. `--confirm` executes. The API has no server-side `validate_only` for single objects, so dry-run = local lint + plan. Exceptions: `image-upload`/`file-upload` write directly (media only, no spend); `bulk-submit` without `--confirm` sends a **validation job** (`validate_only: true`, officially changes nothing).
- **Everything starts `paused`** (`--status` default). Activation only via `*-activate` / `--status active` + `--confirm`.
- **Archiving is irreversible** (there is no delete). `*-archive` refuses a non-paused object without `--force`.
- **Money is in the account currency** (`account` → `currency_code`, typically USD). Flags take currency units (`--lifetime-budget 250`), the API gets micros (×1 000 000). `--max-bid` is **per event**; for CPM campaigns `--max-cpm 40` is more convenient (= 40 000 micros per impression). On oCPC, `--max-bid` is the CPA bid.
- **Times**: `--start/--end` as `YYYY-MM-DD`, ISO 8601 or unix seconds. Insights windows are computed in the account timezone and by default end **yesterday** (today's attribution is preliminary, the API rejects future bounds).
- **Idempotency**: every create automatically carries an `Idempotency-Key` (printed); you can safely repeat the same request with `--idempotency-key <key>`. The CLI never retries writes without idempotency and tells you the write may have gone through.
- **Listings** hide `archived` (`--all` shows them, `--status` filters locally: the API filters only by `name`); they page to the end (`--max-items` limits how much is downloaded; `--limit N` on `campaigns`/`adgroups`/`ads` only trims how many rows are shown).
- Parse only `--json` programmatically (errors go to stderr, stdout stays empty). **Output shape:** listings (`campaigns`, `adgroups`, `ads`, `ad-review`, `audiences`, `feeds`, `pixels`, `event-settings`, `lead-forms`…), `geo-search`, `insights` and `conversion-insights` return a **bare JSON array** (no `data` wrapper); details (`*-detail`, `account`), `pulse`, `conversion-check`, `landing-check`, `api-limits` return an **object**; writes return `{"executed": false, "plan": {…}}` in dry-run and the API response after `--confirm` (updates/state transitions add `_verified`, `_verified_matches`), `plan-apply` `{"executed": …, "plan"|"created": …}`.
- **Verify after write** (`*-update`, `*-activate/pause/archive`): the CLI reads the detail up to 3× with a 1.5 s pause and prints "Verified via detail" only when the expected fields match (`status`, or `name`/`status` from the request). When the detail still shows the old state, it says so: the write went through, the API is eventually consistent, check `*-detail` in a few seconds and do not write again.
- `--ad-group-id` has the alias `--adgroup-id` (the commands are `adgroup-*`).
- Multiple accounts: `--account <name>` (global flag before the command) → `OPENAI_ADS_API_KEY_<NAME>`; required with 2+ accounts (see Multiple accounts).

### Account protection (rate limits)

The API limits **600 req/min per endpoint and 1 200 req/min overall, per ad account and per IP**; bulk jobs 10 / 10 s. The API does not report usage, so the CLI keeps its own sliding window in `.usage/` and waits from 80 % of the limit (`api-limits` shows the state; `OAIADS_IGNORE_RATE_BUDGET=1` turns it off). 429 is retried respecting `Retry-After`. Do not run several instances in parallel.

## Commands

### Account

| Command | What it does | Key flags |
|---|---|---|
| `account` | Account: status, brand/integrity review, currency, tz, home country, spending limits | `--json` |
| `accounts` | Accounts available with this key + locally configured ones | |
| `brand-update` [write] | Account name / URL / favicon → new brand review | `--name`, `--url`, `--favicon-file-id` |
| `negative-keywords` ⚠ deprecated | Account-level negative keywords (removed from the spec 2026-09; never worked on self-serve) | |
| `negative-keywords-set` [write] ⚠ deprecated | **Replaces** the whole list (max 100 × 100 characters) | `--keywords a,b`, `--keywords-file` |
| `negative-keywords-add` / `negative-keywords-remove` [write] ⚠ deprecated | Adds / removes (read-modify-write) | `--keywords` |
| `spend-limits` | Account spending limits: daily limit (incl. today's spend and remainder) + date-range windows + `revision` | |
| `daily-spend-limit-set` [write] | Daily account limit (new from tomorrow; change amount / end); guard `expected_revision` (the CLI reads it) | `--amount`, `--start` (new only), `--end` / `--no-end`, `--expected-revision` |
| `daily-spend-limit-delete` [write] | Removes the daily limit (date-range windows stay) | `--expected-revision` |
| `spend-limit-create` [write] | New date-range window (start inclusive, **end exclusive**) | `--start`, `--end`, `--amount`, `--name`, `--io-id` |
| `spend-limit-update` / `spend-limit-delete` [write] | Edit / delete a window | `--window-id` |
| `account-pause` / `account-activate` [write] | Pause / activate the whole account | |
| `api-limits` | Local budget vs. documented limits | |
| `api-key-create` [write] | Another API key for the account (shown once) | `--name` |
| `landing-check` | Local landing page check: HTTP status for browser and bot UA (WAF/CDN), HTML, favicon, robots.txt (OAI-AdsBot, OAI-SearchBot, `*`), captcha, **oppref survives redirects** | `--url` |

### Campaigns

| Command | What it does | Key flags |
|---|---|---|
| `campaigns` | List (archived hidden) | `--status`, `--all`, `--name`, `--include-issues`, `--order`, `--wide`, `--limit` |
| `campaign-detail` | Detail incl. targeting and serving issues; `--with-children` = the whole tree (ad groups + ads + review) | `--campaign-id`, `--with-children` |
| `campaign-create` [write] | New campaign (paused) | `--name`, `--lifetime-budget` / `--daily-budget`, `--bidding-type impressions\|clicks\|conversions`, `--countries CZ,SK`, `--location-ids`, `--exclude-location-ids`, `--audience-ids`, `--exclude-audience-ids`, `--platforms` (`web` = all web platforms, `desktop_web`, `ios_web`, `android_web`, `ios_app`, `android_app`), `--start`, `--end`, `--description`, `--conversion-event-setting-id` (links the event for reporting; exactly one on oCPC), `--mode` + `--product-feed-id` / `--business-agent-id`, `--query-string-template`, `--targeting-json` |
| `campaign-update` [write] | Edit (budget = whole object; locations/audiences merge into the current targeting, a platform-only change sends only `platforms`); fetches the detail after the write | same + `--campaign-id`, `--status`, `--clear-end-time`, `--clear-targeting`, `--clear-platforms` |
| `plan-apply` [write] | **A whole campaign from one JSON** (campaign → ad groups → ads), dry-run = tree + lint, `--confirm` = sequential write with resume via `plan.state.json`; a repeated run lists differences (↻) and `--update-existing` syncs them (never status) | `--file plan.json`, `--state`, `--update-existing`, `--verbose-lint` |
| `campaign-activate` / `campaign-pause` / `campaign-archive` [write] | State transitions (archive irreversible, brake on paused) | `--campaign-id`, `--force` |

`bidding_type`, `mode` and the oCPC event setting **cannot be changed after creation**. A campaign always has one budget (daily OR lifetime); lifetime can switch to daily, not back.

### Ad groups

| Command | What it does | Key flags |
|---|---|---|
| `adgroups` | List (optionally per campaign); `--bid-check` adds a `bid_too_low` column | `--campaign-id`, `--status`, `--all`, `--name`, `--include-issues`, `--bid-check`, `--limit` |
| `adgroup-detail` | Detail incl. bidding, hints, product set and the `bid_too_low` warning | `--ad-group-id`, `--with-children` |
| `adgroup-create` [write] | New ad group (paused); the billing event is derived from the campaign | `--campaign-id`, `--name`, `--max-bid` (per event) / `--max-cpm`, `--billing-event impression\|click`, `--strategy fixed_bid\|maximize_clicks\|maximize_conversions` (Maximize Results: no bid, only a click campaign with a clicks/conversions goal and a daily budget, no audience multipliers), `--hints "a, b"` (repeatable), `--hints-file`, `--audience-multiplier caud=2.0`, `--product-feed-id` + `--product-filter brand:in:X\|Y` (custom labels `ads_metadata.custom_label_0:in:…`), `--product-set-json`, `--description`, `--query-string-template` |
| `adgroup-update` [write] | Edit (bidding_config is sent whole, hints are replaced) | same + `--ad-group-id`, `--status` |
| `adgroup-activate` / `adgroup-pause` / `adgroup-archive` [write] | State transitions | `--ad-group-id`, `--force` |

### Ads

| Command | What it does | Key flags |
|---|---|---|
| `ads` | List per ad group / campaign / whole account | `--ad-group-id`, `--campaign-id`, `--review-status`, `--status`, `--all`, `--include-issues`, `--limit` |
| `ad-detail` | Detail incl. creative, review reason, appeal, issues | `--ad-id` |
| `ad-review` | Rejected ads / ads with real serving issues + reasons; "waiting for review" and "not running only because paused" listed separately (not a problem; in JSON `_attention: problem\|waiting`) | `--ad-id`, `--campaign-id`, `--ad-group-id` |
| `ad-create` [write] | New ad (paused): `chat_card` or `product_ad_template`; lint title 3–50, body ≤ 100, URL | `--ad-group-id`, `--name`, `--title`, `--body`, `--target-url`, `--file-id` / `--image-url` / `--image-file`, `--price`, `--type`, `--crop x,y,w,h`, `--creative-json`, `--query-string-template` |
| `ad-update` [write] | Edit (the creative is sent whole → re-review) | same + `--ad-id`, `--status` |
| `ad-preview` | Preview (iframe, valid ~24 h) | `--ad-id`, `--out preview.html` |
| `ad-activate` / `ad-pause` / `ad-archive` [write] | State transitions | `--ad-id`, `--force` |

### Files

| Command | What it does | Key flags |
|---|---|---|
| `image-upload` | Image from URL or file → `file_id` (direct write) | `--url` / `--file`, `--purpose account_favicon` |
| `file-upload` | Customer list (.csv/.txt) → `file_id` + filename/mimetype/size for audiences | `--file` |

### Insights & analysis

| Command | What it does | Key flags |
|---|---|---|
| `insights` | Performance (impressions, clicks, spend, CTR, CPC, CPM) for account / campaign / ad group / ad | `--level`, `--object-id`, `--aggregation-level`, `--granularity hourly\|daily\|monthly\|none`, `--since`, `--until`, `--days`, `--timezone`, `--fields`, `--filter JSON` (repeatable), `--sort field:desc`, `--segment product\|country\|device\|platform`, `--segment-first`, `--include`, `--limit`, `--all` |
| `conversion-insights` | Attributed conversions (click-through + view-through); without `--ids` one total row for the account, with `--ids` / `--group-by-entity` one row per entity (without `--ids` it lists the non-archived objects of the level itself) | `--level`, `--ids`, `--group-by-entity`, `--granularity none\|daily`, `--breakdown device\|country`, `--include-zero`, `--since`, `--until`, `--days`, `--timezone` |
| `pulse` | Account digest: period vs. previous, spending limits (daily + windows), conversions (account total), ⚠ rejected / serving issues, ⚠ ad groups with `bid_too_low`, campaigns targeting outside the home country, ℹ waiting for review | `--days` |

### Targeting

| Command | What it does | Key flags |
|---|---|---|
| `geo-search` | Location search (country/region/DMA ids) | `--q`, `--country`, `--limit` |

### Custom audiences

Not available for targeting the EEA/Switzerland. Membership operations are asynchronous and require an `Idempotency-Key` (the CLI generates it).

| Command | What it does | Key flags |
|---|---|---|
| `audiences` | List / eligibility for a purpose | `--intended-use inclusion\|exclusion\|bid_multiplier`, `--ids`, `--granular`, `--all` |
| `audience-detail` | Status, count ranges, membership revision | `--audience-id`, `--granular` |
| `audience-create` [write] | From a file (`file-upload`) or empty | `--name`, `--file-id`, `--filename`, `--mimetype`, `--file-size`, `--identifier-type`, `--auto-resolve`, `--description` |
| `audience-add` / `audience-remove` [write] | Members inline or from a file | `--audience-id`, `--identifiers email:a@b.cz,…`, `--identifiers-file`, `--identifier-type`, `--file-id`, `--expected-revision` |
| `audience-replace` [write] | Replaces the whole membership from a file | `--audience-id`, `--file-id`, `--expected-revision` |
| `audience-merge` [write] | 2–64 audiences → a new one | `--name`, `--ids` |
| `audience-archive` [write] | Archive (permanent) | `--audience-id` |
| `audience-operation` | Poll an operation (suggests resume on `409 recovery_required`) | `--audience-id`, `--operation-id`, `--wait` |
| `audience-operations` | List retained audience operations (add/remove/replace/merge; pages via `next_cursor`) | `--audience-id`, `--limit` |
| `audience-operation-resume` [write] | Finishes an interrupted add/remove with the same id and input (no body or key) | `--audience-id`, `--operation-id` |
| `audience-operation-cancel` [write] | Cancels an add/remove before it starts applying (success = status `failed`; replace/merge cannot be cancelled) | `--audience-id`, `--operation-id` |

### Conversions

| Command | What it does | Key flags |
|---|---|---|
| `pixels` | Conversion sources (source id + pixel id) | |
| `conversion-check` | Measurement audit: pixel → event setting → link to the campaign (→ latest events) | `--events` |
| `pixel-create` [write] | New web pixel (gated per account) | `--name` |
| `capi-key-create` [write] | Conversions API key (shown once, server-side only) | `--name` |
| `event-settings` | Conversion definitions | `--all` |
| `event-setting-create` [write] | New definition (standard event or custom) | `--name`, `--event-type`, `--custom-event-name`, `--source-id`, `--attribution-window` |
| `conversion-events` | Pixel debug stream (last 15 min) | `--pid`, `--limit`, `--wide` |

### Product feeds

| Command | What it does | Key flags |
|---|---|---|
| `feeds` | List of feeds | `--with-counts` |
| `feed-create` / `feed-archive` [write] | Create / archive a feed | `--name`, `--countries` / `--feed-id` |
| `feed-uploads` | Latest catalog uploads + diagnostics | `--limit`, `--paginate` |
| `feed-products` | Product preview by filters | `--feed-id`, `--filter field:op:v`, `--limit`, `--after` |
| `feed-products-patch` [write] | Delta update of variant availability/price/title | `--feed-id`, `--products-json` or `--product-id` + `--variant-id` + `--available` / `--availability-status` / `--price` (minor units) + `--currency` / `--title` |
| `feed-sftp` | SFTP access to the feed | `--feed-id` |
| `feed-sftp-create` [write] | Creates / **rotates** SFTP credentials (password shown once) | `--feed-id`, `--auth-method password\|ssh_key`, `--ssh-public-key` |
| `feed-sftp-activate` / `feed-sftp-pause` [write] | Enable / pause SFTP | `--feed-id` |

### Lead forms and lead sync

OpenAI removed lead forms from the public spec in 2026-09: the `lead-form*` commands are **deprecated** (they print a notice on stderr and will be removed in 2.0; on self-serve accounts they returned 403). Lead sync remains in the spec.

| Command | What it does | Key flags |
|---|---|---|
| `lead-forms` / `lead-form-detail` | List / detail (incl. a specific revision) | `--all` / `--lead-form-id`, `--rev-id` |
| `lead-form-create` [write] | Form draft (3–5 text/choice fields) | `--name`, `--fields-json`, `--privacy-url` |
| `lead-form-update` [write] | New draft revision | `--lead-form-id`, `--fields-json`, `--name`, `--privacy-url`, `--expected-draft-revision-id` |
| `lead-form-publish` / `lead-form-archive` [write] | Publish / archive | `--lead-form-id` |
| `lead-form-test` [write] | Synthetic signed lead to the webhook | `--lead-form-id` |
| `lead-syncs` / `lead-sync-detail` | Webhook subscriptions | `--ad-account-id` / `--subscription-id` |
| `lead-sync-create` [write] | Lead delivery to an https webhook (signing secret shown once) | `--destination-url`, `--signing-secret` |
| `lead-sync-delete` [write] | Cancel a subscription | `--subscription-id` |

### Business Agents

**Deprecated**: the Business Agents endpoints disappeared from the public spec (2026-09; they returned 403 on self-serve). The commands stay for accounts where OpenAI enabled them and will be removed in 2.0.

| Command | What it does | Key flags |
|---|---|---|
| `business-agents` / `business-agent-detail` / `business-agent-tools` | List / detail / available tools | `--business-agent-id` |
| `business-agent-create` / `business-agent-update` [write] | Agent draft (update = full replace) | `--name`, `--instructions` / `--instructions-file`, `--description`, `--starter` (repeatable), `--feed-ids`, `--tools`, `--lead-form-id`, `--privacy-url` |
| `business-agent-preview` | Preview of the agent's reply | `--business-agent-id`, `--message user:…` (repeatable) |
| `business-agent-publish` [write] | Publish the draft | `--business-agent-id` |

### Bulk API (limited preview)

| Command | What it does | Key flags |
|---|---|---|
| `bulk-submit` [write] | Job from a JSON file; without `--confirm` = server-side validation | `--file ops.json`, `--no-partial-failure`, `--skip-validation`, `--wait` |
| `bulk-job` | Job status | `--job-id`, `--wait` |
| `bulk-operations` | Results of individual operations | `--job-id` |

404 = the account does not have the Bulk API enabled. Fields in bulk operations differ from REST (see [docs/api-notes.md](docs/api-notes.md#bulk-api-limited-preview-mimo-spec), Czech).

### Partner data & raw

| Command | What it does | Key flags |
|---|---|---|
| `partner-data-upload-create` [write] / `partner-data-upload` | Register / status of a partner-data upload (.parquet) | `--file`, `--snapshot-date` / `--upload-id` |
| `raw` [write for non-GET] | Any endpoint: `raw GET /campaigns --params '{"limit":5}'` | `method path`, `--params`, `--body`, `--confirm` |

## Skill for Claude Code (/chatgpt-ads)

The canonical version of the skill is in the repo: [skill/chatgpt-ads/SKILL.md](skill/chatgpt-ads/SKILL.md) (create / optimize / analyze / review-check / audiences / conversions / feeds / bulk scenarios + safety rules), [skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md](skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md) (prerequisites, context hints, copy, bids, measurement, market, billing, brief template) and [skill/chatgpt-ads/chatgpt-ads-policies.md](skill/chatgpt-ads/chatgpt-ads-policies.md) (Ad policies checklist). Installation: [skill/INSTALL.md](skill/INSTALL.md).

## Tests

Offline suite (no API calls, no credentials):

```bash
pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
python scripts/check_docs_consistency.py   # CLI ↔ README ↔ CLAUDE.md ↔ skill
```

## Documentation

- [docs/api-notes.md](docs/api-notes.md) (Czech): how the Advertiser API behaves (limits, states, review, money, insights, audiences, conversions, feeds, bulk, idempotency, errors) + a list of things to verify live
- [CLAUDE.md](CLAUDE.md): technical signpost for Claude Code (code structure, safety, release checklist)
- [CHANGELOG.md](CHANGELOG.md)
- Official sources: [developers.openai.com/ads](https://developers.openai.com/ads), [OpenAPI spec](https://developers.openai.com/ads/openapi.json), [Ad policies](https://openai.com/policies/ad-policies/)

## Bugs and ideas

GitHub Issues in this repo. For API errors, attach the output with `--json` (the key never ends up in the output) and the `x-request-id` if the CLI printed one.

## License

MIT, see [LICENSE](LICENSE).

## Author

[Jindřich Fáborský](https://www.faborsky.com), marketer and educator from Prague. I teach marketers to build their own tools with AI.
