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

【お手本】2026-08-07に人間が推敲して決めた理想形。この見た目と密度と順番を再現する。
（記事URLは2投稿目の末尾にこちらで差し込むので、本文には書かない）
--- 1投稿目 ---
3日、4日、2日

オンライン英会話に3回登録して
続いた日数がこれ

レッスンが嫌だったわけじゃない
毎回、話す前にスマホを閉じてた

閉じてた理由がわかってから
90日続いてる

理由はこれ↓
--- 2投稿目 ---
オンライン英会話が続かなかった理由は
予約だった

仕事から帰って、やっとスマホを開いて
「いつにしよう」で閉じる

やめたのは3つ
・レッスンの予約
・先生を毎回選ぶこと
・30分まとめて取ること

予約なしで話せるアプリに変えて
歯みがきのあと、5分だけ話す

最初の週は、7日のうち5日できた
それから90日続いてる

前にやめたとき、どこで閉じた？
授業中か、始める前か

始める前なら
直すのは英語力じゃない

予約なしで話せるところは、ほかにもある
私が何を見て決めたかはブログに書いた
---

【お手本の順番】この並びを守る。
1投稿目: 数字を3つ並べる → 何の数字か説明 → 否定で誤解を潰す → 情景 → 結果 → 「↓」で送る
2投稿目: 1行目で何の話か言う → 情景（独り言） → やめたN個を箇条書き → 代わりにやったこと
        → 結果 → 読者への問いかけ → 読者が今日できること → 「私が何を見て決めたか」で締める

【締め方】「◯◯はブログに書いた」ではなく **「私が何を見て決めたかはブログに書いた」** 型にする。
おすすめではなく判断の共有にすると宣伝の顔をしない。
「ほかにもある」を先に置いて、1つを推していないことを明示する。

【必ず守る型】
・句点（。）を使わない。改行が句点の代わり。お手本に句点は1つも無い
・**誰でも分かる言葉で、読者が自分の場面として思い浮かべられるように書く**（2026-08-07・最優先）
  - 抽象語（手数・設計・最適化・仕組み）で説明しない。**実際の動作と場面で見せる**
    ×「話し始めるまでの手数が減った」 ○「歯みがきが終わったら、そのままアプリを開いて話す」
  - 読者が「それ私だ」と言える具体を必ず入れる。時間帯・場所・指の動き・心の中の独り言
    例「仕事から帰って、ご飯作って、やっとスマホを開いたあと」「いつにしよう、って探してるうちに閉じる」
  - 専門用語・カタカナの概念語を使わない。中学生が読んで分かる語彙にする
  - 説明が2文以上必要になったら、それは抽象的すぎる合図。場面に置き換える
  - **できるだけシンプルに**。1投稿で言うことを1つに絞る。足す前に削れないか考える
  - **読者は賢くない前提**。流し読みしていて推測も逆算もしない。書いていないことは伝わらない
  - 指示語で受けない（×「そこをやめたら」 ○「予約をやめたら」）。前の行を覚えている前提にしない
  - 比喩・言い換え・ひねりを使わない。そのままの言葉で言う
  - **どの投稿から読み始めても分かるように書く**。2投稿目だけが流れてくる人がいる。
    1行目で「何の話か」を言い、前の投稿を読んでいる前提の指示語を使わない。
    結果（何がどうなったか）はどちらの投稿にも入れる
・1行は20字前後。1行に情報を2つ入れない
  読点（、）は自然に必要なところで使ってよい（2026-08-07に緩和）。
  ただし読点でつないで1行を長くしない。切るときは改行で切る
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



def clean(out):
    """モデルの出力から、外に出してはいけないものを落とす。

    リトライでも同じ処理を通す必要があるので関数にしている。
    2026-08-07に、この3つが素通りしてThreads文面に載りかけた。
    """
    out = out.replace("——", "、").replace("—", "、")
    # URLはこちらが差し込むものだけにする（example.com を書いてきた）
    out = re.sub(r"https?://\S+", "", out)
    # 記事のCTAボックスから案件名を書き写すことがある
    out = "\n".join(
        ln for ln in out.split("\n")
        if not ln.lstrip().startswith("▶")
        and not re.search(r"(無料体験|無料トライアル|無料相談|無料カウンセリング)\s*$", ln.strip())
    )
    # 絵文字の直前の半角スペース（指示しても入ることがある）
    return re.sub(r"(?<=[ぁ-んァ-ヴ一-龥ー、。！？…])[  ]+"
                  r"(?=[\U0001F000-\U0001FAFF☀-➿←-⇿⬀-⯿])", "", out)


# 2026-08-07に、生成した原稿を人間が7箇所直した。内訳は
# 指示語で受ける／抽象語で説明する／箇条書きが消える／答えを1投稿目で言い切る、など。
# 警告を出すだけでは直らないので、**合格しない原稿は外に出さない**。
_ABSTRACT = ("手数", "設計", "構造", "物差し", "本質", "最適化", "仕組み化", "可視化")
_VAGUE_HEAD = ("そこ", "それ", "これ", "その", "あの")
# 時間のつなぎ言葉は指示語ではない（「それから90日続いてる」を誤検知していた）
_VAGUE_OK = ("それから", "そのあと", "その後", "そして", "それでも", "それだけ")


def review(t1, t2, title):
    """投稿として出せる状態かを見る。出せない理由を文字列で返す。"""
    bad = []
    both = t1 + "\n" + t2

    if "。" in both:
        bad.append("句点（。）が入っている。改行で切る")

    if "・" not in t2:
        bad.append("2投稿目に箇条書きが無い。手順は箇条書きで独立させる")

    longs = [ln for ln in both.split("\n") if len(ln) > 28]
    if longs:
        bad.append(f"28字を超える行がある（例:「{longs[0][:26]}」）。改行で割る")

    abst = [w for w in _ABSTRACT if w in both]
    if abst:
        bad.append(f"抽象語で説明している（{'・'.join(abst)}）。実際の動作と場面で見せる")

    # 指示語で行を始めると、前の行を覚えている前提になる
    vague = [ln for ln in both.split("\n")
             if ln.strip().startswith(_VAGUE_HEAD)
             and not ln.strip().startswith(_VAGUE_OK)]
    if vague:
        bad.append(f"指示語で受けている（例:「{vague[0][:20]}」）。名指しで書く")

    # 2投稿目だけが流れてくる人がいる。1〜2行目で何の話かを言う
    head = "".join(t2.split("\n")[:2])
    keys = [w for w in re.findall(r"[ぁ-んァ-ヴ一-龥]{3,}", title)][:6]
    if keys and not any(k in head for k in keys):
        bad.append("2投稿目の冒頭に記事の話題語が無い。1行目で何の話かを言う")

    # 1投稿目で答えを言い切らない。最後は次へ送る形で止める
    if not t1.rstrip().endswith(("↓", "→")):
        bad.append("1投稿目が「↓」で終わっていない。答えを出さずに次へ送る")

    if len(t2) < 120:
        bad.append(f"2投稿目が{len(t2)}字と薄い。読者が今日できることを入れる")

    return bad


def main():
    if not ARTICLE_ID:
        print("ARTICLE_ID が未指定")
        sys.exit(1)

    art = get_post(ARTICLE_ID)
    if not art:
        print(f"記事 {ARTICLE_ID} を取得できない")
        sys.exit(1)

    title = art["title"]["rendered"]
    # CTAボックスは案件名の羅列なので、渡すと投稿文に書き写される。
    # 2026-08-07に「▶ QQ English 無料体験」がThreads文面へ漏れた。
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).parent))
    import affiliate_inserter as _ai
    body = re.sub(r"<[^>]+>", "\n", _ai.strip_box(art["content"]["rendered"]))
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    link = art.get("link", "")
    link_line = link + ("&" if "?" in link else "?") + "utm_source=threads" if link else "（記事URL）"

    print(f"元記事: [{ARTICLE_ID}] {title}")
    print(f"リンク: {link_line}\n")

    ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = ("あなたは田中さくら（27歳・営業事務・東京）。\n\n"
              f"下の記事から Threads の投稿を作って。\n\n"
              f"記事タイトル: {title}\n\n記事本文:\n{body[:6000]}\n\n" + RULES)
    msg = ai.messages.create(model="claude-opus-4-8", max_tokens=1500,
                             messages=[{"role": "user", "content": prompt}])
    out = clean(msg.content[0].text.strip())

    t1, t2 = section("THREADS_1", out), section("THREADS_2", out)
    ng = section("NG", out)

    if not t1 or not t2:
        print(f"投稿を作れなかった: {ng or out[:200]}")
        sys.exit(1)

    print("=== ① 1投稿目 ===\n" + t1)
    print("\n=== ② 2投稿目（末尾にリンク） ===\n" + t2 + "\n\n" + link_line)

    # 合格しない原稿は外に出さない。理由を渡して書き直させる
    for attempt in range(1, 4):
        bad = review(t1, t2, title)
        if not bad:
            print(f"\n検査を通過（{attempt}回目）")
            break
        print(f"\n{attempt}回目は不合格:")
        for b in bad:
            print(f"  - {b}")
        if attempt == 3:
            print("\n3回書き直しても通らなかった。人が直す前提で出力する")
            break
        retry = (prompt + "\n\n## 直前の原稿は以下の理由で不合格だった。必ず直すこと\n"
                 + "\n".join(f"- {b}" for b in bad)
                 + "\n\n直した原稿を、同じ出力形式でもう一度出す。")
        msg = ai.messages.create(model="claude-opus-4-8", max_tokens=1500,
                                 messages=[{"role": "user", "content": retry}])
        out = clean(msg.content[0].text.strip())
        t1, t2 = section("THREADS_1", out), section("THREADS_2", out)

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
