# Routine: Daily Article Drafter（テク31）

毎朝1本のドラフトを自動生成して `workspace/drafts/` に置く。

## 登録手順
1. Claude Code で `/schedule` を実行
2. スケジュールを「毎日 06:00」に設定
3. 下のプロンプトを貼る

## スケジュール
毎日 06:00

## プロンプト
```
①./workspace/keyword-queue/ から本日分のキーワードを1件取得する。
  キューが空なら ./workspace/keywords.csv の status=todo から1件選ぶ。
②そのキーワードでSERP上位10件の見出し構造を分析する。
  - 共通する見出し構造 / よく言及される論点トップ5 / 抜け穴を5つ
③上位を抜く独自構造(H2×6, H3×各3)を組み、4000字のドラフトを生成する。
  生成時は以下のNGを厳守:
  ・「〜について」「〜することが大切」禁止
  ・3文字熟語の連発禁止 / 冒頭の挨拶禁止
  ・箇条書きの羅列で逃げない / 同じ語尾を3回連続使わない
④CLAUDE.md の「稼働中の案件」「主要ペルソナ」「NGの訴求軸」を参照し、
  ペルソナに合った実体験ディテール(数字・固有名詞)を差し込む。
⑤./workspace/drafts/YYYY-MM-DD.md として保存する。
⑥完成したら Slack MCP で「本日のドラフト完成: <タイトル>」と通知する。
  Slack未接続なら ./workspace/drafts/ に保存するだけでよい。
```

## 依存
- `workspace/keyword-queue/` または `workspace/keywords.csv`（用意済み）
- `../CLAUDE.md`（メモリ）
- 任意: Slack MCP
