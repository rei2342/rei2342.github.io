# Routine: Weekly SERP Watcher（テク33）

順位変動を週次で監視し、下落キーワードのリライト候補を出す。

## スケジュール
毎週月曜 09:00

## プロンプト
```
①./workspace/keywords.csv の全キーワードについて現在の検索順位を取得する。
②前週比(last_rank列)で5位以上下落したキーワードを抽出する。
③下落キーワードごとに、上位記事との差分を分析する:
  見出し構造 / 文字数 / E-E-A-T要素 の3点。
④優先度順(下落幅×想定収益)にリライト候補レポートを作る。
⑤./workspace/reports/serp-YYYY-MM-DD.md に保存し、Slackに通知する。
⑥keywords.csv の last_rank と checked_at を最新値に更新する。
```

## 依存
- `workspace/keywords.csv`（用意済み。順位は手入力か順位取得MCP/API）
- 任意: Slack MCP
