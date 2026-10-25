# ChatGPT Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · **🇯🇵 日本語** · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

ChatGPT の広告を、ターミナルから、または AI エージェント経由で作成・監視できる CLI です。Ads Manager で何度もクリックする必要はありません。ChatGPT Ads に出稿していて、Claude Code や自作スクリプトでキャンペーンを組み立て・評価したいマーケターや代理店向けです。

OpenAI Advertiser API v1 全体（101 コマンド）をカバーし、エージェントが操作することを前提に作られています。書き込みはデフォルトで dry-run、作成したものはすべて一時停止状態で始まり、API の上限も CLI 自身が守ります。読み取りと書き込みはセルフサーブ（self-serve）アカウントの実運用で検証済みです。

作者：[Jindřich Fáborský](https://www.faborsky.com)

## できること

- キャンペーン、広告グループ、広告の作成・編集・一時停止・アーカイブ。仕様上の制限と Ad policies に対する lint 付き。
- `plan-apply`：1 つの JSON からキャンペーン全体を作成。dry-run はツリー表示で、中断しても再開できます。
- `pulse`、`insights`、`conversion-insights`：成果、アトリビューションされたコンバージョン、却下された広告や低すぎる入札の警告。
- `landing-check` と `conversion-check`：公開前にランディングページ（OAI-AdsBot、robots.txt、リダイレクト）と計測をチェック。
- 代理店向けの複数アカウント：キーが 2 つ以上あると CLI は `--account` を必須にし、別アカウントへの誤書き込みを防ぎます。
- Claude Code 用スキル `/chatgpt-ads`（計画 → 承認 → 書き込みの安全ルール付き）。

## クイックスタート

```bash
git clone https://github.com/faborsky/chatgpt-ads-app.git
cd chatgpt-ads-app
./setup.sh          # creates .venv, installs dependencies, creates .env
# fill in .env (see the full English docs)
./run.sh account    # smoke test
```

必要なもの：Python 3.9+ と OpenAI Ads Manager の API キー。完全なドキュメント（アクセスの取得方法、全 101 コマンド、API の上限）は英語です：**[README.md](../README.md)**

## ライセンス

MIT · [LICENSE](../LICENSE)

## 作者

[Jindřich Fáborský](https://www.faborsky.com)、プラハ在住のマーケター・講師。マーケターが AI で自分のツールを作れるよう教えています。
