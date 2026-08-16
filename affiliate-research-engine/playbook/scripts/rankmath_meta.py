#!/usr/bin/env python3
"""
rankmath_meta.py
Rank Math のメタ（title / description）を更新する。

  python rankmath_meta.py --id 546 --description "…"
  python rankmath_meta.py --file workspace/meta/pending.yaml     # まとめて
  python rankmath_meta.py --id 546 --description "…" --write     # 実際に送る

**--write が無ければ送らない。** 検査結果だけ出す。

規則の正本は config/content/sakura-content-v1.yaml の meta_description。
長さ・KWの位置・禁止表現は、ここではなく正本から読む。

── 反映されないことがある ──────────────────────────
Rank Math は 200 を返しても保存されていないことがある。
送ったあと公開画面の `<meta name="description">` を読んで確かめ、
落ちていたら**1回だけ**送り直す。2回目も落ちたら、
理由を出して止める。**成功したことにしない。**

── 送らないもの ────────────────────────────────
slug・status・date・categories・本文。**メタだけ。**
"""
import argparse
import html as _html
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))

import yaml

SPEC = ROOT / "config/content/sakura-content-v1.yaml"
WP = "https://sakura-eigo.com"
AUTH = ("rei.00pt2342@gmail.com", os.environ.get("WP_APP_PASSWORD", ""))
UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

# 正本の meta_description.forbidden に対応する検出
NG_PATTERNS = [
    ("〜について解説します", re.compile(r"について(?:詳しく)?(?:解説|説明)し")),
    ("煽り", re.compile(r"(?:必見|衝撃|驚愕|絶対に|今すぐ|完全保存版|徹底解説)")),
    # **体言止め＝名詞で終わること。** 句点が無いだけの文を拾わない。
    # 「〜を決められます」「〜が分かる」は述語で終わっているので対象外
    ("体言止め", re.compile(
        r"(?<!ます)(?<!です)(?<!ました)(?<!でした)(?<!ません)"
        r"(?<![るたいうくむぶすつぬぐず])[ァ-ヶ一-龠A-Za-z0-9ー]$")),
]


def spec():
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))["meta_description"]


def check(description, keyword="", sp=None):
    """正本の規則に照らして、直すべき点を返す。**空なら合格。**"""
    sp = sp or spec()
    lo, hi = sp["length"]["min"], sp["length"]["max"]
    out = []
    if not description:
        return ["メタが空"]
    n = len(description)
    if not lo <= n <= hi:
        out.append(f"{n}文字（{lo}〜{hi}に収める）")
    if keyword:
        # 語順そのままで冒頭に入っているか（空白区切りの語を順に見る）
        low, last, head = description.lower(), 0, None
        for w in keyword.split():
            i = low.find(w.lower(), last)
            if i < 0:
                out.append(f"KWの語が無い（『{w}』）")
                head = None
                break
            head = i if head is None else head
            last = i + len(w)
        if head is not None and head > 10:
            out.append(f"KWが冒頭から{head}文字目（冒頭に置く）")
    for name, pat in NG_PATTERNS:
        if pat.search(description):
            out.append(f"禁止表現: {name}")
    return out


def live_description(post_id):
    """公開画面の meta description を読む。**送った結果の確認用。**"""
    import requests
    r = requests.get(f"{WP}/?p={post_id}", headers={"User-Agent": UA["User-Agent"]},
                     timeout=30, verify=False)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', r.text, re.I)
    return (_html.unescape(m.group(1)) if m else ""), ""


def send(post_id, description, title=None):
    """updateMeta を1回叩く。戻り値は (成功か, 説明)。"""
    import requests
    meta = {"rank_math_description": description}
    if title:
        meta["rank_math_title"] = title
    r = requests.post(
        f"{WP}/wp-json/rankmath/v1/updateMeta", auth=AUTH, headers=UA,
        json={"objectID": int(post_id), "objectType": "post", "meta": meta},
        timeout=40, verify=False)
    return r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:120]}"


def apply_one(post_id, description, title=None, keyword="", write=False):
    """1本ぶん。**送ったあと必ず読み直す。落ちていたら1回だけ再送。**"""
    bad = check(description, keyword)
    if bad:
        return False, "規則に外れている: " + " / ".join(bad)
    if not write:
        return True, "検査OK（--write が無いので送っていない）"

    ok, why = send(post_id, description, title)
    if not ok:
        return False, f"送信に失敗: {why}"
    got, err = live_description(post_id)
    if err:
        return False, f"送ったが確認できない: {err}。**成功にしない**"
    if (got or "").strip() == description.strip():
        return True, "反映を確認した"

    # 1回だけ送り直す
    ok2, why2 = send(post_id, description, title)
    got2, err2 = live_description(post_id)
    if not ok2 or err2:
        return False, f"再送も確認できない: {why2 or err2}"
    if (got2 or "").strip() == description.strip():
        return True, "1回目は落ちた。再送で反映を確認した"
    return False, (f"2回送っても反映されない。画面の値『{(got2 or '')[:40]}』。"
                   f"**成功にしない。人が見る**")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int)
    ap.add_argument("--description", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--keyword", default="")
    ap.add_argument("--file", default="", help="{id: {description, title, keyword}} のYAML")
    ap.add_argument("--write", action="store_true", help="付けないと送らない")
    a = ap.parse_args()

    rows = []
    if a.file:
        d = yaml.safe_load(Path(a.file).read_text(encoding="utf-8")) or {}
        for pid, v in d.items():
            rows.append((int(pid), v.get("description", ""),
                         v.get("title"), v.get("keyword", "")))
    elif a.id:
        rows.append((a.id, a.description, a.title or None, a.keyword))
    else:
        print("--id か --file が要る")
        return 1

    ng = 0
    for pid, desc, title, kw in rows:
        ok, why = apply_one(pid, desc, title, kw, a.write)
        print(("  OK  " if ok else "  NG  ") + f"{pid} … {why}")
        ng += 0 if ok else 1
    print(f"\n{len(rows)}件 / 落ちた {ng}件"
          + ("" if a.write else "（--write が無いので1件も送っていない）"))
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
