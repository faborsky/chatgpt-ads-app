# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · **🇳🇴 Norsk** · [🇩🇰 Dansk](README.da.md)

Et CLI for å opprette og følge med på annonser i ChatGPT fra terminalen eller via en AI-agent, uten å klikke rundt i Ads Manager. For markedsførere og byråer som annonserer på ChatGPT Ads og vil bygge og evaluere kampanjer med Claude Code eller egne skript.

Det dekker hele OpenAI Advertiser API v1 (101 kommandoer) og er laget for å styres av en agent: skriving kjøres som dry-run som standard, alt opprettes pauset, og CLI-et holder seg selv innenfor API-grensene. Lesing og skriving er verifisert i ekte drift på en self-serve-konto.

Forfatter: [Jindřich Fáborský](https://www.faborsky.com)

## Hva det gjør

- Kampanjer, annonsegrupper og annonser: opprette, endre, pause og arkivere, med lint mot spesifikasjonens grenser og Ad policies.
- `plan-apply`: en hel kampanje fra én JSON-fil, med dry-run som tre og gjenopptak hvis kjøringen avbrytes.
- `pulse`, `insights` og `conversion-insights`: resultater, attribuerte konverteringer og varsler om avviste annonser eller for lave bud.
- `landing-check` og `conversion-check`: sjekker landingssiden (OAI-AdsBot, robots.txt, omdirigeringer) og målingen før lansering.
- Flere kontoer for byråer: med 2+ nøkler krever CLI-et `--account`, så du aldri skriver til feil konto.
- Skill `/chatgpt-ads` for Claude Code med sikkerhetsregler (plan → godkjenning → skriving).

## Hurtigstart

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

Krav: Python 3.9+ og en API-nøkkel fra OpenAI Ads Manager. Den fullstendige dokumentasjonen (skaffe tilgang, alle 101 kommandoer, API-grenser) er på engelsk: **[README.md](../README.md)**.

## Lisens

MIT · [LICENSE](../LICENSE)

## Forfatter

[Jindřich Fáborský](https://www.faborsky.com), markedsfører og underviser fra Praha. Jeg lærer markedsførere å bygge egne verktøy med AI.
