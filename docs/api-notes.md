# OpenAI Advertiser API — poznámky k reálnému chování

Jak se API chová podle oficiální dokumentace (developers.openai.com/ads, OpenAPI spec 2.3.0, research 2026-09-02, znovu srovnáno 2026-09-24). Položky označené **(živě)** jsou ověřené na reálném účtu; ostatní vychází ze spec/docs. Sekce „Neověřeno živě" na konci = co si ověřit v první live session.

## Základ

- Base URL `https://api.ads.openai.com/v1`, JSON in/out, `Authorization: Bearer <OPENAI_ADS_API_KEY>`.
- **Klíč vydává Ads Manager (ads.openai.com → Settings → API keys) a je scoped na JEDEN ad account.** Víc účtů = víc klíčů (`OPENAI_ADS_API_KEY_<NAME>` + `--account`). `POST /api_keys` umí vyrobit další klíč pro tentýž účet (rotace).
- Spec zná i OAuth (`auth.openai.com`, scopes `ads.admin.all.read/write`, `offline_access`) s hlavičkou `OpenAI-Ad-Account` pro výběr účtu — to je partnerská cesta (agentury). S API klíčem hlavičku **neposílat** (docs u Bulk API to říkají explicitně).
- Update je vždy **POST na `/resource/{id}`** (žádný PUT/PATCH) — jediný PATCH v celém API je `PATCH /feeds/{id}/products` (delta feed).
- Verze API nemá datum ani header — spec `info.version` 2.3.0; changelog v docs (api-overview.md) je jediný signál změn. Kontrolovat občas: https://developers.openai.com/ads/api-overview#changelog. **Pozor: OpenAI mění obsah spec bez změny čísla verze** (2026-09-24: pořád „2.3.0“, ale 78 operací místo 88). Změnu proto hledej diffem operací a schémat (spec vs. cesty v `oaiads/`) a přečtením `https://developers.openai.com/ads/llms-full.txt` (celé docs v jednom souboru), ne podle čísla verze.

## Změny API 2026-09 (srovnání 2026-09-24)

Oproti researchi 2026-09-02. Zdroj: changelog, diff spec, celé docs, živé čtení na dvou self-serve účtech (EUR).

**Nové v API**
- **2026-09-09 — denní limit útraty účtu**: `POST /ad_account/daily_spend_limit` (`amount_micros`, `expected_revision` povinné; `start_date` jen u nového limitu, nejdřív zítra; `end_date` exkluzivní, `null` = bez konce) a `POST /ad_account/daily_spend_limit/delete` (`expected_revision`). `GET /ad_account/spend_limit_windows` teď vrací objekt `{data: [date-range okna], daily_limit, revision, earliest_daily_start_date, earliest_dated_start_date, can_create_daily_limit, evaluated_at}`; `daily_limit` nese `spent_micros`, `remaining_micros`, `spend_as_of`, `next_reset`. Stavy oken `upcoming|active|completed`, max 60 budoucích oken, okna se nesmí překrývat (ani s denním limitem). Chyby: 409 = zastaralá revize, 422 `budget_window_amount_below_spend`, **503 = změna možná prošla, nejdřív znovu načíst**. Limity platí jen pro účty **na fakturu (postpaid invoice)** a všechna volání (i čtení) chtějí **právo spravovat billing**. **(živě)** self-serve API klíč: `403 "Only ad account admins can perform this action."` (dřív 404 `Invalid URL`).
- **2026-09-10 — granulární web platformy**: `targeting.platforms.included` bere `desktop_web`, `ios_web`, `android_web` vedle `web` (= všechny weby, zůstává), `ios_app`, `android_app`. Update: vynechané `platforms` = beze změny, `platforms: null` = zruší jen omezení platforem, `{}` nebo `included: []` = 400. **Update jen s platformami zachová lokace i audiences.** Insights: `segments[]=platform` + `fields[]=platform`; historické řádky `web` se zpětně nerozpadají; filtr `platform IN ["web"]` zahrne všechny weby; per platformu nejsou konverze. **(živě)** segment funguje, metriky jako ploché klíče `clicks`/`spend`/`impressions`.
- **Audience operace** (ve spec nově): `GET /custom_audiences/{id}/operations` (`limit` 1–100, stránkování přes `next_cursor` → `cursor`, pokračovat dokud `has_more`, i přes prázdnou stránku), `POST …/operations/{op}/resume` (jen add/remove; bez těla a bez klíče; na `409 custom_audience_operation_recovery_required`), `POST …/operations/{op}/cancel` (jen add/remove, jen než se začne aplikovat; úspěch = `status: failed`, stav `canceled` neexistuje; `409 custom_audience_mutation_conflict` = už běží nebo hotovo; `503` = zopakovat cancel stejného id).
- **`include[]=bid_too_low`** na ad group (docs, ve spec enum chybí): `bid_too_low: true` = bid je nejspíš moc nízký na spolehlivé doručování. Je to jen doporučení, doručování neblokuje. Nehlásí se u neaktivních sestav a 24 h po úpravě sestavy (úprava reklamy okno neresetuje), takže jeho absence nedokazuje konkurenceschopný bid. **(živě)** funguje na detailu i na `GET /ad_groups`.
- `GET /ad_account` vrací nově **`origin_country_code`** (živě). `GET /conversions/events` bere `limit`. Reporting: `product.carousel_product_card_impressions/clicks`, `order_created_attributed_sales_currency`.
- Conversions API (`bzr.openai.com`, mimo Advertiser API, CLI ho neposílá): `integration_source` (partnerský identifikátor 1–64 znaků), `validate_only`, `action_source` i `offline|physical_store|phone_call|email|other`, `opt_out`, `user` s `first/last_names_sha256`, `regions`, `android_advertising_id` (GAID; IDFA ne), max 1 000 eventů v dávce (chyba jednoho = celá dávka), `timestamp_ms` max 7 dní zpět. Nový **image tag** (`<img src="https://bzr.openai.com/v1/sdk/events?pid=…&event=…&data[type]=…">`, bez JS, bez `user`), **více pixelů** na stránce (`oaiq("measureSingle", pixelId, …)`), cookies `__oppref` 30 dní / `__obref` 365 dní, `oaiq("consent", false)` obě smaže.

**Nově zdokumentované chování (dřív neověřené)**
- **UTM šablony se sčítají**: `landing_page_configuration.query_string_template` na účtu, kampani, sestavě i reklamě se kombinuje; u duplicitního klíče platí priorita **cílová URL > reklama > sestava > kampaň > účet**. Makra `{campaign_id}`, `{ad_id}`, `{oppref}` (příklad `click_id={oppref}`). Tím padá dřívější obava „sestavová šablona nahradí kampaňovou celou“.
- **Maximize Results**: `maximize_clicks` jen v kampani `clicks`, `maximize_conversions` jen v `conversions`; obě `billing_event_type: click`, **denní** budget kampaně, **bez** `max_bid_micros`, bez audience multiplikátorů; `Idempotency-Key` při create povinný. Přepnutí zpět na `fixed_bid` = explicitní bid; multiplikátory se musí poslat znovu. Dostupnost Maximize u produktových kampaní závisí na účtu.
- **Budget**: právě jeden z `daily_spend_limit_micros` / `lifetime_spend_limit_micros`. Celkový → denní jde, denní → celkový ne (nová kampaň). Snížení denního budgetu pod efektivní bid sestavy API může odmítnout; minima denního budgetu závisí na měně (chyba řekne částku).
- Produktové kampaně: geo cílení i vyloučení jen na úrovni **zemí**; filtry product setu i přes `ads_metadata.<klíč>` (vlastní štítky, např. `custom_label_0`); template makro `{{brand}}`; feed nejde archivovat, dokud je navázaný na nearchivovanou kampaň/sestavu. oCPC u produktových kampaní v open beta.
- Retence reportingu: hodinová ~30 dní, produktová ~30 dní, ostatní 365 dní; `POST /conversions/insights` daily max 365 dní. Spend/CPC/CPM se finalizují později než imprese/kliky; konverze denním zpracováním (počkat aspoň den).
- Favicon účtu: `POST /upload` s `purpose: account_favicon` umí i URL webu (API si ikonu najde); min. 128×128 (Files) vs. 256×256 (Account Management) — docs si odporují, bezpečně 256.
- Bulk API: `ad_group.create/update` znají `exclusion_hints` (jen v bulku, REST je nemá); `max_cpm_bid_micros` jen s přístupem pro účet; `ad.update` s kreativou chce `title`, `body`, `target_url` i `file_id`.

**Zmizelo z veřejné spec** (endpointy, CLI příkazy deprecated, odchod ve 2.0): `/ad_account/negative_keywords` (4 operace), `/lead_forms*` (7), `/business_agents*` + `/business_agent_tools` (7). Na self-serve nikdy nefungovaly (404 / 403). `mode: business_agent` a `business_agent_id` na kampani ve spec zůstaly. Lead sync (`/lead_sync_subscriptions*`) zůstal.

**Nové serving kódy (živě)**: `campaign_ended` (reklamy kampaně po `end_time`, očekávaný stav), `review_not_approved` (doprovází `review_status: rejected`).

## Rate limity

- **600 req/min na endpoint, 1 200 req/min celkem — platí per ad account I per IP adresa** (obojí musí sedět). Bulk job creates zvlášť **10 / 10 s / účet**.
- API **nevrací usage** (žádná hlavička s procenty). CLI si vede vlastní klouzavé okno 60 s v `.usage/ratelimit_<account>.json` (per rodina endpointu, ids kolabují na `{id}`) a od 80 % limitu čeká. `api-limits` ukáže stav. Override `OAIADS_IGNORE_RATE_BUDGET=1`.
- 429 = odmítnutí (nic se nezapsalo) → CLI retryuje pro všechny metody (5/15/60 s), ctí `Retry-After` do 120 s.

## Struktura objektů a stavy

- Hierarchie **Campaign → Ad group → Ad**. Kampaň drží budget, časování a targeting; ad group bidding + context hints (+ product set); ad drží kreativu.
- Stavy `active` / `paused` / `archived` (create jen active|paused). Přechody: `POST …/activate|pause|archive` nebo `status` v update. **Archive je nevratný a neexistuje delete** (kromě spend limit window a lead-sync subscription).
- Ad doručuje jen když **ad, ad group i kampaň jsou active**, `review_status == approved`, účet má **schválený brand review** (typicky chybí favicon → `missing_favicon`) a platební metodu. Kódy proč nedoručuje: `serving_issues[].code` na campaign/ad group/ad (`include[]=serving_issues`), např. `ad_account_brand_review_missing_favicon`, `campaign_budget_exhausted`, `landing_page_crawl_issue`, `policy_country_targeting_blocked`, `reserved_query_params_present`, `ad_over_18_only`. **Očekávané stavy, ne závady** (viděno živě): `campaign_not_active`, `ad_group_not_active`, `ad_not_active`, `campaign_not_started` (něco v hierarchii je pozastavené — CLI vše zakládá paused) a `ad_in_review` (minuty po create/update). `ad-review` i `pulse` je z problémů vyřazují.
- Limity per účet (self-serve): 5 000 nearchivovaných kampaní, 5 000 ad groups, 5 000 active+paused ads.
- Listy mají server-side filtr jen `name` (min 3 znaky) a řazení `order`; **status filtr neexistuje** → CLI filtruje lokálně po načtení všeho (cursor `after` = `last_id`, `has_more`, `limit` ≤ 500).

## Review reklam

- Review je automatické (LLM + klasifikátory, lidská eskalace), typicky **minuty**. `review_status`: `in_review` → `approved` | `rejected`; `review.reason` u zamítnutí, `review.screenshot_url` = co reviewer viděl.
- Důvody v spec: crawler_* (403/404/429/5xx), `crawl_failed`, `crawler_bot_blocked`, `crawler_captcha`, `crawler_login_required`, `robots_txt`, `unsupported_content_type`, `landing_page_image_processing_failed`, `landing_page_unusable`, `missing_favicon` — **většina zamítnutí je o landing page, ne o textu**. `landing-check` to testuje lokálně.
- **Každá změna kreativy spustí re-review** (ad může přestat doručovat). Změna názvu/stavu ne.
- `appeal` objekt na ad (`requested/approved/rejected/superseded/failed`) — spec nemá endpoint na podání appealu; jde přes Ads Manager.
- Policy (openai.com/policies/ad-policies, v1.5 2026-08-31): povolené kategorie jsou zatím **spotřební zboží, lokální služby, cestování/zážitky, digitální produkty a vzdělávání**; finance/zdraví/právo jen schválení inzerenti v USA; zakázáno: alkohol/tabák, gambling, dating/adult, drogy, politika, zbraně, jednotlivé job/housing inzeráty, superlativy a „guaranteed" claimy, imitace rozhraní ChatGPT. Detailní checklist: `skill/chatgpt-ads/chatgpt-ads-policies.md`.

## Peníze a bidování

- Vše v **micros** (1 000 000 = 1 jednotka měny účtu, `currency_code` z `GET /ad_account`). Budget min. `1000000`. Limity útraty účtu `amount_micros` min 0, max 10^15 (1 mld. jednotek), násobky nejmenší jednotky měny (USD: 10 000 micros).
- `bidding_type` kampaně: `impressions` (CPM, default) / `clicks` (CPC) / `conversions` (oCPC, platí se za klik, optimalizuje na 1 standardní event). **Po vytvoření neměnné** (ani `mode`, ani event setting u oCPC).
- Ad group `bidding_config.billing_event_type` musí odpovídat: `impression` pro impressions kampaň, `click` pro clicks/conversions. `max_bid_micros` je **per event**: $60 CPM = 60 000 micros per impression; u oCPC je to **CPA bid** (100 000 000 = $100 CPA). `strategy`: `fixed_bid` | `maximize_clicks` | `maximize_conversions` (ve spec, v docs nezmíněno — ověřit).
- Spec zná i `objective` (`reach|clicks|conversions`) a `billing_event_type` na kampani — docs je nepoužívají; CLI je posílá jen když je zadáš.
- `budget` na update = **celý objekt**; právě jeden typ (daily NEBO lifetime), lifetime → daily jde, zpět ne (docs 2026-09).

## Čas a timezone

- `start_time`/`end_time` unix sekundy (2000–2100). Bez `start_time` kampaň běží hned.
- Účet má `timezone` (IANA) — insights `date_range`/`hour_range` bez `timezone` používají účet. Dnešní atribuční čísla jsou předběžná; **bounds nesmí být v budoucnu** (do 5 let zpět) → CLI defaultně končí včerejškem.

## Insights

- 4 scope endpointy (`/ad_account/insights`, `/campaigns/{id}/insights`, `/ad_groups/{id}/insights`, `/ads/{id}/insights`) + `aggregation_level` (`ad_account|campaign|ad_group|ad`, jen na úrovni scope nebo níž). `time_granularity` `hourly|daily|monthly|none`.
- Query pole jsou arrays: `fields[]`, `time_ranges[]`, `filters[]`, `sort[]`, `segments[]`, `includes[]`, `override_segment_group_order[]` (docs používají `[]` sufix — CLI taky, konstanta `ARRAY_SUFFIX`).
- `time_ranges[]` = JSON string: `{"type":"date_range","since":"2026-08-01","until":"2026-08-07","timezone":"Europe/Prague"}` (until inkluzivní) | `unix_range` | `hour_range`.
- **Kanonická jména polí vs. wire klíče**: požádáš `campaign.spend`, dostaneš `spend` (příklady) nebo `campaign_spend` (schema `InsightItemBody` má obě varianty). CLI čte obě (`metric()`).
- Metriky: impressions, clicks, spend, ctr, cpc, cpm; metadata `campaign.name/status/start_time/end_time/budget.*`, `ad.title/copy/link/name/status/review_status`. Atribuční pole: `order_created_attributed_sales`, `order_created_roas`, `cpa`, `post_click_cvr` (stará `attributed_sales_*`/`roas` deprecated, odstranění 2026-08-17).
- `limit` 1–2000 (default 20), cursor `after`/`before`. `filters[]` operátory `IN|GREATER_THAN|LESS_THAN`. Segmenty `product|country|device` (jen zapnuté účty, granularita none/daily/monthly). `includes[]=zero_impression_items` (bez segmentu) nebo `zero_impression_products` (segment product first).
- **Konverze**: `POST /conversions/insights` (`aggregation_level`, `time_ranges`, `entity_ids`, `time_granularity none|daily`, `breakdown device|country`, `group_by_entity`). `conversions == click_through_conversions`; view-through je zvlášť (1-day okno, jen reporting). **Ověřeno živě 2026-09-07:** `group_by_entity` má na serveru default **true** a pak je `entity_ids` povinné (jinak 400 `entity_ids must be provided when group_by_entity is true`); `group_by_entity: false` vrátí **jeden** řádek s `entity_id` = ad account (součet); `entity_ids` = seznam id kampaní + `group_by_entity: true` → řádek per kampaň. `time_ranges` musí být pole **JSON stringů** (objekt → 400 `invalid_type`).

## Targeting

- `targeting.locations.countries` (ISO) a/nebo `targeting.locations.include[{id}]` (max 2 500 ids z `GET /geo_lookup/search` — typy country/region/DMA; CSV katalog developers.openai.com/ads/openai-geotargets.csv). Spec zná i `excluded_locations`. Bez targetingu = všechny dostupné lokality.
- `platforms.included` `web|desktop_web|ios_web|android_web|ios_app|android_app` (granulární weby od 2026-09-10; `web` = všechny). Update jen platforem zachová zbytek targetingu; `null` zruší jen platformy.
- `custom_audiences.ids` / `excluded_custom_audiences.ids` — **nefunguje pro EEA/Švýcarsko** (personalizované reklamy tam zatím nejsou). Pro CZ inzerenta tedy audiences zatím jen mimo EU.
- Update targetingu = celý objekt; `null` ho smaže. CLI si načte současný, ořeže expandovaná location metadata na `{id}` a mergne flagy.
- ~~Negativní klíčová slova na úrovni účtu~~ (`POST /ad_account/negative_keywords`) — **ze spec stažené 2026-09**, na self-serve nikdy nenasazené (404). Kontext řídí jen hints a cílení.

## Custom audiences

- Asynchronní: `upload_pending → processing → rockset_ingest_pending → publishing → ready` | `too_small` | `failed` | `archived`. Počty jen jako rozsahy (`under_25k`, `25k_100k`, …; `none` = nedostupné, ne nula).
- Soubor: UTF-8 CSV/TXT ≤ 500 MB přes `POST /uploads` (multipart, `purpose=custom_audience`); při create posílat **filename, mimetype, file_size přesně**. Identifikátory `email|phone|email_sha256|phone_number_sha256|gaid`; smíšené sloupce → `identifier_resolution: auto`. Jednotypová cesta max 5 M identifikátorů.
- Membership ops (`/add`, `/remove`, `/replace`, `/merge`) **vyžadují `Idempotency-Key`** a vrací `operation_id` → poll `GET …/operations/{op}` (`processing|succeeded|failed`). `expected_revision` z čerstvého čtení (povinný u replace). Inline max ~10 000 identifikátorů / 16 MiB body.
- Chyby: `409 custom_audience_mutation_conflict` (souběžná změna — počkat, znovu načíst), `409 custom_audience_replacement_revision_conflict`, `409 custom_audience_operation_recovery_required` (poslat TÉŽ request se stejným klíčem), `409 custom_audience_policy_revision_mismatch`, `503 custom_audience_operation_unavailable` (retry statusu).
- Eligibility ≠ ready: `GET /custom_audiences?intended_use=inclusion|exclusion|bid_multiplier` vrací jen způsobilé + `policy_revision`. Inclusion/bid multiplier ≈ 25 000 matched users; exclusion i prázdná audience. Bid multipliers 0.1–10× na ad group.
- Archive audience je permanentní.

## Konverze (pixel, CAPI, event settings)

- `POST /conversions/pixels` → `{id: clidsrc_…, pixel_id}`: `id` = source pro event settings, `pixel_id` = do JS pixelu (`oaiq("init",{pixelId})`) a CAPI (`https://bzr.openai.com/v1/events?pid=`). Pixely přes API mají automatic advanced matching.
- `POST /conversions/api_keys` → CAPI klíč (jen server-side, zobrazí se jednou). `POST /conversions/event_settings` (`event_type` standardní nebo `custom`+`custom_event_name`, `attribution_window_days: 30`, přesně 1 `source_ids`). `GET /conversions/events?pid=` = debug stream posledních 15 min (max 50).
- **Per-account gating**: pixel management / CAPI keys → 404 „Not found"; oCPC → 403 „Conversion bidding is not enabled"; event stream → 404. Řeší partner rep, ne retry.
- **`conversion_event_setting_ids` na kampani má dvě role**: u `bidding_type=conversions` je to optimalizační cíl (přesně 1 standardní, neměnný); u CPM/CPC kampaní je to **napojení eventu pro reporting** (bez něj event sbírá data, ale kampaň o něm neví — v Ads Manageru je to poslední, často zapomenutý krok Tools → Conversions). CLI: `campaign-create` bez napojení varuje, `conversion-check`/`pulse` hlásí nenapojené kampaně.
- Pixel v praxi: startuje s consent=true → s cookie lištou volat `oaiq("consent", false)` před `init` a `true` po souhlasu (blokované eventy se nepřehrají); CSP musí pustit `bzrcdn.openai.com` (script-src, connect-src) a `bzr.openai.com` (connect-src, img-src) — bez `'unsafe-inline'`, přes nonce/hash.
- oCPC: přesně jeden aktivní **standardní** event setting (custom nejde), napojený na 1 aktivní source. Standardní eventy: appointment_scheduled, checkout_started, contents_viewed, items_added, lead_created, order_created, page_viewed, registration_completed, subscription_created, trial_started (+ app_installed/app_opened jen přes CAPI).

## Produktové feedy

- Feed vzniká v Ads Manageru (Feeds) nebo `POST /feeds`; katalog jde **SFTP** (`/feeds/{id}/sftp_access` — create/replace credentials = rotace, heslo jednou; activate/pause). Google-kompatibilní schema + `is_ads_eligible: true` (ne `is_ads_enabled`). Uploady a diagnostika: `GET /feeds/uploads`.
- Kampaň `mode: product_feed` + `product_feed_id`; ad group volitelně `product_set` (feed musí sedět; filtry `field:operator:values`, operátory `in|not_in|gt|gte|lt|lte|contains|not_contains|starts_with`, gt/gte/lt/lte jen price/star_rating, jedno pole max jednou); ad `product_ad_template` (`{{product.title}}`, `{{product.body}}`, `{{product.price}}`; bez file_id/target_url; **max 1 nearchivovaný template na ad group**).
- Delta Feeds `PATCH /feeds/{id}/products` — jen existující varianty; `price.amount` v **minor units** (8999 = 89.99); `availability.status` přebíjí `available`. Odpověď `accepted: true` ≠ zaindexováno. Gating 403 `product_feed_api_disabled|product_feed_delta_api_disabled`.
- `POST /feeds/{id}/products/query` = náhled, které produkty projdou filtry (limit ≤ 500).

## Bulk API (limited preview, mimo spec)

- `POST /bulk_mutation_jobs` (1–1 000 operací, 16 MiB, op ≤ 512 KiB; `validate_only`, `partial_failure` default true; request `Idempotency-Key`), `GET /bulk_mutation_jobs/{id}` (`pending|in_progress|completed|partially_failed|failed`), `GET …/operations` (`created|updated|validated|failed|skipped`, `retryable`, `retry_after_seconds`, cursor až po `complete`).
- Typy: `campaign.create/update`, `ad_group.create/update`, `ad.create/update`. **Bulk input má jiná pole než REST** (`max_budget_micros` + `budget_type`, `target_countries`, `location_ids`, `max_cpm_bid_micros` vs `max_bid_micros`, `source_image_url` u ad.create). Reference na rodiče přes `campaign_idempotency_key`/`ad_group_idempotency_key`. Update jen existujících objektů, každý max 1× v jobu.
- 404 = účet nemá preview. CLI dry-run = job s `validate_only: true` (nic nemění, ale nekontroluje existenci update cílů ani stažení obrázků).

## Lead formuláře, lead sync, Business Agents (ve spec, bez public docs)

- Lead form: draft/publish/archive s revizemi (`expected_draft_revision_id`, `published_revision_id`), 3–5 polí `text|choice`, `privacy_policy_url`. `POST …/test_submissions` pošle syntetický podepsaný lead do webhooku.
- Lead sync: `POST /lead_sync_subscriptions` (`ad_account_id`, https `destination_url`, volitelně vlastní `signing_secret` `whsec_…`) → **signing secret jednou**. Webhook `lead_form.response.created` = Standard Webhooks v1 (HMAC-SHA256 nad raw body, hlavičky `webhook-id`, `webhook-timestamp`, `webhook-signature`, `OpenAI-Subscription-Id` musí sedět s podepsaným body).
- Business Agent (`/business_agents`): name ≤ 50, instructions ≤ 4 000, description ≤ 300, až 12 conversation starters, tools z `GET /business_agent_tools`, product feeds, lead form (id + published revision), `preview` (1–10 zpráv), `publish`. Kampaň `mode: business_agent` + `business_agent_id`. Update = **full replace** (vynechané volitelné pole se resetuje, lead_form zůstává dokud nepošleš null).

## Platforma & Ads Manager (Help Center, ověřeno 2026-09-01/02)

- Reklama = 1 blok pod dokončenou odpovědí (Sponsored/Ad), 7 prvků: jméno inzerenta, favicon, štítek, **nadpis ~16 znaků**, **popisek ~32 znaků** (doporučené délky z Help Center; spec dovolí 50/100, ale text se v některých umístěních zkracuje), obrázek („avoid using logo as the primary visual"), landing page. CLI na překročení 16/32 varuje.
- Vidí ji jen **Free a Go** uživatelé (ne Plus/Pro/Business/Enterprise/Edu, ne <18, ne Temporary Chat, ne Atlas). U citlivých témat se nezobrazuje.
- **EEA/Švýcarsko bez personalizace**: cílí se jen kontextem aktuálního vlákna (žádná historie/paměť) a bez custom audiences. Americké benchmarky nepřenášet.
- Crawler **OAI-AdsBot** je pro reklamy povinný (OAI-SearchBot doporučený) — kontroluje landing page proti policy a bere z ní relevanci. Blokace přes WAF/CDN/captcha/JS challenge = 403/429 = reklama neprojde. `landing-check` testuje robots i bot-UA.
- **oppref**: OpenAI přidá do landing URL `?oppref=<click ref>`; pixel ho uloží do cookie `__oppref`, CAPI ho **nezachytí** — musíš ho poslat sám. Redirect/router, který query ustřihne, tiše zabije atribuci kliknutí. `landing-check` to testuje (`oppref_survives`). `obref` je uvnitř `user` a podléhá souhlasu.
- Dedup pixel + CAPI: stejné event `id` (Pixel ID + název eventu + id), první doručení vyhrává.
- Aukce druhocenová vážená relevancí; doporučený max CPC **3–5 USD** (pod 3 USD UI varuje). Min. denní budget 25 USD (US tabulka), **15 € na eurovém účtu (praxe, první CZ setup)**. Denní útrata může být až **2× denní budget**, týdenní součet drží.
- Cíl kampaně po založení neměnný; typ rozpočtu jen jednosměrně. „Maximize results" = automatický bidding (API `strategy: maximize_*`), zapínáno per účet.
- Billing **postpay s payment threshold** (roste s historií, nejde nastavit); selhaná platba → kampaně *Not serving*. Po pauze může reklama běžet ještě **až 24 h** a útrata je účtovatelná.
- **Past při zakládání účtu**: „You don't have permission to create ad accounts in your tenant" — zakládání účtů je tenant-level právo (Ads admin / global admin), nedědí se z adminství existujícího účtu; osobní účet (Free/Plus/Pro, Gmail) nemá Admin Console vůbec (jen Enterprise/Edu). Ověřeno 2026-09-02 i na čistém osobním účtu. Funkční cesta (praxe): někdo s **firemní** e-mailovou adresou projde onboardingem, vytvoří účet s firemní fakturací a kartou a **pozve** správce kampaní (Pending invitation → Accept). Oficiální: ads-support@openai.com.
- **Jedna právní entita + fakturační země + měna = jeden ad account** (po založení nezměnitelné). Role (admin/member/viewer) per účet v Admin Console; role v ChatGPT workspace/API Platform k Ads nic nedávají. Agentura = role v klientově účtu.
- Feed: položky **expirují po 14 dnech** → automatická synchronizace; `is_ads_eligible` vs. `is_eligible_search` jsou oddělené režimy (placené vs. organické).
- Rané veřejné číslo (jeden test, MarTech): CVR 0,21 % vs 3,71 % Google Ads na stejném webu; sestava s keyword-style hints porazila sestavu s větami (proti oficiálnímu doporučení) — testovat obě.

## Idempotence a retry (jak to dělá CLI)

- Spec: `Idempotency-Key` volitelný na `POST /campaigns|/ad_groups|/ads`, **povinný** na audience membership ops, `/lead_sync_subscriptions`, `/test_submissions`, `/ad_account_creation_sessions`. CLI generuje `oaiads-<uuid4>` pro každý create a vytiskne ho; `--idempotency-key` pro bezpečný retry stejného těla (jiné tělo se stejným klíčem = chyba).
- Retry transientů (timeout, connection, 5xx: 2/5/15 s) jen GET a idempotentní zápisy (create s klíčem, update, activate/pause/archive). Nikdy: `/upload(s)`, `/api_keys`, `/conversions/api_keys`, `/sftp_access`, `/lead_sync_subscriptions` (secret jednou / rotace).

## Chyby

- Spec deklaruje jen 200; tvar error těla není dokumentovaný. CLI čte `error.message|detail`, `error.code|type`, případně top-level `message|detail`, a tiskne `HTTP <status> [code]: message` + nápovědu podle statusu + `x-request-id` (pokud přijde) pro support.
- Známé textové kódy z docs: `custom_audience_*` (409/503), `product_feed_api_disabled`, `product_feed_delta_api_disabled` (403), „Conversion bidding is not enabled" (403), „Not found" (404 u gated features), „Client data source not found" (400, špatný `source_ids`).

## Živě ověřeno (vlastní self-serve účet, EUR, 2026-09-02)

1. **Array parametry: `fields[]=a&fields[]=b` fungují; bare `fields=a` → 400 `invalid_type` „expected an array of strings"**. Platí i pro `include[]`. CLI (`ARRAY_SUFFIX="[]"`) i `raw --params` s listem to dělají správně.
2. **Tvar chyby** = Platform-API obálka: `{"error": {"message", "type", "param", "code"}}`, např. `type: invalid_request_error`, `code: integer_above_max_value`, `param: "limit"`; 403 u nezapnutých featur má `type: server_error` a message „403: Business Agent advertiser tools are not enabled." Hlavička **`x-request-id`** (`req_…`) přijde vždy; `openai-processing-ms`; žádné rate-limit hlavičky; před API je Cloudflare (`__cf_bm` cookie, `CF-RAY`). `Retry-After` zatím neviděno (žádný 429).
3. `GET /ads` a `GET /ad_groups` **bez** `ad_group_id`/`campaign_id` vrací celý účet (spec má pravdu, docs ne).
4. **`GET /ad_account/spend_limit_windows` → 404 `Invalid URL`** — endpoint ze spec na self-serve účtu **není nasazený**. Pojistka útraty přes API tedy neexistuje; CLI to hlásí a doporučuje denní budget + `end_time`. Sledovat, kdy se objeví.
5. Business Agents / lead forms / `business_agent_tools` → **403 „Business Agent advertiser tools are not enabled"** (per účet). Bulk API: `GET /bulk_mutation_jobs/<id>` vrátil **422 Invalid Identifier**, ne 404 → endpoint existuje (zápis netestován).
6. Insights s `fields[]` → 200, `{"object":"list","count":0,"data":[],"first_id":null,"last_id":null,"has_more":false}` (účet bez doručení; wire klíče metrik zatím neověřeny).
7. **Geo lookup pro CZ**: `country` Czechia = **`1000055`**, `region` = 14 krajů (Praha `2000330` CZ-10, Jihomoravský…), navíc **`postal_code`** (docs uvádí jen country/region/DMA) — např. `10014330` = 613 00 Brno-Černá Pole.
8. **Ads Manager „Recommended" kampaň** (vygenerovaná z webu): `bidding_type: clicks`, `objective: clicks`, `billing_event_type: click`, `budget.daily_spend_limit_micros` 100 EUR, `start_time` teď, **`targeting.locations.include` = United States** (!) — UI defaultuje na US, u českého účtu nutno přepsat (`campaign-update --location-ids 1000055`). Ad group: `bidding_config = {billing_event_type: click, strategy: maximize_clicks}` **bez `max_bid_micros`** (automatický bidding funguje bez bidu), 4 české context hints ve větách, `status: active`. Ad: `chat_card`, `image_crop {0,0,1,1}`, `review_status: approved` do minut, `review: {status: approved}`. Objekty nesou nedokumentované **`user_external_id`** (`carpet-lite:…`) = stopa generátoru.
9. Pixel: source id má prefix **`cds_`** (docs `clidsrc_`), `pixel_id` 22 znaků; `GET /conversions/events?pid=` funguje (debug stream zapnutý). `GET /conversions/event_settings` funguje (prázdné). `GET /custom_audiences` funguje i na EU účtu (prázdné, vrací `policy_revision`). `GET /feeds` funguje (prázdné).
10. `GET /ad_account`: `review.status` přešel z `in_review` na `approved` během minut po nahrání loga; `account_integrity_review.details.decision: allowed`; `preview_url` = CDN URL loga (`bzrcdn.openai.com`).

11. **Zápisy (první ostrý pilot 2026-09-02, 1 kampaň / 7 ad groups / 18 ads, ~45 zápisů, žádný 429):** `POST /campaigns` (daily budget, `location_ids`, `end_time`, **dva** `conversion_event_setting_ids` na CPC kampani → oba napojené; bez `start_time` OK), `POST /campaigns/{id}` (name + budget celý objekt + end + targeting merge US→CZ v jednom volání), `POST /ad_groups` (`strategy: fixed_bid` + `max_bid_micros` 1 000 000 = **1 € prošlo, minimum bidu API nevynucuje**; `context_hints` 20 českých řádků s diakritikou; **`landing_page_configuration.query_string_template` na ad group se persistuje** — precedence vůči kampani netestována), `POST /upload` multipart PNG 1200×1200 / 1,3 MB → `file_…` (jeden file_id pro 18 reklam), `POST /ads` chat_card (titulky 17–25 zn., popisky 33–39 zn. prošly review). **Review: 17/18 approved do ~3 min, poslední do ~10 min.** `POST /ads/{id}/preview` → `data[0].body` = `<iframe src="https://ads.openai.com/previews/adprev_…?token=v1.…">` 390×220.
12. **Listy jsou eventually consistent**: `GET /campaigns` vracel několik sekund po `POST /campaigns/{id}` staré hodnoty (název, budget, end), `GET /campaigns/{id}` byl čerstvý → po zápisu ověřovat detailem (CLI `*-update` detail dotáhne a přiloží jako `_verified`).
13. **`POST /ad_account/negative_keywords` → 404 `Invalid URL`** na self-serve, a `GET /ad_account` pole `negative_keywords` **vůbec nevrací** — stejná třída nenasazených endpointů jako `spend_limit_windows`. Kontext se řídí jen hints. CLI to hlásí explicitně.
14. Pixel eventy z produkce (`GET /conversions/events`): `page_viewed`/`contents_viewed`, `event_data_json.contents[0].id` nese celou landing query vč. `utm_*` a `oppref` — pixel se vkládá klientsky (curl HTML ho nevidí), ověřovat přes tento stream. SK country id `1000201`.

## Neověřeno živě (zbývá)

- `Idempotency-Key` chování při skutečném retry, `Retry-After` u 429 (žádný 429 zatím nenastal).
- `until=today` u insights; `image_crop` jiný než celý; `price` na chat_card; WebP upload.
- Zda `strategy: maximize_clicks` jde poslat přes API bez `max_bid_micros` (UI to tak vytvořilo; API přijalo `fixed_bid` + bid).
- ~~Precedence `query_string_template`~~ — **zdokumentováno 2026-09**: šablony se sčítají, duplicitní klíč z nejkonkrétnější úrovně (viz Změny API 2026-09). Živě ověřená zůstává jen celá šablona na sestavě; rozdělení kampaň + sestava je podle docs, živě zatím ne.
- Zápis denního limitu útraty (`daily-spend-limit-set`) — self-serve klíč dostane 403 už na čtení; ověřit na účtu na fakturu.
- `audience-operations` / `-resume` / `-cancel` — účty zatím nemají žádné audiences.
- Bulk API zápis (`validate_only`), CAPI klíč (`POST /conversions/api_keys`), `POST /conversions/pixels` na self-serve.

## Poznámky z ostrého provozu

Sem zapisuj, co se při reálném používání rozbilo nebo chovalo jinak, než CLI/docs tvrdí (datum, příkaz, `x-request-id`, co API vrátilo, co jsme čekali). Opravy → CHANGELOG.

### 2026-09-07 — první týden provozu (dva self-serve účty, optimalizace pilotů + příprava větší kampaně) → opraveno v 1.4.0

- 🔴 `plan-apply --file plan.json --confirm` (relativní cesta) spadl **před založením kampaně**: stav se odvodil jako `plan.state.json` (bez adresáře) a `os.makedirs("")` vyhodil `FileNotFoundError`. Dry-run stav nezapisuje, takže prošel. Fix: `_write_json_atomic` cestu normalizuje (`abspath`).
- 🟠 `pulse` hlásil „1 ad(s) not approved / with serving issues“, zatímco `ad-review` na témže účtu říkal 18/18 approved: reklamy v záměrně pozastavené sestavě nesou `ad_group_not_active`. Fix: společná klasifikace v `common.ad_attention` (pauza v hierarchii + `ad_in_review` = očekávané stavy), `pulse` hlásí zvlášť ⚠ / ℹ / „jen pauza“.
- 🟠 `ad-review` dal 12 čerstvě založených reklam (`paused`, `in_review`, kódy `ad_not_active, ad_in_review`) pod „Problems“ — `ad_in_review` nebyl mezi očekávanými kódy. Fix: tamtéž; JSON řádky nesou `_attention`.
- 🟠 `pulse` → `(conversions: HTTP 400 … entity_ids must be provided when group_by_entity is true)` při každém běhu. Server defaultuje `group_by_entity=true`. Fix: `pulse` posílá `false` (součet za účet); `conversion-insights` totéž bez `--ids`, s `--ids`/`--group-by-entity` posílá `entity_ids`. Ověřeno na obou účtech.
- 🟡 `plan-apply` při opakovaném běhu tiše přeskočil objekty ze stavu — úprava textu reklamy nebo hintů v plánu se nikam nezapsala a CLI nic neřeklo („resumable“ sváděl k domněnce, že běh plán sesynchronizuje). Fix: rerun čte detaily, rozdíly hlásí (↻), `--update-existing` je zapíše (nikdy `status`).
- 🟡 Precedence UTM šablony kampaň vs. sestava zůstává neověřená, přitom rozhoduje o měření. Pilot má celou šablonu na sestavě a v GA4 se měří správně. Fix: doporučení „celá šablona na sestavu“ v playbooku/skillu/`plan-example.json`, lint varuje na kombinaci.
- 🟡 Skill citoval bid 3–5 USD/klik jako „sweet spot“ bez kontextu — je to kalibrace OpenAI pro US trh; na levnějším trhu (CZ/SK) doručují i bidy kolem 1 EUR a příliš nízký bid doručování prakticky zastaví. Fix: playbook §4 + skill (začít níž, po 48 h zkontrolovat imprese).
- ⚪ Příkazy `adgroup-*` vs. flag `--ad-group-id` → alias `--adgroup-id`.
- Není chyba appky: `spend_limit_windows` a `negative_keywords` → 404 (nenasazené endpointy); report „na jaké konverzace se reklama spárovala“ platforma neposkytuje.

### 2026-09-07, druhá dávka — nasazení kampaně se stovkami sestav a reklam přes `plan-apply` (v1.4.0) → opraveno v 1.4.1

- 🟠 **Detail je po zápisu zastaralý stejně jako list**: `adgroup-pause` → „pause done“, ale okamžitý re-read detailu ještě `status: active`, o chvíli později `paused` (u všech pauznutých sestav). Řádek „Verified via detail“ tak tvrdil opak toho, co se stalo. Fix: `run_write` čte detail až 3× s pauzou 1,5 s, „verified“ jen při shodě očekávaných polí, jinak explicitní „still shows the OLD state“.
- 🟠 Lint u plánu se stovkami reklam vytiskl ~700 řádků varování o délce titulku/popisku a strom se v nich ztratil. Fix: varování jednoho druhu se skládají do jednoho řádku s počtem a maximem; `--verbose-lint` rozepíše.
- 🟡 Dry-run neměl souhrn před stromem (počty, zápisy, odhad délky). Fix: hlavička `create / existing / writes (+ rough run time) / state` před stromem; v `--json` `estimated_run_time`, `image_uploads_remaining`.
- 🟡 `insights --json` vrací holé pole, jiné příkazy objekt — není chyba, jen to nebylo v README. Fix: README → Použití, tvar výstupu per skupina.
- 🟡 `ads/adgroups/campaigns --limit` byla argparse chyba (README `--limit` uváděl jen u `feed-uploads`/`insights`). Fix: `--limit N` = klientský strop na řádky; stránkování zůstává automatické.
- ✅ **Potvrzeno v provozu (v1.4.0):** `plan-apply` s absolutní cestou a stovkami objektů proběhl bez jediného 429 a bez pádu; `ad-review` po zápisu hlásí „0 problem(s), N in review, M fine (M not serving only because … paused)“ — přesně rozlišení z nálezů 2 a 3; ↻/✓ v dry-runu opakovaného běhu sedí.
- ℹ️ **Nepotvrzeno:** podezření na pomalý `campaign-detail --with-children` u stovek objektů — první běh vypršel jen proto, že šel souběžně s aktivací stovek objektů a CLI čekalo na vlastní rate-limit rozpočet (80 %); opakované měření 0 s. Chování je správné.

### 2026-09-02 — první ostrý zápis (pilot: 1 kampaň, 7 ad groups, 18 ads)

Zkráceně (plné znění interního reportu je mimo repo):

- ✅ Živě prošlo: `campaign-create` (daily budget, `location_ids`, `end_time`, **dva** `conversion_event_setting_ids` na CPC = oba napojené), `campaign-update` (name + budget + end + targeting merge), `adgroup-create` (`fixed_bid` + `max_bid_micros`, `--hints-file` 20 řádků CZ, **`landing_page_configuration.query_string_template` na ad group se persistuje**), `image-upload --file` PNG 1200×1200 (1,3 MB), 18× `ad-create` chat_card (review approved 17/18 do ~3 min, poslední do ~10 min), `ad-preview` (iframe `ads.openai.com/previews/adprev_…?token=v1.…`), `conversion-events` stream (page_viewed z produkce, `contents[0].id` nese celou query vč. `oppref`), `conversion-check`, `landing-check`, `geo-search` (SK `1000201`). Žádný 429 (~45 zápisů).
- ❌ `POST /ad_account/negative_keywords` → **404 `Invalid URL`** na self-serve, stejná třída jako `spend_limit_windows`. GET se tvářil jako prázdný seznam — ověřit, zda CLI 404 na GET tiše nepolyká.
- ⚠️ `campaigns` (list) vrátil pár sekund po `campaign-update` **staré hodnoty**, `campaign-detail` čerstvé → po zápisu ověřovat detailem. *(Doplněno 2026-09-07: i detail zaostává — viz druhá dávka, bod 9.)*
- ⚠️ `campaign-detail --with-children` neukazuje reklamy pod ad groups (jen ad groups).
- ⚠️ `landing-check` tiskne „Recommended robots.txt" i u čistého výsledku (šum).
- Nápad: `campaign-plan/apply` z jednoho YAML (kampaň → ad groups s hints_file + utm_content → ads) místo 25 samostatných volání; hint po update „ověř detailem"; `conversion-events --json`.

### 2026-09-24 — srovnání s API po 2026-09-02 (čtení na dvou účtech) → opraveno v 1.5.0

- 🟠 `pulse` / `ad-review` hlásily reklamy skončené kampaně jako problém: nový serving kód `campaign_ended` nebyl mezi očekávanými stavy (na živém účtu tvořil většinu hlášených „problémů“; skutečné byly jen zamítnuté reklamy s `review_not_approved`). Fix: `campaign_ended` ∈ `PAUSED_CODES`.
- 🟡 `insights --segment …` (country/device/platform/product) s `aggregation_level=campaign` vracel řádky kampaň × segment, ale tabulka ukazovala jen segment, takže řádky vypadaly zdvojeně. Fix: sloupec s entitou.
- 🟡 `spend-limits` / `pulse` / `account` znaly jen 404; self-serve klíč dnes dostává 403 „Only ad account admins“ → `spend-limits` padal s „contact partner rep“. Fix: 403 i 404 = „pojistka přes API nedostupná“.
- ✅ **Živě ověřeno:** `include[]=bid_too_low` (detail i list), `segments[]=platform` s `fields[]=platform` (granulární weby v datech od 2026-09-10), ploché wire klíče metrik (`clicks`, `spend`, `impressions`, `cpc`, `cpm`, `ctr` jako podíl), `origin_country_code` na účtu.

