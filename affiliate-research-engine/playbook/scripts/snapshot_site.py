#!/usr/bin/env python3
"""
snapshot_site.py
統合日次レポートへ渡す**共通スナップショット**を書く。

  python snapshot_site.py            # workspace/reports/daily/snapshots/sakura.json

複数サイトを1枚のレポートに並べるための形。**サイト固有の言葉を鍵に使わない**
（「さくら」「ワーホリ」などは値の側に置く）。別サイトが同じ鍵で埋められる。

**取れない値は 0 にしない。`未取得` を入れる。**
0 と書くと「測って0だった」という意味になり、
「まだ測っていない」「そもそも取れない」と区別できなくなる。
どちらか分からない値を 0 で埋めると、合算した瞬間に嘘になる。

各ブロックに `source` と `as_of` を付ける。
どこから取った数字で、いつ時点かが分からないものは、比較に使えない。
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss
import social_inventory as inv
import social_gate as sg

JST = timezone(timedelta(hours=9))
NA = "未取得"
# ハンドルはここだけ。**投稿URLの組み立てにしか使わない**
HANDLE = "sakura_eigo30"
OUT = ROOT / "workspace/reports/daily/snapshots/sakura.json"


def _md_int(path, pattern):
    """レポートの md から1つの数値を拾う。無ければ 未取得。"""
    p = ROOT / path
    if not p.exists():
        return NA
    m = re.search(pattern, p.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else NA


def sns_block(spec):
    rows = [s for _, s in inv.all_stock(spec)]
    by_state = {}
    for s in rows:
        by_state[s["state"]] = by_state.get(s["state"], 0) + 1
    posted = [s for s in rows if s["state"] == "posted"]

    def posted_url(s):
        """**推測しない。** 記録にあるものだけを返す。
        Xは投稿IDから公開URLが一意に決まるので、そこだけ組み立てる。"""
        if s.get("posted_url") or s.get("thread_root_url"):
            return s.get("posted_url") or s["thread_root_url"]
        if s["platform"] == "x" and s.get("posted_id"):
            return f"https://x.com/{HANDLE}/status/{s['posted_id']}"
        return NA

    def utm_content(s):
        if s.get("utm_content"):
            return s["utm_content"]
        m = re.search(r"utm_content=([^&\s]+)", s.get("text", ""))
        return m.group(1) if m else NA
    return {
        "source": "workspace/social/stock（在庫ファイルそのもの）",
        "as_of": datetime.now(JST).isoformat(timespec="seconds"),
        "inventory_total": len(rows),
        "by_state": by_state,
        "awaiting_approval": by_state.get("awaiting_approval", 0),
        "approved": by_state.get("approved", 0),
        "posted": by_state.get("posted", 0),
        "posts": [{
            "stock_id": s["stock_id"],
            "platform": s["platform"],
            "article_id": s["article_id"],
            "posted_at": s.get("posted_at") or NA,
            "posted_id": s.get("posted_id") or NA,
            "posted_url": posted_url(s),
            "reply_url": (s.get("thread_reply_urls") or [NA])[0],
            "canonical_url": s.get("canonical_url") or NA,
            "utm_content": utm_content(s),
            # 反応はまだ1件も測っていない。**0を入れない**
            "views": NA, "likes": NA, "replies": NA, "reposts": NA,
            "profile_visits": NA, "link_clicks": NA,
            "followers_at_observation": NA,
        } for s in sorted(posted, key=lambda x: x["stock_id"])],
    }


def articles_block():
    live = ROOT / "workspace/claims/live"
    rows = []
    for j in sorted(live.glob("*.json"), key=lambda p: int(p.stem)):
        d = json.loads(j.read_text(encoding="utf-8"))
        rows.append({"id": int(j.stem), "status": d.get("status") or NA,
                     "chars": d.get("chars", NA),
                     "modified_gmt": d.get("modified_gmt") or NA,
                     "fetched_at": d.get("fetched_at") or NA})
    scope = ROOT / "workspace/claims/SCOPE.md"
    published, scope_as_of = NA, NA
    if scope.exists():
        st = scope.read_text(encoding="utf-8")
        m = re.search(r"公開記事（全体）\s*\|\s*\*\*(\d+)\*\*", st)
        published = int(m.group(1)) if m else NA
        m2 = re.search(r"改修の対象範囲\s*(\S+\s+\S+)", st)
        scope_as_of = m2.group(1) if m2 else NA
    return {
        "source": "WordPress REST（article-fetch の控え）/ SCOPE.md",
        "as_of": datetime.now(JST).isoformat(timespec="seconds"),
        "published_total": published,
        "published_total_as_of": scope_as_of,
        "fetched_recently": rows,
    }


def search_block():
    """Search Console。**サイト全体の数字しか無い。記事別は持っていない。**"""
    p = ROOT / "workspace/gsc/LATEST.md"
    if not p.exists():
        return {"source": "Search Console", "as_of": NA, "available": False,
                "clicks": NA, "impressions": NA, "period": NA}
    t = p.read_text(encoding="utf-8")
    def num(pat):
        m = re.search(pat, t)
        return int(m.group(1)) if m else NA
    m = re.search(r"対象期間:\s*(.+)", t)
    d = re.search(r"レポート\s*([0-9-]+)", t)
    return {
        "source": "Search Console（workspace/gsc/LATEST.md）",
        "as_of": d.group(1) if d else NA,
        "period": m.group(1).strip() if m else NA,
        "clicks": num(r"合計クリック:\s*\*\*(\d+)\*\*"),
        "impressions": num(r"合計表示:\s*\*\*(\d+)\*\*"),
        # **記事別は取れていない。0ではない**
        "per_article": NA,
    }


def analytics_block():
    p = ROOT / "workspace/ga4/LATEST.md"
    if not p.exists():
        return {"source": "GA4", "as_of": NA, "sessions": NA, "users": NA,
                "pageviews": NA, "social_sessions": NA, "cta_clicks": NA}
    t = p.read_text(encoding="utf-8")
    m = re.search(r"セッション\s*\*\*(\d+)\*\*\s*/\s*ユーザー\s*\*\*(\d+)\*\*"
                  r"\s*/\s*ページビュー\s*\*\*(\d+)\*\*", t)
    d = re.search(r"GA4 アクセス\s*([0-9-]+)", t)
    return {
        "source": "GA4（workspace/ga4/LATEST.md・直近14日）",
        "as_of": d.group(1) if d else NA,
        "sessions": int(m.group(1)) if m else NA,
        "users": int(m.group(2)) if m else NA,
        "pageviews": int(m.group(3)) if m else NA,
        "social_sessions": NA,   # 参照元別の内訳は別表。ここでは取らない
        # **CTAクリックのイベントはまだ1件も取れていない。0にしない**
        "cta_clicks": NA,
        "key_events": NA,
    }


def revenue_block():
    """成果・収益。**ASP管理画面からは自動で取れない。**"""
    return {
        "source": "ASP管理画面（自動取得の口が無い）",
        "as_of": NA,
        "conversions": NA,
        "revenue_jpy": NA,
        "note": "ログイン取得はしない方針のため、入るとしたら手入力",
    }


def pending_block(spec):
    p = ROOT / "workspace/social/measure_plan.yaml"
    if not p.exists():
        return {"source": NA, "items": []}
    import yaml
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    out = []
    for it in d.get("items", []):
        for o in it.get("observations", []):
            out.append({"stock_id": it["stock_id"],
                        "elapsed_hours": o.get("elapsed_hours"),
                        "scheduled_at": o.get("scheduled_at", NA),
                        "observed_at": o.get("observed_at", NA),
                        "status": "未実施"})
    return {"source": "workspace/social/measure_plan.yaml", "items": out}


def main():
    spec = ss.load_spec()
    snap = {
        "schema": "site-daily-snapshot/1",
        "site_key": "sakura",
        "site_name": "sakura-eigo.com",
        "track": "B",
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "unavailable_marker": NA,
        "rules": [
            "取れない値は 0 ではなく 未取得 と書く",
            "0 は、画面や API がその欄に 0 を返したときだけ書く",
            "24時間値と48時間値は上書きせず別々に持つ",
            "1組の投稿から一般則を出さない",
        ],
        "articles": articles_block(),
        "sns": sns_block(spec),
        "search_console": search_block(),
        "analytics": analytics_block(),
        "revenue": revenue_block(),
        "pending_measurements": pending_block(spec),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"書いた: {OUT.relative_to(ROOT)}")
    return snap


if __name__ == "__main__":
    s = main()
    print(json.dumps(s, ensure_ascii=False, indent=1))
