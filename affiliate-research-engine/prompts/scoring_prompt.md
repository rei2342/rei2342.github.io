あなたはアフィリエイト案件評価の専門家です。
以下の全分析結果をもとに、この案件の総合スコアを算出してください。

## 案件情報
{case_summary}

## LP分析
{lp_analysis}

## 市場分析
{market_analysis}

## 購買トリガー
{buying_triggers}

## SNS適性
{sns_fit}

## リスク分析
{risk_analysis}

## スコアリング基準

### affiliate_score（0〜100）
SNSアフィリエイトとして総合的に稼ぎやすいかを評価する。

各項目を0〜10で評価して合計から算出すること。
- reward_value: 報酬単価の高さ・コスパ
- approval_ease: 承認されやすさ・成果条件の緩さ
- sns_narratability: SNSで語りやすいか・ストーリー化できるか
- testimonial_ease: 体験談として自然に語れるか
- pain_depth: 解決する悩みの深さ・切実さ
- urgency: 今すぐ欲しくなる即効性・緊急性
- differentiation: 競合との差別化余地
- continuation_ease: 継続投稿・長期運用しやすいか
- compliance_safety: 規約・表現リスクの低さ

### platform_fit_scores（各0〜100）
各媒体でのアフィリエイト成果創出可能性。
sns_fitのscoreを参考に、収益化可能性として評価する。

## 出力形式
以下のJSONのみを返してください。

{
  "affiliate_score": 75,
  "platform_fit_scores": {
    "x": 85,
    "threads": 70,
    "tiktok": 60,
    "instagram": 45,
    "note": 70
  },
  "score_breakdown": {
    "reward_value": 8,
    "approval_ease": 7,
    "sns_narratability": 9,
    "testimonial_ease": 8,
    "pain_depth": 9,
    "urgency": 8,
    "differentiation": 7,
    "continuation_ease": 7,
    "compliance_safety": 7
  },
  "score_reasoning": "スコアの根拠を100字以内で"
}
