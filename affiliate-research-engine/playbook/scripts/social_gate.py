#!/usr/bin/env python3
"""
social_gate.py
X・Threadsの投稿文を、出す前に見る。**落ちたら投稿しない。**

記事側の `quality_rules.unverified_self_facts()` をそのまま使う。
SNSだけ別基準にすると、記事で止めたものがSNSから漏れる。

  from social_gate import run_gates
  results = run_gates(spec, platform, parts, article, history)

戻り値は [(gate_id, ok, detail), ...]。1つでも ok=False なら出さない。
"""
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as qr

EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿←-⇿"
                   r"⬀-⯿️]")
URL = re.compile(r"https?://\S+")


def _plain(t):
    """URLと絵文字を除いた本文の長さを数えるための素の文字列。"""
    return EMOJI.sub("", URL.sub("", t)).strip()


def _ngrams(t, n=3):
    t = re.sub(r"\s+", "", URL.sub("", t))
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def jaccard(a, b):
    x, y = _ngrams(a), _ngrams(b)
    return len(x & y) / len(x | y) if x | y else 0.0


# ── 個別のゲート ────────────────────────────────────
def fact_gate(spec, text):
    """未確認の一人称の事実。**記事側と同じ関数を使う。**

    記事側は一人称の印（私・自分）を手がかりにしている。SNSは主語を落とすので、
    印が無くても落とすものを仕様の leak_patterns から足す。
    """
    hits = [str(h) for h in qr.unverified_self_facts(text)]
    for pat in spec["persona"].get("leak_patterns", []):
        m = re.search(pat["re"], text)
        if m:
            hits.append(f"{pat['name']}: {m.group(0)}")
    return (not hits, "; ".join(hits[:3]))


def broken_gate(spec, text):
    bad = [x for x in spec["forbidden"]["patterns"]["broken_output"]
           if x in text]
    return (not bad, " ".join(bad))


def shape_gate(spec, platform, parts):
    """URLだけの投稿、空投稿、行数、空行、絵文字、ハッシュタグ。"""
    bad = []
    s = spec["style"]
    for i, p in enumerate(parts, 1):
        body = _plain(p)
        if not body:
            bad.append(f"{i}投稿目がURLだけ、または空")
            continue
        n_emoji = len(EMOJI.findall(p))
        lim = s["emoji"]["x" if platform == "x" else "threads"]
        if not lim["min"] <= n_emoji <= lim["max"]:
            bad.append(f"{i}投稿目の絵文字が{n_emoji}個"
                       f"（{lim['min']}〜{lim['max']}）")
        if re.search(r"#\S", p):
            bad.append(f"{i}投稿目にハッシュタグがある")
        if re.search(r"[↓→]\s*$", p.strip()) and platform == "threads":
            bad.append(f"{i}投稿目が矢印で終わっている（強制の『↓』は廃止）")
    if platform == "x":
        p = parts[0]
        lines = [l for l in p.split("\n") if l.strip()]
        x = spec["x"]
        if not x["lines"]["min"] <= len(lines) <= x["lines"]["max"]:
            bad.append(f"{len(lines)}行（{x['lines']['min']}〜"
                       f"{x['lines']['max']}行）")
        blanks = len(re.findall(r"\n\s*\n", p.strip()))
        if blanks > x["blank_lines_max"]:
            bad.append(f"空行が{blanks}つ（{x['blank_lines_max']}つまで）")
    return (not bad, " / ".join(bad))


def length_gate(spec, platform, parts):
    bad = []
    if platform == "x":
        n = len(_plain(parts[0]))
        lo, hi = spec["x"]["length"]["min"], spec["x"]["length"]["max"]
        if not lo <= n <= hi:
            bad.append(f"{n}字（{lo}〜{hi}）")
        # X本体の上限。URLは23文字換算
        raw = URL.sub("x" * 23, parts[0])
        if len(raw) > spec["x"]["hard_limit"]:
            bad.append(f"URL込みで{len(raw)}字（上限{spec['x']['hard_limit']}）")
    else:
        t = spec["threads"]
        keys = ["part1", "part2"]
        for i, p in enumerate(parts):
            if i >= len(keys):
                bad.append(f"{i + 1}投稿目が多い（最大{t['parts']['max']}）")
                break
            lo = t[keys[i]]["length"]["min"]
            hi = t[keys[i]]["length"]["max"]
            n = len(_plain(p))
            if not lo <= n <= hi:
                bad.append(f"{i + 1}投稿目が{n}字（{lo}〜{hi}）")
    return (not bad, " / ".join(bad))


def link_gate(spec, platform, parts, article):
    """URLの位置・utm・記事URLとの一致。"""
    bad = []
    want = article["url"]
    utm = spec[platform]["url"]["utm"]
    last = parts[-1]
    urls = URL.findall("\n".join(parts))
    if not urls:
        bad.append("URLが無い")
    else:
        if not URL.search(last) or not last.rstrip().endswith(urls[-1]):
            bad.append("URLが最終投稿の末尾に無い")
        for u in urls:
            if utm not in u:
                bad.append(f"utmが無い: {u}")
            base = u.split("?")[0]
            if base.rstrip("/") != want.split("?")[0].rstrip("/"):
                bad.append(f"記事URLと違う: {u}")
            if "example.com" in u or "?p=" in u:
                bad.append(f"公開URLでない: {u}")
    if len(urls) > 1:
        bad.append(f"URLが{len(urls)}個ある")
    return (not bad, " / ".join(bad))


def article_gate(spec, article):
    bad = []
    if article.get("status") != "publish":
        bad.append(f"記事が {article.get('status')}")
    if not article.get("modified_gmt"):
        bad.append("modified_gmt が無い（あとで stale を判定できない）")
    return (not bad, " / ".join(bad))


def unchanged_gate(spec, article, stock_modified):
    ok = stock_modified and article.get("modified_gmt") == stock_modified
    return (bool(ok), "" if ok else
            f"生成時 {stock_modified} → 今 {article.get('modified_gmt')}")


def duplicate_gate(spec, text, history):
    """過去180日の投稿と、完全一致・近似重複が無いか。"""
    th = spec["duplicate"]["near_threshold"]
    for h in history:
        if jaccard(text, h["text"]) >= 1.0:
            return (False, f"完全一致: {h.get('stock_id', h.get('posted_id'))}")
        j = jaccard(text, h["text"])
        if j >= th:
            return (False, f"近似 {j:.2f}: "
                           f"{h.get('stock_id', h.get('posted_id'))}")
    return (True, "")


def cross_platform_gate(spec, text, other_text):
    """XとThreadsが同じ文になっていないか。"""
    if not other_text:
        return (True, "もう片方がまだ無い")
    j = jaccard(text, other_text)
    th = spec["duplicate"]["near_threshold"]
    return (j < th, f"XとThreadsの近さ {j:.2f}（{th}未満にする）")


def subset_gate(spec, parts, article):
    """記事に無い言い切りを足していないか。**警告ではなく落とす。**

    記事本文に出てこない数値を投稿へ書いたら止める。
    数値は言い切りになりやすく、あとから直せない。
    """
    body = article.get("body", "")
    bad = []
    for p in parts:
        for n in re.findall(r"[0-9]+(?:\.[0-9]+)?", _plain(p)):
            if len(n) >= 2 and n not in body:
                bad.append(f"記事に無い数字: {n}")
    return (not bad, " / ".join(sorted(set(bad))))


def style_warnings(spec, parts):
    """落とさないが知らせるもの。短行の連打・不自然な改行。"""
    warn = []
    for i, p in enumerate(parts, 1):
        lines = [l for l in p.split("\n") if l.strip()]
        short = [l for l in lines if len(l) <= 12]
        if len(lines) >= 5 and len(short) / len(lines) > 0.7:
            warn.append(f"{i}投稿目が短い行の連打（{len(short)}/{len(lines)}行）")
        for w in spec["style"]["avoid"]:
            pass
        if re.search(r"実は|意志が弱いんじゃない|な人だけ見て", p):
            warn.append(f"{i}投稿目に定型フックがある")
    return warn


# ── まとめて走らせる ────────────────────────────────
def run_gates(spec, platform, parts, article, history=(), other_text="",
              stock_modified=None):
    text = "\n\n".join(parts)
    res = [
        ("article_published", *article_gate(spec, article)),
        ("fact_gate", *fact_gate(spec, text)),
        ("broken_output", *broken_gate(spec, text)),
        ("style_gate", *shape_gate(spec, platform, parts)),
        ("length_gate", *length_gate(spec, platform, parts)),
        ("link_gate", *link_gate(spec, platform, parts, article)),
        ("subset_gate", *subset_gate(spec, parts, article)),
        ("duplicate_gate", *duplicate_gate(spec, text, history)),
        ("cross_platform_gate", *cross_platform_gate(spec, text, other_text)),
    ]
    if stock_modified is not None:
        res.append(("article_unchanged",
                    *unchanged_gate(spec, article, stock_modified)))
    return res


def passed(results):
    return all(ok for _, ok, _ in results)


def fmt(results):
    return "\n".join(("OK  " if ok else "NG  ") + gid
                     + (f" … {d}" if d else "")
                     for gid, ok, d in results)
