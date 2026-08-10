#!/usr/bin/env python3
"""
test_snapshot.py
統合Daily Report へ渡す snapshot の検査。

  python test_snapshot.py

守るもの
  1. 実測0が measured になる（0 を unavailable にしない）
  2. unavailable が 0 にならない（null のまま）
  3. generated_at が入っている
  4. secret が含まれない
  5. schema_version が一致する
  6. site が sakura
  7. 古い snapshot を識別できる
  8. snapshot が落ちても本体処理を止めない
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import snapshot_sakura as sn

ROOT = Path(__file__).resolve().parents[1]
fails = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "NG  ") + name + (f" … {detail}" if detail else ""))
    if not ok:
        fails.append(name)


# ── Metric の形 ──────────────────────────────────────
m0 = sn.metric(0, "measured", "wordpress", "実測して0だった")
check("実測0は measured で value 0",
      m0["value"] == 0 and m0["status"] == "measured", str(m0))
check("実測0が unavailable に化けない", m0["status"] != "unavailable")

mu = sn.unavailable("x_api", "読み取りAPIが無い")
check("unavailable の value は null（0にしない）",
      mu["value"] is None and mu["status"] == "unavailable", str(mu))

mm = sn.metric(123, "measuring", "threads_insights", "まだ確定していない")
check("measuring は値を渡しても null になる",
      mm["value"] is None and mm["status"] == "measuring", str(mm))

try:
    sn.metric(None, "measured", "wordpress")
    check("measured なのに値が無いものは作れない", False, "作れてしまった")
except AssertionError:
    check("measured なのに値が無いものは作れない", True)

try:
    sn.metric(1, "guessed", "wordpress")
    check("知らない status は作れない", False, "作れてしまった")
except AssertionError:
    check("知らない status は作れない", True)

for m in (m0, mu, mm):
    check(f"Metricに5つの鍵がそろう（{m['status']}）",
          set(m) == {"value", "status", "source", "observed_at", "note"},
          str(sorted(m)))

# ── 組み立てた snapshot ──────────────────────────────
snap = sn.build()
check("schema_version が site-daily-snapshot/1",
      snap["schema_version"] == "site-daily-snapshot/1",
      snap["schema_version"])
check("site が sakura", snap["site"] == "sakura", snap["site"])
check("generated_at が入っている", bool(snap.get("generated_at")),
      str(snap.get("generated_at")))
check("generated_at にタイムゾーンが付いている",
      datetime.fromisoformat(snap["generated_at"]).tzinfo is not None)
for b in ("articles", "sns", "revenue", "data_sources",
          "collection_errors", "human_actions"):
    check(f"ブロック {b} がある", b in snap)

# すべての Metric が3つの status のどれかで、null と 0 が混ざらない
bad = []
for name in ("articles", "sns", "revenue"):
    for m in sn._flat(snap[name]):
        if m["status"] not in ("measured", "unavailable", "measuring"):
            bad.append(f"{name}: 知らない status {m['status']}")
        if m["status"] == "measured" and m["value"] is None:
            bad.append(f"{name}: measured なのに null")
        if m["status"] != "measured" and m["value"] is not None:
            bad.append(f"{name}: {m['status']} なのに値が入っている")
        if not m.get("source"):
            bad.append(f"{name}: source が空")
        if not m.get("observed_at"):
            bad.append(f"{name}: observed_at が空")
check("value と status が食い違っていない", not bad, " / ".join(bad[:3]))

# 収益は推測で0を入れない
rev = snap["revenue"]
zeros = [k for k, v in rev.items()
         if v["status"] == "unavailable" and v["value"] == 0]
check("取れない収益を0で埋めていない", not zeros, " ".join(zeros))

# ── secret ───────────────────────────────────────────
check("秘密が混ざっていない", not sn.has_secret(snap),
      str(sn.has_secret(snap))[:120])

leaky = dict(snap)
leaky["debug"] = {"note": "THREADS_ACCESS_TOKEN=THAAbcdef0123456789xyz"}
check("トークンらしき値を見つけられる", bool(sn.has_secret(leaky)))
leaky2 = dict(snap)
leaky2["debug"] = {"url": "https://graph.threads.net/v1.0/me?access_token=abc123def"}
check("URLに載ったトークンを見つけられる", bool(sn.has_secret(leaky2)))
okmsg = dict(snap)
okmsg["debug"] = {"note": "THREADS_ACCESS_TOKEN が無い"}
check("名前だけの説明文は秘密扱いしない", not sn.has_secret(okmsg),
      str(sn.has_secret(okmsg))[:80])

os.environ["SNAPSHOT_TEST_SECRET"] = "sk-test-abcdefgh12345678"
try:
    # 環境変数の実値が混ざったら見つかること（既知の鍵名で試す）
    os.environ["WP_APP_PASSWORD"] = "wp-secret-value-1234"
    leaky3 = dict(snap)
    leaky3["debug"] = {"pw": "wp-secret-value-1234"}
    check("環境変数の実値が混ざったら見つける", bool(sn.has_secret(leaky3)))
finally:
    os.environ.pop("WP_APP_PASSWORD", None)
    os.environ.pop("SNAPSHOT_TEST_SECRET", None)

# ── 古い snapshot ────────────────────────────────────
now = datetime.now(sn.JST)
fresh = {"generated_at": (now - timedelta(hours=2)).isoformat(),
         "stale_after_hours": 24}
old = {"generated_at": (now - timedelta(hours=25)).isoformat(),
       "stale_after_hours": 24}
edge = {"generated_at": (now - timedelta(hours=23, minutes=59)).isoformat(),
        "stale_after_hours": 24}
future = {"generated_at": (now + timedelta(hours=3)).isoformat(),
          "stale_after_hours": 24}
check("2時間前は古くない", sn.is_stale(fresh, now)[0] is False,
      sn.is_stale(fresh, now)[1])
check("23時間59分前はまだ古くない", sn.is_stale(edge, now)[0] is False)
check("25時間前は STALE", sn.is_stale(old, now)[0] is True,
      sn.is_stale(old, now)[1])
check("generated_at が無ければ STALE", sn.is_stale({}, now)[0] is True)
check("読めない generated_at は STALE",
      sn.is_stale({"generated_at": "きのう"}, now)[0] is True)
check("タイムゾーンが無ければ STALE",
      sn.is_stale({"generated_at": "2026-08-10T12:00:00"}, now)[0] is True)
check("未来の時刻も STALE", sn.is_stale(future, now)[0] is True)
check("いま書いた snapshot は古くない", sn.is_stale(snap, now)[0] is False)

# ── 落ちても止めない ─────────────────────────────────
_orig = sn.articles_block
try:
    sn.articles_block = lambda: (_ for _ in ()).throw(
        RuntimeError("WordPressが落ちている"))
    s2 = sn.build()
    check("収集が例外を投げても snapshot は返る", isinstance(s2, dict))
    check("落ちた収集は collection_errors に残る",
          any(e["block"] == "articles" for e in s2["collection_errors"]),
          str(s2["collection_errors"])[:120])
    check("落ちても他のブロックは埋まる", bool(s2["sns"]))
finally:
    sn.articles_block = _orig
    sn.ERRORS.clear()

# 実行そのものが 0 で終わること（本体の後段を止めない）
r = subprocess.run([sys.executable, str(ROOT / "scripts/snapshot_sakura.py")],
                   capture_output=True, text=True, cwd=str(ROOT))
check("スクリプト単体の終了コードが0", r.returncode == 0,
      (r.stdout + r.stderr)[-200:])

# 書き出したファイルが読める形になっているか
for p in sn.OUT_PATHS:
    check(f"{p.name} が {p.parent.name}/ に出ている", p.exists(), str(p))
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        check(f"{p.parent.parent.parent.name}: JSONとして読める",
              d["schema_version"] == "site-daily-snapshot/1")
        check(f"{p.parent.parent.parent.name}: site=sakura",
              d["site"] == "sakura")

_a = json.loads(sn.OUT_PATHS[0].read_text(encoding="utf-8"))
_b = json.loads(sn.OUT_PATHS[1].read_text(encoding="utf-8"))
check("2つの置き場で中身が同じ", _a == _b)

print()
if fails:
    print(f"失敗 {len(fails)}件")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("失敗 0件")
