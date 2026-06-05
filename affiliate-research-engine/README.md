# Affiliate Research Engine v1

人間の欲望・感情・購買トリガーを分析し、SNSで収益化可能な導線を研究・蓄積するOS。

## セットアップ

```bash
cd affiliate-research-engine
pip install -r requirements.txt
cp .env.example .env  # APIキーを設定
```

`.env` ファイル:
```
LLM_BACKEND=claude          # "claude" or "openai"
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...       # OpenAI使用時のみ
```

## 使い方

### 1. 案件分析

```bash
python main.py analyze-case --input data/cases/sample_case.json
```

出力: `outputs/cases/{case_name}_{timestamp}.json`

### 2. 投稿案生成

分析済みファイルを開き、`appeals` の中から使いたい `appeal_id` をコピーする。

```bash
python main.py generate-posts \
  --input outputs/cases/sample_ai_tool_20260528_120000.json \
  --appeal-ids "uuid-1,uuid-2,uuid-3" \
  --platform x
```

対応媒体: `x` / `threads` / `tiktok` / `instagram` / `note`

生成した投稿案は同じJSONの `generated_posts[]` に追記保存される。

## 入力データ形式

`data/cases/sample_case.json` を参照。

```json
{
  "case_name": "案件名",
  "affiliate_url": "https://example.com",
  "lp_text": "LP本文をここに貼る",
  "asp_name": "A8",
  "reward": 3000,
  "category": "AIツール",
  "conversion_condition": "無料登録",
  "restrictions": "SNS投稿可。リスティング不可。",
  "sns_allowed": true,
  "listing_allowed": false,
  "pr_required": true,
  "sns_examples": ["伸びている投稿例"],
  "competitor_examples": ["競合記事や投稿"]
}
```

## 運用フロー（最小PDCA）

```
1. 案件JSON作成 → analyze-case 実行（分析）
2. outputs/ のJSONを開き、appeals を確認
3. human_feedback.status を "selected" に変更（人間レビュー）
4. generate-posts 実行（投稿案生成）
5. 手動で投稿
6. 実績を performance / generated_posts[].performance に記録
```

## 出力JSON構造

| フィールド | 内容 |
|-----------|------|
| `information_quality` | confirmed / inferred / missing の情報品質分類 |
| `lp_analysis` | LP訴求・悩み・ベネフィット分析 |
| `market_analysis` | 需要・SNS相性・トレンド分析 |
| `buying_triggers` | 購買トリガーの構造化（強さ・理由付き） |
| `emotion_analysis` | primary / secondary 感情分類 |
| `sns_fit` | 5媒体の適性スコア（1-5）と理由 |
| `algorithm_fit_reason` | 媒体別アルゴリズム適性の説明 |
| `scores` | affiliate_score / platform_fit_scores / risk_score |
| `ai_content_risk` | AIコンテンツリスクスコアと理由 |
| `appeals` | 10カテゴリ×10件の訴求フック（合計100件） |
| `generated_posts` | generate-posts で生成した投稿案 |
| `human_feedback` | 採用・却下・メモ（手動記入） |
| `performance` | 投稿後の実績データ（手動記入） |

## ディレクトリ構成

```
affiliate-research-engine/
├── main.py                    # CLI
├── config.py                  # 設定
├── requirements.txt
├── core/
│   ├── llm_client.py          # LLM呼び出し（Claude/OpenAI差し替え可）
│   ├── input_loader.py        # 入力バリデーション・information_quality生成
│   └── storage.py             # ファイルI/O（将来DB移行の窓口）
├── analyzers/
│   ├── lp_analyzer.py
│   ├── market_analyzer.py
│   ├── buying_trigger_analyzer.py
│   ├── sns_fit_analyzer.py
│   └── risk_analyzer.py
├── generators/
│   ├── appeal_generator.py
│   ├── post_generator.py
│   └── report_generator.py
├── prompts/                   # LLMプロンプトテンプレート
├── data/cases/                # 入力データ
└── outputs/cases/             # 分析結果JSON
```

## Phase2以降のロードマップ

- CSV一括インポート（複数案件を一度に処理）
- 案件比較レポート（ランキング生成）
- SQLiteによるローカルDB化
- performance 蓄積後の予測精度評価
- SNS API連携（X API v2 / Threads API）
