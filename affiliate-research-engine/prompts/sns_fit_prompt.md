あなたはSNSアルゴリズムとアフィリエイトマーケティングの専門家です。
以下の案件情報と購買トリガーをもとに、各SNS媒体との相性とアルゴリズム適性を分析してください。

## 案件情報
{case_summary}

## LP分析結果
{lp_analysis}

## 購買トリガー
{buying_triggers}

## 市場分析
{market_analysis}

## SNS投稿例
{sns_examples}

## 各媒体のアルゴリズム特性（参考）
- X（旧Twitter）: 危機感・断定・議論・速報性が拡散しやすい。短文で刺さるフックが重要
- Threads: 共感・体験談・日常感が滞在時間を伸ばす。Instagramとの連動が強み
- TikTok: 冒頭3秒の驚き・即効性・視覚的変化が重要。エンタメ性と情報性の両立
- Instagram: ビジュアル・ライフスタイル・Before/After。リール冒頭のフック文が重要
- note: 検索需要・情報密度・長期資産性。SEOと相性がよい案件が向く

## 分析指示
各媒体について以下を評価してください。
- score: 1〜5（5が最も相性が良い）
- reason: この案件が相性よい/悪い理由（50字以内）
- good_appeals: この媒体で効く訴求タイプ（配列）
- bad_appeals: この媒体で避けるべき訴求タイプ（配列）

## 出力形式
以下のJSONのみを返してください。

{
  "sns_fit": {
    "x":         {"score": 5, "reason": "理由", "good_appeals": ["不安訴求", "損失回避訴求"], "bad_appeals": ["優越訴求"]},
    "threads":   {"score": 4, "reason": "理由", "good_appeals": ["共感訴求", "体験談訴求"], "bad_appeals": []},
    "tiktok":    {"score": 3, "reason": "理由", "good_appeals": ["時短訴求"], "bad_appeals": ["知らないと損訴求"]},
    "instagram": {"score": 2, "reason": "理由", "good_appeals": [], "bad_appeals": []},
    "note":      {"score": 4, "reason": "理由", "good_appeals": ["比較訴求", "初心者訴求"], "bad_appeals": []}
  },
  "algorithm_fit_reason": {
    "x": "なぜXのアルゴリズムとこの案件が相性がよいか（または悪いか）",
    "threads": "Threadsについての説明",
    "tiktok": "TikTokについての説明",
    "instagram": "Instagramについての説明",
    "note": "noteについての説明"
  },
  "emotion_analysis": {
    "primary": ["不安", "損失回避"],
    "secondary": ["優越感", "時短"]
  }
}

emotion_analysisの選択肢:
不安 / 損失回避 / 時短 / 優越感 / 共感 / 憧れ / コンプレックス解消 / 失敗回避 / お得感 / 知らないと損 / 自己投資 / 収入増 / 効率化 / 面倒回避
