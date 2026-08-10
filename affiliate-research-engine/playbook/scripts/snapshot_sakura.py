#!/usr/bin/env python3
"""
snapshot_sakura.py
統合Daily Report（Ray側）へ渡す**さくらの実績スナップショット**を書く。

  python snapshot_sakura.py

**既存の投稿生成・記事生成・WordPress更新には一切触らない。** 読むだけ。
この処理が落ちても本体を止めない（`main()` は例外を外へ出さない）。
取れなかったものは `collection_errors` に理由を残して、そのまま終わる。

── 値の書き方（ここが全部）──────────────────────────
すべての数字は次の形にする。

  {"value": 0, "status": "measured", "source": "wordpress",
   "observed_at": "2026-08-10T17:00:00+09:00", "note": ""}

  実測して0だった   → value: 0     / status: measured
  取得できない      → value: null  / status: unavailable
  計測中（まだ早い）→ value: null  / status: measuring

**この3つを混ぜない。** 0 と null を同じ扱いにすると、
「反応が無かった」と「見ていない」が合算の瞬間に区別できなくなる。

── GSC / GA4 を入れない理由 ────────────────────────
Ray側がGoogleから直接取れている。ここで二重に取ると、
どちらが正かの判断が要る数字が2つできる。**足りないのは
WordPressの記事状態・SNSの状態・収益**なので、そこだけ埋める。

── 秘密情報 ────────────────────────────────────
トークン・パスワード・サービスアカウントJSONは**1つも書かない。**
`source` に入れるのは取得元の名前だけ（"wordpress" / "threads_api" など）。
"""
import json
import os
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # .../playbook
ENGINE = ROOT.parent                                # .../affiliate-research-engine
sys.path.insert(0, str(Path(__file__).parent))

JST = timezone(timedelta(hours=9))
SCHEMA = "site-daily-snapshot/1"
SITE = "sakura"

# 出す先は2つ。**同じ中身を書く。**
#  ① さくら側の作業ツリー（これまでの置き場）
#  ② Ray側が読む相対パス（affiliate-research-engine/workspace/...）
OUT_PATHS = [
    ROOT / "workspace/reports/daily/snapshots/sakura.json",
    ENGINE / "workspace/reports/daily/snapshots/sakura.json",
]

WP = "https://sakura-eigo.com/wp-json/wp/v2"
UA = {"User-Agent": "sakura-snapshot"}

ERRORS = []      # collection_errors
ACTIONS = []     # human_actions


def now():
    return datetime.now(JST).isoformat(timespec="seconds")


def metric(value, status, source, note="", observed_at=None):
    """1つの数字。**status を必ず自分で決める。既定値を作らない。**"""
    assert status in ("measured", "unavailable", "measuring"), status
    if status == "measured":
        assert value is not None, "measured なのに値が無い"
    else:
        value = None       # unavailable / measuring は必ず null
    return {"value": value, "status": status, "source": source,
            "observed_at": observed_at or now(), "note": note}


def unavailable(source, why):
    return metric(None, "unavailable", source, why)


def fail(block, why):
    """取れなかったことを記録する。**例外は外へ出さない。**"""
    ERRORS.append({"block": block, "reason": str(why)[:300], "at": now()})


def need_human(action_id, purpose, where, steps, inputs, done_when):
    ACTIONS.append({"id": action_id, "purpose": purpose, "where": where,
                    "steps": steps, "inputs": inputs, "done_when": done_when})


def yesterday_range():
    """昨日（JST）の 00:00:00 〜 23:59:59 を JST の naive 文字列で返す。

    WordPress の日付フィルタはサイトのローカル時刻（JST）で効く。
    GMT の値を渡すと9時間ずれる。
    """
    t = datetime.now(JST)
    y = (t - timedelta(days=1)).date()
    return (f"{y}T00:00:00", f"{y}T23:59:59", str(y))


# ── WordPress ────────────────────────────────────────
def wp_count(**params):
    """X-WP-Total を読む。**本文は取らない**（1件だけ要求する）。"""
    import requests
    p = {"per_page": 1, "_fields": "id", **params}
    r = requests.get(f"{WP}/posts", params=p, headers=UA, timeout=30,
                     auth=wp_auth(), verify=False)
    if r.status_code != 200:
        hint = ""
        if r.status_code == 400 and params.get("status") in ("draft", "future"):
            # 非公開statusは認証必須。未認証だと401ではなく400で返る
            hint = ("（非公開statusの取得は認証が必要です。"
                    "WP_USER / WP_APP_PASSWORD を確認してください）")
        raise RuntimeError(f"HTTP {r.status_code} ({params}){hint}")
    return int(r.headers.get("X-WP-Total", 0))


def wp_auth():
    """下書き・予約は認証が要る。**パスワードは値として出さない。**

    ★ユーザー名を "sakura" で決め打ちしていたため認証が通っていなかった。
      他のスクリプト（affiliate_inserter.py / brand_apply.py）は
      rei.00pt2342@gmail.com を使っている。
      認証が通らないと WordPress は status=draft / future を
      HTTP 400 rest_invalid_param で返す（認証すれば200）。
      401ではなく400で返るので、権限の問題だと気づきにくい。
    """
    pw = os.environ.get("WP_APP_PASSWORD", "")
    user = os.environ.get("WP_USER") or "rei.00pt2342@gmail.com"
    return (user, pw) if pw else None


def articles_block():
    src = "wordpress"
    y0, y1, yday = yesterday_range()
    out = {}
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    def one(key, note="", **params):
        try:
            n = wp_count(**params)
            out[key] = metric(n, "measured", src, note)
        except Exception as e:
            out[key] = unavailable(src, f"取得に失敗: {e}")
            fail(f"articles.{key}", e)

    one("published_total", status="publish")
    one("published_yesterday", f"{yday}（JST）に公開されたもの",
        status="publish", after=y0, before=y1)
    one("updated_yesterday", f"{yday}（JST）に更新されたもの",
        status="publish", modified_after=y0, modified_before=y1)
    if wp_auth():
        one("drafts", status="draft")
        one("scheduled", status="future")
    else:
        why = "WP_APP_PASSWORD が無い。下書き・予約は認証しないと数えられない"
        out["drafts"] = unavailable(src, why)
        out["scheduled"] = unavailable(src, why)
        fail("articles.drafts/scheduled", why)
    return out


# ── SNS ──────────────────────────────────────────────
def posts_yesterday(platform):
    """在庫の投稿履歴から、昨日出した本数を数える。**実測。0なら0。**"""
    import social_spec as ss
    import social_inventory as inv
    spec = ss.load_spec()
    _, _, yday = yesterday_range()
    rows = [r for r in inv.read_history(spec, platform)
            if r.get("result") == "ok"
            and str(r.get("posted_at", "")).startswith(yday)]
    return len(rows)


def threads_user_metrics():
    """Threadsのアカウント単位の数字。取れなければ unavailable。

    投稿ごとの数字は threads_insights.py が毎日取っている。
    **同じものを取り直さない。** ここで欲しいのはアカウント側の
    フォロワーとプロフィール表示で、投稿単位では出ない。
    """
    import requests
    token = os.environ.get("THREADS_ACCESS_TOKEN", "")
    if not token:
        accts = os.environ.get("THREADS_ACCOUNTS", "")
        if accts:
            try:
                for a in json.loads(accts):
                    if a.get("name") == "さくら" and a.get("token"):
                        token = a["token"]
                        break
            except Exception as e:
                fail("sns.threads.token", e)
    if not token:
        return {}, "THREADS_ACCESS_TOKEN が無い"
    base = "https://graph.threads.net/v1.0"
    got = {}
    try:
        r = requests.get(f"{base}/me/threads_insights",
                         params={"metric": "followers_count",
                                 "access_token": token},
                         timeout=30)
        d = r.json()
        if r.status_code != 200:
            return {}, f"HTTP {r.status_code}: {str(d)[:120]}"
        for m in d.get("data", []):
            v = m.get("total_value", {}).get("value")
            if m.get("name") == "followers_count" and v is not None:
                got["followers"] = int(v)
    except Exception as e:
        return {}, f"取得に失敗: {e}"
    return got, ""


def threads_views_yesterday():
    """昨日出した投稿の表示数の合計。**昨日出していなければ 0 ではない。**

    投稿が0本の日は「合計する対象が無い」ので、値そのものが無い。
    0 と書くと「出したのに誰も見なかった」と読めるので measuring にする。
    """
    p = ROOT / "workspace/threads_insights/history.jsonl"
    if not p.exists():
        return None, "history.jsonl が無い"
    _, _, yday = yesterday_range()
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    mine = [r for r in rows if r.get("account") == "さくら"]
    if not mine:
        return None, "さくらの行が無い"
    # 同じ投稿が毎日入っているので、投稿IDごとに最後の測定だけ使う
    last = {}
    for r in mine:
        last[r["id"]] = r
    y = [r for r in last.values()
         if str(r.get("posted_at", ""))[:10] == yday]
    if not y:
        return None, f"{yday} に出した投稿が無い"
    return sum(int(r.get("views") or 0) for r in y), ""


def sns_block():
    out = {}
    # ── X ──
    xsrc = "social_inventory"
    try:
        out["x"] = {
            "posts_yesterday": metric(posts_yesterday("x"), "measured", xsrc,
                                      "在庫の投稿履歴から実測"),
            "followers": unavailable(
                "x_api", "読み取り用のAPIを持っていない（投稿用トークンのみ）"),
            "views": unavailable(
                "x_api", "読み取り用のAPIを持っていない。画面からの手入力待ち"),
            "profile_visits": unavailable("x_api", "同上"),
            "link_clicks": unavailable("x_api", "同上"),
        }
    except Exception as e:
        fail("sns.x", e)
        out["x"] = {k: unavailable(xsrc, f"取得に失敗: {e}") for k in
                    ("posts_yesterday", "followers", "views",
                     "profile_visits", "link_clicks")}

    # ── Threads ──
    tsrc = "threads_api"
    try:
        user, why = threads_user_metrics()
        if why:
            fail("sns.threads.user", why)
        views, vwhy = threads_views_yesterday()
        out["threads"] = {
            "posts_yesterday": metric(posts_yesterday("threads"), "measured",
                                      "social_inventory", "在庫の投稿履歴から実測"),
            "followers": (metric(user["followers"], "measured", tsrc)
                          if "followers" in user
                          else unavailable(tsrc, why or "followers_count が返らない")),
            "views": (metric(views, "measured", "threads_insights",
                             "昨日出した投稿の表示数の合計")
                      if views is not None
                      else metric(None, "measuring", "threads_insights", vwhy)),
            "profile_visits": unavailable(
                tsrc, "アカウント単位のプロフィール表示は未取得。画面からの手入力待ち"),
            "link_clicks": unavailable(
                tsrc, "Threads APIにリンククリックの指標が無い。GA4側で見る"),
        }
    except Exception as e:
        fail("sns.threads", e)
        out["threads"] = {k: unavailable(tsrc, f"取得に失敗: {e}") for k in
                          ("posts_yesterday", "followers", "views",
                           "profile_visits", "link_clicks")}
    return out


# ── 収益 ─────────────────────────────────────────────
def revenue_block():
    """ASPの管理画面から自動で取る口が無い。**推測で0を入れない。**"""
    src = "asp_manual"
    why = ("ASP管理画面へのログイン取得はしない方針（規約とBAN回避）。"
           "手入力の台帳もまだ無い")
    keys = ("cta_clicks", "affiliate_clicks", "conversions_pending",
            "conversions_confirmed", "revenue_pending", "revenue_confirmed")
    ledger = ROOT / "workspace/revenue/ledger.json"
    if ledger.exists():
        try:
            d = json.loads(ledger.read_text(encoding="utf-8"))
            _, _, yday = yesterday_range()
            row = (d.get("by_date") or {}).get(yday)
            if row is not None:
                return {k: (metric(int(row[k]), "measured", "manual_ledger",
                                   f"{yday} 分の手入力")
                            if k in row else unavailable(src, why))
                        for k in keys}
        except Exception as e:
            fail("revenue.ledger", e)
    need_human(
        "REVENUE_LEDGER",
        "収益の実績を統合Dailyに載せる（いまは全項目 unavailable）",
        "A8.net / もしもアフィリエイト の管理画面 → レポート（日別）",
        ["前日分の日別レポートを開く",
         "クリック数・発生件数・確定件数・発生報酬・確定報酬を控える",
         f"{ledger.relative_to(ROOT)} を作り、"
         '{"by_date": {"YYYY-MM-DD": {"affiliate_clicks": 0, '
         '"conversions_pending": 0, "conversions_confirmed": 0, '
         '"revenue_pending": 0, "revenue_confirmed": 0}}} の形で書く',
         "コミットすると翌日のsnapshotから measured になる"],
        "整数のみ（円は税込・整数）。0件の日は0を書く（未入力と区別するため）",
        "snapshot の revenue が unavailable から measured に変わること")
    return {k: unavailable(src, why) for k in keys}


# ── 組み立て ─────────────────────────────────────────
def build():
    blocks = {}
    for name, fn in (("articles", articles_block),
                     ("sns", sns_block),
                     ("revenue", revenue_block)):
        try:
            blocks[name] = fn()
        except Exception as e:
            fail(name, f"{e}\n{traceback.format_exc()[-400:]}")
            blocks[name] = {}
    snap = {
        "schema_version": SCHEMA,
        "site": SITE,
        "site_name": "sakura-eigo.com",
        "generated_at": now(),
        "stale_after_hours": 24,
        "value_status": {
            "measured": "実測できた。0 は「測って0だった」",
            "unavailable": "取得できない。value は null。0 にしない",
            "measuring": "計測中。まだ値が確定していない。value は null",
        },
        "articles": blocks["articles"],
        "sns": blocks["sns"],
        "revenue": blocks["revenue"],
        "data_sources": {
            "wordpress": {"used_for": ["articles"],
                          "auth": "アプリケーションパスワード（値は出さない）"},
            "social_inventory": {"used_for": ["sns.*.posts_yesterday"],
                                 "auth": "不要（リポジトリ内の在庫ファイル）"},
            "threads_api": {"used_for": ["sns.threads.followers"],
                            "auth": "アクセストークン（値は出さない）"},
            "threads_insights": {"used_for": ["sns.threads.views"],
                                 "auth": "不要（毎日の取得結果を読むだけ）"},
            "x_api": {"used_for": [], "auth": "投稿用のみ。読み取りは持っていない"},
            "asp_manual": {"used_for": ["revenue.*"], "auth": "手入力"},
            "excluded": {
                "google_search_console": "Ray側が直接取得しているので二重に持たない",
                "google_analytics_4": "同上",
            },
        },
        "collection_errors": ERRORS,
        "human_actions": ACTIONS,
    }
    return snap


# **名前ではなく値を探す。**
# 「WP_APP_PASSWORD が無い」のような説明文は秘密ではない。
# 秘密なのは、名前のうしろに実体が続いている形と、環境変数の実値のほう。
SECRET_HINTS = re.compile(
    r"(?i)(?:access[_-]?token|api[_-]?key|api[_-]?secret|app[_-]?password|"
    r"client[_-]?secret|private[_-]?key|WP_APP_PASSWORD|"
    r"THREADS_ACCESS_TOKEN|X_API_[A-Z]*|GSC_SERVICE_ACCOUNT[A-Z_]*)"
    r"\s*[=:]\s*[\"']?[A-Za-z0-9_\-./+]{8,}"
    r"|Bearer\s+[A-Za-z0-9_\-./+]{8,}"
    r"|BEGIN [A-Z ]*PRIVATE KEY"
    r"|(?:\?|&)access_token=")


def has_secret(snap):
    """**秘密が混ざっていないか。** 混ざっていたら書かない。"""
    text = json.dumps(snap, ensure_ascii=False)
    hits = [m.group(0)[:40] for m in SECRET_HINTS.finditer(text)]
    # 環境変数の実値そのものが入っていないかも見る
    for k in ("WP_APP_PASSWORD", "THREADS_ACCESS_TOKEN", "X_API_KEY",
              "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET",
              "GSC_SERVICE_ACCOUNT_JSON", "ANTHROPIC_API_KEY"):
        v = os.environ.get(k, "")
        if len(v) >= 8 and v in text:
            hits.append(f"{k} の値そのもの")
    return hits


def is_stale(snap, at=None):
    """**古いsnapshotを今日の値として使わせない。**

    戻り値は (古いか, 理由)。generated_at が無い・読めない場合も「古い」。
    読む側（Ray）はこれが True なら STALE_SNAPSHOT として扱う。
    """
    raw = (snap or {}).get("generated_at")
    if not raw:
        return True, "generated_at が無い"
    try:
        g = datetime.fromisoformat(raw)
    except Exception:
        return True, f"generated_at を読めない: {raw!r}"
    if g.tzinfo is None:
        return True, "generated_at にタイムゾーンが無い"
    limit = float((snap or {}).get("stale_after_hours") or 24)
    age = ((at or datetime.now(JST)) - g).total_seconds() / 3600
    if age > limit:
        return True, f"{age:.1f}時間前（上限 {limit:.0f}時間）"
    if age < -0.5:
        return True, f"未来の時刻（{age:.1f}時間）"
    return False, f"{age:.1f}時間前"


def main():
    """**例外を外へ出さない。** 落ちても本体の処理を止めないため。"""
    try:
        snap = build()
    except Exception as e:
        snap = {"schema_version": SCHEMA, "site": SITE,
                "generated_at": now(), "stale_after_hours": 24,
                "articles": {}, "sns": {}, "revenue": {},
                "data_sources": {},
                "collection_errors": ERRORS + [
                    {"block": "build", "reason": str(e)[:300], "at": now()}],
                "human_actions": ACTIONS}
    leaked = has_secret(snap)
    if leaked:
        print(f"秘密が混ざっている。**書かない**: {leaked[:3]}")
        return 1
    body = json.dumps(snap, ensure_ascii=False, indent=1) + "\n"
    for p in OUT_PATHS:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
            print(f"書いた: {p}")
        except Exception as e:
            print(f"書けない: {p} … {e}")
    n_ok = sum(1 for b in ("articles", "sns", "revenue")
               for m in _flat(snap.get(b, {}))
               if m.get("status") == "measured")
    n_na = sum(1 for b in ("articles", "sns", "revenue")
               for m in _flat(snap.get(b, {}))
               if m.get("status") == "unavailable")
    print(f"measured {n_ok} / unavailable {n_na} / "
          f"エラー {len(snap['collection_errors'])} / "
          f"人の作業 {len(snap['human_actions'])}")
    return 0


def _flat(block):
    """articles は1段、sns は2段。どちらも Metric まで降りる。"""
    for v in block.values():
        if isinstance(v, dict) and "status" in v:
            yield v
        elif isinstance(v, dict):
            for w in v.values():
                if isinstance(w, dict) and "status" in w:
                    yield w


if __name__ == "__main__":
    sys.exit(main())
