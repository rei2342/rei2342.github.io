あなたはコンテンツ戦略の専門家です。
以下の発信者プロフィールと候補一覧から、今回書くべきN件を選択してください。

## 発信者プロフィール
{creator_profile}

## 候補一覧（Asset Candidatesより・status=draftのみ）
{candidates_json}

## 選択基準（優先順）
1. seed_rate    : 書いた後に次のコンテンツネタが最も多く生まれるか（最優先）
2. theme_balance: 同一テーマが連続しないよう分散させる
3. asset_type_balance: 同一資産タイプが連続しないよう分散させる
4. predicted_score: 他条件が同等なら高スコアを優先（最低優先）

## 選択数
{n}件を選択してください。

## expected_next_seeds について
各選択候補に対して、この投稿を書いた後に「自然に次のコンテンツネタとして生まれる」と予測される候補を3〜5件列挙してください。

これは後で「actual_generated_seeds（実際に生まれた種）」と比較して学習するためのデータです。
- theme / asset_type は必ず記載する（後の分類に使う）
- confidence は「この種が実際の投稿に繋がる確率」（0〜100）
- 架空・推測ではなく、発信者の一次情報から生まれる種に絞ること

## 出力形式
以下のJSONのみを返してください。

{
  "selected": [
    {
      "candidate_id": "（candidates JSONのidフィールドをそのまま）",
      "title": "候補タイトル",
      "theme": "テーマ名",
      "asset_type": "資産タイプ名",
      "predicted_score": 98,
      "seed_rate": 97,
      "selection_reason": "なぜこれを選んだか（30〜60字）",
      "expected_next_seeds": [
        {
          "title": "次に生まれると予測されるコンテンツタイトル",
          "theme": "テーマ名",
          "asset_type": "資産タイプ名",
          "confidence": 92
        }
      ]
    }
  ],
  "selection_logic": "今回の選択全体の方針（50〜100字）",
  "total_seed_count": 6
}
