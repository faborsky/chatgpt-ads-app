# ChatGPT Ads — campaign playbook (how the platform wants campaigns built)

Distilled from OpenAI's official Ads docs and Help Center (Ads in ChatGPT: The Basics, Create Campaigns / Ad Groups / Ads, Measurement Pixel, Conversions API, Product Feeds, Billing, Identity & Access — verified 2026-09-01/02) plus the first published practitioner data. Marked **(practice)** where the source is a real setup, not OpenAI. Use it to turn a project brief into a concrete, compliant setup: structure → context hints → copy → bids → measurement.

## 0. Prerequisites gate — nothing goes live until these hold

The channel is a *system integration*, not a media line. Check every layer before the first `--confirm`:

| # | Layer | What must be true | How to verify |
|---|---|---|---|
| 1 | **Account** | Brand review `approved` (name, URL, favicon ≥ 128×128), payment method added, right legal entity/country/currency (cannot be changed later) | `account` (review.status, currency_code, timezone) |
| 2 | **Spend fuse** | An active spend limit window covers the test period — or, where the endpoint answers 404 (self-serve accounts, 2026-09-02), a daily budget the user accepts at 2× plus a campaign end date | `spend-limits` → `spend-limit-create`, else `--daily-budget` + `--end` |
| 3 | **Crawlability** | Landing page returns a clean **200 to OAI-AdsBot** (mandatory; OAI-SearchBot recommended) — in `robots.txt` AND through WAF/CDN/anti-bot (Cloudflare, Akamai, captcha, JS challenge, geo blocks, rate limits). The crawler both reviews the page for policy and uses its content for relevance. | `landing-check --url …` (browser vs bot UA, robots, favicon) |
| 4 | **oppref survives** | OpenAI appends `?oppref=<click ref>` to the landing URL. www/https/locale/consent redirects and SPA routers must keep it, or the Pixel has nothing to store and click attribution is silently lost | `landing-check` (`oppref_survives`); walk the funnel manually with `?oppref=test123` |
| 5 | **Measurement** | Pixel (`oaiq("measure", …)`) and/or Conversions API deployed *before* the campaign, **even on CPC** (§5). Both → same event `id` for dedup (Pixel ID + event name + id; first delivery wins). CAPI must pass `oppref` itself; the Pixel stores it in the `__oppref` cookie automatically. Consent hook + CSP allow-list in place. Event setting **linked to the campaign** | `conversion-check --events`, `pixels`, `event-settings` |
| 6 | **Feed (e-shops)** | Google-compatible feed with `is_ads_eligible=true`; items expire after **14 days** → automated sync (SFTP/hosted URL), not a one-off upload; conversational attributes improve matching **(practice: Mergado)** | `feeds --with-counts`, `feed-uploads` |
| 7 | **Policy** | Category allowed for the advertiser's market (EU: consumer goods, local services, travel/experiences, digital products & education) — see `chatgpt-ads-policies.md` | manual |

Robots snippet to hand to the client:

```
User-agent: OAI-AdsBot
Allow: /

User-agent: OAI-SearchBot
Allow: /
```

## 1. Structure and goals

- **Check what Ads Manager generated for you first** (`campaign-detail --with-children`): the "Recommended" campaign it builds from your website defaults to **United States** targeting, `clicks` bidding with `maximize_clicks` (no bid), a daily budget and four generic hints. Fix locations (`--location-ids <country id from geo-search>`) before anything goes active.
- Hierarchy **campaign → ad group → ad**. Campaign = budget, schedule, locations, platforms (web / iOS / Android), goal. Ad group = context hints + bid (+ product set). Ad = title, body, image, landing URL.
- **One ad group = one product category / one intent.** Different products or different user situations → different ad groups. Never mix.
- Goals: `impressions` (CPM, awareness), `clicks` (CPC, traffic and first tests), `conversions` (oCPC — pays per click, optimizes toward one standard conversion event; only once measurement is live). **The goal cannot be changed after creation**; budget type changes only one way. Wrong choice = new campaign.
- Start new advertisers on **CPC with a daily budget**, not CPM and not lifetime **(practice + OpenAI onboarding)**.
- **Budget lives only on the campaign; ad groups share it.** With the 15 €/25 $ daily minimum, "more situations" means **more ad groups inside one campaign**, not more campaigns. One campaign per market/goal, 3–8 ad groups per campaign is the normal shape.
- **Verify writes with `*-detail`, not lists** — lists lag a few seconds after an update (verified live).
- Everything is created `paused`; activate bottom-up (ad → ad group → campaign) only after `ad-review` shows approved.

## 2. Context hints — the only targeting lever, and OpenAI describes it three ways

There are no keywords, no demographics, no interest audiences. An ad group carries **context hints**; the system infers fit with the *current conversation thread* (in the EEA/CH exclusively the thread — no history, no memory, no personalization yet). What a hint *is* OpenAI phrases differently in two help articles — treat that as licence to test, not as a contradiction:

| Source (help.openai.com, verified 2026-09-03) | Wording | Reading |
|---|---|---|
| *Create Ad Groups for ChatGPT Ads* (20001211) | "Context hints that **describe what your product offers, who it helps, or when it may be useful**" · "ask yourself: **What** else should we know about this product, **who** it helps, and **when** it's useful?" | **P — product description**: the official example is `cushioned everyday running shoes for beginners training for their first 5K` |
| same article | "Stay focused on the **product, theme, or intent** of the ad group" · "**Define relevant conversation types** for the ad group" · "clarify the types of conversations, needs, and topics your ad group is designed to support" | **S / C — situation or conversation**: the need the person has, or the question they are asking |
| *Ads in ChatGPT: The Basics* (20001207) | "context hints that **describe the conversations, topics, or keywords** where their products or services may be relevant" | **K — topics / keywords**: terse terms are explicitly allowed |

Rules OpenAI states that hold for **every** style: one product category / theme / intent per ad group (different messaging or landing page → separate ad group); a hint must add information beyond title, body and landing page; describe needs or situations rather than broad audience labels; clear natural phrases rather than disconnected terms; only genuine use cases; cover the different ways people describe the same problem; hints are **not exact match** and never guarantee delivery; several ads per ad group.

### The four hint styles (same intent, different register)

| Style | Example (course for marketers) | When |
|---|---|---|
| **P** product description | `praktický kurz vibe codingu pro marketéra, který si chce postavit vlastní appku a nikdy neprogramoval` | The official example. Safe default. |
| **S** situation / need | `marketér chce automatizovat reporting a nemá vývojáře` | Closest to "who it helps, when it's useful". |
| **C** conversation / question | `ptá se, jestli se dá naučit stavět appky s AI bez programování` | Mirrors what the user actually types; the first Czech pilots ran on this style. |
| **K** topics / keywords | `kurz AI`, `vibe coding`, `Claude Code kurz` | The *Basics* wording; the one public A/B (MarTech) saw keyword-style beat full questions on impressions, CTR and CPC. |

| Bad | Good |
|---|---|
| `running shoes` (disconnected term used *alone*) | `cushioned everyday running shoes for beginners training for their first 5 km race` |
| `AI course` | `hands-on course for a marketer who wants to build their own small apps and has never programmed` |

### Decide the route WITH the user — and prefer testing routes against each other

Nobody has enough data yet to call one style "correct". The skill therefore asks, it does not assume:

1. **One route** — the user picks a primary style (default recommendation: **P + S mixed**, i.e. the official example register) and every ad group uses it.
2. **Head-to-head test (recommended for a first campaign)** — same intent, **same ads**, one ad group per style (`P`, `C`, `K`; add `S` if budget allows), each with its own `utm_content`; nothing else differs. Read impressions/CTR/CPC per ad group in `insights --aggregation-level ad_group` and engagement/conversions per `utm_content` in analytics after ≥ 1 week (≥ 100 clicks per group before judging). Budget is shared at campaign level, so the test costs no extra money, only clicks split three ways.
3. **Control group always** — whichever route is primary, keep one keyword-style (`K`) group with identical ads. It is the cheapest sanity check on the whole mechanism.

Write it down in the campaign record which style each ad group uses, so results can be attributed to the style and not to the copy.

### Where to mine situations and phrasings

Search-term reports from Google Ads / Sklik, Search Console queries, keyword research clusters, on-site search and FAQ, support and sales questions, competitor landing pages, the landing page itself (its H2s are the product's own "when it's useful" list). Working recipe: list 8–15 **situations** in which a person benefits (task, decision, question they would type), write each in the chosen style (10–25 words for P/S/C, 1–4 words for K), add 3–5 phrasings per situation with different vocabulary, keep 20–60 hints per ad group (limit 2 000).

**Control ad group naming**: make the style visible in the ad group name (e.g. `G · kontrolní (K – klíčovky)`, `A · situace (C – otázky)`), give it the **same ads** so only the hints differ, and its own `utm_content`.

Account-level **negative keywords** exist in the spec but were not deployed on self-serve accounts (404, 2026-09-02) — until they are, the only way to avoid a context is to not describe it. There is **no report of the prompts/topics that triggered an impression**; optimisation is by hint variants and outcome metrics only.

## 3. Ad copy and creative

- Seven elements: advertiser name, favicon, Sponsored/Ad label, **headline (~16 chars recommended, max 50)**, **description (~32 chars recommended, max 100)**, image, landing page. Text is truncated in some placements — write to 16/32, not to the maximum.
- Register: concrete benefit, no slogan, no superlatives, no "guaranteed", no ChatGPT/OpenAI mentions. `Fresh meal kits, delivered for less` is the reference tone.
- Image: renders as a **small square thumbnail (~64 px) next to the text** — so **no text in the image, no logo as the primary visual**, one recognisable object/scene. 1200×1200 PNG (1.3 MB) uploads fine; one `file_id` can back all ads of a campaign.
- **Volume and variety**: several ads per ad group, each with a *different argument* (price, speed, outcome, social proof…), not paraphrases. Ads Manager can also auto-suggest variants from site metadata — review before publishing.
- Landing page: a public page consistent with the ad (course page, not the order form; an order/checkout path is often `Disallow`ed in robots and fails review). No reserved query params (`oai*`, `oppref`, `obref`).

## 4. Bids and budgets

- Second-price auction weighted by relevance — the highest bid does not simply win.
- Recommended max CPC **$3–5** (below $3 Ads Manager warns you will get few impressions) **(Help Center)**. The API does **not** enforce a minimum (1 € was accepted) — if you start below the recommendation, check impressions after 48 h and raise before judging the channel. Bids are per event in micros: `--max-bid 4` = 4 USD per click; CPM via `--max-cpm`.
- Minimum daily budget: **25 USD** (US table); **15 € on a EUR account (practice, first Czech setup)**. Daily spend can reach **2× the daily budget** on a given day; the weekly total holds.
- "Maximize results" automatic bidding exists in Ads Manager (API `strategy: maximize_clicks | maximize_conversions`) — feature availability is per account.
- Budget is a campaign object replaced as a whole; the spend limit window is the account-level cap.

## 5. Measurement details that bite

**Measure conversions even on CPC.** Buying model and measurement are unrelated: without a conversion event you compare CPC across channels (meaningless), you can never move to oCPC (it needs conversion data — and since the goal is immutable that means a *new* campaign, so measure from day one), and nobody processes `oppref` (the Pixel captures it into a cookie; without the Pixel your own analytics only has UTMs). The one public test looked fine on CTR and had 0.21 % CVR.

**Setup order (Ads Manager → Tools → Conversions, or API):** 1) data source = pixel (`pixel-create`) → 2) conversion event = event setting (`event-setting-create`) → 3) implement on the site (pixel snippet / CAPI) → 4) **link the event to the campaign** (`campaign-create/update --conversion-event-setting-id`). Step 4 is the one people forget: the event then collects data the campaign never sees. `conversion-check` audits all four; `pulse` warns about active campaigns with no linked event.

**UTM convention** (the API appends its own `oppref`; UTMs are yours): put `utm_source=chatgpt&utm_medium=cpc&utm_campaign=<slug>` on the campaign `query_string_template` and **`utm_content=<ad-group-key>` on each ad group** (ad group = targeting variant, verified to persist). GA4 files this under *Paid Other* unless you map the source. Precedence campaign vs ad group template is not yet verified — keep the campaign one generic.

**Pixel implementation gotchas (not in the Ads Manager help):**
- The Pixel is injected client-side (GTM etc.) — `curl`/HTML checks won't see it; verify with `conversion-events --pid …` (the debug stream shows `contents[0].id` with the full landing query incl. `oppref`).
- **Consent**: the Pixel starts with consent = true. With a cookie bar call `oaiq("consent", false)` *before* `oaiq("init", …)` and `oaiq("consent", true)` after the user agrees. Blocked events are not replayed.
- **CSP**: allow `bzrcdn.openai.com` (script-src, connect-src) and `bzr.openai.com` (connect-src, img-src). Do not add `'unsafe-inline'` for it — use a nonce or hash.

- Standard events: order_created, lead_created, registration_completed, checkout_started, trial_started, subscription_created, page_viewed, contents_viewed, items_added, appointment_scheduled (+ app_installed/app_opened via CAPI only). Custom events measure but cannot be oCPC goals.
- **Dedup**: browser + server sending the same conversion → same event `id`; OpenAI keeps the first delivery.
- **oppref** (click reference in the landing URL) — Pixel captures it; CAPI does not ("the API does not capture oppref for you"). `obref` lives inside `user` and is consent-dependent.
- View-through conversions (1-day window) are reporting-only; CPA, CVR, bidding and billing stay click-based. `conversions == click_through_conversions`.
- Attribution for the current account-local day is preliminary — report windows ending yesterday.

## 6. Market realities (especially EU / Czech)

- Ads are shown only to **Free and Go** users, never on Plus/Pro/Business/Enterprise/Edu, under-18 accounts, Temporary Chat or the Atlas browser; never next to sensitive topics (health, mental health, politics…). B2B decision-makers on paid plans are largely unreachable.
- **EEA/Switzerland: no personalization** (context of the current thread only) and **no custom audiences** for EEA-targeted campaigns. US case studies and benchmarks do not transfer.
- Custom audiences elsewhere: inclusion needs ≥ 25 000 matched users (100 000 recommended); exclusion works with small lists.
- Early public data is thin and unflattering: one A/B (MarTech, ~1 500 users) saw **0.21 % CVR vs 3.71 % on Google Ads** and 17 s vs 41 s engagement; ads appeared on ~26 % of commercial prompts in the US (SE Ranking). Treat the channel as an **experiment with its own budget**, evaluated on cost per acquired customer, not CTR.
- Practitioners report beta friction: charges without visible impressions, campaigns stuck in "Not serving", weak topical matching. Features roll out per account week by week (weekly product e-mail) — two advertisers may not see the same options.

## 7. Billing, accounts, roles

- **Postpay with a payment threshold**: the card is charged whenever unpaid spend hits the threshold (grows with payment history; not editable), remainder at month end. Failed payment → campaigns stop, status *Not serving*. Ads can keep serving up to **24 h after pausing** and that spend is billable.
- **One legal entity + billing country + currency = one ad account**, fixed at creation. Several companies/clients → several accounts under one tenant (Admin Console manages users, groups, SSO; roles are assigned per account: admin / member / viewer; ChatGPT workspace roles grant nothing in Ads).
- Agencies: get a role inside the client's own account (client keeps billing). Creating accounts on behalf of clients is discouraged; the programmatic path (`/ad_account_creation_sessions`) is for approved API partners only.
- API keys are scoped to one account; `accounts` lists what a key can see; always confirm `account` (name, currency, timezone) before writing.
- **Trap: "You don't have permission to create ad accounts in your tenant"** — creating ad accounts is a *tenant-level* right (Ads admin / global admin), not inherited from being admin of an existing ad account, and a personal account (Free/Plus/Pro, plain Gmail) has no Admin Console at all (Enterprise/Edu only). Buying Plus/Pro does not help; "Available" in the country table means the country is eligible, not that every account passes. Documented route: ads-support@openai.com. **Route that worked (practice, 2026-09-02):** a colleague creates a *company* e-mail address, onboards on ads.openai.com, creates the ad account with the company's billing address and card, then invites the person who will run campaigns; they accept the *Pending invitation* with their own (even personal) login. The Create-account button stays greyed for them — the invitation is the only door.

## 8. Brief → setup template

The fastest way from brief to account is **one plan file** → `plan-apply --file plan.json` (dry-run prints the whole tree with copy lengths) → `--confirm` (sequential, idempotent, resumable via `plan.state.json`). Template: `docs/plan-example.json` in the app repo.

```
Project: <name>            Market: <countries>      Currency (account): <…>
Goal: clicks (CPC) | conversions (oCPC on <event>) | impressions (CPM)
Budget: daily <…> (min 15 €/25 $)   Spend cap window: <from> → <to (excl.)> <amount>
Landing: <public URL> (landing-check ✅, oppref ✅, OAI-AdsBot ✅)
Measurement: pixel <id> / CAPI key ✅ / event setting <ces_…> (dedup by event id) → LINKED to every campaign ✅
Site: consent hook before init ✅   CSP allows bzrcdn.openai.com + bzr.openai.com ✅

Campaign query_string_template: utm_source=chatgpt&utm_medium=cpc&utm_campaign=<slug>
Ad group A — <intent 1>    bid: <…>/click   utm_content=A-<slug>
  hints (situations, 20–60): …
  ads (3–5 angles): title ≤16 | body ≤32 | image (no text, no logo) | URL
Ad group B — <intent 2> …  utm_content=B-<slug>
Ad group G — control (keyword-style hints, SAME ads) …  utm_content=G-control
Negative keywords (account): …
Evaluation: CAC vs other channels after ≥ 2 weeks; weekly review of ad-review + pulse.
```
