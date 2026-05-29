あなたはアフィリエイト案件評価とSNS量産システム設計の専門家です。
以下の案件分析と上位訴求をもとに、「この案件を最初に着手すべきか」を判定してください。

## 案件基本情報
{case_summary}

## LP分析
{lp_analysis}

## 市場分析
{market_analysis}

## 購買トリガー
{buying_triggers}

## SNS適性
{sns_fit}

## リスク評価
{risk_analysis}

## 上位10訴求（スコア順）
{top_appeals}

---

## 出力1: winning_summary（勝ち筋サマリー）

この案件でアフィリエイト収益を上げるための「勝ち筋」を分析してください。

- **winning_angle**: なぜこの案件で勝てるか（具体的に60字以内）
- **best_platforms**: 最も成果が出やすい媒体（配列、最大3つ）
- **best_appeal_types**: 最も機能しやすい訴求タイプ（配列、最大3つ）
- **difficulty**: Easy / Medium / Hard
- **difficulty_reason**: 難易度の理由（30字以内）
- **start_priority**: High / Medium / Low（最初に着手すべきか）
- **start_priority_reason**: 優先度の判断根拠（50字以内）

### start_priority の判定基準
- **High**: 以下を多く満たす案件
  - 購買トリガーが明確で体験談化しやすい
  - SNS投稿を30本以上量産しやすい訴求がある
  - 成果条件が緩く承認率が高い
  - リスクが低く継続投稿しやすい
  - automation_fitが高い（AI＋システムで量産検証しやすい）
- **Medium**: 一部満たすが制約もある案件
- **Low**: 競合が強すぎる・規約リスクが高い・体験談化しにくい案件

## 出力2: case_score（案件スコア）

この案件を将来的に複数案件と横並び比較することを前提に、各軸を0〜100で評価してください。

- **total**: 総合スコア（以下の加重平均）
- **profitability**: 収益性（報酬単価×確定率×CPAの見込み）
- **sns_scalability**: SNS拡張性（投稿を量産・継続しやすいか）
- **content_repeatability**: コンテンツ量産可能性（1案件から何本作れるか）
- **conversion_closeness**: 購買意欲との近さ（LPの訴求と購買トリガーの一致度）
- **risk_safety**: リスク安全性（規約・薬機法・炎上リスクの低さ）
- **automation_fit**: 自動化適性（以下を総合評価）
  - AI分析のしやすさ（LP・市場情報が整理されているか）
  - 訴求量産のしやすさ（パターンが多く展開しやすいか）
  - SNS継続投稿のしやすさ（ネタが尽きにくいか）
  - 実績検証のしやすさ（CTR・CVを測定・改善しやすいか）
- **rank_reason**: このスコアの根拠（50字以内）

## 出力形式

以下のJSONのみを返してください。

{
  "winning_summary": {
    "winning_angle": "AI議事録という具体的な悩みと直結。体験談として語りやすく投稿量産しやすい",
    "best_platforms": ["x", "threads"],
    "best_appeal_types": ["時短訴求", "体験談訴求"],
    "difficulty": "Medium",
    "difficulty_reason": "競合増加中だが差別化余地あり",
    "start_priority": "High",
    "start_priority_reason": "体験談×時短訴求でSNS量産しやすく、確定率75%で検証しやすい"
  },
  "case_score": {
    "total": 87,
    "profitability": 90,
    "sns_scalability": 88,
    "content_repeatability": 85,
    "conversion_closeness": 92,
    "risk_safety": 75,
    "automation_fit": 90,
    "rank_reason": "購買トリガーが明確で自動化量産に最も向いている案件"
  }
}
