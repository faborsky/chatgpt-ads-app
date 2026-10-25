# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · **🇩🇪 Deutsch** · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

CLI, mit dem du Anzeigen in ChatGPT aus dem Terminal oder über einen KI-Agenten anlegst und überwachst, ohne dich durch den Ads Manager zu klicken. Für Marketer und Agenturen, die auf ChatGPT Ads werben und Kampagnen mit Claude Code oder eigenen Skripten aufbauen und auswerten wollen.

Es deckt die komplette OpenAI Advertiser API v1 ab (101 Befehle) und ist dafür gebaut, dass ein Agent es bedient: Schreibvorgänge laufen standardmäßig als Dry-Run, alles startet pausiert, und das CLI hält die API-Limits selbst ein. Lesen und Schreiben sind im Live-Betrieb auf einem Self-Serve-Konto verifiziert.

Autor: [Jindřich Fáborský](https://www.faborsky.com)

## Was es kann

- Kampagnen, Anzeigengruppen und Anzeigen anlegen, ändern, pausieren und archivieren, mit Lint gegen Spec-Limits und Ad policies.
- `plan-apply`: eine ganze Kampagne aus einer einzigen JSON-Datei, mit Dry-Run als Baum und Fortsetzung nach einem Abbruch.
- `pulse`, `insights` und `conversion-insights`: Performance, attribuierte Conversions und Warnungen bei abgelehnten Anzeigen oder zu niedrigen Geboten.
- `landing-check` und `conversion-check`: prüfen vor dem Start Landingpage (OAI-AdsBot, robots.txt, Weiterleitungen) und Tracking.
- Mehrere Konten für Agenturen: ab 2 Schlüsseln verlangt das CLI `--account`, damit nie aufs falsche Konto geschrieben wird.
- Skill `/chatgpt-ads` für Claude Code mit Sicherheitsregeln (Plan → Freigabe → Schreiben).

## Schnellstart

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

Voraussetzungen: Python 3.9+ und ein API-Schlüssel aus dem OpenAI Ads Manager. Die vollständige Dokumentation (Zugang einrichten, alle 101 Befehle, API-Limits) gibt es auf Englisch: **[README.md](../README.md)**.

## Lizenz

MIT · [LICENSE](../LICENSE)

## Autor

[Jindřich Fáborský](https://www.faborsky.com), Marketer und Dozent aus Prag. Ich bringe Marketern bei, mit KI eigene Tools zu bauen.
