# Changelog

Všechny podstatné změny v tomto projektu. Formát vychází z [Keep a Changelog](https://keepachangelog.com/), verzování je [SemVer](https://semver.org/) (verze žije v `oaiads/__init__.py`).

## [1.5.0] — 2026-09-24 — Srovnání s API po 2026-09-02 🆕

Nové porovnání appky s API: changelog OpenAI (9. a 10. září), celé docs znovu přečtené (`llms-full.txt`), aktuální OpenAPI spec strojově porovnaná s tím, co CLI posílá (verze spec je pořád 2.3.0, obsah ale jiný: 78 operací místo 88), čtení ověřené živě na dvou self-serve účtech. Detail v `docs/api-notes.md → Změny API 2026-09`.

### Přidáno
- **Denní limit útraty účtu** (API 2026-09-09): `daily-spend-limit-set` (`--amount`, `--start` jen u nového, `--end` / `--no-end`, `--expected-revision`, jinak si ho CLI načte) a `daily-spend-limit-delete`. Zápisy nejsou automaticky opakované (503 = změna možná prošla → znovu načíst). `spend-limits` ukazuje denní limit (dnešní útrata, zbytek), `revision`, `can_create_daily_limit`, nejbližší možné starty; `account` a `pulse` denní limit taky.
- **Granulární web platformy** (API 2026-09-10): `--platforms` bere `desktop_web`, `ios_web`, `android_web` (a dál `web` = všechny weby, `ios_app`, `android_app`); `--clear-platforms` pošle `targeting.platforms: null` (zruší jen omezení platforem). Prázdný seznam CLI odmítne (API vrací 400), `web` + konkrétní web platforma = varování na redundanci. Validace i v `plan-apply`.
- **`insights --segment platform`**: výkon po platformách (ověřeno živě; metriky chodí jako ploché klíče `clicks`/`spend`).
- **`bid_too_low`** (docs 2026-09, ve spec zatím chybí, živě funguje na detailu i výpisu): `adgroup-detail` ho vždy načte a ukáže, `adgroups --bid-check` přidá sloupec a souhrn, `pulse` hlásí počet aktivních sestav s tímto varováním.
- **Audience operace**: `audience-operations` (výpis uchovaných operací, stránkování přes `next_cursor` i přes prázdné stránky), `audience-operation-resume` a `audience-operation-cancel` (bez těla a bez `Idempotency-Key`, podle docs). `audience-operation` při `409 custom_audience_operation_recovery_required` rovnou poradí resume a `503 …unavailable` při `--wait` bere jako „zkus znovu“, ne jako selhání.
- Insights: varování, když okno sahá za retenci (hodinová data ~30 dní, produktová ~30 dní, ostatní 365 dní).
- Produktové filtry: `ads_metadata.<klíč>` (vlastní štítky) bez varování „neznámé pole“.

### Změněno
- **Maximize Results podle nových docs**: `--strategy maximize_clicks|maximize_conversions` bez `--max-bid`; CLI kontroluje odpovídající cíl kampaně (clicks / conversions), click billing a **denní** budget; při přepnutí na Maximize zahodí `max_bid_micros` a vyprázdní audience multiplikátory, zpět na `fixed_bid` chce explicitní bid.
- **Budget je vždy jeden**: `--daily-budget` a `--lifetime-budget` zároveň = chyba (i v `plan-apply`); `campaign-update` odmítne přepnout denní budget na celkový (API to neumí, jen celkový → denní).
- **UTM šablony**: OpenAI zdokumentovalo, že šablony na účtu, kampani, sestavě a reklamě se **sčítají** a u duplicitního klíče vyhrává konkrétnější úroveň (URL > reklama > sestava > kampaň > účet). Varování „precedence neověřená, sestavová může kampaňovou celou nahradit“ nahradilo varování jen na duplicitní klíče (`adgroup-create`, `adgroup-update`, `plan-apply`).
- `campaign-update` se samotnými platformami pošle jen `targeting.platforms` (API zbytek zachová) a nečte ani neposílá zpět lokace a audiences (odpadá riziko `409 custom_audience_mutation_conflict`).
- Limity útraty: 403 „Only ad account admins can perform this action“ (tak odpovídá self-serve klíč od 2026-09-09, dřív 404) CLI bere stejně jako 404: pojistka přes API není dostupná, `spend-limits` / `account` / `pulse` nepadají.
- `pulse` pozná domovskou zemi z nového pole účtu `origin_country_code` (timezone jen jako záloha); stav okna `upcoming` (dřív chybně `scheduled`).

### Opraveno
- **`campaign_ended` byl „problém“**: reklamy skončené kampaně (serving issue `campaign_ended`) hlásil `pulse` i `ad-review` jako chybu. Živě to byla většina hlášených „problémů“. Teď je to očekávaný stav jako pauza.
- **Segmentované insights vypadaly zdvojeně**: řádek je kampaň × segment, ale tabulka ukazovala jen segment. Přidán sloupec s entitou (platí i pro country/device/product).

### Deprecated
- Endpointy, které OpenAI stáhlo z veřejné specifikace: **negativní klíčová slova** (`negative-keywords*`), **lead formuláře** (`lead-form*`) a **Business Agents** (`business-agent*`), celkem 18 příkazů. Na self-serve účtech nikdy nefungovaly (404/403). Zůstávají pro účty, kterým je OpenAI zapnulo, na stderr upozorní a ve 2.0 odejdou. Lead sync (`lead-sync*`) ve specifikaci zůstal. `campaign-create --mode business_agent` varuje.

### Dokumentace
- api-notes: nová sekce „Změny API 2026-09“ (co přibylo, co zmizelo, co je nově zdokumentované, co jsme ověřili živě); vyřešené body z „Neověřeno živě“ (wire klíče metrik, precedence UTM).
- Skill a playbook: limity útraty, platformy, Maximize Results, `bid_too_low`, UTM, audience operace, Conversions API novinky (`integration_source`, `validate_only`, offline `action_source`), image tag, `measureSingle`.

## [1.4.1] — 2026-09-07 — Druhá dávka nálezů (kampaň o stovkách objektů) 🔧

Z nasazení kampaně se stovkami sestav a reklam přes `plan-apply` ve v1.4.0. Detail v `docs/api-notes.md → Poznámky z ostrého provozu → 2026-09-07, druhá dávka`.

### Opraveno
- **Ověření po zápisu tvrdilo víc, než API dovoluje**: `adgroup-pause` prošel, ale okamžitý re-read detailu ještě vrátil `status: active` a řádek „Verified via detail“ vypadal jako neúspěšný zápis (u všech pauznutých sestav). Detail je eventually consistent stejně jako listy. Teď CLI detail čte až 3× s pauzou 1,5 s a „Verified via detail (status match)“ napíše jen když očekávaná pole (u `*-activate/pause/archive` `status`, u `*-update` `name`/`status` z requestu) skutečně sedí; jinak řekne „⚠ Detail still shows the OLD state after 3 reads … re-check with *-detail“. `--json` nese `_verified_matches` a `_verified_expect`.
- **Lint tiskl stejné varování stokrát** (u plánu se stovkami reklam ~700 řádků o délce titulku/popisku, strom se v nich ztratil). Varování jednoho druhu (liší se jen číslem) se od 3 kusů skládají do jednoho řádku s počtem a maximem (`⚠ 231× creative.title is N chars — … [N up to 40]`); chyby (spec limity) se neskládají nikdy. `plan-apply --verbose-lint` vypíše každé zvlášť.

### Přidáno
- **Souhrn dry-runu `plan-apply` před stromem**: kolik kampaní / sestav / reklam vznikne, kolik obrázků se nahraje, kolik objektů už existuje (a kolik se liší), počet zápisů celkem a **hrubý odhad délky běhu** (sekvenčně ~0,5 s na zápis, nebo pacing na 80 % limitu, co je větší). V `--json` jako `image_uploads_remaining` a `estimated_run_time`.
- **`--limit N` u výpisů** `campaigns` / `adgroups` / `ads`: klientský strop na počet řádků po lokálních filtrech (stránkování zůstává automatické; `--max-items` omezuje, kolik se stáhne). Dřív argparse chyba.

### Dokumentace
- README: **tvar `--json` výstupu** per skupina příkazů (výpisy a insights = holé pole, detaily/`pulse`/`conversion-check` = objekt, zápisy = `{"executed": …}` / odpověď API) — na `insights --json` se při psaní automatu narazilo (`'list' object has no attribute 'get'`).
- api-notes: druhá dávka nálezů + co se ve v1.4.0 potvrdilo v provozu (`plan-apply` se stovkami objektů bez 429, klasifikace serving issues, čekání na vlastní rate-limit rozpočet při souběžném běhu není chyba).

## [1.4.0] — 2026-09-07 — Nálezy z týdne ostrého provozu 🔧

Reakce na osm nálezů z prvního týdne provozu na dvou účtech (optimalizace pilotů, příprava větší kampaně). Detail v `docs/api-notes.md → Poznámky z ostrého provozu → 2026-09-07`.

### Opraveno
- **`plan-apply --file plan.json --confirm` padal dřív, než něco vytvořil** (relativní cesta → `plan.state.json` bez adresáře → `os.makedirs("")` → `FileNotFoundError`). Suchý běh stav nezapisuje, takže prošel; spadl až ostrý běh. Zápis stavu teď cestu normalizuje; test na holý název souboru.
- **`pulse` hlásil falešný poplach** u reklam v záměrně pozastavené sestavě (`ad_group_not_active`), zatímco `ad-review` na témže účtu říkal „vše schválené“. Oba příkazy teď sdílejí jednu klasifikaci: `campaign_not_active`, `ad_group_not_active`, `ad_not_active`, `campaign_not_started` a `ad_in_review` jsou očekávané stavy, ne problémy. `pulse` hlásí zvlášť ⚠ zamítnuté / skutečné serving issues, ℹ čeká na review a „neběží jen kvůli pauze“.
- **`ad-review` řadil čerstvě založené reklamy pod „Problems“** (kód `ad_in_review` nebyl mezi očekávanými) — teď jsou ve „Waiting for review“; JSON řádky nesou `_attention: problem|waiting`.
- **`pulse` volal konverze s HTTP 400** (`entity_ids must be provided when group_by_entity is true` — server defaultuje `group_by_entity=true`). Posílá `group_by_entity: false` = jeden součtový řádek za účet. Stejně `conversion-insights` bez `--ids`; s `--ids`, nebo s `--group-by-entity` (bez `--ids` si vylistuje nearchivované objekty dané úrovně), = řádek per entita. Ověřeno živě na dvou účtech.

### Přidáno
- **`plan-apply` při opakovaném běhu porovná plán s živými objekty** (přečte detaily) a každý rozdíl vypíše (↻). Nic existujícího nemění, dokud nedostane **`--update-existing`** — pak sesynchronizuje název, budget / end / targeting / napojené eventy, bidding (celý objekt, živé klíče zachová), hints, UTM šablonu a kreativu (merge s živou; nový obrázek nahraje jednou pro všechny reklamy). `status` se nikdy nesynchronizuje (aktivace a pauza zůstávají explicitní `*-activate` / `*-pause`); změna kreativy znovu spouští review (CLI varuje). Bez flagu dry-run i `--confirm` řeknou, kolik objektů se liší — dřív se změny v plánu tiše ignorovaly.
- Alias `--adgroup-id` pro `--ad-group-id` (příkazy jsou `adgroup-*`, flag byl jen dlouhý tvar).
- Lint: `plan-apply` i `adgroup-create` varují, když má UTM šablonu kampaň i sestava (precedence neověřená; sestavová šablona může kampaňovou celou nahradit a `utm_source/medium/campaign` zmizí).

### Dokumentace
- **UTM**: celá šablona (`utm_source`/`utm_medium`/`utm_campaign` + `utm_content`) patří na sestavu; kampaňová se nepoužívá, dokud se precedence neověří (playbook §5 a §8, skill, `docs/plan-example.json`).
- **Bidy**: doporučení OpenAI 3–5 USD/klik je kalibrace pro americký trh; na levnějších trzích (CZ/SK) doručují i bidy kolem 1 EUR, příliš nízký bid doručování prakticky zastaví → začít níž a po 48 h zkontrolovat imprese (playbook §4, skill).
- api-notes: `group_by_entity`, `time_ranges` jako JSON stringy, očekávané serving kódy, zápis z provozu 2026-09-07.

## [1.3.2] — 2026-09-03 — Úklid před zveřejněním 🧹

### Změněno
- Interní report z pilotu přesunut mimo repo; z docs odstraněna request ID a zmínky konkrétních účtů/osob; `docs/plan-example.json` je neutrální demo (example.com, Acme); testy používají neutrální názvy účtů. Repo neobsahuje žádné klíče ani ID účtů, kampaní či pixelů — ověřeno grepem přes pracovní strom i historii.

## [1.3.1] — 2026-09-03 — Styly context hints 🧪

### Změněno
- Playbook §2 přepsán: doslovné citace obou nápověd OpenAI (*Create Ad Groups* 20001211: „what your product offers, who it helps, or when it may be useful“, „product, theme, or intent“, „define relevant conversation types“; *Basics* 20001207: „conversations, topics, or keywords“), z nich čtyři styly hintů P/S/C/K s příklady, pravidla platná pro všechny styly, doporučení testovat styly proti sobě (stejné reklamy, sestava na styl, `utm_content`, K kontrola vždy, ≥ 100 kliků na sestavu než soudit) a kde těžit situace (search-term reporty, GSC, klíčovka, FAQ, landing page). Skill scénář create se na styl ptá, nehádá.

## [1.3.0] — 2026-09-03 — Přejmenování na chatgpt-ads-app 🏷️

### Změněno
- Repo `faborsky/openai-ads-app` → **`faborsky/chatgpt-ads-app`**, složka, entrypoint `openai_ads_cli.py` → `chatgpt_ads_cli.py`, bundlovaný skill `skill/openai-ads/` → `skill/chatgpt-ads/` (`/chatgpt-ads`, soubory `chatgpt-ads-campaign-playbook.md`, `chatgpt-ads-policies.md`), placeholder `<OPENAI_ADS_APP_DIR>` → `<CHATGPT_ADS_APP_DIR>`, banner.
- **Beze změny** (názvy API, ne produktu): proměnné `OPENAI_ADS_API_KEY*`, `OPENAI_ADS_DEFAULT_ACCOUNT`, `OPENAI_ADS_AD_ACCOUNT`, balík `oaiads`, `OAIADS_*`. Existující `.env` funguje dál; `git remote` po `gh repo rename` GitHub přesměruje.

## [1.2.3] — 2026-09-02

### Přidáno
- `*-pause` / `*-activate` / `*-archive` po zápisu dotáhnou detail a vypíšou ověřený stav (list může pár sekund tvrdit starý stav — viděno živě).

## [1.2.2] — 2026-09-02 — Hermetické testy

### Opraveno
- Testy už nečtou vývojářův `.env` (pojmenované klíče v něm spouštěly guard na víc účtů a 3 testy padaly; v1.2.1 se omylem commitla s červenou suitou). Nová proměnná `OAIADS_NO_DOTENV=1` vypne načítání `.env` (testy, CI).

## [1.2.1] — 2026-09-02 — Víc účtů bez omylu 🔐

### Přidáno
- **Guard na výběr účtu**: při 2+ nakonfigurovaných klíčích (`OPENAI_ADS_API_KEY_<NAME>`) CLI odmítne volání bez `--account` a vypíše dostupné účty; `OPENAI_ADS_DEFAULT_ACCOUNT=<name>` nastaví výchozí; jediný nakonfigurovaný účet se vybere automaticky (i pojmenovaný). Aktivní účet se u víc účtů tiskne na stderr (`[account: …]`).
- README „Více účtů (agentury)“, `.env.example` s pojmenovanými klíči, skill pravidlo 11 (výběr účtu z privátního mapování, nikdy nehádat) a šablona `my-accounts.md` v `skill/INSTALL.md`.

## [1.2.0] — 2026-09-02 — Kampaň z jednoho souboru + nálezy z ostrého pilotu 🧭

Reakce na report z prvního ostrého zápisu (1 kampaň, 7 sestav, 18 reklam přes CLI).

### Přidáno
- **`plan-apply --file plan.json [--confirm] [--state]`**: kampaň → sestavy (hints/hints_file, bid, `utm_content` šablona) → reklamy (sdílený `image_file`/`image_url` nebo per-ad) z jednoho JSON. Dry-run = lint všeho + strom s délkami textů; `--confirm` = sekvenční zápis s Idempotency-Key per objekt a stavem v `<plan>.state.json` (resume po pádu, klíče se znovu použijí, hotové objekty se přeskočí). Umí i napojení na existující kampaň (`campaign.id`). Šablona `docs/plan-example.json`.
- `campaign-detail --with-children` ukazuje celý strom včetně reklam a review stavu.
- `*-update --confirm` dotáhne detail (`_verified`) a upozorní, že listy pár sekund zaostávají.
- `ad-review` odděluje „Waiting for review" od „Problems"; `--wide` na listech a `conversion-events`; `pulse` varuje na kampaně cílící mimo zemi odvozenou z timezone účtu.
- `landing-check` tiskne doporučený robots.txt jen když něco blokuje / robots chybí.

### Opraveno
- Negativní klíčová slova: `GET /ad_account` na self-serve pole nevrací a `POST /ad_account/negative_keywords` → 404 „Invalid URL" — CLI to hlásí explicitně (dřív se tvářilo jako prázdný seznam).

### Dokumentace
- api-notes: zápisy ověřené živě (dva event settings na CPC, UTM šablona na sestavě persistuje, bid 1 € prošel, review ~3 min, preview iframe, eventual consistency listů, negativa 404, pixel stream s `oppref`), zbývající TODO.
- Playbook: rozpočet jen na kampani (víc situací = víc sestav), bid minimum nevynucené → kontrola impresí po 48 h, obrázek = malý čtvercový náhled bez textu/loga, UTM konvence (`utm_content` per sestava, GA4 „Paid Other"), kontrolní sestava se stejnými reklamami, pixel klientsky → `conversion-events`, ověřovat detailem; §8 odkazuje na `plan-apply`.
- Skill: scénář create přes `plan-apply`, verifikace detailem, in_review ≠ problém.

## [1.1.1] — 2026-09-02 — První živé ověření 🔬

Read-only průchod reálným self-serve účtem (EUR). Zápisy zatím netestovány.

### Opraveno
- `raw --params` s listem posílá `key[]=…` (bare opakovaný klíč API odmítá 400 `invalid_type`).
- `ad-review` nepočítá `campaign_not_active` / `ad_group_not_active` / `ad_not_active` / `campaign_not_started` jako problém — jen říká, kolik reklam nedoručuje kvůli pauze v hierarchii.
- Chybové hlášky nesou `type/code/param` z ověřené obálky `{"error":{message,type,param,code}}`.
- `spend-limits` / `account` / `pulse`: endpoint `spend_limit_windows` vrací na self-serve účtu 404 „Invalid URL" — CLI to vysvětlí a doporučí náhradní pojistku (denní budget + end_time), místo aby sekci tiše vynechalo.

### Dokumentace
- api-notes: sekce „Živě ověřeno" (array syntaxe, tvar chyb, x-request-id, GET /ads bez filtru, 404/403/422 gating, CZ geo ids vč. PSČ, jak vypadá kampaň vygenerovaná Ads Managerem — **cílí defaultně na United States**, `strategy: maximize_clicks` bez bidu, `user_external_id`), zbývající TODO a prostor pro poznámky z ostrého provozu.

## [1.1.0] — 2026-09-02 — Měření konverzí jako první občan 📐

### Přidáno
- **`conversion-check`** (`--events`): audit měření pixel → event setting → napojení na kampaň → poslední pixel eventy, s vysvětlením gatingu (404 = pixel management nezapnutý).
- `pulse` hlásí aktivní kampaně bez napojeného conversion eventu; `event-setting-create` napoví krok napojení.
- Playbook §5/§7 a api-notes: proč měřit konverze i na CPC (CAC vs CPC, oCPC = nová kampaň, oppref jen přes pixel), pořadí kroků v Ads Manageru, consent hook `oaiq("consent", false)` a CSP allow-list pro pixel, past „no permission to create ad accounts in your tenant" (tenant-level právo, osobní účet bez Admin Console) a ověřená cesta přes firemní e-mail + pozvánku.

### Opraveno
- `--conversion-event-setting-id` už neimplikuje oCPC: na CPM/CPC je to napojení eventu pro reporting (libovolný počet), u `--bidding-type conversions` přesně jeden standardní. `campaign-create` bez napojení varuje.

## [1.0.0] — 2026-09-02 — První vydání 🚀

Kompletní CLI nad **OpenAI Advertiser API v1** (reklamy v ChatGPT), postavené z oficiální OpenAPI specifikace 2.3.0 a dokumentace na developers.openai.com/ads (stav k 2026-09-02).

### Přidáno
- **94 příkazů** pokrývajících všech 88 operací ze spec: účet (brand, negativní klíčová slova, spend limit windows, pauza/aktivace, API klíče), kampaně, ad groups, ads (chat_card i product_ad_template, preview), soubory, insights (4 scope endpointy + conversion insights), geo lookup, custom audiences (create/add/remove/replace/merge/archive + polling operací), konverze (pixely, CAPI klíče, event settings, debug stream), produktové feedy (vč. Delta Feeds API a SFTP), lead formuláře + lead-sync webhooky, Business Agents, partner data uploady; navíc **Bulk API** (limited preview, mimo spec) a `raw` escape hatch na cokoliv dalšího.
- **Bezpečnostní model**: zápisy jsou defaultně dry-run (lokální lint + přesný plán requestu), `--confirm` provede; vše vzniká `paused`; archivace (nevratná) odmítá nezapauzované objekty bez `--force`; každý create nese `Idempotency-Key`; zápisy bez idempotence se nikdy neretryují.
- **Rate-limit budget** přes spuštění (`.usage/`): 80 % z 600 req/min/endpoint a 1 200 req/min celkem, zvláštní budget 10/10 s pro bulk joby; respektuje `Retry-After`.
- **Preflight lint**: limity ze spec (title 3–50, body ≤ 100, URL ≤ 2048 bez rezervovaných parametrů, názvy 3–1000, hints ≤ 2000, budget ≥ 1 jednotka) + heuristiky nad Ad policies v1.5 (kategorie, superlativy, zmínky ChatGPT/OpenAI, caps, emoji) jako varování.
- `landing-check`: lokální kontrola landing page — HTTP status pro browser i bot UA (odhalí WAF/CDN blokaci), robots.txt pro **OAI-AdsBot** (povinný) / OAI-SearchBot / `*`, favicon, captcha a test, že `?oppref=` přežije redirecty (jinak tichá ztráta atribuce kliknutí).
- Lint varuje na texty nad doporučené délky z Help Center (~16 znaků nadpis, ~32 popisek).
- `skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md`: jak se kampaně podle OpenAI stavět mají — 7-vrstvá brána prerekvizit (účet, spend cap, OAI-AdsBot + WAF, oppref, měření + dedup, feed, policy), pravidla context hints (situace, ne klíčová slova; 1 sestava = 1 záměr; kontrolní keyword-style sestava), copy (16/32, bez loga jako hlavního vizuálu, varianty s různými argumenty), bidy (CPC 3–5 USD, min. denní budget 15 €/25 $, 2× denní útrata), měření (pixel+CAPI dedup, oppref/obref), realita EU trhu (jen Free/Go, bez personalizace v EEA, bez audiences), fakturace (payment threshold, 24 h doběh), účty a role, šablona briefu.
- `pulse`: digest účtu (období vs. předchozí, spend capy, review problémy, konverze) s tolerancí k nezapnutým featurám.
- Peníze v **micros ⇄ měna účtu** přes Decimal; `--max-cpm` převádí CPM na bid per impression.
- Bundlovaný skill `/chatgpt-ads` (SKILL.md + chatgpt-ads-policies.md + INSTALL.md), README (CZ), CLAUDE.md (EN), docs/api-notes.md, `scripts/check_docs_consistency.py`, 69+ offline testů.

### Známé mezery
- **Neověřeno proti živému účtu** — viz sekce „Neověřeno živě" v docs/api-notes.md (syntaxe array parametrů `fields[]`, tvar error JSONu, `Retry-After`, `until=today`).
