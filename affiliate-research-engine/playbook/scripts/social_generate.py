#!/usr/bin/env python3
"""
social_generate.py
公開中の記事から、X と Threads の投稿文を**別々の素材で**作って在庫へ入れる。

  # Actions で（記事を取り直して生成する）
  python social_generate.py --articles 521,546 --source wp

  # 手元で（ローカルの記事ダンプ＋用意した下書きを使う）
  python social_generate.py --articles 521 --source local \
      --drafts workspace/social/drafts/trial5.yaml

**投稿はしない。** 作るのは在庫だけで、state は awaiting_approval で止まる。
ゲートに落ちたら rejected にして理由を残す。作り直しも即投稿もしない。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss
import social_gate as sg
import social_inventory as inv

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"


def fetch_article(pid):
    """**公開中の最新本文**を取り直す。下書きなら None を返す。"""
    import requests
    import urllib3
    urllib3.disable_warnings()
    r = requests.get(f"{WP_BASE}/posts/{pid}",
                     auth=(WP_USER, os.environ.get("WP_APP_PASSWORD", "")),
                     params={"_fields": "id,title,content,link,status,"
                                        "modified_gmt"},
                     headers={"User-Agent": "Mozilla/5.0"},
                     verify=False, timeout=40)
    if r.status_code != 200:
        return None
    d = r.json()
    sys.path.insert(0, str(Path(__file__).parent))
    import affiliate_inserter as ai
    body = re.sub(r"<[^>]+>", "\n", ai.strip_box(d["content"]["rendered"]))
    return {"id": str(d["id"]),
            "title": re.sub(r"<[^>]+>", "", d["title"]["rendered"]),
            "url": d["link"], "status": d["status"],
            "modified_gmt": d.get("modified_gmt"),
            "body": re.sub(r"\n{3,}", "\n\n", body).strip()}


def ask(prompt, model="claude-opus-4-8", max_tokens=1200):
    import anthropic
    ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = ai.messages.create(model=model, max_tokens=max_tokens,
                             messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text.strip()


def generate_api(spec, article):
    """記事 → 素材4つ → X本文 / Threads本文。**素材の段階で分ける。**"""
    out = ask(ss.extraction_prompt(spec, article))
    material = {k: ss.section(k.upper(), out)
                for k in spec["extraction"]["fields"]}
    x_text = ask(ss.x_prompt(spec, article, material))
    th = ask(ss.threads_prompt(spec, article, material))
    parts = [ss.section("PART1", th), ss.section("PART2", th)]
    return material, [x_text.strip()], [p for p in parts if p.strip()]


def generate_file(spec, article, drafts):
    """用意した下書きを使う。ゲートと在庫の作り方は API と同じ。"""
    d = drafts["articles"][str(article["id"])]
    return d["material"], [d["x"].strip()], [p.strip() for p in d["threads"]]


def attach_url(spec, platform, parts, article):
    url = ss.with_utm(spec, article["url"], platform)
    parts = list(parts)
    parts[-1] = parts[-1].rstrip() + "\n" + url
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--articles", required=True, help="記事ID（カンマ区切り）")
    ap.add_argument("--source", choices=["wp", "local"], default="wp")
    ap.add_argument("--drafts", default="")
    ap.add_argument("--platforms", default="x,threads")
    a = ap.parse_args()

    spec = ss.load_spec()
    drafts = (yaml.safe_load(Path(a.drafts).read_text(encoding="utf-8"))
              if a.drafts else None)
    plats = [p.strip() for p in a.platforms.split(",") if p.strip()]

    made, blocked = [], []
    for pid in [x.strip() for x in a.articles.split(",") if x.strip()]:
        article = (fetch_article(pid) if a.source == "wp"
                   else inv.local_article(pid))
        if not article:
            print(f"[{pid}] 記事を取得できない。飛ばす")
            continue
        if article.get("status") != "publish":
            # 下書きのうちは作らない。開けないURLの在庫を残さない
            print(f"[{pid}] {article['status']} なので作らない")
            continue

        if a.source == "local" and drafts:
            material, x_parts, th_parts = generate_file(spec, article, drafts)
        else:
            material, x_parts, th_parts = generate_api(spec, article)

        texts = {}
        for platform, raw in (("x", x_parts), ("threads", th_parts)):
            if platform not in plats or not raw:
                continue
            parts = attach_url(spec, platform, raw, article)
            other = texts.get("threads" if platform == "x" else "x", "")
            hist = inv.read_history(spec, platform,
                                    spec["duplicate"]["window_days"])
            hist += [{"text": s["text"], "stock_id": s["stock_id"]}
                     for _, s in inv.all_stock(spec, platform)
                     if s["article_id"] != int(pid)]
            res = sg.run_gates(spec, platform, parts, article,
                               history=hist, other_text=other)
            stock = inv.new_stock(spec, platform, article, parts,
                                  material, res)
            if sg.passed(res):
                inv.transition(spec, stock, "gated")
                inv.transition(spec, stock, "awaiting_approval")
                made.append(stock["stock_id"])
            else:
                inv.transition(spec, stock, "gated")
                inv.transition(spec, stock, "rejected",
                               rejected_reason="; ".join(
                                   f"{g}: {d}" for g, ok, d in res if not ok))
                blocked.append(stock["stock_id"])
            texts[platform] = stock["text"]
            p = inv.save(spec, stock)
            print(f"[{pid}] {platform}: {stock['state']} → {p.name}")
            for line in sg.fmt(res).split("\n"):
                if line.startswith("NG"):
                    print("      " + line)
            for w in sg.style_warnings(spec, parts):
                print("      警告 " + w)

    print(f"\n承認待ち {len(made)} / ゲートで止めた {len(blocked)}")
    print("**投稿はしていない。**")


if __name__ == "__main__":
    main()
