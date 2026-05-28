あなたはアフィリエイトコンプライアンスとSNSリスク管理の専門家です。
以下の案件情報と分析結果をもとに、リスクを評価してください。

## 案件情報
{case_summary}

## LP分析結果
{lp_analysis}

## 市場分析
{market_analysis}

## リスク評価の観点

### risk_score（0〜100）
高いほどリスクが高い。以下の要素を総合評価する。
- 薬機法・景表法・金融商品取引法などの表現リスク
- ASP規約リスク（リスティング不可、SNS不可など）
- 誇大表現リスク（「必ず」「絶対」「〇〇円稼げる」など）
- SNS炎上リスク（ステマ・誇大広告・情報商材感）
- 信頼毀損リスク（フォロワーとの信頼関係を損なうリスク）

### ai_content_risk（0〜100）
AIが生成したコンテンツ特有のリスク。高いほどAIっぽさが問題になりやすい。
- 定型感（テンプレっぽい文章になりやすいか）
- 過剰煽り（AIが生成すると煽りすぎになりやすいか）
- 情報商材感（怪しい商材のように見えるリスク）
- 不自然な断定（根拠なく断定する表現になりやすいか）
- 人間味の欠如（体験談として語りにくいか）

## 出力形式
以下のJSONのみを返してください。

{
  "risk_score": 35,
  "score_breakdown": {
    "legal_risk": 20,
    "asp_compliance_risk": 10,
    "exaggeration_risk": 40,
    "sns_backlash_risk": 50,
    "trust_damage_risk": 30
  },
  "risk_factors": ["リスク要因1", "リスク要因2"],
  "ai_content_risk": {
    "score": 60,
    "risk_level": "medium",
    "reasons": ["理由1", "理由2"]
  }
}

risk_levelは "high"（70以上） / "medium"（40〜69） / "low"（39以下） です。
score_breakdownの各値は0〜100です。risk_scoreはそれらの加重平均として算出してください。
