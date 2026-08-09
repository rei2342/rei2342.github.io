#!/usr/bin/env python3
"""
eyecatch_prompt.py
記事の3つ目の成果物として、**アイキャッチ画像の生成プロンプト**を作る。

記事生成の成果物は3つ。
  1. 記事本文
  2. Threads投稿文
  3. アイキャッチ画像生成プロンプト  ← これ

**これは公開コンテンツではない。画像制作専用の一時データ。**
  WordPressの本文へ入れない / SEOタイトル・メタへ入れない /
  SNS投稿文へ混ぜない / 読者から見える場所へ出さない /
  公開処理のpayloadへ含めない

  画像の生成・検証・WordPress反映が終わったら削除する。
  失敗したら削除せず、再実行の対象として残す。

  TITLE="…" SLUG="…" POST=993 CATEGORY="AI英語学習" \
  LEAD="画像内の短い文言" SUB="補助文言" SCENE="場面と小物" \
  python eyecatch_prompt.py
出力: workspace/eyecatch-prompts/<記事IDまたはslug>.md
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
OUT = Path("affiliate-research-engine/playbook/workspace/eyecatch-prompts")

# カテゴリごとの差し色。基調（淡い桜色・クリーム・白）は全カテゴリ共通で、
# **差し色だけ**を変える。6枚並べたときにシリーズとして揃うのはこのため
ACCENT = {
    "AI英語学習":        ("soft periwinkle blue", "#A9B8E8"),
    "英語学習法":        ("soft sakura pink", "#F2A8C0"),
    "TOEIC・スコア":     ("muted coral", "#F0A48C"),
    "英会話サービス比較": ("soft mint green", "#A6D8C4"),
    "英語コーチング":    ("warm apricot", "#F3C48A"),
    "海外留学・ワーホリ": ("light sky blue", "#9FC9E8"),
    "フィリピン・セブ留学": ("aqua turquoise", "#8FD3D8"),
    "留学エージェント・費用": ("soft lavender", "#C4B5E0"),
}
DEFAULT_ACCENT = ("soft sakura pink", "#F2A8C0")

# ── さくらの人物設定。**毎回そのまま入れる。** 記事ごとに別人にしない ──
CHARACTER = """A recurring Japanese woman character named Sakura, drawn the
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
  watercolour-like shading, matching the existing Sakura illustrations"""

LAYOUT = """Composition (keep consistent across the whole series):
- canvas exactly 1200 x 675 px, 16:9
- Sakura is placed on the RIGHT third of the canvas, from about the waist up
- the LEFT half is open space holding the short Japanese text
- background is a light gradient of pale sakura pink, cream and white, with
  a few soft cherry-blossom petals; the category accent colour appears only
  as a small highlight (an object, a line, or a sticky note)
- generous margins. Nothing important within 40px of any edge
- the scene and props must be specific to this article, so that the image is
  recognisable on its own"""

READABILITY = """Text rules:
- render the Japanese text EXACTLY as given, no other words
- 2 to 3 lines maximum, large enough to stay legible in a small phone
  thumbnail (main line roughly 60-72px tall on the 1200px canvas)
- the supporting line is clearly smaller than the main line
- do NOT place the full article title in the image
- this must be an ILLUSTRATED SCENE with the character, not a text card.
  A plain white background with only text on it is rejected"""

BANNED = """Never include, in the artwork or in any text inside it:
- ages, TOEIC or any test scores, prices or amounts of money
- study periods, usage periods, or any duration
- words meaning success / improved / got better / achieved
- any screen that suggests the person actually used a named service
- service logos, app UI, or any reproduction of a real product screen
- the old site name (さくらの英語挑戦記 / Sakura's English Challenge)
- the old persona details (a stated age, a job title, a personal deadline)
- any number or conclusion that does not appear in the article body
- small print or paragraphs of text that cannot be read at thumbnail size"""


def build(post_id, slug, title, lead, sub, scene, category, alt, filename):
    accent_name, accent_hex = ACCENT.get(category, DEFAULT_ACCENT)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    lead_disp = lead.replace("\n", " / ")
    prompt = f"""{CHARACTER}

{LAYOUT}
- category accent colour for this article: {accent_name} ({accent_hex})

Scene for this specific article:
{scene}

Japanese text to render in the left half:
- main lines (large): {lead_disp}
- supporting line (smaller, below): {sub}

{READABILITY}

{BANNED}

Output: a single 1200x675 illustration, soft and calm, suitable as a blog
header. Same character, same palette family and same margins as the rest of
the series, but a different pose, scene and props from any other image."""

    return f"""# アイキャッチ生成プロンプト（一時データ・公開しない）

> **これは記事の3つ目の成果物です。公開コンテンツではありません。**
> WordPressの本文・SEOタイトル・メタ・SNS投稿文へ入れないでください。
> 画像の生成 → 反映 → 検証が通ったら、このファイルを削除します。
> 失敗した場合は削除せず、再実行の対象として残します。
>
> 作成 {stamp}

記事ID：{post_id}
slug：{slug}
記事タイトル：{title}
画像内の短い文言：{lead_disp}
補助文言：{sub}
避ける要素：年齢／TOEICスコア／金額／学習期間／利用期間／「成功」「伸びた」「改善した」／
サービスのロゴ・UI・使ったと誤認させる画面／旧サイト名／旧人物設定／
本文にない数字や結論／読めない細かい文字／文字だけのカード型
推奨ファイル名：{filename}
alt：{alt}
カテゴリ：{category}
使用するブランド配色：淡い桜色・クリーム・白を基調／差し色 {accent_name}（{accent_hex}）
人物の配置：右側（腰から上）。左半分を文言のために空ける
記事固有の小物・場面：{scene}

## 画像生成プロンプト

```
{prompt}
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
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    post_id = os.environ.get("POST", "")
    slug = os.environ.get("SLUG", "")
    title = os.environ.get("TITLE", "")
    lead = os.environ.get("LEAD", "")
    sub = os.environ.get("SUB", "")
    scene = os.environ.get("SCENE", "")
    category = os.environ.get("CATEGORY", "")
    alt = os.environ.get("ALT", "")
    filename = os.environ.get("FILENAME", f"eyecatch-{slug}.png")
    if not (slug or post_id):
        print("SLUG か POST が要る")
        sys.exit(1)
    name = post_id or slug
    path = OUT / f"{name}.md"
    path.write_text(build(post_id, slug, title, lead, sub, scene, category,
                          alt, filename), encoding="utf-8")
    print(f"→ {path}")


if __name__ == "__main__":
    main()
