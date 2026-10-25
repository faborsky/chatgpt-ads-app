# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · **🇧🇷 Português** · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

CLI para criar e acompanhar anúncios no ChatGPT pelo terminal ou por meio de um agente de IA, sem clicar no Ads Manager. Para profissionais de marketing e agências que anunciam no ChatGPT Ads e querem montar e avaliar campanhas com o Claude Code ou com scripts próprios.

Cobre a OpenAI Advertiser API v1 inteira (101 comandos) e foi feito para ser operado por um agente: toda escrita é dry-run por padrão, tudo nasce pausado e a CLI respeita sozinha os limites da API. Leituras e gravações verificadas em uso real em uma conta self-serve.

Autor: [Jindřich Fáborský](https://www.faborsky.com)

## O que ele faz

- Campanhas, grupos de anúncios e anúncios: criar, editar, pausar e arquivar, com lint contra os limites da especificação e as Ad policies.
- `plan-apply`: uma campanha inteira a partir de um único JSON, com dry-run em árvore e retomada se for interrompido.
- `pulse`, `insights` e `conversion-insights`: desempenho, conversões atribuídas e alertas de anúncios reprovados ou lances baixos demais.
- `landing-check` e `conversion-check`: verifica a landing page (OAI-AdsBot, robots.txt, redirecionamentos) e a mensuração antes do lançamento.
- Várias contas para agências: com 2+ chaves a CLI exige `--account`, para nunca gravar na conta errada.
- Skill `/chatgpt-ads` para o Claude Code com regras de segurança (plano → aprovação → gravação).

## Início rápido

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

Requisitos: Python 3.9+ e uma chave de API do OpenAI Ads Manager. A documentação completa (como obter o acesso, os 101 comandos, limites da API) está em inglês: **[README.md](../README.md)**.

## Licença

MIT · [LICENSE](../LICENSE)

## Autor

[Jindřich Fáborský](https://www.faborsky.com), profissional de marketing e educador de Praga. Ensino profissionais de marketing a criar suas próprias ferramentas com IA.
