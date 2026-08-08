#!/usr/bin/env python3
"""
article_patcher.py
公開中の記事の指摘を、全面リライトせずに直す。

wp_audit で見つかる指摘（料金の基準日なし・注意点なし・制度の出典なし・
根拠を超える断定）は、記事の骨格を作り直すほどの話ではない。
全面リライトすると別の箇所が壊れるので、必要な部分だけ触る。

2段階で動く。間に claude -p を挟むのは、料金と制度を
**実際にWebで確認してから**日付を入れるため。
確認していない数字に「2026年◯月◯日時点」と押すのは、
訂正ではなく新しい虚偽を作る行為なので、機械では日付を入れない。

  --prepare … 直すべき記事を洗い出し、tasks/<id>.md に指示を書く
  --apply   … out/<id>.html を検査して、通ったものだけWordPressへ反映する
"""
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import affiliate_inserter as _ai
import quality_rules as _q
import wp_audit as _wa

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

ROOT = Path("affiliate-research-engine/playbook/workspace/patches")
TASKS = ROOT / "tasks"
OUT = ROOT / "out"

# 1回で全部やると、途中で落ちたときに何が済んだか分からなくなる。
# 少しずつ流して、結果を見てから次を回す。
BATCH = int(os.environ.get("BATCH", "8"))


def targets():
    """指摘のある記事を、直せる種類に絞って返す。

    アイキャッチ未設定・カテゴリ未分類・文字数不足は、文章を直す話ではないので
    ここでは扱わない（別のツールの担当）。
    """
    fixable = ("料金", "注意点", "確認日も出典", "断定", "実現しない予定",
               "制度", "体験表現")
    out = []
    for p in _wa.published():
        iss = [i for i in _wa.audit(p) if any(k in i for k in fixable)]
        if iss:
            out.append((p, iss))
    return out


def prepare():
    TASKS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in TASKS.glob("*.md"):
        old.unlink()

    found = targets()
    print(f"直す対象 {len(found)}本（今回は先頭{BATCH}本）")

    for post, issues in found[:BATCH]:
        pid = post["id"]
        title = re.sub(r"<[^>]+>", "", post["title"]["rendered"])
        body = post["content"]["rendered"]
        (TASKS / f"{pid}.md").write_text(
            f"# 記事 {pid} を直す\n\n"
            f"タイトル: {title}\n"
            f"URL: {post.get('link','')}\n\n"
            "## 指摘\n\n"
            + "".join(f"- {i}\n" for i in issues)
            + "\n## 現在の本文（HTML）\n\n```html\n" + body + "\n```\n",
            encoding="utf-8")
        print(f"  [{pid}] {' / '.join(issues)}")

    (ROOT / "TASKS.md").write_text(
        f"# 直す対象 {date.today().isoformat()}\n\n"
        f"検出 {len(found)}本 / 今回 {min(BATCH, len(found))}本\n\n"
        + "".join(f"- [{p['id']}] {' / '.join(i)}\n" for p, i in found) + "\n",
        encoding="utf-8")
    return len(found)


def check(pid, new_html, old_post):
    """直したものを検査する。

    全面リライト用の audit() をそのまま当てると、元から字数やH2本数が
    範囲外の記事まで弾いてしまい、直せるものまで直せない。
    ここで見るのは「指摘が消えたか」「新しい問題を作っていないか」だけにする。
    """
    old_html = old_post["content"]["rendered"]
    old_text = _q.strip_tags(old_html)
    new_text = _q.strip_tags(new_html)
    # CTAボックスは全記事共通の定型文で、中に「さくらが確かめた」が入っている。
    # 外さずに文体を見ると、全記事が三人称視点として落ちる。
    body_text = _q.strip_tags(_ai.strip_box(new_html))
    problems = []

    if len(new_text) < len(old_text) * 0.9:
        problems.append(f"本文が{len(old_text)}→{len(new_text)}字に減っている")

    # 直したつもりで指摘が残っていないか
    fake = dict(old_post)
    fake["content"] = {"rendered": new_html}
    left = [i for i in _wa.audit(fake)
            if any(k in i for k in ("料金", "注意点", "確認日も出典", "断定",
                                    "実現しない予定", "制度", "体験表現"))]
    if left:
        problems += [f"指摘が残っている: {i}" for i in left]

    # リンクを落としていないか。収益導線が消えるのが一番痛い。
    n_old = len(_q.AFFILIATE_LINK_RE.findall(old_html))
    n_new = len(_q.AFFILIATE_LINK_RE.findall(new_html))
    if n_new < n_old:
        problems.append(f"アフィリエイトリンクが{n_old}→{n_new}本に減っている")

    # 直しついでに文体が崩れていないか（既存ルールの一部だけ見る）
    if "——" in body_text:
        problems.append("emダッシュが混入")
    third = re.findall(r"(?:田中)?さくら(?:は|が|の|も|に|を)", body_text)
    if third:
        problems.append(f"三人称視点が{len(third)}件混入")

    return problems


def sentences(text):
    return [x.strip() for x in re.split(r"(?<=[。？！])", text) if x.strip()]


def diff_report(old_html, new_html):
    """変わった文だけを (変更前, 変更後) で返す。

    全文diffだと読めないので、文単位で消えたもの・増えたものを並べる。
    数字・アフィリンク・見出しを勝手に触っていないかを、ここで人が見る。
    """
    o = sentences(_q.strip_tags(old_html))
    n = sentences(_q.strip_tags(new_html))
    removed = [x for x in o if x not in n]
    added = [x for x in n if x not in o]
    return removed, added


def report():
    """out/ にある修正案を、適用せずに一覧で出す。"""
    files = sorted(OUT.glob("*.html"))
    if not files:
        print("out/ にHTMLが無い。先に生成する")
        return

    L = [f"# 修正案の一覧 {date.today().isoformat()}\n\n",
         "**まだ何も反映していない。** 内容を確認してから `--apply` を実行する。\n\n",
         "保護するもの: 実体験・数値・タイトル・URL・内部リンク・アフィリンク・検索意図。\n"
         "直すのは未来の宣言と、進行型の設定だけ。\n\n"]

    for f in files:
        pid = int(f.stem)
        r = requests.get(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                         headers={"User-Agent": "Mozilla/5.0"},
                         verify=False, timeout=40)
        if r.status_code != 200:
            L.append(f"## [{pid}] 取得失敗 HTTP {r.status_code}\n\n")
            continue
        post = r.json()
        old_html = post["content"]["rendered"]
        new_html = f.read_text(encoding="utf-8").strip()
        new_html = re.sub(r"^```html?\n?", "", new_html)
        new_html = re.sub(r"\n?```$", "", new_html)

        title = re.sub(r"<[^>]+>", "", post["title"]["rendered"])
        L.append(f"## [{pid}] {title}\n\n{post.get('link','')}\n\n")

        # 何を指摘されて直したのか
        L.append("**検出理由**\n\n")
        for i in _wa.audit(post):
            L.append(f"- {i}\n")
        L.append("\n")

        removed, added = diff_report(old_html, new_html)
        if not removed and not added:
            L.append("（本文の変更なし）\n\n")
            continue

        L.append("**修正案**\n\n")
        for x in removed[:12]:
            L.append(f"- 変更前: {x[:120]}\n")
        for x in added[:12]:
            L.append(f"- 変更後: {x[:120]}\n")
        if len(removed) > 12 or len(added) > 12:
            L.append(f"- （ほか 変更前{max(0,len(removed)-12)}文 / 変更後{max(0,len(added)-12)}文）\n")

        # 保護対象が壊れていないか、その場で見せる
        no = len(_q.AFFILIATE_LINK_RE.findall(old_html))
        nn = len(_q.AFFILIATE_LINK_RE.findall(new_html))
        ho = len(re.findall(r"<h2", old_html))
        hn = len(re.findall(r"<h2", new_html))
        lo = len(_q.strip_tags(old_html))
        ln = len(_q.strip_tags(new_html))
        L.append(f"\n**保護対象の確認**: アフィリンク {no}→{nn} / "
                 f"H2 {ho}→{hn} / 本文 {lo}→{ln}字\n\n---\n\n")

    (ROOT / "REVIEW.md").write_text("".join(L), encoding="utf-8")
    print("".join(L)[:4000])
    print(f"\n→ {ROOT / 'REVIEW.md'} に全文")


def apply():
    files = sorted(OUT.glob("*.html"))
    if not files:
        print("out/ にHTMLが無い。生成ステップが動いていない可能性がある")
        return

    L = [f"# 修正の適用 {date.today().isoformat()}\n\n",
         f"モード: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n",
         "| ID | 結果 | 内容 |\n|---|---|---|\n"]
    ok = ng = 0

    for f in files:
        pid = int(f.stem)
        r = requests.get(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                         headers={"User-Agent": "Mozilla/5.0"},
                         verify=False, timeout=40)
        if r.status_code != 200:
            L.append(f"| {pid} | 取得失敗 | HTTP {r.status_code} |\n")
            ng += 1
            continue
        post = r.json()

        new_html = f.read_text(encoding="utf-8").strip()
        new_html = re.sub(r"^```html?\n?", "", new_html)
        new_html = re.sub(r"\n?```$", "", new_html)
        # CTAボックスは毎回作り直す。文中の案件が変わっている場合があるため。
        topic = _ai.classify_full(re.sub(r"<[^>]+>", "", post["title"]["rendered"]), new_html)
        cta, _ = _ai.build_cta(topic)
        new_html = _ai.strip_box(new_html) + cta

        problems = check(pid, new_html, post)
        if problems:
            L.append(f"| {pid} | 不合格 | {' / '.join(problems)} |\n")
            print(f"[{pid}] 不合格: {' / '.join(problems)}")
            ng += 1
            continue

        if DRY_RUN:
            L.append(f"| {pid} | 合格（未反映） | DRY_RUN |\n")
            print(f"[{pid}] 合格（DRY RUN）")
            ok += 1
            continue

        u = requests.post(f"{WP_BASE}/posts/{pid}", auth=(WP_USER, WP_PASS),
                          json={"content": new_html},
                          headers={"User-Agent": "Mozilla/5.0"},
                          verify=False, timeout=60)
        if u.status_code in (200, 201):
            L.append(f"| {pid} | 反映 | 更新済み |\n")
            print(f"[{pid}] 反映した")
            ok += 1
        else:
            L.append(f"| {pid} | 反映失敗 | HTTP {u.status_code} |\n")
            ng += 1

    L.append(f"\n合格 {ok}本 / 不合格 {ng}本\n")
    (ROOT / "APPLY.md").write_text("".join(L), encoding="utf-8")
    print(f"\n合格 {ok} / 不合格 {ng}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--prepare"
    if mode == "--prepare":
        prepare()
    elif mode == "--report":
        report()
    elif mode == "--apply":
        apply()
    else:
        print("使い方: article_patcher.py [--prepare|--report|--apply]")
        sys.exit(1)
