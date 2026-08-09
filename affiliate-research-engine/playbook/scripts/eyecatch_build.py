#!/usr/bin/env python3
"""
eyecatch_build.py
アイキャッチを**作り直して、WordPressへ反映する。**

`seo/EYECATCH_ACTIONS.md` で差し替えが要ると判定した18本と、
表記だけ直す2本を対象にする。

作る画像に入れないもの（EYECATCH_ACTIONS.md の禁止事項）:
  年齢 / スコア / 金額 / 期間 / 「成功」「改善」「伸びた」/ 旧サイト名 /
  実際に使ったように見せる表現 / 読めないほど小さい文字

入れるもの:
  記事の検索意図が分かる短い見出し（最大2行）
  記事の役割（比較・選び方・確認項目・計算方法）を示す小さな札
  さくらのブランド色（ピンク系パステル）と桜の花びら

**数字を焼き込まない。** 本文の数字は改定されるが画像は追随しない。
今回の18本のうち14本は、数字を入れたことが原因で古くなった。

  DRY_RUN=false python eyecatch_build.py
出力: workspace/seo/eyecatch_new/<id>.png / EYECATCH_APPLY.md
"""
import io
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3
from PIL import Image, ImageDraw, ImageFont

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))

JST = timezone(timedelta(hours=9))
WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
OUT = Path("affiliate-research-engine/playbook/workspace/seo/eyecatch_new")
BK = Path("affiliate-research-engine/playbook/workspace/backups")

W, H = 1200, 675
INK = (74, 58, 63)
SUB = (150, 116, 124)
PINK = (232, 138, 166)
CARD = (255, 252, 253)

FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]
FONTS_R = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]

# 記事ID → (役割の札, 見出し1行目, 見出し2行目, alt)
# 見出しは**数字を入れない**。記事の検索意図をそのまま短く言う
PLAN = {
    # A 事実の捏造にあたるもの
    "304": ("確認項目", "TOEICが止まったら", "勉強法より先に内訳を分ける",
            "TOEICのスコアが止まったときに、リスニングとリーディングの内訳を分けて確認する項目"),
    "282": ("確認項目", "点数の外側で", "確かめること",
            "TOEICの点数では測れない、話す練習の量を確かめる確認項目"),
    "521": ("切り分け", "リスニングが動かない", "止まっている場所を分ける",
            "TOEICリスニングが伸びないとき、音が拾えないのか残らないのかを切り分ける手順"),
    "32":  ("確認項目", "勉強法を選ぶ前に", "確かめる4つのこと",
            "TOEICの勉強法を選ぶ前に確認する4つの項目"),
    # B 削除した主張が残っているもの
    "546": ("確認項目", "オンライン英会話が", "続かないのは手数のせい",
            "オンライン英会話が続かない理由を、話し始めるまでの手数で確認する"),
    "281": ("順番", "帰国後に落ちやすい", "力から先に手を打つ",
            "留学から帰国した後に落ちやすい英語力の順番を並べた表"),
    "294": ("決め方", "比較が終わらないなら", "決め方を先に決める",
            "留学の比較が終わらないときに、決め方のほうを先に決める手順"),
    "137": ("読み分け", "体験談は", "到達点か傾きかで読む",
            "英語コーチングの体験談を、到達点と傾きに分けて読み分ける方法"),
    "150": ("手順", "続かないなら", "空いた日から戻る手順を決める",
            "英語の勉強が続かないときに、空いた日から戻る手順を決める"),
    "292": ("確認項目", "教材を買う前に", "確かめる3つのこと",
            "独学が止まる人が教材を買う前に確認する3つの項目"),
    "117": ("手順", "今日やった分に", "明日の出番を1つ付ける",
            "英語をゼロから始めるときに、今日の学習に明日の出番を付ける手順"),
    "149": ("計算方法", "まとめ記事の総額を", "3つの箱に組み替える",
            "カナダのワーキングホリデー費用を3つの箱に分けて計算する方法"),
    # C 記事の主張と逆を言っているもの
    "301": ("言い回し", "勧められたとき", "その場で使う言葉",
            "留学エージェントに勧められたときに、その場で使う言い回し集"),
    "310": ("分かれ目", "アプリで足りる人と", "足りない人の分かれ目",
            "無料や低価格の英語アプリで足りる人と、足りない人の分かれ目"),
    "28":  ("並べ直し", "上達しない理由は", "1本の鎖として並べ直す",
            "英会話が上達しない理由を、1本の鎖としてつなげて並べ直す"),
    # D 内容が合っていないもの
    "526": ("計算方法", "「現地が一番早い」を", "1時間あたりで確かめる",
            "留学先を費用と時間の1時間あたりで並べて比べる計算方法"),
    "33":  ("頻度順", "仕事の英語の電話は", "職務の場面から固める",
            "仕事の英語の電話に備えて、職務の場面を頻度順に並べる"),
    "235": ("比較表", "セブ島留学の比較表に", "帰国後の列を足す",
            "セブ島留学の比較表に、帰国後の項目を足して比べる"),
    # E 表記だけ直せばよいもの
    "23":  ("計算方法", "貯金はいくら必要か", "自分の数字に組み替える",
            "ワーキングホリデーの貯金額を、自分の条件で計算し直す方法"),
    "283": ("確認項目", "事前学習が続かない", "ときに見るところ",
            "セブ島留学に初心者で行く前に、事前学習が続かない原因を見る確認項目"),
}


def font(size, bold=True):
    for p in (FONTS if bold else FONTS_R):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def petal(d, x, y, r, fill):
    d.ellipse([x - r, y - r * 0.62, x + r, y + r * 0.62], fill=fill)


def build(pid, chip, l1, l2):
    im = Image.new("RGB", (W, H), (253, 244, 247))
    d = ImageDraw.Draw(im, "RGBA")

    # 背景。淡いピンクの帯を重ねて、平らに見えないようにする
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)],
               fill=(253 - int(6 * t), 244 - int(10 * t), 247 - int(4 * t)))
    d.ellipse([-180, -220, 520, 320], fill=(250, 226, 234, 150))
    d.ellipse([W - 420, H - 300, W + 200, H + 220], fill=(250, 226, 234, 130))

    # 花びら。位置は記事IDから決めるので、毎回同じ絵になる
    seed = int(pid)
    for i in range(22):
        a = (seed * 37 + i * 61) % 360
        x = 60 + ((seed * 53 + i * 149) % (W - 120))
        y = 40 + ((seed * 29 + i * 97) % (H - 80))
        r = 9 + ((seed + i * 7) % 12)
        alpha = 70 + ((seed + i * 11) % 60)
        if 300 < x < 900 and 180 < y < 520:
            continue                       # 文字の上には置かない
        petal(d, x, y, r, (240, 170, 195, alpha))
        _ = a

    # 白いカード
    d.rounded_rectangle([90, 150, W - 90, H - 150], radius=28,
                        fill=CARD, outline=(244, 214, 224), width=3)

    # 役割の札
    f_chip = font(30, False)
    tw = d.textlength(chip, font=f_chip)
    d.rounded_rectangle([132, 196, 132 + tw + 46, 196 + 54], radius=27,
                        fill=(252, 231, 238))
    d.text((132 + 23, 196 + 27), chip, font=f_chip, fill=PINK, anchor="lm")

    # 見出し。スマホのサムネイルでも読めるサイズにする
    f1 = font(58)
    f2 = font(58)
    while d.textlength(l1, font=f1) > W - 300 and f1.size > 40:
        f1 = font(f1.size - 2)
    while d.textlength(l2, font=f2) > W - 300 and f2.size > 40:
        f2 = font(f2.size - 2)
    d.text((132, 300), l1, font=f1, fill=INK, anchor="lm")
    d.text((132, 300 + f1.size + 26), l2, font=f2, fill=INK, anchor="lm")

    # 下線とサイト名
    d.rounded_rectangle([132, 300 + f1.size + 26 + f2.size // 2 + 34,
                         132 + 120,
                         300 + f1.size + 26 + f2.size // 2 + 40],
                        radius=3, fill=PINK)
    d.text((W - 132, H - 196), "sakura-eigo.com", font=font(26, False),
           fill=SUB, anchor="rm")
    return im


# **文字カード型の画像を、これ以上サイトへ出さない。**
# 2026-08-09に20本を文字カード型で反映したが、これは
# 「文字だけのカード型は禁止」「白背景に記事タイトルを置いただけの画像は禁止」
# に当てはまる。仮画像を設定して公開する処理は禁止なので、
# **反映は既定で止める。** 画像はイラストで作り直し、
# workspace/eyecatch-prompts/<記事ID>.md のプロンプトから生成する。
ALLOW_CARD = os.environ.get("ALLOW_CARD", "false").lower() == "true"


def main():
    if not DRY_RUN and not ALLOW_CARD:
        print("文字カード型の反映は止めている。"
              "イラストで作り直す（workspace/eyecatch-prompts/ を見る）。")
        print("どうしても走らせるなら ALLOW_CARD=true を明示する。")
        return
    day = datetime.now(JST).strftime("%Y-%m-%d")
    OUT.mkdir(parents=True, exist_ok=True)
    (BK / day / "eyecatch").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    L = [f"# アイキャッチの作り直しと反映 {stamp}\n\n",
         f"モード: **{'DRY RUN（作るだけ）' if DRY_RUN else 'LIVE（反映した）'}**\n\n",
         "数字・年齢・スコア・金額・期間・結果の語は入れていない。\n"
         "**古い画像は消していない。** ロールバックできるようにメディアに残す。\n\n",
         "| 記事 | 役割 | 見出し | 新しい画像 | 前のmedia ID | 結果 |\n",
         "|---|---|---|---|---|---|\n"]
    for pid, (chip, l1, l2, alt) in sorted(PLAN.items(), key=lambda x: int(x[0])):
        im = build(pid, chip, l1, l2)
        path = OUT / f"{pid}.png"
        im.save(path, "PNG", optimize=True)

        g = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                         params={"context": "edit"}, verify=False, timeout=45)
        old_media = g.json().get("featured_media") if g.status_code == 200 else ""
        (BK / day / "eyecatch" / f"{pid}.json").write_text(
            json.dumps({"id": pid, "checked_at": stamp,
                        "old_featured_media": old_media},
                       ensure_ascii=False, indent=2), encoding="utf-8")

        if DRY_RUN:
            L.append(f"| {pid} | {chip} | {l1} {l2} | `{path.name}` | "
                     f"{old_media} | （DRY RUN） |\n")
            print(f"[{pid}] 作った（DRY RUN）")
            continue

        name = f"eyecatch-{pid}-{day.replace('-', '')}.png"
        up = requests.post(
            f"{WP}/media", auth=AUTH, verify=False, timeout=120,
            headers={**UA, "Content-Disposition":
                     f'attachment; filename="{name}"',
                     "Content-Type": "image/png"},
            data=path.read_bytes())
        if up.status_code not in (200, 201):
            L.append(f"| {pid} | {chip} | {l1} {l2} | — | {old_media} | "
                     f"❌ アップロード {up.status_code} |\n")
            print(f"[{pid}] アップロード失敗 {up.status_code}")
            continue
        mid = up.json()["id"]
        requests.post(f"{WP}/media/{mid}", auth=AUTH, headers=UA, verify=False,
                      timeout=60, json={"alt_text": alt, "title": alt[:60]})
        st = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                           verify=False, timeout=60,
                           json={"featured_media": mid})
        ok = st.status_code in (200, 201)
        L.append(f"| {pid} | {chip} | {l1} {l2} | media {mid} | {old_media} | "
                 f"{'✅' if ok else '❌ ' + str(st.status_code)} |\n")
        print(f"[{pid}] media {mid} {'OK' if ok else st.status_code}")

    (BK / day / "EYECATCH_APPLY.md").write_text("".join(L), encoding="utf-8")
    print(f"\n→ workspace/backups/{day}/EYECATCH_APPLY.md")


if __name__ == "__main__":
    main()
