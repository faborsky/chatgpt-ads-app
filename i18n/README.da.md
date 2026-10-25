# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · **🇩🇰 Dansk**

Et CLI til at oprette og overvåge annoncer i ChatGPT fra terminalen eller via en AI-agent, uden at klikke rundt i Ads Manager. Til marketingfolk og bureauer, der annoncerer på ChatGPT Ads og vil bygge og evaluere kampagner med Claude Code eller egne scripts.

Det dækker hele OpenAI Advertiser API v1 (101 kommandoer) og er bygget til at blive styret af en agent: skrivninger kører som dry-run som standard, alt oprettes på pause, og CLI'et holder sig selv inden for API-grænserne. Læsning og skrivning er verificeret i rigtig drift på en self-serve-konto.

Forfatter: [Jindřich Fáborský](https://www.faborsky.com)

## Hvad det gør

- Kampagner, annoncegrupper og annoncer: oprette, ændre, sætte på pause og arkivere, med lint mod specifikationens grænser og Ad policies.
- `plan-apply`: en hel kampagne fra én JSON-fil, med dry-run som træ og genoptagelse, hvis kørslen bliver afbrudt.
- `pulse`, `insights` og `conversion-insights`: resultater, attribuerede konverteringer og advarsler om afviste annoncer eller for lave bud.
- `landing-check` og `conversion-check`: tjekker landingssiden (OAI-AdsBot, robots.txt, omdirigeringer) og målingen før lancering.
- Flere konti til bureauer: med 2+ nøgler kræver CLI'et `--account`, så du aldrig skriver til den forkerte konto.
- Skill `/chatgpt-ads` til Claude Code med sikkerhedsregler (plan → godkendelse → skrivning).

## Hurtig start

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

Krav: Python 3.9+ og en API-nøgle fra OpenAI Ads Manager. Den fulde dokumentation (skaf adgang, alle 101 kommandoer, API-grænser) er på engelsk: **[README.md](../README.md)**.

## Licens

MIT · [LICENSE](../LICENSE)

## Forfatter

[Jindřich Fáborský](https://www.faborsky.com), marketingmand og underviser fra Prag. Jeg lærer marketingfolk at bygge deres egne værktøjer med AI.
