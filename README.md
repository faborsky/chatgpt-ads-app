# ChatGPT Ads App

**Verze 1.3.2** · Python CLI pro reklamy v ChatGPT přes **OpenAI Advertiser API v1** (OpenAPI spec 2.3.0) — 96 příkazů, všech 88 operací ze specifikace + Bulk API + `plan-apply` + `raw` escape hatch. Stavěné pro orchestraci AI agentem (Claude Code) i pro vlastní automatizace: `--json` výstupy, dry-run zápisy, idempotence, vlastní rate-limit budget.

Appka vznikla jako součást ekosystému kurzu [AI First](https://aifirst.cz) — praktická ukázka, jak si marketér může nechat AI postavit a řídit vlastní nástroje nad úplně novou reklamní platformou. Novinky sleduj přes **Watch → Custom → Releases** na GitHubu, changelog je v [CHANGELOG.md](CHANGELOG.md).

> ✅ **Stav:** čtení i zápisy (kampaň, sestavy, reklamy, upload, preview) ověřené v ostrém provozu na self-serve účtu (2026-09-02). Co zbývá ověřit: [docs/api-notes.md → Neověřeno živě](docs/api-notes.md). Dry-run (bez `--confirm`) nic neposílá.

## 🆕 Co je nového (1.3.1)

- **Context hints: čtyři styly místo jedné pravdy.** OpenAI popisuje hinty ve dvou nápovědách třemi způsoby (popis produktu „co / komu / kdy“ · téma či záměr sestavy · „conversations, topics, or keywords“). Playbook §2 to cituje doslova, odvozuje styly **P** (popis produktu), **S** (situace), **C** (otázka v konverzaci), **K** (témata/klíčová slova) a skill se ptá uživatele na cestu — nebo navrhne test stylů proti sobě (stejné reklamy, jedna sestava na styl, vlastní `utm_content`, kontrolní K sestava vždy).

### 1.3.0

- **Přejmenováno na `chatgpt-ads-app`** (repo, složka, entrypoint `chatgpt_ads_cli.py`, skill `/chatgpt-ads`, placeholder `<CHATGPT_ADS_APP_DIR>`). Produkt se jmenuje ChatGPT Ads; „OpenAI“ zůstává jen tam, kde je to název API — proměnné `OPENAI_ADS_API_KEY*` a balík `oaiads` se **nemění**, `.env` ani skripty nic přepisovat nemusí. Kdo má skill nainstalovaný ze starého názvu: `mv ~/.claude/skills/openai-ads ~/.claude/skills/chatgpt-ads` a znovu krok 2 z `skill/INSTALL.md`.

### 1.2.1

- **Víc účtů bez omylu**: při 2+ nakonfigurovaných klíčích CLI **odmítne volání bez `--account`** (zápis na špatný klientský účet nejde vrátit); jediný nakonfigurovaný účet se vybere sám; `OPENAI_ADS_DEFAULT_ACCOUNT` nastaví výchozí. Aktivní účet se tiskne na stderr (`[account: …]`). Sekce [Více účtů (agentury)](#více-účtů-agentury), pravidlo ve skillu a šablona privátního souboru `my-accounts.md` v `skill/INSTALL.md`.

### 1.2.0

- **`plan-apply`**: celá kampaň (kampaň → sestavy s hints a UTM → reklamy se sdíleným obrázkem) z **jednoho JSON** — dry-run vytiskne strom s délkami textů a lintem, `--confirm` zakládá sekvenčně s Idempotency-Key a zapisuje ID do `plan.state.json`, takže přerušený běh navážeš stejným příkazem. Šablona: [docs/plan-example.json](docs/plan-example.json). Nahrazuje 25 samostatných volání z prvního pilotu.
- **Po zápisu ověřeno živě**: `campaign-create/update`, `adgroup-create` (UTM šablona na sestavě se persistuje), `image-upload`, 18× `ad-create` (review do ~3 min), `ad-preview`. Listy jsou po zápisu pár sekund stale → `*-update` teď dotáhne detail a řekne to.
- `campaign-detail --with-children` = celý strom včetně reklam a review; `ad-review` odděluje „čeká na review" od problémů; `--wide` na listech a `conversion-events`; `pulse` varuje, když kampaň cílí na jinou zemi, než naznačuje timezone účtu (past auto-generované kampaně = USA).
- **Negativní klíčová slova na self-serve účtu nejsou** (`POST` → 404, `GET /ad_account` pole nevrací) — CLI to říká explicitně místo prázdného seznamu. Playbook: rozpočet jen na kampani (víc situací = víc sestav), bid minimum API nevynucuje, obrázek = malý čtvercový náhled bez textu, UTM konvence, pixel klientsky → ověřovat přes `conversion-events`.

### 1.1.1

- **Poprvé ověřeno proti živému účtu** (read-only): syntaxe `fields[]`, tvar chyb + `x-request-id`, gating (spend limit windows 404, Business Agents 403), CZ geo ids vč. PSČ, jak vypadá kampaň vygenerovaná Ads Managerem (**cílí defaultně na USA** — zkontroluj `campaign-detail`). Detaily v [docs/api-notes.md → Živě ověřeno](docs/api-notes.md).
- `ad-review` odlišuje „nedoručuje, protože je pauza" od skutečných problémů; `raw --params` umí array parametry.

### 1.1.0

- **`conversion-check`**: audit měření pixel → event setting → napojení na kampaň → poslední pixel eventy (`--events`); vysvětlí gating (404 = pixely nezapnuté).
- `--conversion-event-setting-id` na kampani má nově správnou sémantiku: na CPM/CPC = napojení eventu pro reporting (poslední krok, který se zapomíná), u oCPC přesně jeden standardní. `campaign-create` bez napojení varuje, `pulse` hlásí aktivní kampaně bez eventu.
- Playbook: proč měřit konverze i na CPC, consent hook + CSP pro pixel, past „no permission to create ad accounts in your tenant" a cesta přes firemní e-mail + pozvánku.

### 1.0.0

- Kompletní pokrytí API: účet + spend limit windows + negativní klíčová slova, kampaně / ad groups / ads, insights (4 scope + konverze), geo lookup, custom audiences, konverze (pixel, CAPI, event settings), produktové feedy (SFTP, Delta Feeds), lead formuláře + webhooky, Business Agents, Bulk API, partner data.
- Bezpečnostní model pro agenta: dry-run default, vše vzniká `paused`, nevratná archivace s brzdou, automatický `Idempotency-Key`, lokální rate-limit budget, lint proti spec limitům i Ad policies, `landing-check` na nejčastější důvody zamítnutí.
- Bundlovaný skill `/chatgpt-ads` pro Claude Code.

## Dva způsoby, jak appku používat

**A) Orchestrace přes Claude Code (doporučeno)** — appku řídí AI agent, ty zadáváš úkoly česky. Zkopíruj si tento prompt do Claude Code:

> Naklonuj si repo `https://github.com/faborsky/chatgpt-ads-app.git` do `~/dev/chatgpt-ads-app`, spusť `./setup.sh`, nainstaluj skill podle `skill/INSTALL.md` a proveď mě vyplněním `.env` (potřebuju API klíč z OpenAI Ads Manageru — postup je v README v sekci „Získání přístupů"). Pak ověř funkčnost přes `./run.sh account`.

Skill `/chatgpt-ads` pak umí scénáře create / optimize / analyze / review-check / audiences / conversions / feeds se zabudovanými bezpečnostními pravidly (plán → schválení → zápis, paused starty, dry-run, policy checklist).

**B) Vlastní automatizace** — CLI má stabilní `--json` výstupy, dry-run default, rate-limit budget a retry logiku, takže jde bezpečně volat ze skriptů, cronů nebo vlastních agentů:

```bash
./run.sh campaigns --json | jq '.[].name'
./run.sh insights --days 7 --aggregation-level campaign --json
./run.sh campaign-create --name "Test" --lifetime-budget 50 --bidding-type clicks            # dry-run: vytiskne plán
./run.sh campaign-create --name "Test" --lifetime-budget 50 --bidding-type clicks --confirm  # zápis (paused)
```

## Požadavky

- Python 3.9+
- Advertiser účet v [OpenAI Ads Manageru](https://ads.openai.com) se schváleným brand review a platební metodou
- API klíč vydaný v Ads Manageru (Settings → API keys), scoped na jeden ad account

## Instalace

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # vytvoří .venv, nainstaluje závislosti, založí .env
# vyplň .env (viz níže)
./run.sh account    # test funkčnosti
```

### Windows

Skripty `setup.sh`/`run.sh` jsou bashové — na Windows použij **Git Bash** (součást [Git for Windows](https://git-scm.com/download/win)) nebo **WSL** a postup výše funguje beze změny. Alternativně čistý PowerShell:

```powershell
git clone https://github.com/faborsky/chatgpt-ads-app.git; cd chatgpt-ads-app
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # vyplň klíč
python chatgpt_ads_cli.py account
```

## Získání přístupů krok za krokem

### 0) Advertiser účet (jednorázově)

1. Založ účet na [ads.openai.com](https://ads.openai.com) (Ads Manager). Projdeš ověřením firmy a **brand review** — účet neservuje, dokud nemá schválený název, URL a **favicon** (min. 128 × 128 px). Přidej platební metodu.
2. Zkontroluj, že tvoje kategorie je povolená ([Ad policies](https://openai.com/policies/ad-policies/)): v první fázi spotřební zboží, lokální služby, cestování a zážitky, digitální produkty a vzdělávání. Finance / zdraví / právo jen schválení inzerenti v USA; alkohol, gambling, dating, politika, zbraně, jednotlivé job/housing inzeráty jsou zakázané. Shrnutí pro operátora: [skill/chatgpt-ads/chatgpt-ads-policies.md](skill/chatgpt-ads/chatgpt-ads-policies.md).

### 1) API klíč

Ads Manager → **Settings → API keys** → vydej klíč. Klíč je scoped na **jeden ad account** (pro další účty další klíče).

### 2) .env

```
OPENAI_ADS_API_KEY=<klíč>                       # jeden účet
# víc účtů: OPENAI_ADS_API_KEY_<NAZEV>=<klíč>  →  ./run.sh --account <nazev> <příkaz>   (viz Více účtů)
```

`.env` má práva 600 a je v `.gitignore`. Klíč nikdy neputuje v URL, jen v hlavičce `Authorization`.

### 3) Ověření a pojistka

```bash
./run.sh account            # název, měna, timezone, brand review, spend capy
./run.sh spend-limits       # žádné okno? →
./run.sh spend-limit-create --start 2026-09-02 --end 2026-10-01 --amount 500 --name "Září cap" --confirm
```

**Spend limit window je account-level strop útraty** (start inkluzivní, konec exkluzivní). Nastav ho, než na účet s kartou pustíš agenta. **Pozor:** na self-serve účtu endpoint zatím vrací 404 (2026-09-02) — pak je pojistkou denní budget kampaně (útrata může být až 2× za den) + `--end`, a `pulse` na sledování.

## Prerekvizity před první kampaní

ChatGPT Ads jsou systémová integrace, ne položka v mediaplánu. Než něco pustíš, musí sedět: schválený brand review + platební metoda, **spend limit window**, landing page dostupná pro **OAI-AdsBot** (robots.txt i WAF/CDN), **oppref přežije redirecty**, nasazené měření (pixel a/nebo Conversions API se sdíleným event id, consent hook, CSP) **napojené na kampaň** — i na CPC, jinak porovnáváš CPC místo ceny za zákazníka, u e-shopů feed s `is_ads_eligible` a automatickou synchronizací (položky expirují po 14 dnech). Pozor na založení účtu: osobní účet nemá právo zakládat ad accounty v tenantu — funguje firemní e-mail + pozvánka (viz playbook §7). Všechno kromě měření ověří `./run.sh landing-check --url …` a `./run.sh account`. Kompletní checklist, pravidla pro context hints (popisuj situace, ne klíčová slova), doporučené délky textů (~16 / ~32 znaků), bidding a fakturační pasti: [skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md](skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md).

## Více účtů (agentury)

Jeden ad account = jedna právní entita, země a měna; agentura nebo firma s víc značkami má tedy **víc účtů a víc klíčů**. Konvence, která brání nejhoršímu omylu (zápis na cizí účet):

1. **Jeden pojmenovaný klíč na účet** v `.env`: `OPENAI_ADS_API_KEY_ACME=…`, `OPENAI_ADS_API_KEY_BRANDX=…`. Název = slug klienta/značky. Bez „bare“ `OPENAI_ADS_API_KEY`, aby žádný účet nebyl implicitní.
2. **Každé volání říká účet**: `./run.sh --account acme campaigns`. Při 2+ nakonfigurovaných účtech CLI volání bez `--account` **odmítne** a vypíše, co je k dispozici. Jediný nakonfigurovaný účet se vybere sám; kdo chce výchozí, nastaví `OPENAI_ADS_DEFAULT_ACCOUNT=acme`. Aktivní účet se u víc účtů tiskne na stderr jako `[account: acme]`.
3. **Mapování projekt → účet nepatří do repa ani do sdíleného skillu** (je to klientské). Žije v privátní vrstvě: soubor `my-accounts.md` vedle skillu (šablona v [skill/INSTALL.md](skill/INSTALL.md)) nebo v projektové dokumentaci klienta. Skill se do něj podívá, a když projekt nemá řádek, **zeptá se** — nikdy nehádá.
4. **Před prvním zápisem `account`**: jméno účtu, měna a timezone v odpovědi musí sedět na klienta. Lokální stav (`.usage/`) je per účet, takže rate budget jednoho klienta neblokuje druhého.
5. Nový účet klienta: založí ho klient na svou entitu a pozve správce (viz playbook §7); klíč vydá v Ads Manageru účtu; správce ho uloží jako další `OPENAI_ADS_API_KEY_<NAZEV>` a přidá řádek do `my-accounts.md`.

## Kampaň z jednoho souboru (`plan-apply`)

```bash
cp docs/plan-example.json plan.json        # uprav: budget, end, location_ids, event setting, hints, texty, obrázek
./run.sh plan-apply --file plan.json       # dry-run: strom kampaně, délky textů, lint — nic se neposílá
./run.sh plan-apply --file plan.json --confirm   # založí kampaň → sestavy → reklamy (paused), resume přes plan.state.json
./run.sh campaign-detail --campaign-id cmpn_… --with-children   # ověření stromu + review
```

Plán umí i `"campaign": {"id": "cmpn_existing"}` (jen přidat sestavy a reklamy do existující kampaně), `defaults` pro sestavy/reklamy, `hints_file` (řádek = hint), sdílený `image_file` nebo `image_url`, `utm_content` per sestava přes `query_string_template`.

## Použití — konvence

- **Zápisy jsou defaultně dry-run**: příkaz vytiskne přesný request, který by poslal, a nic neodešle. `--confirm` provede. API nemá server-side `validate_only` pro jednotlivé objekty, takže dry-run = lokální lint + plán. Výjimky: `image-upload`/`file-upload` zapisují rovnou (jen média, žádná útrata); `bulk-submit` bez `--confirm` pošle **validační job** (`validate_only: true`, oficiálně nic nemění).
- **Vše vzniká `paused`** (`--status` default). Aktivace jen přes `*-activate` / `--status active` + `--confirm`.
- **Archivace je nevratná** (delete neexistuje). `*-archive` odmítne nezapauzovaný objekt bez `--force`.
- **Peníze v měně účtu** (`account` → `currency_code`, typicky USD). Flagy berou jednotky měny (`--lifetime-budget 250`), API dostane micros (×1 000 000). `--max-bid` je **per event**; pro CPM kampaně je pohodlnější `--max-cpm 40` (= 40 000 micros per impression). U oCPC je `--max-bid` CPA bid.
- **Časy**: `--start/--end` jako `YYYY-MM-DD`, ISO 8601 nebo unix sekundy. Insights okna se počítají v timezone účtu a defaultně končí **včerejškem** (dnešní atribuce je předběžná, budoucí meze API odmítá).
- **Idempotence**: každý create nese automaticky `Idempotency-Key` (vytiskne se); stejný request zopakuješ bezpečně přes `--idempotency-key <klíč>`. Zápisy bez idempotence CLI nikdy neretryuje a řekne ti, že zápis mohl projít.
- **Listy** skrývají `archived` (`--all` je ukáže, `--status` filtruje lokálně — API filtruje jen `name`); stránkují až do konce (`--max-items`).
- Programově parsuj jen `--json` (chyby jdou na stderr, stdout zůstává prázdný).
- Víc účtů: `--account <name>` (globální flag před příkazem) → `OPENAI_ADS_API_KEY_<NAME>`; při 2+ účtech je povinný (viz Více účtů).

### Ochrana účtu (rate limity)

API limituje **600 req/min na endpoint a 1 200 req/min celkem, per ad account i per IP**; bulk joby 10 / 10 s. Usage API nevrací, proto si CLI vede vlastní klouzavé okno v `.usage/` a od 80 % limitu čeká (`api-limits` ukáže stav; `OAIADS_IGNORE_RATE_BUDGET=1` vypne). 429 retryuje s ohledem na `Retry-After`. Nespouštěj víc instancí paralelně.

## Příkazy

### Účet

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `account` | Účet: status, brand review, měna, tz, negativní klíčová slova, spend capy | `--json` |
| `accounts` | Účty dostupné s tímto klíčem + lokálně nakonfigurované | |
| `brand-update` [write] | Název / URL / favicon účtu → nový brand review | `--name`, `--url`, `--favicon-file-id` |
| `negative-keywords` | Account-level negativní klíčová slova (na self-serve účtu zatím nedostupné — CLI to hlásí) | |
| `negative-keywords-set` [write] | **Nahradí** celý seznam (max 100 × 100 znaků) | `--keywords a,b`, `--keywords-file` |
| `negative-keywords-add` / `negative-keywords-remove` [write] | Přidá / odebere (read-modify-write) | `--keywords` |
| `spend-limits` | Spend limit windows (strop útraty účtu) | |
| `spend-limit-create` [write] | Nové okno (start inkluzivní, **end exkluzivní**) | `--start`, `--end`, `--amount`, `--name`, `--io-id` |
| `spend-limit-update` / `spend-limit-delete` [write] | Úprava / smazání okna | `--window-id` |
| `account-pause` / `account-activate` [write] | Pauza / aktivace celého účtu | |
| `api-limits` | Lokální budget vs. dokumentované limity | |
| `api-key-create` [write] | Další API klíč pro účet (zobrazí se jednou) | `--name` |
| `landing-check` | Lokální kontrola landing page: HTTP status pro browser i bot UA (WAF/CDN), HTML, favicon, robots.txt (OAI-AdsBot, OAI-SearchBot, `*`), captcha, **oppref přežije redirecty** | `--url` |

### Kampaně

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `campaigns` | Seznam (archived skryté) | `--status`, `--all`, `--name`, `--include-issues`, `--order`, `--wide` |
| `campaign-detail` | Detail vč. targetingu a serving issues; `--with-children` = celý strom (sestavy + reklamy + review) | `--campaign-id`, `--with-children` |
| `campaign-create` [write] | Nová kampaň (paused) | `--name`, `--lifetime-budget` / `--daily-budget`, `--bidding-type impressions\|clicks\|conversions`, `--countries CZ,SK`, `--location-ids`, `--exclude-location-ids`, `--audience-ids`, `--exclude-audience-ids`, `--platforms web,ios_app,android_app`, `--start`, `--end`, `--description`, `--conversion-event-setting-id` (napojení eventu pro reporting; u oCPC přesně jeden), `--mode` + `--product-feed-id` / `--business-agent-id`, `--query-string-template`, `--targeting-json` |
| `campaign-update` [write] | Úprava (budget = celý objekt, targeting se mergne); po zápisu dotáhne detail | totéž + `--campaign-id`, `--status`, `--clear-end-time`, `--clear-targeting` |
| `plan-apply` [write] | **Celá kampaň z jednoho JSON** (kampaň → sestavy → reklamy), dry-run = strom + lint, `--confirm` = sekvenční zápis s resume přes `plan.state.json` | `--file plan.json`, `--state` |
| `campaign-activate` / `campaign-pause` / `campaign-archive` [write] | Stavové přechody (archive nevratný, brzda na paused) | `--campaign-id`, `--force` |

`bidding_type`, `mode` a oCPC event setting **po vytvoření nejde změnit**.

### Ad groups

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `adgroups` | Seznam (volitelně po kampani) | `--campaign-id`, `--status`, `--all`, `--name`, `--include-issues` |
| `adgroup-detail` | Detail vč. biddingu, hints, product setu | `--ad-group-id`, `--with-children` |
| `adgroup-create` [write] | Nová ad group (paused); billing event se odvodí z kampaně | `--campaign-id`, `--name`, `--max-bid` (per event) / `--max-cpm`, `--billing-event impression\|click`, `--strategy fixed_bid\|maximize_clicks\|maximize_conversions`, `--hints "a, b"` (opak.), `--hints-file`, `--audience-multiplier caud=2.0`, `--product-feed-id` + `--product-filter brand:in:X\|Y`, `--product-set-json`, `--description`, `--query-string-template` |
| `adgroup-update` [write] | Úprava (bidding_config se pošle celý, hints se nahradí) | totéž + `--ad-group-id`, `--status` |
| `adgroup-activate` / `adgroup-pause` / `adgroup-archive` [write] | Stavové přechody | `--ad-group-id`, `--force` |

### Reklamy

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `ads` | Seznam po ad group / kampani / celém účtu | `--ad-group-id`, `--campaign-id`, `--review-status`, `--status`, `--all`, `--include-issues` |
| `ad-detail` | Detail vč. kreativy, review reason, appeal, issues | `--ad-id` |
| `ad-review` | Reklamy neschválené / se serving issues + důvody | `--ad-id`, `--campaign-id`, `--ad-group-id` |
| `ad-create` [write] | Nová reklama (paused) — `chat_card` nebo `product_ad_template`; lint titulku 3–50, body ≤ 100, URL | `--ad-group-id`, `--name`, `--title`, `--body`, `--target-url`, `--file-id` / `--image-url` / `--image-file`, `--price`, `--type`, `--crop x,y,w,h`, `--creative-json`, `--query-string-template` |
| `ad-update` [write] | Úprava (kreativa se pošle celá → re-review) | totéž + `--ad-id`, `--status` |
| `ad-preview` | Náhled (iframe, platí ~24 h) | `--ad-id`, `--out preview.html` |
| `ad-activate` / `ad-pause` / `ad-archive` [write] | Stavové přechody | `--ad-id`, `--force` |

### Soubory

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `image-upload` | Obrázek z URL nebo souboru → `file_id` (přímý zápis) | `--url` / `--file`, `--purpose account_favicon` |
| `file-upload` | Seznam zákazníků (.csv/.txt) → `file_id` + filename/mimetype/size pro audiences | `--file` |

### Insights & analýza

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `insights` | Výkon (impressions, clicks, spend, CTR, CPC, CPM) pro účet / kampaň / ad group / ad | `--level`, `--object-id`, `--aggregation-level`, `--granularity hourly\|daily\|monthly\|none`, `--since`, `--until`, `--days`, `--timezone`, `--fields`, `--filter JSON` (opak.), `--sort field:desc`, `--segment product\|country\|device`, `--segment-first`, `--include`, `--limit`, `--all` |
| `conversion-insights` | Atribuované konverze (click-through + view-through) | `--level`, `--ids`, `--granularity none\|daily`, `--breakdown device\|country`, `--group-by-entity`, `--include-zero`, `--since/--until/--days` |
| `pulse` | Digest účtu: období vs. předchozí, spend capy, review problémy, konverze | `--days` |

### Cílení

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `geo-search` | Hledání lokalit (country/region/DMA ids) | `--q`, `--country`, `--limit` |

### Custom audiences

Nejsou dostupné pro cílení na EEA/Švýcarsko. Membership operace jsou asynchronní a vyžadují `Idempotency-Key` (CLI generuje).

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `audiences` | Seznam / způsobilost pro účel | `--intended-use inclusion\|exclusion\|bid_multiplier`, `--ids`, `--granular`, `--all` |
| `audience-detail` | Stav, rozsahy počtů, membership revision | `--audience-id`, `--granular` |
| `audience-create` [write] | Ze souboru (`file-upload`) nebo prázdná | `--name`, `--file-id`, `--filename`, `--mimetype`, `--file-size`, `--identifier-type`, `--auto-resolve`, `--description` |
| `audience-add` / `audience-remove` [write] | Členové inline nebo souborem | `--audience-id`, `--identifiers email:a@b.cz,…`, `--identifiers-file`, `--identifier-type`, `--file-id`, `--expected-revision` |
| `audience-replace` [write] | Nahradí celé členství souborem | `--audience-id`, `--file-id`, `--expected-revision` |
| `audience-merge` [write] | 2–64 audiences → nová | `--name`, `--ids` |
| `audience-archive` [write] | Archivace (permanentní) | `--audience-id` |
| `audience-operation` | Poll operace | `--audience-id`, `--operation-id`, `--wait` |

### Konverze

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `pixels` | Konverzní zdroje (source id + pixel id) | |
| `conversion-check` | Audit měření: pixel → event setting → napojení na kampaň (→ poslední eventy) | `--events` |
| `pixel-create` [write] | Nový web pixel (gated per účet) | `--name` |
| `capi-key-create` [write] | Conversions API klíč (zobrazí se jednou, jen server-side) | `--name` |
| `event-settings` | Definice konverzí | `--all` |
| `event-setting-create` [write] | Nová definice (standardní event nebo custom) | `--name`, `--event-type`, `--custom-event-name`, `--source-id`, `--attribution-window` |
| `conversion-events` | Debug stream pixelu (posledních 15 min) | `--pid`, `--limit`, `--wide` |

### Produktové feedy

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `feeds` | Seznam feedů | `--with-counts` |
| `feed-create` / `feed-archive` [write] | Založení / archivace feedu | `--name`, `--countries` / `--feed-id` |
| `feed-uploads` | Poslední katalogové uploady + diagnostika | `--limit`, `--paginate` |
| `feed-products` | Náhled produktů podle filtrů | `--feed-id`, `--filter field:op:v`, `--limit`, `--after` |
| `feed-products-patch` [write] | Delta update dostupnosti/ceny/titulku variant | `--feed-id`, `--products-json` nebo `--product-id` + `--variant-id` + `--available` / `--availability-status` / `--price` (minor units) + `--currency` / `--title` |
| `feed-sftp` | SFTP přístup k feedu | `--feed-id` |
| `feed-sftp-create` [write] | Vytvoří / **rotuje** SFTP credentials (heslo jednou) | `--feed-id`, `--auth-method password\|ssh_key`, `--ssh-public-key` |
| `feed-sftp-activate` / `feed-sftp-pause` [write] | Zapnutí / pauza SFTP | `--feed-id` |

### Lead formuláře a lead sync

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `lead-forms` / `lead-form-detail` | Seznam / detail (i konkrétní revize) | `--all` / `--lead-form-id`, `--rev-id` |
| `lead-form-create` [write] | Draft formuláře (3–5 polí text/choice) | `--name`, `--fields-json`, `--privacy-url` |
| `lead-form-update` [write] | Nová draft revize | `--lead-form-id`, `--fields-json`, `--name`, `--privacy-url`, `--expected-draft-revision-id` |
| `lead-form-publish` / `lead-form-archive` [write] | Publikace / archivace | `--lead-form-id` |
| `lead-form-test` [write] | Syntetický podepsaný lead do webhooku | `--lead-form-id` |
| `lead-syncs` / `lead-sync-detail` | Webhook subscriptions | `--ad-account-id` / `--subscription-id` |
| `lead-sync-create` [write] | Doručování leadů na https webhook (signing secret jednou) | `--destination-url`, `--signing-secret` |
| `lead-sync-delete` [write] | Zrušení subscription | `--subscription-id` |

### Business Agents

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `business-agents` / `business-agent-detail` / `business-agent-tools` | Seznam / detail / dostupné nástroje | `--business-agent-id` |
| `business-agent-create` / `business-agent-update` [write] | Draft agenta (update = full replace) | `--name`, `--instructions` / `--instructions-file`, `--description`, `--starter` (opak.), `--feed-ids`, `--tools`, `--lead-form-id`, `--privacy-url` |
| `business-agent-preview` | Náhled odpovědi agenta | `--business-agent-id`, `--message user:…` (opak.) |
| `business-agent-publish` [write] | Publikace draftu | `--business-agent-id` |

### Bulk API (limited preview)

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `bulk-submit` [write] | Job z JSON souboru; bez `--confirm` = server-side validace | `--file ops.json`, `--no-partial-failure`, `--skip-validation`, `--wait` |
| `bulk-job` | Stav jobu | `--job-id`, `--wait` |
| `bulk-operations` | Výsledky jednotlivých operací | `--job-id` |

404 = účet nemá Bulk API zapnuté. Pole v bulk operacích se liší od REST (viz [docs/api-notes.md](docs/api-notes.md#bulk-api-limited-preview-mimo-spec)).

### Partner data & raw

| Příkaz | Co dělá | Klíčové flagy |
|---|---|---|
| `partner-data-upload-create` [write] / `partner-data-upload` | Registrace / stav partner-data uploadu (.parquet) | `--file`, `--snapshot-date` / `--upload-id` |
| `raw` [write pro ne-GET] | Libovolný endpoint: `raw GET /campaigns --params '{"limit":5}'` | `method path`, `--params`, `--body`, `--confirm` |

## Skill pro Claude Code (/chatgpt-ads)

Kanonická verze skillu je v repu: [skill/chatgpt-ads/SKILL.md](skill/chatgpt-ads/SKILL.md) (scénáře create / optimize / analyze / review-check / audiences / conversions / feeds / bulk + bezpečnostní pravidla), [skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md](skill/chatgpt-ads/chatgpt-ads-campaign-playbook.md) (prerekvizity, context hints, copy, bidy, měření, trh, fakturace, šablona briefu) a [skill/chatgpt-ads/chatgpt-ads-policies.md](skill/chatgpt-ads/chatgpt-ads-policies.md) (checklist Ad policies). Instalace: [skill/INSTALL.md](skill/INSTALL.md).

## Testy

Offline suite (žádné volání API, žádné credentials):

```bash
pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
python scripts/check_docs_consistency.py   # CLI ↔ README ↔ CLAUDE.md ↔ skill
```

## Dokumentace

- [docs/api-notes.md](docs/api-notes.md) — jak se Advertiser API chová (limity, stavy, review, peníze, insights, audiences, konverze, feedy, bulk, idempotence, chyby) + seznam věcí k ověření živě
- [CLAUDE.md](CLAUDE.md) — technický signpost pro Claude Code (struktura kódu, safety, release checklist)
- [CHANGELOG.md](CHANGELOG.md)
- Oficiální zdroje: [developers.openai.com/ads](https://developers.openai.com/ads), [OpenAPI spec](https://developers.openai.com/ads/openapi.json), [Ad policies](https://openai.com/policies/ad-policies/)

## Chyby a náměty

GitHub Issues v tomto repu. U chyb API přilož výstup s `--json` (klíč se do výstupů nikdy nedostane) a `x-request-id`, pokud ho CLI vytisklo.

## Licence

MIT — viz [LICENSE](LICENSE).
