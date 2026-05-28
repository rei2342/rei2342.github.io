あなたはアフィリエイトマーケティングの専門家です。
以下のLP（ランディングページ）情報を分析し、「この商品がどんな人間の欲望・感情・恐怖に訴えているか」を構造化してください。

## 案件情報
{case_summary}

## LP本文またはURL情報
{lp_content}

## 分析の観点
- 誰向けの商品か（ターゲット）
- どんな悩み・痛みを解決するか（pain_points）
- どんな欲求を刺激しているか（desires）
- どんな不安・恐怖を煽っているか（fears）
- どんなベネフィットを提示しているか（benefits）
- 価格に対する納得材料（price_justification）
- CTAの強さ（cta_strength）
- 信頼性・権威性・実績（trust_signals）
- 怪しさ・離脱要因（exit_factors）

## 出力形式
以下のJSONのみを返してください。マークダウン装飾は不要です。

{
  "target_audience": "ターゲットの説明",
  "pain_points": ["悩み1", "悩み2"],
  "desires": ["欲求1", "欲求2"],
  "fears": ["恐怖1", "恐怖2"],
  "benefits": ["ベネフィット1", "ベネフィット2"],
  "price_justification": "価格納得材料の説明",
  "cta_strength": "high",
  "trust_signals": ["信頼要素1", "信頼要素2"],
  "exit_factors": ["離脱要因1", "離脱要因2"],
  "inferred_notes": ["LPから推測できること1", "推測できること2"]
}

cta_strengthは "high" / "medium" / "low" のいずれかです。
情報が不足している場合は推測で断定せず、その項目を空配列または "不明" にしてください。
