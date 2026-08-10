#!/usr/bin/env python3
"""
social_inventory.py
SNS投稿の**唯一の在庫**。読み書きと状態遷移だけを持つ。

  workspace/social/stock/x/<記事ID>-<変種>.yaml
  workspace/social/stock/threads/<記事ID>-<変種>.yaml
  workspace/social/history/x.jsonl
  workspace/social/history/threads.jsonl

状態は仕様の lifecycle に従う。**決められた遷移以外は例外で止める。**
勝手に posted へ飛ばせないようにするため。
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss

JST = timezone(timedelta(hours=9))
GENERATOR_VERSION = "social-v1"


def now():
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def paths(spec):
    return {k: ROOT / v for k, v in spec["paths"].items()
            if isinstance(v, str)}


def content_hash(parts):
    return hashlib.sha256("\n\n".join(parts).encode()).hexdigest()[:16]


def stock_path(spec, platform, article_id, variant="a"):
    return (ROOT / spec["paths"]["stock"] / platform
            / f"{article_id}-{variant}.yaml")


def new_stock(spec, platform, article, parts, material, gate_results,
              variant="a"):
    sid = f"{platform.upper()}-{article['id']}-{variant}"
    return {
        "stock_id": sid,
        "platform": platform,
        "article_id": int(article["id"]),
        "article_modified_gmt": article.get("modified_gmt"),
        "article_title": article["title"],
        "article_url": article["url"],
        "text": "\n\n".join(parts),
        "thread_parts": parts,
        "state": "generated",
        "gate_results": [{"id": g, "ok": ok, "detail": d}
                         for g, ok, d in gate_results],
        "approved_at": None,
        "rejected_reason": None,
        "scheduled_at": None,
        "posted_at": None,
        "posted_id": None,
        "content_hash": content_hash(parts),
        "generator_version": GENERATOR_VERSION,
        "material": material,
        "created_at": now(),
        "history": [{"at": now(), "state": "generated"}],
    }


def save(spec, stock):
    p = stock_path(spec, stock["platform"], stock["article_id"],
                   stock["stock_id"].rsplit("-", 1)[1])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(stock, allow_unicode=True, sort_keys=False,
                                width=200), encoding="utf-8")
    return p


def load(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def all_stock(spec, platform=None):
    base = ROOT / spec["paths"]["stock"]
    out = []
    for p in sorted(base.glob("*/*.yaml")):
        if platform and p.parent.name != platform:
            continue
        out.append((p, load(p)))
    return out


def transition(spec, stock, to, **fields):
    """**決められた遷移以外は通さない。**"""
    allowed = spec["lifecycle"]["transitions"].get(stock["state"], [])
    if to not in allowed:
        raise ValueError(f"{stock['stock_id']}: "
                         f"{stock['state']} → {to} は許されていない"
                         f"（可: {allowed or 'なし'}）")
    stock["state"] = to
    stock.update(fields)
    stock.setdefault("history", []).append({"at": now(), "state": to})
    return stock


def history_path(spec, platform):
    return ROOT / spec["paths"]["history"] / f"{platform}.jsonl"


def append_history(spec, platform, row):
    p = history_path(spec, platform)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_history(spec, platform, days=None):
    p = history_path(spec, platform)
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    if days:
        cut = datetime.now(JST) - timedelta(days=days)
        rows = [r for r in rows
                if r.get("posted_at", "") >= cut.strftime("%Y-%m-%dT%H:%M:%S")]
    return rows


def idempotency_key(stock):
    """二重投稿の防止。platform + article_id + content_hash。"""
    return f"{stock['platform']}:{stock['article_id']}:{stock['content_hash']}"


def already_posted(spec, stock):
    key = idempotency_key(stock)
    return any(r.get("idempotency_key") == key
               for r in read_history(spec, stock["platform"]))


def live_article(article_id):
    """**公開画面から取り直した本文**を生成元にする。

    ローカルの控え（workspace/claims/posts）は古いことがある。
    実際に 310 で、直したはずの旧断定が控えだけに残っていた。
    ここは `article-fetch` が WordPress から取ってきたものだけを読む。
    """
    d = ROOT / "workspace/claims/live"
    h, j = d / f"{article_id}.html", d / f"{article_id}.json"
    if not h.exists() or not j.exists():
        return None
    meta = json.loads(j.read_text(encoding="utf-8"))
    html = h.read_text(encoding="utf-8")
    # **タグの種類で変換を分ける。**
    # 全部を改行にすると、<strong> が文の途中に入っているだけで
    # 1文が3行に割れる。そのせいで照合の単位が壊れていた（310で落ちた）。
    #  - <li>       → 「・」付きの行（箇条書きだと分かるように残す）
    #  - ブロック要素 → 改行
    #  - 装飾・リンク → 消すだけ（文を割らない）
    body = re.sub(r"(?i)<li[^>]*>", "\n・", html)
    body = re.sub(r"(?i)</?(?:p|div|h[1-6]|ul|ol|li|br|hr|table|tr|td|th|"
                  r"blockquote|section)[^>]*>", "\n", body)
    body = re.sub(r"<[^>]+>", "", body)
    return {"id": str(article_id), "title": meta["title"],
            "url": meta["link"], "status": meta["status"],
            "modified_gmt": meta["modified_gmt"],
            "fetched_at": meta.get("fetched_at"),
            "html": html,
            "body": re.sub(r"\n{3,}", "\n\n", body).strip()}


def local_article(article_id, posts_dir=None):
    """ローカルに落としてある記事本文から、生成に要る形を作る。"""
    posts = Path(posts_dir or ROOT / "workspace/claims/posts")
    f = posts / f"{article_id}.txt"
    if not f.exists():
        return None
    lines = f.read_text(encoding="utf-8").split("\n")
    art = {"id": str(article_id), "title": lines[0].lstrip("# ").strip(),
           "url": lines[1].strip(), "body": "\n".join(lines[2:]),
           "status": "unknown", "modified_gmt": None}
    # 記事の状態は Actions で取った控えから読む。**推測しない。**
    st = ROOT / "workspace/social/article_state.yaml"
    if st.exists():
        rec = (yaml.safe_load(st.read_text(encoding="utf-8"))
               .get("posts", {}).get(str(article_id)))
        if rec:
            art["status"] = rec.get("status")
            art["modified_gmt"] = rec.get("modified_gmt")
    return art
