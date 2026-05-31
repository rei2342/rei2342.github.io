あなたはコンテンツ戦略の専門家です。
以下の発信者の「一次情報・実体験」を元に、具体的なコンテンツ資産候補を生成してください。

## 発信者プロフィール（静的・誰であるか）
{creator_profile}

## 発信者メモリ（動的・変化の履歴）
{creator_memory}

## 高スコアのテーマ × 資産タイプ（Asset Type Matrixより）
{top_types}

## 重要な制約
候補は必ず発信者の「一次情報」から引き出すこと。
- creator_profile.current_projects に含まれる実際のプロジェクト・活動
- creator_profile.first_hand_domains に含まれる実体験領域
- creator_memory.entries に含まれる変化・発見・失敗・驚きの記録

架空の体験・推測・「たぶん需要があると思う」だけの候補は禁止。
source_experience には必ずcreator_profileまたはcreator_memoryの具体的な記載を引用すること。

## 「変化」を起点にした候補を優先する
creator_memoryの各エントリには before_belief → discovery → surprise が記録されている。
「テーマについての記事」より「考えが変わった体験の記事」の方が強い候補になる。

悪い候補例: 「AIツール比較5選」（誰でも書ける）
良い候補例: 「5000行作って最後に気づいた：Candidate Engineの方が重要だった」（この発信者にしか書けない）

## 評価軸（各0〜100）

### uniqueness（一次情報独自性）
この発信者の実体験・実装・実データが根拠になっているか
- 0: 誰でも書ける一般論 / 50: 経験は活かせるが差別化は薄い / 100: この発信者にしか作れない

### durability（資産耐久性）
1年後も参照・利用される価値があるか
- 0: 翌日消える / 50: 数ヶ月有効 / 100: 5年後も使われる

### seed_rate（ネタ連鎖率）
この1本を起点に次のコンテンツが自動生成されるか
- 0: 1本で完結 / 50: 少し展開できる / 100: 1本が10本のネタを生む

predicted_score = 3軸の平均値（整数）

## 出力形式
各テーマ × 資産タイプごとに5〜8件の候補を生成（score≥70のテーマ×タイプは8件、score<70は3件）。
以下のJSONのみを返してください。

{
  "candidates": [
    {
      "title": "具体的なコンテンツタイトル（日本語、読者が読みたいと思う表現で）",
      "theme": "テーマ名",
      "asset_type": "資産タイプ名",
      "predicted_score": 98,
      "breakdown": {
        "uniqueness": 99,
        "durability": 98,
        "seed_rate": 97
      },
      "rationale": "なぜこれが高スコアか（30〜60字）",
      "source_experience": "creator_profileまたはcreator_memoryのどの一次情報・変化体験が根拠か（具体的に引用）"
    }
  ]
}
