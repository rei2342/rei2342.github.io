#!/usr/bin/env python3
"""
social_claims.py
SNS文を**命題の単位**へ割って、公開本文の命題と突き合わせる。

数字が合っているかだけでは足りない。
「Aなら原因はB」「Cで足りる」のような**因果・診断・効果**は、
記事に無ければ、書き手が勝手に足した断定になる。

見るのは4つ。

  対象   … 何について言っているか（語の重なり）
  行動   … 読者にさせることか、事実の主張か
  極性   … 記事が否定していることを肯定していないか
  モダリティ … 記事が「確認項目」と言っているものを言い切っていないか

完全一致は求めない。**矛盾しないこと**を見る。
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# 内容語らしきもの。ひらがなだけの語は助詞や語尾が多いので拾わない
TERM = re.compile(r"[一-龥ァ-ヴー]{2,}|[A-Za-z]{3,}|[0-9]+")
SENT_END = re.compile(r"(?<=[。？！])|\n")
STOP = {"こと", "もの", "とき", "ため", "ほう", "場合", "自分", "記事",
        "確認", "項目", "内容", "今日", "次の", "ここ", "それ", "これ"}


def terms(t):
    return {w for w in TERM.findall(t) if w not in STOP and len(w) >= 2}


# 記事へ送るための一言。**主張ではない**ので照合の対象から外す
META = re.compile(r"記事(の(ほう|中))?(に|へ|で)(置いて|書いて|まとめて|あります)"
                  r"|続きは|詳しくは")


def split(text):
    """(文, 箇条書きか) の組で返す。

    箇条書きは名詞止めや操作の断片になる。文と同じ物差しで
    「言い切っている」と見るとほぼ全部が引っかかるので、分けて扱う。
    """
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("http"):
            continue
        if line.startswith(("・", "-", "*")):
            out.append((line.lstrip("・-* ").strip(), True))
            continue
        for s in SENT_END.split(line):
            s = (s or "").strip()
            if s:
                out.append((s, False))
    return [(s, b) for s, b in out if terms(s)]


def sentences(text):
    return [s for s, _ in split(text)]


def modality(spec, s, bullet=False):
    """directive → hedged → interrogative → assertive の順に決める。

    「〜かもしれません。確かめてください」のように混ざるので、
    **弱いほうを優先**する。強く採ると誤って落とす。
    """
    m = spec["claims"]["modality"]
    if re.search(r"か$", s):
        return "interrogative"          # 箇条書きの「〜か」も問い
    if bullet:
        # 箇条書きは操作か項目。言い切りとして扱わない
        return "directive"
    for kind in ("directive", "interrogative", "hedged"):
        for pat in m[kind]:
            if re.search(pat, s):
                return kind
    for pat in m["assertive"]:
        if re.search(pat, s):
            return "assertive"
    return "assertive"          # 体言止めも言い切りとして扱う


def is_risky(spec, s):
    return any(re.search(p, s) for p in spec["claims"]["risky"])


# 判定できない短文でも、これを含むなら人が見る。
# 比較・因果・診断・効果・全面否定
SENSITIVE = re.compile(
    r"より|ほうが|比べ|決まりません|決まらない|足り|向い|"
    r"原因|理由|だから|なので|効く|伸び|変わ|"
    r"ではありません|ではない|ありません$|ません。?$|ない。?$")


def is_sensitive(s):
    return bool(SENSITIVE.search(s))


def negated(s):
    """「ではなく」は対比であって否定ではない。数えない。"""
    s = re.sub(r"ではなく|じゃなく|だけでなく", "", s)
    return bool(re.search(r"ない|ません|ず[、。]", s))


def best_match(spec, s, article_sents):
    """記事側で、いちばん語が重なる文を探す。"""
    st = terms(s)
    if not st:
        return None, 0.0
    best, score = None, 0.0
    for a in article_sents:
        at = terms(a)
        if not at:
            continue
        ov = len(st & at) / len(st)
        if ov > score:
            best, score = a, ov
    return best, score


def article_hedged(a):
    # 「例」1文字は「例として」以外にも当たるので使わない
    return bool(re.search(r"可能性|かもしれ|ことがあ|場合があ|とは限|とはかぎ|"
                          r"確認項目|提案|目安|例えば|試算|こともあ", a or ""))


def check(spec, parts, article, inferences=()):
    """命題ごとの判定を返す。

    [{text, modality, risky, matched, overlap, verdict, why}, ...]
    verdict は次の7つ。

      ok                 記事の記述と矛盾しない
      declared           判断として宣言済み（弱めてある）
      unjudged           内容語が少なく、**判定していない**
      needs_human_review 判定できないのに、言い切りかつ危うい話題
      unsupported        記事に対応する記述が無い
      contradiction      記事と肯定・否定が逆
      overclaim          記事が可能性としているのに言い切っている

    **`unjudged` を `ok` と同じ扱いにしない。** 「判定しない」と
    「記事に支持されている」を混ぜると、支持の件数が水増しになる。
    """
    c = spec["claims"]
    asents = sentences(article.get("body", ""))
    declared = {re.sub(r"\s+", "", x["text"]) for x in inferences}
    out = []
    for p in parts:
        for s, bullet in split(p):
            if META.search(s):
                continue            # 記事へ送る一言。主張ではない
            key = re.sub(r"\s+", "", s)
            mod = modality(spec, s, bullet)
            risky = is_risky(spec, s)
            a, ov = best_match(spec, s, asents)
            st = terms(s)
            row = {"text": s, "modality": mod, "risky": risky,
                   "matched": a, "overlap": round(ov, 2), "terms": len(st)}

            if key in declared:
                # 書き手が判断として宣言したもの。**弱めてあることが条件**
                if mod == "assertive":
                    row.update(verdict="overclaim",
                               why="判断として宣言しているが言い切っている。"
                                   "弱める")
                else:
                    row.update(verdict="declared", why="判断として宣言済み")
                out.append(row)
                continue

            if mod in ("directive", "interrogative"):
                # 行動の提案・問いかけ。事実の主張ではないが、
                # **記事に無い操作をさせない**ので対応は要る
                if ov >= c["term_overlap_min"]:
                    row.update(verdict="ok", why="記事に同じ操作がある")
                else:
                    row.update(verdict="unsupported",
                               why="記事に対応する操作が見つからない")
                out.append(row)
                continue

            if ov < c["term_overlap_min"]:
                row.update(
                    verdict="unsupported" if risky else "ok",
                    why=("記事に対応する記述が見つからない" if risky
                         else "因果・効果を言っていないので通す"))
                out.append(row)
                continue

            # 内容語が少ない文は、何にでも高く一致してしまう。
            # **少ない文でモダリティや極性を判定しない。**誤検知になる
            if len(st) < c.get("min_terms_to_judge", 3):
                # 試作のあいだは、判定できない短文のうち
                # **言い切っていて、しかも危うい話題のもの**を人へ回す
                if mod in ("assertive", "hedged") and (risky or is_sensitive(s)):
                    row.update(
                        verdict="needs_human_review",
                        why=f"内容語が{len(st)}語で判定できない。"
                            "言い切りで、比較・因果・診断・効果・否定のどれかを"
                            "含むので人が見る")
                else:
                    row.update(verdict="unjudged",
                               why=f"内容語が{len(st)}語しかない。判定しない")
                out.append(row)
                continue

            # 極性の食い違いは、**言い切っている長い文だけ**で見る。
            # 断片や提案で見ると「〜ない」が普通に出るので誤検知になる
            if (not bullet and mod == "assertive" and len(s) >= 20
                    and ov >= c["contradiction_overlap"]
                    and negated(s) != negated(a)):
                row.update(verdict="contradiction",
                           why="記事と肯定・否定が逆になっている")
                out.append(row)
                continue

            if mod == "assertive" and article_hedged(a):
                row.update(verdict="overclaim",
                           why="記事は確認項目・可能性として書いているのに、"
                               "投稿が言い切っている")
                out.append(row)
                continue

            row.update(verdict="ok", why="記事の記述と矛盾しない")
            out.append(row)
    return out


def failures(rows):
    """**落とすもの。** unjudged と needs_human_review は落とさない。
    落とさないが、数えて出す。"""
    return [r for r in rows if r["verdict"] in
            ("unsupported", "contradiction", "overclaim")]


def counts(rows):
    """supported / unsupported / unjudged / needs_human_review を数える。"""
    sup = sum(1 for r in rows if r["verdict"] in ("ok", "declared"))
    uns = len(failures(rows))
    unj = sum(1 for r in rows if r["verdict"] == "unjudged")
    nhr = sum(1 for r in rows if r["verdict"] == "needs_human_review")
    return {"supported": sup, "unsupported": uns,
            "unjudged": unj, "needs_human_review": nhr, "total": len(rows)}


def fmt(rows):
    L = ["| 命題 | モダリティ | 一致 | 判定 | 理由 |\n|---|---|---|---|---|\n"]
    for r in rows:
        L.append(f"| {r['text'][:38]} | {r['modality']} | {r['overlap']} "
                 f"| {r['verdict']} | {r['why']} |\n")
    return "".join(L)


if __name__ == "__main__":
    import social_spec as ss
    import social_inventory as inv
    spec = ss.load_spec()
    art = inv.local_article(sys.argv[1])
    rows = check(spec, [sys.argv[2]], art)
    print(fmt(rows))
