# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · **🇫🇷 Français** · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

CLI pour créer et suivre des annonces dans ChatGPT depuis le terminal ou via un agent IA, sans cliquer dans Ads Manager. Pour les marketeurs et les agences qui font de la pub sur ChatGPT Ads et veulent construire et analyser leurs campagnes avec Claude Code ou leurs propres scripts.

Il couvre toute l'OpenAI Advertiser API v1 (101 commandes) et il est conçu pour être piloté par un agent : les écritures sont en dry-run par défaut, tout démarre en pause et le CLI respecte lui-même les limites de l'API. Lectures et écritures vérifiées en conditions réelles sur un compte self-serve.

Auteur: [Jindřich Fáborský](https://www.faborsky.com)

## Ce qu'il fait

- Campagnes, groupes d'annonces et annonces : créer, modifier, mettre en pause et archiver, avec un lint contre les limites de la spec et les Ad policies.
- `plan-apply` : une campagne entière à partir d'un seul fichier JSON, avec dry-run en arbre et reprise après une interruption.
- `pulse`, `insights` et `conversion-insights` : performances, conversions attribuées et alertes sur les annonces refusées ou les enchères trop basses.
- `landing-check` et `conversion-check` : vérifient la landing page (OAI-AdsBot, robots.txt, redirections) et la mesure avant le lancement.
- Plusieurs comptes pour les agences : dès 2 clés, le CLI exige `--account` pour ne jamais écrire sur le mauvais compte.
- Skill `/chatgpt-ads` pour Claude Code avec des règles de sécurité (plan → validation → écriture).

## Démarrage rapide

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

Prérequis : Python 3.9+ et une clé API d'OpenAI Ads Manager. La documentation complète (obtenir l'accès, les 101 commandes, limites de l'API) est en anglais : **[README.md](../README.md)**.

## Licence

MIT · [LICENSE](../LICENSE)

## Auteur

[Jindřich Fáborský](https://www.faborsky.com), marketeur et formateur à Prague. J'apprends aux marketeurs à créer leurs propres outils avec l'IA.
