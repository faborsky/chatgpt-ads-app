# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · **🇸🇪 Svenska** · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

Ett CLI för att skapa och bevaka annonser i ChatGPT från terminalen eller via en AI-agent, utan att klicka runt i Ads Manager. För marknadsförare och byråer som annonserar på ChatGPT Ads och vill bygga och utvärdera kampanjer med Claude Code eller egna skript.

Det täcker hela OpenAI Advertiser API v1 (101 kommandon) och är byggt för att styras av en agent: skrivningar körs som dry-run som standard, allt skapas pausat och CLI:t håller sig själv inom API-gränserna. Läsning och skrivning är verifierade i skarp drift på ett self-serve-konto.

Författare: [Jindřich Fáborský](https://www.faborsky.com)

## Vad det gör

- Kampanjer, annonsgrupper och annonser: skapa, ändra, pausa och arkivera, med lint mot specens gränser och Ad policies.
- `plan-apply`: en hel kampanj från en enda JSON-fil, med dry-run som träd och återupptagning om körningen avbryts.
- `pulse`, `insights` och `conversion-insights`: resultat, attribuerade konverteringar och varningar för avvisade annonser eller för låga bud.
- `landing-check` och `conversion-check`: kontrollerar landningssidan (OAI-AdsBot, robots.txt, omdirigeringar) och mätningen före lansering.
- Flera konton för byråer: med 2+ nycklar kräver CLI:t `--account`, så att du aldrig skriver till fel konto.
- Skill `/chatgpt-ads` för Claude Code med säkerhetsregler (plan → godkännande → skrivning).

## Snabbstart

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

Krav: Python 3.9+ och en API-nyckel från OpenAI Ads Manager. Den fullständiga dokumentationen (skaffa åtkomst, alla 101 kommandon, API-gränser) finns på engelska: **[README.md](../README.md)**.

## Licens

MIT · [LICENSE](../LICENSE)

## Författare

[Jindřich Fáborský](https://www.faborsky.com), marknadsförare och utbildare från Prag. Jag lär marknadsförare att bygga egna verktyg med AI.
