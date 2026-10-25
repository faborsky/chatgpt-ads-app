# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · **🇨🇳 简体中文** · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

一个命令行工具：在终端里或通过 AI 智能体创建和监控 ChatGPT 广告，不用在 Ads Manager 里来回点击。适合在 ChatGPT Ads 上投放广告、想用 Claude Code 或自己的脚本搭建和评估广告系列的营销人员和代理公司。

它覆盖完整的 OpenAI Advertiser API v1（101 个命令），专为由智能体操作而设计：所有写入默认是 dry-run，所有对象都以暂停状态创建，CLI 会自己控制在 API 限额内。读取和写入均已在一个自助（self-serve）账户的实际投放中验证。

作者：[Jindřich Fáborský](https://www.faborsky.com)

## 功能

- 广告系列、广告组和广告：创建、修改、暂停、归档，并按规范限制和 Ad policies 做 lint 检查。
- `plan-apply`：用一个 JSON 文件建好整个广告系列，dry-run 以树状显示，中断后可续跑。
- `pulse`、`insights` 和 `conversion-insights`：效果数据、归因转化，以及被拒广告和出价过低的提醒。
- `landing-check` 和 `conversion-check`：上线前检查落地页（OAI-AdsBot、robots.txt、重定向）和转化跟踪。
- 代理公司多账户：配置 2 个以上密钥时 CLI 强制要求 `--account`，避免写错账户。
- 适用于 Claude Code 的 `/chatgpt-ads` 技能，内置安全规则（计划 → 批准 → 写入）。

## 快速开始

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

环境要求：Python 3.9+ 和 OpenAI Ads Manager 的 API 密钥。完整文档（获取访问权限、全部 101 个命令、API 限额）为英文：**[README.md](../README.md)**。

## 许可证

MIT · [LICENSE](../LICENSE)

## 作者

[Jindřich Fáborský](https://www.faborsky.com)，来自布拉格的营销人和讲师，教营销人员用 AI 自己做工具。
