あなたはSNSアフィリエイトマーケティングの市場分析専門家です。
以下の案件情報・SNS例・競合事例をもとに、「この欲望はSNSで燃えるか」を分析してください。

## 案件情報
{case_summary}

## LP分析結果
{lp_analysis}

## SNS投稿例
{sns_examples}

## 競合事例
{competitor_examples}

## 分析項目
- demand_strength: 需要の強さ（ユーザーが今すぐ解決したい問題か）
- sns_compatibility: SNSとの相性（感情・ストーリー・拡散可能性）
- search_demand: 検索需要の有無（能動的に調べる人がいるか）
- trend: トレンド性（growing / stable / declining）
- seasonality: 季節性（あれば説明、なければnull）
- competition_level: 競合の多さ（high / medium / low）
- beginner_friendly: 初心者でも売りやすいか（true / false）
- testimonial_convertible: 体験談として語りやすいか（true / false）

## 出力形式
以下のJSONのみを返してください。

{
  "demand_strength": "high",
  "sns_compatibility": "high",
  "search_demand": "medium",
  "trend": "growing",
  "seasonality": null,
  "competition_level": "medium",
  "beginner_friendly": true,
  "testimonial_convertible": true,
  "reasoning": "分析の根拠を100字以内で説明"
}

demand_strength / sns_compatibility / search_demand / competition_level は "high" / "medium" / "low" のいずれかです。
trend は "growing" / "stable" / "declining" のいずれかです。
