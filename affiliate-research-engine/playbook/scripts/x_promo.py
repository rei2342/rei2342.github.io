#!/usr/bin/env python3
"""
x_promo.py
公開済みの記事を X で告知する。記事URL付きの1投稿を作って流す。

2026-08-04に65投稿の実績を集計したところ、リンク付きの投稿が
平均43.0（中央値43）、リンクなしが平均24.9（中央値21）で、
リンク付きのほうが明確に伸びていた。
「リンクを貼ると伸びない」という一般論はこのアカウントには当てはまらない。

ARTICLE_ID … 告知する記事のID（公開済みであること）
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import anthropic
import requests
import urllib3

urllib3.disable_warnings()

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
ARTICLE_ID = os.environ.get("ARTICLE_ID", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
# 生成に任せず、人が推敲した文をそのまま投稿したいとき用
POST_TEXT = os.environ.get("POST_TEXT", "").strip()
STATE = "affiliate-research-engine/playbook/workspace/x_state.json"

RULES = """【実測で伸びた投稿】2026-08-04時点の表示回数。この短さと質感を真似る。
（54回）「留学エージェントって無料なんだ」って知ったとき、うれしいより先に身構えた経験ない？
（40回）意志が弱いんじゃなかったんだと最近気づいた
（38回）「30歳でも遅くない」って読むたびに少し安心して、そのまま何も決めずにタブを閉じてきた。5年間ずっと。
（37回）昨日30分だけど英語の勉強続いた、これって進んでるってことなのか

【実測で伸びなかった型】書かない。
長い考察・分析（11〜16回）。1投稿に主張を2つ以上入れているもの。

【今回の条件】
・記事を読んでもらうための告知だが、宣伝臭を出さない
・記事の中にある具体（数字・実際にやったこと）を1つだけ持ち出す
・60〜90字。1投稿1メッセージ
・改行を使う。読点は多くても2個
・最後は読者への問いかけか、続きが気になる止め方にする
・絵文字は2個まで。絵文字の直前に半角スペースを入れない
・ハッシュタグは入れない
・URLは書かない（こちらで末尾に付ける）
・「——」禁止。漢数字禁止（27歳・3ヶ月のようにアラビア数字）
・対比構文（〜じゃなくて／〜ではなく）は使わない

本文だけ出力。説明不要。"""


def get_post(pid):
    r = requests.get(f"{WP_BASE}/posts/{pid}",
                     auth=(WP_USER, WP_PASS),
                     params={"_fields": "id,title,content,link,status"},
                     headers={"User-Agent": "Mozilla/5.0"},
                     verify=False, timeout=40)
    return r.json() if r.status_code == 200 else None


def main():
    if not ARTICLE_ID:
        print("ARTICLE_ID が未指定")
        sys.exit(1)

    art = get_post(ARTICLE_ID)
    if not art:
        print(f"記事 {ARTICLE_ID} を取得できない")
        sys.exit(1)

    if art.get("status") != "publish":
        print(f"記事 {ARTICLE_ID} は {art.get('status')} 状態。"
              f"公開前に告知するとリンク先が読めないので中止する")
        sys.exit(1)

    title = art["title"]["rendered"]
    body = re.sub(r"<[^>]+>", "\n", art["content"]["rendered"])
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    url = art["link"] + ("&" if "?" in art["link"] else "?") + "utm_source=x"

    if POST_TEXT:
        text = POST_TEXT
        print("（手入れしたテキストを使用。生成はスキップ）")
    else:
        ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = ai.messages.create(
            model="claude-opus-4-8",
            max_tokens=600,
            messages=[{"role": "user", "content":
                       "あなたは田中さくら（27歳・営業事務・東京）。\n\n"
                       f"下の記事を X で告知する投稿を1つ書いて。\n\n"
                       f"記事タイトル: {title}\n\n記事本文:\n{body[:4000]}\n\n" + RULES}],
        )
        text = msg.content[0].text
    text = text.strip().replace("——", "、").replace("—", "、")
    text = re.sub(r"(?<=[ぁ-んァ-ヴ一-龥ー、。！？…])[  ]+"
                  r"(?=[\U0001F000-\U0001FAFF☀-➿←-⇿⬀-⯿])", "", text)
    text = re.sub(r"https?://\S+", "", text).strip()   # 本文中のURLは落とす

    # 1投稿目に本文、2投稿目（返信）にリンク。Threadsと形を揃える。
    # ※実測ではリンクを本文に入れた投稿が伸びていた（平均43 vs 25）。
    #   返信に分けるとカードが出ないぶん不利かもしれないので、
    #   ?utm_source=x で後から比較できるようにしてある。
    tweet = text
    print(f"元記事: [{ARTICLE_ID}] {title}")
    print(f"\n--- 1投稿目（{len(tweet)}字）---\n{tweet}")
    print(f"\n--- 2投稿目（返信）---\n{url}\n")

    # 結果をファイルにも残す（ジョブログが取りにくいので確認用）
    from pathlib import Path
    out_dir = Path("affiliate-research-engine/playbook/workspace/x_promo")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"promo_{ARTICLE_ID}.md").write_text(
        f"# X告知 — [{ARTICLE_ID}] {title}\n\n"
        f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"
        f"## 1投稿目\n\n```\n{tweet}\n```\n\n"
        f"## 2投稿目（返信・リンクだけ）\n\n{url}\n\n"
        f"1投稿目の文字数: {len(tweet)}\n", encoding="utf-8")

    if DRY_RUN:
        print("DRY RUN のため投稿しない")
        return

    import tweepy
    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    first = client.create_tweet(text=tweet)
    first_id = first.data["id"]
    client.create_tweet(text=url, in_reply_to_tweet_id=first_id)
    print(f"投稿した（スレッド2連 / 1投稿目 id={first_id}）")

    # 直後に自動投稿が重ならないよう、間隔の起点を更新する
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    now = datetime.now(timezone.utc)
    st["last_post"] = now.isoformat()
    st["next_allowed"] = (now + timedelta(hours=64)).isoformat()
    st["last_text"] = tweet
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=2)
    print(f"next_allowed = {st['next_allowed']}")


if __name__ == "__main__":
    main()
