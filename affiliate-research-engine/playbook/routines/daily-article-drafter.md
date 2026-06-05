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
⑥./workspace/drafts/ に保存する。
  Notion MCP が使えるなら「案件管理」DB（ID: 375e0ec8-90e1-80cf-b15d-f1360a14ce33）の
  該当案件の「メモ」列に「ドラフト生成済: <タイトル> YYYY-MM-DD」と追記する。
```

## 依存
- `workspace/keyword-queue/` または `workspace/keywords.csv`（初期キーワード投入済み）
- `../CLAUDE.md`（Track B: 英語コーチング・留学）
- Notion MCP（.mcp.json 設定済み）
