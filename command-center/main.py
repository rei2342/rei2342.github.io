#!/usr/bin/env python3
"""COMMAND CENTER CLI

  python main.py discover [--root ~/dev ...]     ローカルから実アカウントの痕跡を探す（読み取り専用）
  python main.py accounts                       マスターから認識したアカウントと媒体ルーティング
  python main.py import <json> [--merge]        Astra の accounts_master.json を取り込む
  python main.py env-template                   マスターから config/.env.example を生成
  python main.py crawl <account>|--all [--platform x] 実アカウントを取得して文体を校正
  python main.py generate --account さくら [--topic ...] [--all]  媒体分を一括生成（テーマ省略=実データから自動選定）
  python main.py drafts [<account>]             下書き一覧
  python main.py approve <draft_id> [-p x ...]  承認
  python main.py publish <draft_id> [--live]    配信（--live 無しは outbox へ保存のみ）
  python main.py buzz [--loop] [--live]         バズ検知（＋設定次第で追撃リプライ）
  python main.py reply <alert_id> [--live]      検知した投稿へ追撃リプライ
  python main.py note-login <account>           note のログインセッションを保存
  python main.py enable <account> <platform>    その媒体への書き込みを許可
  python main.py dashboard                      Streamlit を起動
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config as C  # noqa: E402
from core import account_loader as L  # noqa: E402


def _p(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_accounts(a):
    s = C.load_settings()
    for acct in L.get_accounts():
        print(f"\n■ {acct.label}  ({acct.key})")
        print(f"  funnel: {acct.funnel_summary()}")
        for r in acct.route(s):
            mark = "●" if r.can_publish else ("○" if r.readable else "×")
            print(f"  {mark} {r.platform:<10} {str(r.handle or ''):<18} {str(r.url or '-'):<45} {r.reason}")
        dest = acct.own_destinations()
        if dest:
            print("  誘導先: " + " / ".join(f"{d['type']}={d['url']}" for d in dest))
        for p in acct.active_platforms():
            pool = L.affiliate_pool(acct, acct.platform(p)["url"], s)
            ok = [x["program_name"][:24] for x in pool if x["usable"]]
            if ok:
                print(f"  案件@{p}: {len(ok)}件 " + ", ".join(ok[:4]) + (" …" if len(ok) > 4 else ""))
    print("\n● 配信可  ○ 生成のみ  × 稼働対象外")


def cmd_env_template(a):
    m = L.load_master()
    lines = ["# 生成: python main.py env-template（アカウントは accounts_master.json から動的に展開）",
             "# 値は config/.env に書く。.env は git に入れない。", "",
             "# GitHub Actions では既存 Secret REI_AFFSAKU を ANTHROPIC_API_KEY として渡している",
             "ANTHROPIC_API_KEY=", "",
             "# 既存 Secret と同じ形式も読める: THREADS_ACCOUNTS=[{\"name\":\"さくら\",\"token\":\"...\"},{\"name\":\"AKIRA\",\"token\":\"...\"}]",
             "THREADS_ACCOUNTS=", "",
             "# ---- 既存 GitHub Secrets と同名（settings.credentials.global_fallback_account のアカウントで使う）",
             "WP_USER=", "WP_APP_PASSWORD=", "X_API_KEY=", "X_API_SECRET=", "X_ACCESS_TOKEN=", "X_ACCESS_TOKEN_SECRET=",
             "THREADS_ACCESS_TOKEN=", ""]
    for acct in L.get_accounts(m):
        sfx = C.env_suffix(acct.key)
        act = acct.active_platforms()
        lines.append(f"# ---- {acct.label} ({acct.key})  稼働: {', '.join(act) or 'なし'}")
        for p in act:
            for k in C.CRED_KEYS.get(p, []) + C.OPTIONAL_KEYS.get(p, []):
                lines.append(f"{k}__{sfx}=")
        lines.append("")
    out = C.CONFIG_DIR / ".env.example"
    out.write_text("\n".join(lines), encoding="utf-8")
    if not C.ENV_PATH.exists():
        C.ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
        print(f"作成: {C.ENV_PATH}")
    print(f"作成: {out}")


def main():
    ap = argparse.ArgumentParser(description="COMMAND CENTER")
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("discover"); d.add_argument("--root", action="append"); d.add_argument("--no-browser", action="store_true")
    sp.add_parser("accounts")
    i = sp.add_parser("import"); i.add_argument("path"); i.add_argument("--merge", action="store_true")
    sp.add_parser("env-template")
    c = sp.add_parser("crawl"); c.add_argument("account", nargs="?"); c.add_argument("--all", action="store_true"); c.add_argument("--platform", action="append"); c.add_argument("--no-llm", action="store_true")
    g = sp.add_parser("generate"); g.add_argument("account_pos", nargs="?"); g.add_argument("topic_pos", nargs="?")
    g.add_argument("--account"); g.add_argument("--topic", default=""); g.add_argument("--all", action="store_true")
    g.add_argument("--platform", action="append"); g.add_argument("--affiliate", action="append")
    g.add_argument("--source", action="append"); g.add_argument("--notes", default="")
    ds = sp.add_parser("drafts"); ds.add_argument("account", nargs="?")
    ap_ = sp.add_parser("approve"); ap_.add_argument("draft_id"); ap_.add_argument("-p", "--platform", action="append")
    pb = sp.add_parser("publish"); pb.add_argument("draft_id"); pb.add_argument("-p", "--platform", action="append"); pb.add_argument("--live", action="store_true")
    b = sp.add_parser("buzz"); b.add_argument("--loop", action="store_true"); b.add_argument("--live", action="store_true")
    r = sp.add_parser("reply"); r.add_argument("alert_id"); r.add_argument("--live", action="store_true"); r.add_argument("--text")
    nl = sp.add_parser("note-login"); nl.add_argument("account")
    en = sp.add_parser("enable"); en.add_argument("account"); en.add_argument("platform"); en.add_argument("--off", action="store_true")
    sp.add_parser("dashboard")
    a = ap.parse_args()

    if a.cmd == "discover":
        from core import discovery

        rep = discovery.run(a.root, include_browser=not a.no_browser)
        print(f"scanned={rep['files_scanned']} matched={len(rep['matched_to_master'])} candidates={len(rep['unmatched_candidates'])}")
        _p({"matched_to_master": rep["matched_to_master"][:30], "unmatched_candidates": rep["unmatched_candidates"][:30],
            "credential_keys": {k: {"has_real_value": v["has_real_value"], "github_secret": v.get("github_secret", False),
                                    "files": v["files"][:3]} for k, v in rep["credential_keys"].items()}})
    elif a.cmd == "accounts":
        cmd_accounts(a)
    elif a.cmd == "import":
        new = json.loads(Path(a.path).read_text(encoding="utf-8"))
        _, w = L.import_master(new, "merge" if a.merge else "replace", note=f"cli {a.path}")
        print("取り込み完了"); [print("  warn:", x) for x in w]
        cmd_accounts(a)
    elif a.cmd == "env-template":
        cmd_env_template(a)
    elif a.cmd == "crawl":
        from core.account_crawler import crawl

        for n in ([x.key for x in L.get_accounts()] if a.all else [a.account]):
            acct = L.get_account(n)
            res = crawl(acct.key, platforms=a.platform, use_llm=not a.no_llm)
            print(f"■ {acct.label}")
            for p, d in res["platforms"].items():
                print(f"  {'✓' if d['ok'] else '✗'} {p:<10} {d.get('source') or '':<20} {len(d.get('posts', []))}件 {(d.get('error') or '')[:120]}")
            sm = res.get("style_metrics") or {}
            if sm:
                print(f"  文体: 平均{sm['avg_chars']}字 / 1行{sm['chars_per_line']}字 / です・ます率{sm['desu_masu_ratio']} / 絵文字{sm['emoji_per_post']}/投稿")
            if res.get("tone_summary_error"):
                print(f"  トーン要約: {res['tone_summary_error'][:120]}")
    elif a.cmd == "generate":
        from core.content_generator import generate

        names = [x.key for x in L.get_accounts()] if a.all else [a.account or a.account_pos]
        if not names[0]:
            sys.exit("アカウントを指定: generate --account さくら（全員なら --all）")
        failed = 0
        for n in names:
            acct = L.get_account(n)
            try:
                d = generate(acct.key, a.topic or a.topic_pos or "", a.platform, a.affiliate, a.notes, a.source)
            except Exception as e:
                failed += 1
                print(f"✗ {acct.label}: {type(e).__name__}: {e}")
                continue
            errs = [i for i in d["issues"] if i["level"] == "error"]
            print(f"✓ {acct.label}: draft {d['id']}  テーマ「{d['topic'][:40]}」 媒体={list(d['outputs'])} error={len(errs)} warn={len(d['issues']) - len(errs)}")
            for i in d["issues"]:
                print(f"    {i['level']:5} {i['platform']} {i['where']}: {i['msg']}")
        sys.exit(1 if failed else 0)
    elif a.cmd == "drafts":
        from core import drafts

        for d in drafts.list_all(L.get_account(a.account).key if a.account else None):
            print(d["id"], d["topic"][:30], d.get("platform_status"))
    elif a.cmd == "approve":
        from core import drafts

        _p(drafts.approve(a.draft_id, a.platform)["platform_status"])
    elif a.cmd == "publish":
        from publishers.base import publish_draft

        _p(publish_draft(a.draft_id, a.platform, live=a.live))
    elif a.cmd == "buzz":
        from automation import buzz_hunter

        if a.loop:
            buzz_hunter.loop(live=a.live)
        else:
            _p(buzz_hunter.run_once(live=a.live))
    elif a.cmd == "reply":
        from automation import buzz_hunter

        _p(buzz_hunter.execute(a.alert_id, live=a.live, text=a.text))
    elif a.cmd == "note-login":
        from publishers.note_publisher import login

        print("保存:", login(L.get_account(a.account).key))
    elif a.cmd == "enable":
        acct = L.get_account(a.account)
        L.set_write_enabled(acct.key, a.platform, not a.off)
        print(f"{acct.label}.{a.platform} write_enabled={not a.off}")
    elif a.cmd == "dashboard":
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(C.ROOT / "dashboard" / "app.py")], cwd=C.ROOT)


if __name__ == "__main__":
    main()
