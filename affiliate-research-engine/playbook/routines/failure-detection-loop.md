# Routine: Failure Detection Loop（テク35）

反応が悪い記事を自動検知して改修案を出す。

## スケジュール
毎週金曜 10:00

## プロンプト
```
①アクセス解析(GA4等)から過去30日のPV/CVデータを取得する。
  解析MCP/API未接続なら手元のエクスポートCSVを ./workspace/reports/ に置いて読む。
②過去90日比でPVが30%以上下落した記事を抽出する。
③各記事について:
  ・原因仮説(SEO / トレンド / 競合)
  ・改修方向性3つ
  ・工数見積
  をまとめる。
④優先度順(下落幅×収益寄与)に並べて ./workspace/reports/failure-YYYY-MM-DD.md に保存する。
```

## 依存
- 任意: アクセス解析MCP/API（なければ手動エクスポート）
- 任意: Slack MCP
