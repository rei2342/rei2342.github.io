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

import subprocess

import requests
import urllib3

# 借りているワークフロー（rewrite-uploader）は pyyaml を入れていない。
# **足りないものはここで入れる。** ワークフロー側を直すと本来の用途に影響する
try:
    import yaml
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                           "pyyaml"])
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


def trash(pid):
    """**ゴミ箱へ移すだけ。** force を付けないので完全削除にならない。

    POST の status=trash は REST が受け付けない（rest_invalid_param）。
    DELETE が既定でゴミ箱へ移す動きになる。
    """
    r = requests.delete(f"{WP}/posts/{pid}", auth=AUTH, headers=UA,
                        params={"force": "false"}, verify=False, timeout=60)
    return r.status_code, r.text[:160]


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
        code, body = trash(b["id"])
        after = get(b["id"])
        print(f"[{b['id']}] ゴミ箱へ: HTTP {code} "
              f"→ status={(after or {}).get('status')} "
              f"{body if code >= 300 else ''}")
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
            # 全文を出すとログの末尾から読めなくなる。**要点だけ出す**
            print(f"--- STOCK {platform} {p.name} 保存 "
                  f"({len(p.read_text(encoding='utf-8'))}字) ---")
        # ログの末尾に要点だけ出す。YAML全文は上に出しているが、
        # 末尾から読むので、確かめたいことをここへまとめる
        print("\n=== DRY RUN の結果（末尾にまとめる）===")
        print(f"記事 {pid} / status={art['status']} / "
              f"modified_gmt={art['modified_gmt']} / 本文{len(art['body'])}字")
        for platform in ("x", "threads"):
            f = inv.stock_path(spec, platform, pid)
            if not f.exists():
                continue
            st = inv.load(f)
            ng = [g["id"] for g in st["gate_results"] if not g["ok"]]
            print(f"{platform}: state={st['state']} / "
                  f"hash={st['content_hash']} / "
                  f"ゲート落ち={ng or 'なし'} / 保存={f.name}")
        print("**投稿していない。在庫を作っただけ。**")


# ── 記事の取得と反映（2026-08-10 追加）──────────────────
# **ローカルの控えを反映の土台にしない。**
# workspace/claims/posts/310.raw.html は 2026-08-09 13:58 のパッチより
# 古く、直したはずの旧断定が2件残っていた。これを土台にすると、
# 直した内容を巻き戻して公開することになる。
# だから反映の直前に、**そのとき公開されている本文を取り直す。**
LIVE_DIR = ROOT / "workspace/claims/live"
BACKUP_DIR = ROOT / "workspace/backups"
PATCH_DIR = ROOT / "workspace/social/patches"

KEEP_FIELDS = ["id", "date", "date_gmt", "modified", "modified_gmt", "slug",
               "status", "type", "link", "author", "featured_media",
               "categories", "tags"]


def _get_post(pid):
    import requests
    r = requests.get(f"{WP}/posts/{pid}", auth=AUTH,
                     params={"context": "edit"}, headers=UA,
                     verify=False, timeout=60)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    return r.json(), None


def _git_push(paths, message):
    """Actions の中から控えを残す。**ローカルでは呼ばれない。**"""
    import subprocess
    if not os.environ.get("GITHUB_ACTIONS"):
        print("  （ローカル実行なのでコミットしない）")
        return
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"],
                   check=False)
    subprocess.run(["git", "config", "user.email",
                    "github-actions[bot]@users.noreply.github.com"],
                   check=False)
    subprocess.run(["git", "add", *[str(p) for p in paths]], check=False)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if r.returncode == 0:
        print("  （差分なし）")
        return
    subprocess.run(["git", "commit", "-m", message], check=False)
    subprocess.run(["git", "push"], check=False)


def article_fetch(ids, dry=True):
    """**いま公開されている本文**を取り直して控える。書き込みはしない。"""
    import json
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    for pid in ids:
        d, err = _get_post(pid)
        if err:
            print(f"[{pid}] 取得できない: {err}")
            continue
        raw = d["content"]["raw"]
        (LIVE_DIR / f"{pid}.html").write_text(raw, encoding="utf-8")
        meta = {k: d.get(k) for k in KEEP_FIELDS}
        meta["title"] = d["title"]["raw"]
        from datetime import datetime, timedelta, timezone
        meta["fetched_at"] = datetime.now(
            timezone(timedelta(hours=9))).isoformat(timespec="seconds")
        meta["chars"] = len(re.sub(r"<[^>]+>", "", raw))
        (LIVE_DIR / f"{pid}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{pid}] {meta['status']} / {meta['chars']}字 / "
              f"modified {meta['modified_gmt']} / slug {meta['slug']}")
    _git_push([LIVE_DIR], "公開中の本文を取り直す（反映の土台にする）")


def link_check(ids, dry=True):
    """**実際のリンク先**を確かめる。CTAも内部リンクも、最終URLまで追う。

    ブランドのトップページを見ても、CTAの着地先は分からない。
    本文に入っているhrefをそのまま辿る。
    """
    import json
    import requests
    sys.path.insert(0, str(Path(__file__).parent))
    import quality_rules as qr

    out = {}
    for pid in ids:
        f = LIVE_DIR / f"{pid}.html"
        if not f.exists():
            print(f"[{pid}] live の控えが無い。先に article-fetch")
            continue
        html = f.read_text(encoding="utf-8")
        rec = {"cta": [], "internal": []}
        # CTA（アフィリのリンク）
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            url, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not re.search(r"af\.moshimo\.com|px\.a8\.net", url):
                continue
            if url.startswith("//"):
                url = "https:" + url
            row = {"anchor": label[:70], "href": url[:110]}
            try:
                r = requests.get(url, headers=UA, timeout=40,
                                 allow_redirects=True, verify=False)
                row["status"] = r.status_code
                row["final_url"] = r.url[:140]
                row["final_host"] = r.url.split("/")[2] if "//" in r.url else ""
            except Exception as e:                      # noqa: BLE001
                row["status"] = f"取得できない（{type(e).__name__}）"
            rec["cta"].append(row)
            print(f"[{pid}] CTA {row.get('status')} {row.get('final_host','')} "
                  f"← {label[:40]}")
        # 内部リンク
        rec["internal"] = qr.internal_link_gate(html, check_http=True)
        for x in rec["internal"]:
            print(f"[{pid}] 内部 {x['http']} noindex={x['noindex']} "
                  f"{x['title_match']} ← {x['anchor'][:30]}")
        out[str(pid)] = rec

    d = ROOT / "workspace/market/links"
    d.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timedelta, timezone
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    (d / f"{stamp}.json").write_text(json.dumps(out, ensure_ascii=False,
                                                indent=1), encoding="utf-8")
    print(f"\n→ workspace/market/links/{stamp}.json")
    _git_push([d], "CTAと内部リンクの着地先を確認")


def article_apply(ids, dry=True):
    """**取り直した本文へ**、指定した置換だけを当てて反映する。

    やること
      1. 公開中の本文を取り直す
      2. 期待した文字列がすべて在ることを確かめる（1つでも無ければ止める）
      3. 完全バックアップを保存する
      4. 置換して、ゲートを回す
      5. content だけ送る（title/slug/status/date/author は送らない）
      6. 送ったあと取り直して、入っているか確かめる
    """
    import json
    import yaml as _y
    import requests
    sys.path.insert(0, str(Path(__file__).parent))
    import quality_rules as qr

    from datetime import datetime, timedelta, timezone
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime(
        "%Y-%m-%d_%H%M")
    bdir = BACKUP_DIR / stamp
    bdir.mkdir(parents=True, exist_ok=True)
    applied, held = [], []

    for pid in ids:
        pf = PATCH_DIR / f"apply_{pid}.yaml"
        if not pf.exists():
            print(f"[{pid}] 置換指示が無い（{pf.name}）。触らない")
            held.append((pid, "置換指示が無い"))
            continue
        spec = _y.safe_load(pf.read_text(encoding="utf-8"))

        d, err = _get_post(pid)
        if err:
            print(f"[{pid}] 取得できない: {err}")
            held.append((pid, err))
            continue
        before = d["content"]["raw"]

        # **完全バックアップ。** 記事オブジェクトごと残す
        (bdir / f"{pid}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        (bdir / f"{pid}.before.html").write_text(before, encoding="utf-8")

        # 変えてはいけないものを控える
        fixed = {k: d.get(k) for k in
                 ("slug", "link", "date", "date_gmt", "status", "author")}

        ok = True
        for g in spec.get("guards", {}).get("must_contain", []):
            if g not in before:
                print(f"[{pid}] 期待した文字列が無い: {g[:44]}")
                ok = False
        for g in spec.get("guards", {}).get("must_not_contain", []):
            if g in before:
                print(f"[{pid}] 在ってはいけない文字列がある: {g[:44]}")
                ok = False
        if not ok:
            held.append((pid, "本文が想定と違う。触らない"))
            continue

        after = before
        for i, rep in enumerate(spec["replacements"], 1):
            find, to = rep["find"], rep.get("replace", "")
            n = after.count(find)
            want = rep.get("count", 1)
            if n != want:
                print(f"[{pid}] 置換{i}: {n}件（{want}件のはず）"
                      f" — {find[:40]}")
                ok = False
                break
            after = after.replace(find, to)
        if not ok:
            held.append((pid, "置換が想定どおりに当たらない"))
            continue

        # 反映後の検査。**指示された5つを0件にする**
        gates = {
            "fact_gate(unverified_self_facts)": qr.unverified_self_facts(after),
            "official_gate(official_spec_without_source)":
                qr.official_spec_without_source(after),
            "cta_gate(cta_claim_gate)": qr.cta_claim_gate(after),
            "cta_gate(cta_box_text_gate)": qr.cta_box_text_gate(after),
            "institution_country_gate": qr.institution_country_gate(after),
            "price_without_basedate":
                qr.price_without_basedate(qr.strip_tags(after)),
            "hype_words": qr.hype_words(qr.strip_tags(after)),
            "personal_plan": qr.personal_plan(qr.strip_tags(after)),
            "experience_claims":
                qr.experience_claims(qr.strip_tags(after), after)[:3],
            "fact_claims": qr.fact_claims(qr.strip_tags(after), after),
            "missing_caveat": qr.missing_caveat(after, qr.strip_tags(after)),
        }
        ng = {k: v for k, v in gates.items() if v}
        for k, v in gates.items():
            print(f"  {'NG' if v else 'OK'} {k}"
                  + (f" … {str(v)[:80]}" if v else ""))
        if ng:
            print(f"[{pid}] ゲートNG {len(ng)}件。**反映しない**")
            held.append((pid, f"ゲートNG: {' / '.join(ng)}"))
            continue

        h2 = len(re.findall(r"<h2", after))
        if not 4 <= h2 <= 7:
            print(f"[{pid}] H2が{h2}本（4〜7の範囲外）。反映しない")
            held.append((pid, f"H2が{h2}本"))
            continue

        (bdir / f"{pid}.after.html").write_text(after, encoding="utf-8")
        chars = len(re.sub(r"<[^>]+>", "", after))
        print(f"[{pid}] 検査OK / H2 {h2}本 / {chars}字 / "
              f"CTA {after.count('af.moshimo.com') + after.count('px.a8.net')}")

        if dry:
            print(f"[{pid}] DRY RUN。送っていない")
            applied.append((pid, "dry"))
            continue

        r = requests.post(f"{WP}/posts/{pid}", auth=AUTH,
                          json={"content": after},   # content だけ
                          headers=UA, verify=False, timeout=60)
        if r.status_code not in (200, 201):
            print(f"[{pid}] 反映失敗 HTTP {r.status_code}")
            held.append((pid, f"HTTP {r.status_code}"))
            continue

        # 送ったあと取り直して、変えてはいけないものが変わっていないか見る
        d2, err2 = _get_post(pid)
        if err2:
            print(f"[{pid}] 反映後の確認ができない: {err2}")
            applied.append((pid, "反映したが未確認"))
            continue
        moved = {k: (fixed[k], d2.get(k)) for k in fixed
                 if fixed[k] != d2.get(k)}
        got = d2["content"]["raw"]
        print(f"[{pid}] 反映した / modified {d2.get('modified_gmt')} / "
              f"本文一致 {got.strip() == after.strip()}")
        if moved:
            print(f"[{pid}] ⚠ 変わってはいけない項目が変わった: {moved}")
        applied.append((pid, "反映"))

    print(f"\n反映 {len(applied)}件 / 保留 {len(held)}件")
    for pid, why in held:
        print(f"  保留 {pid}: {why}")
    _git_push([BACKUP_DIR], f"反映前のバックアップ（{stamp}）")


def run(arg, dry=True):
    cmd, _, rest = arg.partition(":")
    ids = [x.strip() for x in rest.split(",") if x.strip()]
    if cmd == "memo-trash":
        memo_trash(ids, dry)
    elif cmd == "article-patch":
        article_patch(ids, dry)
    elif cmd == "generate":
        generate(ids, dry)
    elif cmd == "article-fetch":
        article_fetch(ids, dry)
    elif cmd == "link-check":
        link_check(ids, dry)
    elif cmd == "article-apply":
        article_apply(ids, dry)
    elif cmd == "market":
        # 市場調査の取得。**記事もWordPressも触らない**ので dry は見ない
        import market_research
        market_research.main(rest or "all")
        _git_push([ROOT / "workspace/market"], "市場調査の控えを取得")
    else:
        print(f"知らないコマンド: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    run(sys.argv[1], os.environ.get("DRY_RUN", "true").lower() == "true")
