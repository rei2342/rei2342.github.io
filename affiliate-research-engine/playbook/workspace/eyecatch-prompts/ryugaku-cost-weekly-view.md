# アイキャッチ生成プロンプト（一時データ・公開しない）

> **これは記事の3つ目の成果物です。公開コンテンツではありません。**
> WordPressの本文・SEOタイトル・メタ・SNS投稿文へ入れないでください。
> 画像の生成 → 反映 → 検証が通ったら、このファイルを削除します。
> 失敗した場合は削除せず、再実行の対象として残します。
>
> 作成 2026-08-10 JST

記事ID：（下書き・未採番）
slug：ryugaku-cost-weekly-view
記事タイトル：留学費用を総額で見て諦めかけた社会人が、やめた3つと決めた1つの基準
画像内の短い文言：留学費用は / 総額で見ない
補助文言：中身で選ぶ
避ける要素：年齢／TOEICスコア／金額・数字／学習期間・利用期間／「成功」「伸びた」「改善した」／
サービスのロゴ・UI・使ったと誤認させる画面／旧サイト名／旧人物設定／
本文にない数字や結論／読めない細かい文字／文字だけのカード型
推奨ファイル名：eyecatch-ryugaku-cost-weekly-view.png
alt：留学費用を総額ではなく1週間あたりの中身で見比べる考え方を、机で整理している場面
カテゴリ：留学・費用
使用するブランド配色：淡い桜色・クリーム・白を基調／差し色 soft gold（#E8C878）
人物の配置：右側（腰から上）。左半分を文言のために空ける
記事固有の小物・場面：Sakura is at a desk comparing two plain paper quotes side by side. An open notebook shows a single long horizontal bar divided into a few equal segments (representing splitting a total into weekly pieces), drawn simply with no numbers. A small globe and a tiny paper airplane sit on the desk as travel motifs. Calm, thinking-with-the-reader mood.

## 画像生成プロンプト

```
A recurring Japanese woman character named Sakura, drawn the
same way in every image of this site:
- Japanese woman, adult, approachable and warm, NOT a teenager and NOT
  exaggeratedly youthful
- shoulder-length to long brown hair, softly waved, with a small sakura
  (cherry blossom) hair clip as her single signature accessory
- clean, tidy everyday clothing: a soft knit or blouse in cream or pale
  grey, with one small sakura-pink accent (cardigan, scarf or clip)
- expression: calm, friendly, thinking alongside the reader. She is a guide
  sorting things out WITH the reader, never a teacher lecturing from above.
  No pointing finger, no raised index finger, no "explaining" pose
- soft hand-drawn illustration style with gentle linework and light
  watercolour-like shading, matching the existing Sakura illustrations

Composition (keep consistent across the whole series):
- canvas exactly 1200 x 675 px, 16:9
- Sakura is placed on the RIGHT third of the canvas, from about the waist up
- the LEFT half is open space holding the short Japanese text
- background is a light gradient of pale sakura pink, cream and white, with
  a few soft cherry-blossom petals; the category accent colour appears only
  as a small highlight (an object, a line, or a sticky note)
- generous margins. Nothing important within 40px of any edge
- the scene and props must be specific to this article, so that the image is
  recognisable on its own
- category accent colour for this article: soft gold (#E8C878)

Scene for this specific article:
Sakura is at a desk comparing two plain paper quotes side by side. An open
notebook shows a single long horizontal bar divided into a few equal segments
(representing splitting a total into weekly pieces), drawn simply with NO
numbers on it. A small globe and a tiny paper airplane sit on the desk as
travel motifs, both plain and generic with no brand marks. Soft daylight.
Business-casual, calm.

Japanese text to render in the left half:
- main lines (large): 留学費用は / 総額で見ない
- supporting line (smaller, below): 中身で選ぶ

Text rules:
- render the Japanese text EXACTLY as given, no other words
- 2 to 3 lines maximum, large enough to stay legible in a small phone
  thumbnail (main line roughly 60-72px tall on the 1200px canvas)
- the supporting line is clearly smaller than the main line
- do NOT place the full article title in the image
- this must be an ILLUSTRATED SCENE with the character, not a text card.
  A plain white background with only text on it is rejected

Never include, in the artwork or in any text inside it:
- ages, TOEIC or any test scores, prices or amounts of money
- study periods, usage periods, or any duration
- words meaning success / improved / got better / achieved
- any screen that suggests the person actually used a named service
- service logos, app UI, or any reproduction of a real product screen
- the old site name (さくらの英語挑戦記 / Sakura's English Challenge)
- the old persona details (a stated age, a job title, a personal deadline)
- any number or conclusion that does not appear in the article body
- small print or paragraphs of text that cannot be read at thumbnail size

Output: a single 1200x675 illustration, soft and calm, suitable as a blog
header. Same character, same palette family and same margins as the rest of
the series, but a different pose, scene and props from any other image.
```

## 反映前のチェック

- [ ] 画像生成済み
- [ ] WordPressへアップロード済み
- [ ] featured_media へ設定済み
- [ ] alt 設定済み
- [ ] 画像内の文字と本文が一致している
- [ ] 未確認の主張が入っていない
- [ ] サムネイルに縮小しても読める
- [ ] OGPで崩れていない
- [ ] 既存の記事と見分けがつく
- [ ] 文字カード型になっていない

**全部にチェックが付くまで、記事を公開・予約しない。**
仮画像を設定して公開するのは禁止。画像を作れない場合は下書きで止めて、
このファイルを残す。
