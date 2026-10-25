# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · **🇪🇸 Español** · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

CLI para crear y vigilar anuncios en ChatGPT desde la terminal o a través de un agente de IA, sin hacer clic en Ads Manager. Para marketers y agencias que anuncian en ChatGPT Ads y quieren montar y evaluar campañas con Claude Code o con sus propios scripts.

Cubre la OpenAI Advertiser API v1 completa (101 comandos) y está pensado para que lo maneje un agente: todas las escrituras son dry-run por defecto, todo nace en pausa y la CLI respeta sola los límites de la API. Lecturas y escrituras verificadas en uso real en una cuenta self-serve.

Autor: [Jindřich Fáborský](https://www.faborsky.com)

## Qué hace

- Campañas, grupos de anuncios y anuncios: crear, editar, pausar y archivar, con lint contra los límites de la especificación y las Ad policies.
- `plan-apply`: una campaña entera desde un solo JSON, con dry-run en árbol y reanudación si se interrumpe.
- `pulse`, `insights` y `conversion-insights`: rendimiento, conversiones atribuidas y avisos de anuncios rechazados o pujas demasiado bajas.
- `landing-check` y `conversion-check`: revisa la landing page (OAI-AdsBot, robots.txt, redirecciones) y la medición antes del lanzamiento.
- Varias cuentas para agencias: con 2+ claves la CLI exige `--account`, para no escribir nunca en la cuenta equivocada.
- Skill `/chatgpt-ads` para Claude Code con reglas de seguridad (plan → aprobación → escritura).

## Inicio rápido

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

Requisitos: Python 3.9+ y una clave de API de OpenAI Ads Manager. La documentación completa (cómo conseguir el acceso, los 101 comandos, límites de la API) está en inglés: **[README.md](../README.md)**.

## Licencia

MIT · [LICENSE](../LICENSE)

## Autor

[Jindřich Fáborský](https://www.faborsky.com), marketer y formador de Praga. Enseño a los marketers a crear sus propias herramientas con IA.
