#!/usr/bin/env python3
"""
threads_builder.py
公開済みの記事から Threads のスレッド2連を作り直し、投稿用メモを更新する。

ARTICLE_ID … 元になる記事のID（この記事のURLを2投稿目の末尾に貼る）
MEMO_ID    … 更新する【Threads用】メモのID（省略すると新規作成）

数字は記事に書かれているものだけを使う。手順が書かれていない記事からは作らない。
"""
import html as htmlmod
import os
import re
import sys

import anthropic
import requests
import urllib3

urllib3.disable_warnings()

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
ARTICLE_ID = os.environ.get("ARTICLE_ID", "")
MEMO_ID = os.environ.get("MEMO_ID", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

RULES = """【投稿はスレッド2連で作る】
1投稿目=フック。最後を『これだけ↓』のように次へ送る形で止める。リンクは入れない
2投稿目=中身。手順・結果・読者への翻訳。ここに価値を全部入れる。
  記事リンクはこの2投稿目の末尾に置く（本文では書かない。こちらで差し込む）

リンクを3投稿目に分けるのは2026-08-05に試して失敗した。
1投稿目780表示に対し、①いいね2 ②いいね1 ③反応0。3枚目まで開く人がほとんどおらず、
記事への遷移がほぼ0だった。1投稿目にリンクを入れないのは維持する（表示が落ちるため）が、
2投稿目まで来た人の目の前にリンクを置く。

【お手本】人間が推敲して決めた理想形。この見た目と密度を再現する。
--- 1投稿目 ---
セブ島留学
8コマ入れて3日でパンクした

授業を6コマに減らした
浮いた2時間はこれだけ↓
--- 2投稿目 ---
・その日出た表現を3つ選ぶ
・声に出して10回
・翌朝もう1回

4日目
前の日の表現が勝手に口から出た

日本でもできる
教材は増やさない

学校選びは「1日何コマか」を見る
8コマは多い

コマ数の決め方はブログにまとめた
---

【必ず守る型】
・句点（。）を使わない。改行が句点の代わり。お手本に句点は1つも無い
・1行は20字前後。読点（、）は1行に1個まで。1行に情報を2つ入れない
・意味のまとまりごとに空行を入れる
・有益性が芯。読者が今日できる手順を必ず入れる
  手順は箇条書きで独立させ、真似できる粒度にする（3つ選ぶ／10回／翌朝1回 のように数える形）
・読者への翻訳を1行入れる。体験談で終わらせず持ち帰れる形にする
・数字は記事に実際に書かれているものだけ使う。作らない
  冒頭に数字を3つ並べない（『35万円、120コマ、28日。』は演出になる）
・短いほど良い（1投稿目は120字以内、2投稿目は300字以内目安）
・最終行はその投稿で扱った具体の続きを予告する形にする
  （○『コマ数の決め方はブログにまとめた』）
  『noteに書いた』『続きはこちら』のような固定文言は使わない

【禁止】
・対比構文（『〜じゃなかった』『〜ではなく』『〜のほうだ』）
・「設計」「構造」「物差し」「本質」
・教訓や説教で締める（×『27歳のいま動かないと30歳で後悔する』）
・感情の演出（×『泣きそうになった』）。事実を淡々と置けば感情は伝わる
・「——」(emダッシュ)。漢数字（27歳・3ヶ月のようにアラビア数字）
・金額の表記を混ぜる（35万円と45000円を同じ投稿に置かない）
・ハッシュタグ・URL

【記事に再現できる手順が無ければ】
THREADS_1 と THREADS_2 を空にして、代わりに ===NG=== に理由を書く。
有益性の無い投稿を出すより出さないほうがよい。

【出力形式】以下のブロックだけを出力する。説明不要。
===THREADS_1===
（1投稿目・フック。最後は『↓』で次へ送る。リンク禁止）
===THREADS_2===
（2投稿目・中身。手順の箇条書きと読者への翻訳を必ず入れる）
"""


def get_post(pid):
    r = requests.get(f"{WP_BASE}/posts/{pid}",
                     auth=(WP_USER, WP_PASS),
                     params={"_fields": "id,title,content,link,status"},
                     headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=40)
    return r.json() if r.status_code == 200 else None


def section(tag, text):
    m = re.search(rf"==={tag}===\s*(.*?)(?====[A-Z_0-9]+===|$)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def main():
    if not ARTICLE_ID:
        print("ARTICLE_ID が未指定")
        sys.exit(1)

    art = get_post(ARTICLE_ID)
    if not art:
        print(f"記事 {ARTICLE_ID} を取得できない")
        sys.exit(1)

    title = art["title"]["rendered"]
    body = re.sub(r"<[^>]+>", "\n", art["content"]["rendered"])
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    link = art.get("link", "")
    link_line = link + ("&" if "?" in link else "?") + "utm_source=threads" if link else "（記事URL）"

    print(f"元記事: [{ARTICLE_ID}] {title}")
    print(f"リンク: {link_line}\n")

    ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = ai.messages.create(
        model="claude-opus-4-8",
        max_tokens=1500,
        messages=[{"role": "user", "content":
                   "あなたは田中さくら（27歳・営業事務・東京）。\n\n"
                   f"下の記事から Threads の投稿を作って。\n\n"
                   f"記事タイトル: {title}\n\n記事本文:\n{body[:6000]}\n\n" + RULES}],
    )
    out = msg.content[0].text.strip().replace("——", "、").replace("—", "、")
    out = re.sub(r"(?<=[ぁ-んァ-ヴ一-龥ー、。！？…])[  ]+"
                 r"(?=[\U0001F000-\U0001FAFF☀-➿←-⇿⬀-⯿])", "", out)

    t1, t2 = section("THREADS_1", out), section("THREADS_2", out)
    ng = section("NG", out)

    if not t1 or not t2:
        print(f"投稿を作れなかった: {ng or out[:200]}")
        sys.exit(1)

    print("=== ① 1投稿目 ===\n" + t1)
    print("\n=== ② 2投稿目（末尾にリンク） ===\n" + t2 + "\n\n" + link_line)

    # 句点が混ざっていないかだけ機械で見る（いちばん戻りやすい癖）
    kuten = t1.count("。") + t2.count("。")
    if kuten:
        print(f"\n注意: 句点が{kuten}個混ざっている")

    # 結果をファイルにも残す（ログが取りにくいので確認用）
    from pathlib import Path
    out_dir = Path("affiliate-research-engine/playbook/workspace/threads")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"built_{ARTICLE_ID}.md").write_text(
        f"# Threads 2連 — [{ARTICLE_ID}] {title}\n\n"
        f"## ① 1投稿目（フック・リンクなし）\n\n```\n{t1}\n```\n\n"
        f"## ② 2投稿目（スレッドに続けて・末尾のURLまで貼る）\n\n"
        f"```\n{t2}\n\n{link_line}\n```\n\n"
        f"句点の混入: {kuten}個\n", encoding="utf-8")

    if DRY_RUN:
        print("\nDRY RUN のため更新しない")
        return

    style = ("background:#f6f6f6;padding:16px 20px;border-radius:6px;"
             "white-space:pre-wrap;font-size:1.05em;line-height:1.9")

    def block(label, text):
        return (f"<h3>{label}</h3>\n<div style=\"{style}\">"
                f"{htmlmod.escape(text)}</div>\n")

    content = (
        "<p style=\"color:#c0392b;font-weight:bold\">"
        "※これは投稿用メモです。公開せず、コピーして使ったら削除してください。</p>\n"
        + block("① 1投稿目（フック・リンクなし）", t1)
        + block("② 2投稿目（スレッドに続けて・末尾のURLまで貼る）",
                t2 + "\n\n" + link_line)
        + f"<p style=\"font-size:0.85em;color:#999\">元記事: {htmlmod.escape(title)}</p>"
    )

    if MEMO_ID:
        r = requests.post(f"{WP_BASE}/posts/{MEMO_ID}",
                          auth=(WP_USER, WP_PASS), json={"content": content},
                          headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=40)
        print(f"\nメモ {MEMO_ID} を更新: HTTP {r.status_code}")
    else:
        r = requests.post(f"{WP_BASE}/posts",
                          auth=(WP_USER, WP_PASS),
                          json={"title": "【Threads用】" + title[:30],
                                "content": content, "status": "draft"},
                          headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=40)
        print(f"\nメモを新規作成: HTTP {r.status_code} / id={r.json().get('id')}")


if __name__ == "__main__":
    main()
