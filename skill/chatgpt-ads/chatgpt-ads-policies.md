# OpenAI Ad Policies — operator checklist

Source: https://openai.com/policies/ad-policies/ (v1.5, updated 2026-08-31) and the Ad Tools Terms. This is a working summary for preflight — the policy page wins on conflicts; re-read it when a review reason surprises you.

## 1. Is the category allowed at all?

**Allowed today (initial phase):** household & consumer goods, local services, travel & experiences/entertainment, digital products, education. Categories expand over time.

**Restricted — approved advertisers, US only, case-by-case:** financial services (cards, loans, insurance, investing, mortgages, payments; NOT credit repair, debt settlement, bullion), health services (devices, dental, supplements, health insurance, hospitals, diagnostics, minimally invasive cosmetic, vision), legal services (licensed in the jurisdiction). Outside the US these are **prohibited** → for a Czech advertiser: do not attempt.

**Disallowed:** adult/dating/sexual (lingerie in retail context OK), alcohol (> 0.5 % ABV) & tobacco/vaping, counterfeit goods, gambling (casino hotel stays without gambling focus OK; games without real-money prizes OK), graphic sexual or violent content, individual **job listings and housing rentals/sales** (platforms OK if no specific listing), political content (elections, policy, contested social issues), recreational drugs incl. THC (non-intoxicating hemp/CBD topicals OK), scams/fraud/impersonation, sensitive topics/tragedies, weapons, unsubstantiated wellness claims (diet pills, detox, health coaching).

**Advertiser eligibility:** a business whose *primary* model is in a restricted/prohibited category may be ineligible even for a compliant ad.

## 2. Baseline standards (apply to every ad, any category)

- **Truthful, not misleading**: no unfounded claims about capabilities, pricing, outcomes, affiliations or comparisons; no exaggerated results, false endorsements, "guaranteed", "#1", "risk-free".
- **Professional language**: no obscenity, vulgarity, shock — even in product/event names.
- **No discrimination/harassment**: nothing derogatory toward protected groups.
- **No interface imitation**: the ad must not look, function or sound like ChatGPT/OpenAI, nor imply endorsement ("official ChatGPT partner").
- **End-to-end consistency**: creative, image AND landing page are reviewed together; an approved creative may not lead to disallowed content (food delivery → alcohol delivery = rejection).
- OpenAI may refuse any ad or link for any reason.

## 3. Advertiser policies

- Accurate business identity, ownership, affiliations; only your own/licensed trademarks and brand assets.
- **Destination integrity**: landing page clearly relates to the advertiser and the offer; no deceptive redirects, typosquats, unverified messaging channels.
- No circumventing review/enforcement; keep required licences; comply with law in every targeted region; don't misrepresent location or service area.

## 4. What the reviewer actually does

Automated LLM + classifier review of **title, body, image and landing page** (human escalation for risk/severity). Typically minutes. Ads whose landing page cannot be crawled are ineligible → the crawler must get a 200 HTML page without login/captcha, `robots.txt` must not block it, and the site needs a favicon (account favicon ≥ 128×128). Continuous monitoring after approval: delivery can be limited or the ad removed later; repeat violations → account suspension.

## 5. Placement (what you cannot control, but should expect)

Ads never show next to sensitive conversations (mental/personal health, emotional reliance, sensitive journeys) or brand-unsafe topics (child safety, violence, hate, politics, regulated goods, weapons, …). Context hints and negative keywords steer *when* an ad is useful, not around these blocks. Advertisers never see user chats.

## 6. Preflight checklist for the operator

1. Category allowed for the advertiser's country? (EU advertiser → consumer goods, local services, travel, digital products, education only.)
2. Title ≤ 50 / body ≤ 100 chars, plain professional tone, no superlatives or guarantees, no "ChatGPT/OpenAI" in copy, no emoji/CAPS/!!!.
3. Image: own/licensed asset, no sexualised or violent content, square-friendly (chat_card supports a square crop), text in the image legible and consistent with the copy.
4. Landing page: `landing-check` passes (200, HTML, robots OK, favicon), page content matches the ad and contains nothing from a disallowed category, no reserved query params (`oai*`, `oppref`, `obref`).
5. Audiences: first-party data only, consent/legal basis in place, never for EEA/CH targeting.
6. Conversions: pixel/CAPI on pages you own; CAPI key server-side only.
7. Everything created paused; activation after `ad-review` shows approved and the user says go.

## Changelog of the policy (for awareness)

v1.5 Aug 2026 legal services US · v1.4 Aug 2026 housing/jobs listings clarified · v1.3 Jul 2026 advertiser policies + finance/health markets · v1.2 May 2026 integrity section · v1.1 Apr 2026 regulated-advice contexts no longer blanket-blocked · v1.0 Mar 2026 initial.
