#!/usr/bin/env python3
"""
social_ops.py
サイトへ触る必要がある作業を、Actions から回すための入口。

開発環境から sakura-eigo.com と Anthropic API へ出られない。
`rewrite-uploader.yml` に WP_APP_PASSWORD と ANTHROPIC_API_KEY が
両方あるので、そこから `TARGET_IDS=ops:<コマンド>` で呼ぶ。

コマンド

  ops:memo-trash:547,584,618,640,641
      旧【Threads用】メモを**控えてからゴミ箱へ**移す。完全削除はしない
  ops:article-patch:526
      workspace/social/patches/<記事ID>.yaml のとおりに本文を1か所だけ直す
  ops:generate:521
      公開本文を取り直して、API で在庫を1件作る。**投稿しない**

`DRY_RUN=true` のあいだは、**読むだけで何も書かない。**
結果は標準出力へ出す（このワークフローは workspace/social/ を
コミットしないので、ログから控える）。
"""
import json
import os
import re
import sys
from pathlib import Path

import requests
import urllib3
import yaml

urllib3.disable_warnings()
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))

WP = "https://sakura-eigo.com/wp-json/wp/v2"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0"}


def get(pid, **params):
    r = requests.get(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                     params={"context": "edit", **params},
                     verify=False, timeout=45)
    return r.json() if r.status_code == 200 else None


def post(pid, payload):
    r = requests.post(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                      json=payload, verify=False, timeout=60)
    return r.status_code, r.text[:200]


# ── メモをゴミ箱へ ──────────────────────────────────
def memo_trash(ids, dry):
    print(f"=== memo-trash {'（読むだけ）' if dry else '（実行）'} ===")
    backups = []
    for pid in ids:
        d = get(pid)
        if not d:
            print(f"[{pid}] 取得できない")
            continue
        title = d["title"]["raw"]
        if "Threads用" not in title:
            # **取り違えて記事を消さないための番人**
            print(f"[{pid}] 「{title[:20]}」は【Threads用】メモではない。飛ばす")
            continue
        backups.append({"id": d["id"], "title": title, "status": d["status"],
                        "date": d.get("date"), "link": d.get("link"),
                        "content": d["content"]["raw"]})
        print(f"[{pid}] 控えた: {title} / {d['status']} / "
              f"{len(d['content']['raw'])}字")
    print("\n--- BACKUP_JSON_BEGIN ---")
    print(json.dumps(backups, ensure_ascii=False))
    print("--- BACKUP_JSON_END ---\n")
    if dry:
        print("DRY RUN。ゴミ箱へ移していない。")
        return
    for b in backups:
        code, body = post(b["id"], {"status": "trash"})
        print(f"[{b['id']}] ゴミ箱へ: HTTP {code} {body if code >= 300 else ''}")
    print("**完全削除はしていない。** ゴミ箱から戻せる。")


# ── 記事本文を1か所だけ直す ─────────────────────────
def article_patch(ids, dry):
    for pid in ids:
        f = ROOT / f"workspace/social/patches/{pid}.yaml"
        if not f.exists():
            print(f"[{pid}] パッチが無い: {f}")
            continue
        spec = yaml.safe_load(f.read_text(encoding="utf-8"))
        d = get(pid)
        if not d:
            print(f"[{pid}] 取得できない")
            continue
        body = d["content"]["raw"]
        new = body
        for r in spec["replacements"]:
            if r["find"] not in new:
                print(f"[{pid}] 見つからない: {r['find'][:30]}。**触らない**")
                new = None
                break
            new = new.replace(r["find"], r["replace"].strip())
        if new is None:
            continue
        v = spec.get("verify_after", {})
        missing = [x for x in v.get("must_contain", []) if x not in new]
        left = [x for x in v.get("must_not_contain", []) if x in new]
        print(f"[{pid}] {spec['reason']}")
        print(f"      {len(body)}字 → {len(new)}字 / "
              f"足りない {missing} / 残っている {left}")
        if missing or left:
            print(f"[{pid}] 検査に落ちた。**書き込まない**")
            continue
        if dry:
            print(f"[{pid}] DRY RUN。書き込んでいない")
            continue
        code, msg = post(pid, {"content": new})
        print(f"[{pid}] 反映: HTTP {code} {msg if code >= 300 else ''}")
        after = get(pid)
        print(f"[{pid}] modified_gmt = {after.get('modified_gmt')}")


# ── APIで在庫を作る（投稿しない）────────────────────
def generate(ids, dry):
    import social_spec as ss
    import social_generate as gen
    import social_inventory as inv
    import social_gate as sg
    spec = ss.load_spec()
    for pid in ids:
        art = gen.fetch_article(pid)
        if not art:
            print(f"[{pid}] 記事を取得できない")
            continue
        print(f"[{pid}] {art['title']}")
        print(f"      status={art['status']} modified_gmt={art['modified_gmt']}")
        print(f"      本文 {len(art['body'])}字")
        if art["status"] != "publish":
            print(f"[{pid}] 公開されていないので作らない")
            continue
        material, x_parts, th_parts = gen.generate_api(spec, art)
        print("      素材: " + json.dumps(material, ensure_ascii=False)[:400])
        for platform, raw in (("x", x_parts), ("threads", th_parts)):
            if not raw or not raw[0]:
                continue
            parts = gen.attach_url(spec, platform, raw, art)
            res = sg.run_gates(spec, platform, parts, art)
            stock = inv.new_stock(spec, platform, art, parts, material, res)
            inv.transition(spec, stock, "gated")
            inv.transition(spec, stock,
                           "awaiting_approval" if sg.passed(res) else
                           "rejected")
            p = inv.save(spec, stock)
            print(f"\n--- STOCK {platform} {p} ---")
            print(p.read_text(encoding="utf-8"))
            print(f"--- END STOCK {platform} ---")
        print(f"[{pid}] **投稿していない。** 在庫を作っただけ")


def run(arg, dry=True):
    cmd, _, rest = arg.partition(":")
    ids = [x.strip() for x in rest.split(",") if x.strip()]
    if cmd == "memo-trash":
        memo_trash(ids, dry)
    elif cmd == "article-patch":
        article_patch(ids, dry)
    elif cmd == "generate":
        generate(ids, dry)
    else:
        print(f"知らないコマンド: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    run(sys.argv[1], os.environ.get("DRY_RUN", "true").lower() == "true")
