"""オフライン検査（API キー・ネット不要）。python -m pytest tests -q または python tests/test_pipeline.py"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import account_loader as L  # noqa: E402
from core import config as C  # noqa: E402
from core import guards  # noqa: E402


def test_routing_is_data_driven():
    m = L.load_master()
    for a in L.get_accounts(m):
        for p in a.active_platforms():
            v = a.platform(p)
            assert v["status"] == "active" and v["url"], (a.key, p)
        for p, v in a.platforms.items():
            if v.get("status") != "active":
                assert p not in a.active_platforms()


def test_affiliate_media_guard():
    s = C.load_settings()
    for a in L.get_accounts():
        for p in a.platforms:
            target = a.platform(p).get("url")
            for af in L.affiliate_pool(a, target, s):
                if af["usable"]:
                    assert af["affiliate_url"] and af["registered_media_url"]
                    assert L.url_within(target, af["registered_media_url"])
        # 自動投稿では auto_publish_allowed=false の案件は使えない
        for p in a.active_platforms():
            for af in L.affiliate_pool(a, a.platform(p)["url"], s, for_auto_publish=True):
                assert not af["usable"] or af["program_id"] in (s.get("affiliate", {}).get("auto_publish_overrides") or [])


def test_url_within():
    assert L.url_within("https://sakura-eigo.com/", "https://sakura-eigo.com/")
    assert L.url_within("https://www.sakura-eigo.com/abc/", "https://sakura-eigo.com/")
    assert not L.url_within("https://note.com/sakura_eigo30", "https://sakura-eigo.com/")
    assert not L.url_within("https://note.com/rayait1917x", "https://note.com/rayait1917")


def test_guards():
    lim = C.load_settings()["platform_limits"]
    ctx = {"allowed_urls": ["https://a.example/"], "affiliate_urls": ["https://px.a8.net/x"], "pr_label": "PR"}
    i = guards.check_platform("x", {"posts": ["あ" * 141]}, ctx, lim)
    assert guards.has_errors(i)
    i = guards.check_platform("x", {"posts": ["見て https://px.a8.net/x"]}, {**ctx, "allowed_urls": ["https://px.a8.net/x"]}, lim)
    assert any("PR" in x["msg"] for x in i)
    i = guards.check_platform("x", {"posts": ["捏造 https://evil.example/"]}, ctx, lim)
    assert any("許可リスト外" in x["msg"] for x in i)
    assert guards.x_weighted_len("abc https://example.com/very/long") == 4 + 23


def _fake_result(targets, acct, ctx):
    own = acct.own_destinations()[0]["url"] if acct.own_destinations() else ""
    outs = {}
    for p in targets:
        if p == "wordpress":
            outs[p] = {"title": "t", "slug": "t", "excerpt": "e", "meta_description": "m",
                       "html": "<h2>見出し</h2>" + "<p>本文。</p>" * 400, "affiliate_program_ids": []}
        elif p == "note":
            outs[p] = {"title": "t", "markdown": "## 見出し\n" + "本文。\n" * 500, "hashtags": [], "affiliate_program_ids": []}
        elif p in ("x", "threads"):
            outs[p] = {"posts": ["迷っている人へ。確認するのは1点だけ。", f"続きはこちら {own}"], "buzz_followup": f"まとめ {own}"}
        elif p == "instagram":
            outs[p] = {"slides": [{"headline": f"見出し{i}", "body": "本文" * 10} for i in range(6)],
                       "caption": "保存して見返してね。詳しくはプロフィールから", "hashtags": ["#a", "#b", "#c"]}
    return {"reader_problem": "r", "angle": "a", "outputs": outs}


def test_generate_to_dryrun_publish(tmp_path=None):
    from core import content_generator as G
    from core import drafts
    from publishers.base import publish_draft

    s = C.load_settings()
    made = []
    for acct in L.get_accounts():
        targets = acct.active_platforms()
        ctx = G.build_context(acct, targets, s, None, [])
        d = G.finalize_draft(acct, "テスト", targets, _fake_result(targets, acct, ctx), ctx, s, render_images=True)
        made.append(d["id"])
        assert set(d["outputs"]) == set(targets)
        assert not guards.has_errors(d["issues"]), d["issues"]
        if "instagram" in targets:
            assert len(d["outputs"]["instagram"]["image_paths"]) == 6
        drafts.approve(d["id"])
        r = publish_draft(d["id"], live=False)
        assert r["dry_run"] and all(v.get("ok") for v in r["results"].values()), r
    for i in made:  # 後片付け
        drafts.path(i).unlink(missing_ok=True)


def test_buzz_evaluate():
    from automation.buzz_hunter import evaluate

    th = C.load_settings()["buzz"]["thresholds"]["x"]
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    hit, sig = evaluate({"created_at": old, "impressions": 3000, "engagements": 30}, "x", th, 30)
    assert hit and sig["views_per_hour"] >= 800
    hit, _ = evaluate({"created_at": old, "impressions": 100, "engagements": 1}, "x", th, 30)
    assert not hit


def test_buzz_followup_uses_own_url_only():
    from automation.buzz_hunter import build_followup

    s = C.load_settings()
    for acct in L.get_accounts():
        for p in ("x", "threads"):
            if acct.is_active(p) and acct.own_destinations():
                text, issues = build_followup(acct, p, {"post_id": "0"}, s)
                assert not guards.has_errors(issues), (acct.key, issues)
                assert any(d["url"] in text for d in acct.own_destinations())


def test_revenue_csv():
    from core import revenue

    bak = revenue.LEDGER.read_bytes() if revenue.LEDGER.exists() else None
    try:
        csv = "成果発生日,プログラム名,成果報酬額,ステータス\n2026/11/07,プログリット,30000,発生\n".encode("cp932")
        n, mp = revenue.import_csv(csv, "sakura_eigo30", "A8.net")
        assert n == 1 and mp["amount"] == "成果報酬額"
        n2, _ = revenue.import_csv(csv, "sakura_eigo30", "A8.net")
        assert n2 == 0  # 重複は入れない
    finally:
        if bak is None:
            revenue.LEDGER.unlink(missing_ok=True)
        else:
            revenue.LEDGER.write_bytes(bak)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except Exception as e:
                fails += 1
                print("FAIL", name, repr(e)[:400])
    sys.exit(1 if fails else 0)
