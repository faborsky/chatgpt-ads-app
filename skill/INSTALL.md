# Instalace skillu /chatgpt-ads do Claude Code

Skill je v repu v jediné kanonické verzi (`skill/chatgpt-ads/`) — instalace = kopie + dosazení cesty k appce.

## 1. Zkopíruj skill

```bash
cp -r <cesta-k-repu>/skill/chatgpt-ads ~/.claude/skills/chatgpt-ads
```

## 2. Dosaď cestu k appce

Skill volá CLI přes placeholder `<CHATGPT_ADS_APP_DIR>`. Nahraď ho skutečnou cestou:

```bash
APP_DIR="$HOME/dev/chatgpt-ads-app"   # uprav na svou cestu
sed -i '' "s#<CHATGPT_ADS_APP_DIR>#$APP_DIR#g" ~/.claude/skills/chatgpt-ads/SKILL.md   # macOS
# Linux: sed -i "s#<CHATGPT_ADS_APP_DIR>#$APP_DIR#g" ~/.claude/skills/chatgpt-ads/SKILL.md
```

## 3. Ověř

V Claude Code spusť `/chatgpt-ads` — bare volání spustí přehled účtu (`run.sh pulse`). Pokud skill hlásí, že `<CHATGPT_ADS_APP_DIR>` je stále v souboru, krok 2 se nepovedl.

## Doplň si vlastní know-how (volitelné, doporučené)

Skill je záměrně generický — mechanika, bezpečnostní pravidla a policy checklist, žádná strategie. Vlastní playbook (cílové CPC/CPA, jaké context hints fungují, zakázané postupy…) přidej jako další soubor do `~/.claude/skills/chatgpt-ads/` (např. `my-strategy.md`) a připiš ho do sekce **Load Reference Documents** v SKILL.md. Při aktualizaci skillu z repa se tvůj soubor nepřepíše — přepisuj jen SKILL.md a chatgpt-ads-policies.md.

## Víc účtů (agentury, víc značek): `my-accounts.md`

Každý ad account má vlastní klíč (`OPENAI_ADS_API_KEY_<NAZEV>` v `.env`) a skill musí vědět, který projekt patří ke kterému. Mapování je klientské, proto **nepatří do repa** — založ si ho vedle skillu (soubor se při aktualizaci skillu nepřepíše):

```markdown
# my-accounts.md — projekt → účet (privátní, mimo git)

| Projekt / klient | `--account` | Měna | Timezone | Poznámka |
|---|---|---|---|---|
| Acme e-shop | acme | EUR | Europe/Prague | pixel px_…, kontakt: … |
| BrandX | brandx | USD | America/New_York | oCPC na order_created |

Pravidla: každé volání s `--account`; před prvním zápisem `account` a zkontrolovat název/měnu; projekt bez řádku = zeptat se.
```

Skill si soubor načte ze sekce **Load Reference Documents** a při 2+ účtech odmítne pracovat bez jasného `--account` (stejně jako CLI).

## Aktualizace

Nová verze appky může přinést i novou verzi skillu — po `git pull` zopakuj kroky 1–2 (svoje vlastní reference soubory zachovej).
