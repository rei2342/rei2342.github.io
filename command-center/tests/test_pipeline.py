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

    import shutil

    s = C.load_settings()
    made, outbox_files = [], []
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
        outbox_files += [v["outbox"] for v in r["results"].values() if isinstance(v.get("outbox"), str)]
    for i in made:  # 後片付け（ダッシュボードの outbox・画像にダミーを残さない）
        drafts.path(i).unlink(missing_ok=True)
        C.DATA_DIR.joinpath("outbox", "note", f"{i}.png").unlink(missing_ok=True)
        shutil.rmtree(C.ROOT / s.get("publishing", {}).get("instagram", {}).get("media_dir", "data/media") / i,
                      ignore_errors=True)
    for f in outbox_files:
        Path(f).unlink(missing_ok=True)
        Path(f).with_suffix(".png").unlink(missing_ok=True)


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


def test_llm_backend_fallback_order():
    """先頭が残高不足などで落ちたら次へ。拒否は次へ回さない。鍵が無いものは飛ばす。"""
    from core import llm

    calls = []
    orig = dict(llm.BACKENDS)
    try:
        def broke(*a):
            calls.append("broke"); raise llm.LLMError("credit balance is too low")

        def missing(*a):
            calls.append("missing"); raise llm.BackendUnavailable("no key")

        def ok(*a):
            calls.append("ok"); return {"v": 1}

        llm.BACKENDS.update({"anthropic_api": broke, "openai": missing, "claude_cli": ok})
        s = {"llm": {"backends": ["anthropic_api", "openai", "claude_cli"]}}
        assert llm.generate_json("s", "u", {"type": "object"}, s) == {"v": 1}
        assert calls == ["broke", "missing", "ok"] and llm.last_backend == "claude_cli"

        def refuse(*a):
            raise llm.LLMRefusal("refused")

        llm.BACKENDS.update({"anthropic_api": refuse})
        calls.clear()
        try:
            llm.generate_json("s", "u", {"type": "object"}, s)
            raise AssertionError("拒否が次のバックエンドに回った")
        except llm.LLMRefusal:
            pass
        assert calls == []
    finally:
        llm.BACKENDS.clear(); llm.BACKENDS.update(orig)


def test_cli_env_drops_api_keys():
    import os

    from core import llm

    os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "x") or "x"
    env = llm._cli_env()
    assert not any(k.startswith(("ANTHROPIC", "CLAUDE")) for k in env) and env.get("USER")


def test_local_logs_only_own_posts(tmp=None):
    import json
    import tempfile

    from core import account_crawler as A

    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.jsonl"
        f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
            {"text": "本人の投稿テキストです。十分な長さ", "url": "https://x.com/sakura_eigo30/status/1"},
            {"text": "競合の投稿テキストです。十分な長さ", "url": "https://x.com/someone_else/status/2"},
        ]), encoding="utf-8")
        orig = A._local_log_paths
        try:
            A._local_log_paths = lambda *a: [(f, False)]
            got = A.crawl_local_logs("x", "sakura_eigo30", "sakura_eigo30")["posts"]
            assert [p["url"] for p in got] == ["https://x.com/sakura_eigo30/status/1"]
            A._local_log_paths = lambda *a: [(f, True)]  # アカウント専用ログは絞らない
            assert len(A.crawl_local_logs("x", "sakura_eigo30", "sakura_eigo30")["posts"]) == 2
        finally:
            A._local_log_paths = orig


def test_candidate_notes_survive_replace_import():
    m = L.load_master()
    if not m.get("candidate_notes"):
        return
    import copy

    bak = C.MASTER_PATH.read_bytes()
    try:
        new = copy.deepcopy(m); new.pop("candidate_notes")
        L.import_master(new, "replace", note="test")
        assert L.load_master().get("candidate_notes") == m["candidate_notes"]
    finally:
        C.MASTER_PATH.write_bytes(bak)


def test_a8_decode_matches_verified_codes():
    from core import affiliate_unlock as U

    m = L.load_master()
    for p in m["asp_inventory"]["a8"]["programs"]:
        if p.get("affiliate_url"):
            d = U.decode_a8(p["affiliate_url"])
            assert d["advertiser"] == int(p["program_id"][1:-3]), p["program_id"]


def test_harvested_codes_checked_against_console_media():
    """公開記事のタグは、管理画面の媒体別コードと2番目のブロックが一致したときだけ媒体が決まる。"""
    from core import affiliate_unlock as U

    m = L.load_master()
    codes = {"s00000017068001": {
        "001": {"href": "x", "partner_code": "4S2ALU", "material": "TEXT", "media_options": [], "sns_link": True},
        "007": {"href": "x", "partner_code": "4S2F8I", "material": "TEXT", "media_options": [], "sns_link": True}}}
    rows = [{"account_key": "sakura_eigo30", "site": "https://sakura-eigo.com/", "page": "p", **U.decode_a8(h)}
            for h in ("https://px.a8.net/svt/ejp?a8mat=4BA75B+4S2ALU+3NP4+5YRHE",   # 001 のコード → ok
                      "https://px.a8.net/svt/ejp?a8mat=4BA75B+4S2F8I+3NP4+5YRHE",   # 007 のコードを sakura に → ずれ
                      "https://px.a8.net/svt/ejp?a8mat=4BA75B+ZZZZZZ+3NP4+5YRHE")]  # どれとも一致しない
    st = {r["partner_code"]: r["state"] for r in U.check_harvest(m, {"rows": rows}, codes)}
    assert st == {"4S2ALU": "ok", "4S2F8I": "media_mismatch", "ZZZZZZ": "not_in_console"}


def test_cushion_routes_sns_to_own_wp():
    from core import content_generator as G

    s = C.load_settings()
    a = L.get_account("sakura_eigo30")
    ctx = G.build_context(a, a.active_platforms(), s, None, [])
    wp = a.platform("wordpress")["url"]
    for p, c in ctx["per_platform"].items():
        if p == "wordpress":
            continue
        assert not c["affiliate_urls"], p            # SNS/note に広告リンクは渡さない
        if c.get("cushion"):
            assert c["cushion"]["via_url"] == wp and wp in c["allowed_urls"]


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
