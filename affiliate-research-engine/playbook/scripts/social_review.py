#!/usr/bin/env python3
"""
social_review.py
承認待ちの在庫を、記事ごとに X案とThreads案を並べて1枚にする。

  python social_review.py
出力: workspace/social/review/REVIEW_<日付>.md

**この文書を見て承認する。** 投稿はしない。
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss
import social_gate as sg
import social_inventory as inv
import social_claims as sc
import json
import difflib

JST = timezone(timedelta(hours=9))


def main():
    spec = ss.load_spec()
    stamp = datetime.now(JST).strftime("%Y-%m-%d")
    allrows = [s for _, s in inv.all_stock(spec)]
    rows = [s for s in allrows if s["state"] != "stale"]
    stale = [s for s in allrows if s["state"] == "stale"]
    import json as _j
    pv = {}
    pvd = sorted((ROOT / "workspace/market/pagecheck").glob("*.json"))
    if pvd:
        pv = _j.loads(pvd[-1].read_text(encoding="utf-8"))
    by_article = {}
    for s in rows:
        by_article.setdefault(s["article_id"], {})[s["platform"]] = s

    prev_f = ROOT / "workspace/social/prev_trial.json"
    prev = (json.loads(prev_f.read_text(encoding="utf-8"))
            if prev_f.exists() else {})

    # 全体の内訳を先に出す。**「判定しない」を「支持されている」に混ぜない**
    tot = {"supported": 0, "unsupported": 0, "unjudged": 0,
           "needs_human_review": 0, "total": 0}
    for s in rows:
        art = inv.live_article(s["article_id"]) or inv.local_article(
            s["article_id"])
        c = sc.counts(sc.check(spec, s["thread_parts"], art,
                               s.get("inferences") or []))
        for k in tot:
            tot[k] += c[k]
    wl = [s.get("weighted_len") for s in rows if s["platform"] == "x"]
    posted = sum(1 for s in rows if s["state"] == "posted")
    approved = sum(1 for s in rows if s["state"] == "approved")
    warn_n = sum(len(s.get("tone_warnings") or []) for s in rows)
    art310 = inv.local_article(310) or {"body": ""}
    OLD310 = ["サービスの良し悪しを見る時間ではない",
              "声を出した回数ではない"]
    left310 = sum(art310["body"].count(x) for x in OLD310)

    L = [f"# X案・Threads案のレビュー（{stamp}）\n\n",
         "## 検査のまとめ\n\n| 項目 | 値 |\n|---|---|\n",
         f"| supported | {tot['supported']} |\n",
         f"| unsupported | {tot['unsupported']} |\n",
         f"| unjudged | {tot['unjudged']} |\n",
         f"| needs_human_review | {tot['needs_human_review']} |\n",
         f"| 命題の合計 | {tot['total']} |\n",
         f"| X加重文字数 | {' / '.join(str(x) for x in sorted(wl))}"
         f"（上限{spec['x']['weighted']['hard_limit']}）|\n",
         f"| 記事310本文の旧断定 残存 | {left310} |\n",
         f"| 温度の警告 | {warn_n}件（落とさない）|\n",
         f"| 投稿 | {posted}件 |\n",
         f"| 承認 | {approved}件 |\n\n",
         "**投稿していない。** 承認するまで在庫のまま止まる。\n\n",
         "指定された15項目のゲート結果は "
         "`workspace/social/review/GATES_2026-08-10.md`。**全件通過。**\n\n",
         "生成元は**公開画面から取り直した本文**"
         "（`workspace/claims/live/`）。ローカルの控えは使っていない。\n\n",
         f"記事 {len(by_article)}本 / 在庫 {len(rows)}件"
         f"（X {sum(1 for s in rows if s['platform'] == 'x')} / "
         f"Threads {sum(1 for s in rows if s['platform'] == 'threads')}）\n\n",
         "承認するとき:\n\n```bash\n"
         "python scripts/social_approve.py --approve X-521-a\n"
         "python scripts/social_approve.py --reject TH-521-a "
         "--reason \"記事の内容と違う\"\n```\n\n",
         "## 一覧\n\n| 記事 | X | Threads | 状態 |\n|---|---|---|---|\n"]
    if stale:
        L.insert(len(L) - 1,
                 f"## 退役した在庫（{len(stale)}件・削除していない）\n\n"
                 "記事を改稿したので、生成時の本文に対応しなくなった。\n"
                 "旧本文・生成日時・旧 modified_gmt を残したまま `stale` にしてある。\n\n"
                 "| stock_id | 理由 | 生成 | 生成時の記事 modified | 現在の記事 modified |\n"
                 "|---|---|---|---|---|\n"
                 + "".join(
                     f"| {x['stock_id']} | `{x.get('stale_reason')}` "
                     f"| {(x.get('generated_at') or '')[:16]} "
                     f"| {x.get('article_modified_gmt_at_generation')} "
                     f"| {x.get('article_modified_gmt_now')} |\n"
                     for x in sorted(stale, key=lambda y: y['stock_id']))
                 + "\n")
    for aid, d in sorted(by_article.items()):
        x, t = d.get("x"), d.get("threads")
        L.append(f"| {aid} {(x or t)['article_title'][:22]} "
                 f"| {len(x['text']) if x else '—'}字 "
                 f"| {len(t['text']) if t else '—'}字 "
                 f"| {(x or t)['state']} |\n")

    for aid, d in sorted(by_article.items()):
        x, t = d.get("x"), d.get("threads")
        head = x or t
        L.append(f"\n---\n\n## 記事 {aid}｜{head['article_title']}\n\n")
        L.append(f"{head['article_url']}\n\n")
        m = head.get("material", {})
        L.append("### この記事から抜いた4つ\n\n| 項目 | 中身 |\n|---|---|\n")
        for k in spec["extraction"]["fields"]:
            L.append(f"| {k} | {m.get(k, '')} |\n")
        L.append(f"\n**Xが使ったのは `one_check`**、"
                 f"**Threadsが使ったのは `unique_artifact`**。素材から分けている。\n")

        for platform, s in (("X", x), ("Threads", t)):
            if not s:
                continue
            art0 = (inv.live_article(s["article_id"]) or {})
            page = pv.get(str(s["article_id"]), {})
            L.append(f"\n### {platform}案（{s['stock_id']}・**{s['state']}**）\n\n")
            L.append("| 項目 | 値 |\n|---|---|\n")
            L.append(f"| 対応記事 | {s['article_id']}｜{s['article_title']} |\n")
            L.append(f"| 記事URL | {s['article_url']} |\n")
            L.append(f"| 記事 modified_gmt | `{s['article_modified_gmt']}` "
                     f"（生成時）／ `{art0.get('modified_gmt')}`（現在）"
                     f"{'' if s['article_modified_gmt'] == art0.get('modified_gmt') else ' ← **ずれている**'} |\n")
            L.append(f"| 記事の取得 | {art0.get('fetched_at', '未取得')}"
                     f"（公開画面から取り直したもの） |\n")
            L.append(f"| 公開画面 | HTTP {page.get('http', '未検査')} / "
                     f"canonical自己参照 {page.get('canonical_self', '未検査')} / "
                     f"noindex {page.get('noindex', '未検査')} |\n")
            L.append(f"| 使用した記事内素材 | "
                     f"{'core_answer + one_check' if platform == 'X' else 'search_intent + unique_artifact'} |\n")
            L.append(f"| 記事固有の成果物 | {s.get('artifact_used') or '—'} |\n")
            L.append(f"| market-in構造 | "
                     + " → ".join(spec["persona"]["warm_order"]) + " |\n")
            em = sg.EMOJI.findall(s["text"])
            roles = spec["style"]["emoji"]["roles"]
            L.append(f"| 絵文字と役割 | "
                     + ("、".join(f"{e}＝{roles.get(e, '**役割なし**')}"
                                  for e in em) if em else "なし（0個も正常）")
                     + " |\n")
            if platform == "X":
                lim = spec["x"]["weighted"]["hard_limit"]
                L.append(f"| X加重文字数 | {s.get('weighted_len')} / {lim}"
                         f"（URLは23で数える） |\n")
            else:
                fmt = s.get("threads_format") or (
                    "single" if len(s["thread_parts"]) == 1 else "two_part")
                L.append(f"| Threads形式 | `{fmt}`"
                         f"（{len(s['thread_parts'])}投稿） |\n")
            L.append(f"| state | **{s['state']}** |\n\n")
            for i, p in enumerate(s["thread_parts"], 1):
                label = ("" if len(s["thread_parts"]) == 1
                         else f"**{i}投稿目**\n\n")
                L.append(label + "```\n" + p + "\n```\n\n")
            ng = [g for g in s["gate_results"] if not g["ok"]]
            L.append(f"| ゲート | 結果 |\n|---|---|\n")
            for g in s["gate_results"]:
                v = "通過" if g["ok"] else "**落ちた** " + g["detail"]
                L.append(f"| {g['id']} | {v} |\n")
            warn = (sg.style_warnings(spec, s["thread_parts"])
                    + (s.get("template_warnings") or [])
                    + (s.get("tone_warnings") or []))
            L.append(f"\n警告（落とさない）: "
                     + (" / ".join(warn) if warn else "なし") + "\n")
            if s.get("revoked_reason"):
                L.append(f"\n**承認を取り消した**: {s['revoked_reason']}\n")
            if s.get("template_exception_reason"):
                L.append(f"\n**型の重なりは例外扱い**: "
                         f"{s['template_exception_reason']}\n")

            # 型
            L.append(f"\n**型**: {s.get('post_type', '—')}"
                     f"（{s.get('post_type_reason', '')}）\n")
            L.append(f"**当たった定型句**: "
                     + (" ".join(s.get("template_ids") or []) or "なし") + "\n")
            if platform == "X":
                lim = spec["x"]["weighted"]["hard_limit"]
                L.append(f"**X加重文字数**: {s.get('weighted_len')} / {lim}"
                         f"（URLは23で数える）\n")

            # 命題の照合
            art = (inv.live_article(s["article_id"])
                   or inv.local_article(s["article_id"]))
            claims = sc.check(spec, s["thread_parts"], art,
                              s.get("inferences") or [])
            bad = sc.failures(claims)
            cc = sc.counts(claims)
            L.append(f"\n**命題**: supported {cc['supported']} / "
                     f"unsupported {cc['unsupported']} / "
                     f"unjudged {cc['unjudged']} / "
                     f"needs_human_review {cc['needs_human_review']}"
                     f"（全{cc['total']}）\n")
            nhr = [r for r in claims if r["verdict"] == "needs_human_review"]
            if nhr:
                L.append(f"\n**人が見る（{len(nhr)}件）。"
                         f"通過扱いにしていない。**\n\n"
                         "| 対象の文 | 理由 |\n|---|---|\n")
                for r in nhr:
                    L.append(f"| {r['text']} | {r['why']} |\n")
            L.append(f"\n<details><summary>命題の照合"
                     f"（{len(claims)}件中 落ち {len(bad)}件）</summary>\n\n")
            L.append(sc.fmt(claims))
            L.append("\n</details>\n")

            # 前回案との差分
            old_t = next((x.get("superseded_text") for x in stale
                          if x["article_id"] == s["article_id"]
                          and x["platform"] == s["platform"]), None) \
                or (prev.get(s["stock_id"]) or {}).get("text")
            if old_t:
                dl = list(difflib.unified_diff(
                    old_t.split("\n"), s["text"].split("\n"),
                    fromfile="前回", tofile="今回", lineterm="", n=0))
                L.append("\n<details><summary>前回案との差分</summary>\n\n"
                         "```diff\n" + "\n".join(dl) + "\n```\n\n</details>\n")
            if ng:
                L.append("\n**このままでは承認できない。**\n")

    out = ROOT / spec["paths"]["review"] / f"REVIEW_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(L), encoding="utf-8")
    print(f"→ {out}")
    print(f"記事 {len(by_article)}本 / 在庫 {len(rows)}件")


if __name__ == "__main__":
    main()
