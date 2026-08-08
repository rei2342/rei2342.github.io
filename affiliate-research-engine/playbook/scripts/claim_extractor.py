#!/usr/bin/env python3
"""
claim_extractor.py
公開記事から「体験の主張」を**命題単位**で抜き出し、重複をまとめる。

単語や数値で束ねると、別の主張が混ざる。
「フィリピンへ留学した」「フィリピン留学の費用を調べた」
「フィリピンでは英語が公用語」は、同じ「フィリピン」でも全部ちがう。

そこで 主語＋行動／状態＋対象＋数値 の単位で切り出す。
**記事は一切修正しない。** 抽出と整理だけをする。

判定は文の形から機械的に推測しているだけで、完全ではない。
人が元の文を読んで確かめられるよう、必ず原文と前後の文脈を残す。

出力:
  workspace/claims/CLAIMS.csv … 人が confirmation 列を埋める
  workspace/claims/CLAIMS.md  … 読む用（上位から詳細）
"""
import csv
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims")
SETTING_FILES = [
    Path("affiliate-research-engine/CLAUDE.md"),
    *sorted(Path("affiliate-research-engine/playbook/workspace/drafts").glob("*.md")),
]
TOP = int(__import__("os").environ.get("TOP", "10"))

# ── 行動・状態。どれに当たるかで「体験の主張」かが決まる ──────────────
# 体験: 本人が実際にやったと読める
ACT_EXPERIENCE = {
    "留学した": r"留学(?:し|に行っ|して)", "渡航した": r"渡航し|現地に行っ",
    "通った": r"通っ", "使った": r"使っ(?:た|て)", "試した": r"試し",
    "続けた": r"続け(?:た|られ)", "やめた": r"やめ(?:た|て)|挫折し|중断",
    "受けた": r"受け(?:た|て)", "受験した": r"受験し",
    "登録した": r"登録し|申し込(?:んだ|み)", "払った": r"払っ|支払っ",
    "溶かした": r"溶かし|無駄にし|無駄にし",
    "後回しにした": r"後回しに(?:し|してき)", "止まっていた": r"止まっ|停滞し|動かなかっ",
    "働いている": r"(?:として|で)働(?:い|く)|の仕事をし",
}
# 調査: 調べただけ。体験ではない
ACT_RESEARCH = {
    "調べた": r"調べ", "比較した": r"比較し|比べ", "候補にした": r"候補に(?:し|入れ)",
    "見た": r"(?:サイトを|公式を)見", "問い合わせた": r"問い合わせ",
    "検索した": r"検索し", "読んだ": r"(?:記事を|口コミを)読",
    "探した": r"探し(?:た|始め|回っ)", "検討した": r"検討し",
}
# 一般論・第三者。さくらの主張ではない
GENERAL_MARK = r"と言われ|一般的に|多くの人|人によって|とされ|らしい|そうだ|だろう|かもしれない"

SUBJ_SELF = r"私|自分|僕"
SUBJ_READER = r"あなた|読者|みなさん"

# 対象（何について言っているか）
TARGETS = [
    ("フィリピン", r"フィリピン"), ("セブ島", r"セブ島?"),
    ("オーストラリア", r"オーストラリア|豪州"), ("カナダ", r"カナダ"),
    ("ニュージーランド", r"ニュージーランド"), ("シンガポール", r"シンガポール"),
    ("イギリス", r"イギリス|英国"), ("台湾", r"台湾"), ("韓国", r"韓国"),
    ("ハワイ", r"ハワイ"), ("国内留学", r"国内留学"),
    ("英語学習", r"英語(?:学習|の勉強|を勉強)"), ("英語", r"英語"),
    ("TOEIC", r"TOEIC"), ("ワーホリ", r"ワーホリ|ワーキングホリデー"),
    ("オンライン英会話", r"オンライン英会話"), ("英会話スクール", r"(?:英会話)?スクール"),
    ("英語コーチング", r"英語コーチング|コーチング"),
    ("営業事務", r"営業事務"), ("仕事の英語", r"仕事で英語|会議|議事録|電話対応"),
    ("発音矯正アプリ", r"発音矯正(?:の)?(?:アプリ|サービス|ツール)?"),
    ("英語アプリ", r"英語(?:学習)?アプリ|アプリ"),
    ("教材", r"教材|参考書|単語帳|問題集"),
    ("無料体験", r"無料体験|体験レッスン"),
    ("レッスン", r"レッスン|授業"),
]
for _n in _q.SERVICE_NAMES:
    TARGETS.insert(0, (_n, re.escape(_n)))

NUM_RE = re.compile(r"([0-9][0-9,\.]*)\s*(年間|年|ヶ月|か月|カ月|週間|日間|日|時間|分|"
                    r"回|点|万円|円|コマ|本|ページ)")

# 「5年間」と「5年」、「3ヶ月」と「3か月」は同じ。表記を1つに寄せる
UNIT_CANON = {"年間": "年", "か月": "ヶ月", "カ月": "ヶ月", "日間": "日"}


def canon_value(num, unit):
    n = num.replace(",", "").rstrip(".")
    return f"{n}{UNIT_CANON.get(unit, unit)}"

NEEDS = {
    "留学した": "パスポートの出入国記録", "渡航した": "パスポートの出入国記録",
    "受験した": "TOEIC公式マイページのスコアと受験日",
    "払った": "クレジットカード・銀行の明細", "溶かした": "クレジットカード・銀行の明細",
    "使った": "サービスのアカウント履歴", "続けた": "サービスのアカウント履歴",
    "通った": "受講記録・領収書", "受けた": "サービスのアカウント履歴",
    "登録した": "サービスのアカウント履歴", "やめた": "サービスのアカウント履歴",
    "働いている": "職務経歴（本人の申告で足りる）",
    "後回しにした": "本人の記憶で足りる", "止まっていた": "TOEIC公式マイページ",
}


# 本文のブロック要素。ここから文を取り出す
BLOCK_RE = re.compile(
    r"<(p|li|h2|h3|h4|blockquote|td|figcaption)\b[^>]*>(.*?)</\1>",
    re.DOTALL | re.IGNORECASE)

# 抽出対象から外すブロック。**本文中の実体験は外さない**ので、
# 文言ではなくHTML構造とアフィリンクの有無で判定する。
EXCLUDE_HTML = {
    "blockquote": "引用・口コミ",
    "figcaption": "キャプション",
}


def blocks(html):
    """記事HTMLを (種別, 除外理由 or None, 文の並び, 除外時の残り本文) で返す。

    CTAボックスは affiliate_inserter が付ける定型なので、まるごと外す。
    引用（blockquote）は第三者の口コミなので外す。

    **アフィリンクを含むブロックは注意が要る。** 体験を書いた段落の末尾に
    公式リンクがあることがあり、丸ごと外すと体験主張まで消える。
    リンク部分を取り除いた本文に体験表現が残るなら、
    「要確認」として別一覧に出す（黙って捨てない）。
    """
    import affiliate_inserter as _ai2
    html = _ai2.strip_box(html)
    out = []
    for m in BLOCK_RE.finditer(html):
        tag = m.group(1).lower()
        inner = m.group(2)
        reason = EXCLUDE_HTML.get(tag)
        rest = ""
        if not reason and _q.AFFILIATE_LINK_RE.search(inner):
            # リンクを取り除いた残りに体験表現があるか
            rest = _q.strip_tags(re.sub(r"<a\b.*?</a>", "", inner, flags=re.DOTALL | re.I))
            if any(v in rest for v in _q.EXPERIENCE_VERBS):
                # 体験が書かれている段落。リンクだけ除いて本文は拾う
                ss = [x.strip() for x in re.split(r"(?<=[。？！])", rest) if x.strip()]
                out.append((tag, None, ss, rest))
                continue
            reason = "アフィリエイト導線"
        if not reason and re.search(r"<a\b", inner) and len(_q.strip_tags(inner)) < 40:
            reason = "リンクだけの行"
        text = _q.strip_tags(inner)
        if not text:
            continue
        ss = [x.strip() for x in re.split(r"(?<=[。？！])", text) if x.strip()]
        out.append((tag, reason, ss, rest or text))
    return out


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[。？！\n])", text) if s.strip()]


def parse(sent, carried=None):
    """1文から命題を取り出す。取れなければ None。

    carried … (主語, 継承の種類)。日本語は主語を書かないので文脈から引き継ぐ。
    引き継ぎは見出し（h2/h3）でリセットする。CTAやリンクでは切らない。

    **主語の確信度と、体験かどうかは別に判定する。**
    主語が分からなくても「誰かの具体的な体験を表す文」ではあるので、
    体験候補（possible）として監査には残す。
    """
    if re.search(GENERAL_MARK, sent):
        kind = "一般論"
    else:
        kind = None

    act = act_type = None
    for name, pat in ACT_EXPERIENCE.items():
        if re.search(pat, sent):
            act, act_type = name, "体験"
            break
    if not act:
        for name, pat in ACT_RESEARCH.items():
            if re.search(pat, sent):
                act, act_type = name, "調査"
                break
    if not act:
        return None

    # 動詞の目的語を維持する。動詞より後ろに出てくる語は対象にしない。
    # 「発音矯正のアプリを探し始めた。speekという…」から
    # 「speekを使った」を作らないため。
    vpos = re.search(ACT_EXPERIENCE.get(act) or ACT_RESEARCH.get(act), sent)
    vstart = vpos.start() if vpos else len(sent)
    best = None
    for n, pat in TARGETS:
        for tm in re.finditer(pat, sent):
            if tm.end() > vstart:
                continue
            # 動詞に近く、助詞（を/に/へ/で）が続くものを優先する
            tail = sent[tm.end():tm.end() + 2]
            score = (vstart - tm.end()) - (30 if re.match(r"[をにへで]", tail) else 0)
            if best is None or score < best[0]:
                best = (score, n)
    if not best:
        return None
    target = best[1]

    m = NUM_RE.search(sent)
    value = canon_value(m.group(1), m.group(2)) if m else ""

    if re.search(SUBJ_READER, sent):
        subj, conf = "読者", "explicit"
    elif re.search(SUBJ_SELF, sent):
        subj, conf = "さくら", "explicit"
    elif kind == "一般論":
        subj, conf = "第三者", "explicit"
    elif carried and carried[0] in ("さくら", "読者", "第三者"):
        subj, conf = carried[0], carried[1]
    else:
        subj, conf = "unknown", "unknown"

    if re.search(r"(?:する|します|したい|予定|つもり|だろう)$", sent.rstrip("。")):
        tense = "未来"
    elif re.search(r"(?:た|だ|ていた|ている)[。、]?$", sent.rstrip("。")) or "し" in act:
        tense = "過去"
    else:
        tense = "現在"

    kind_label = ("一般論" if kind == "一般論" else
                  "第三者口コミ" if subj == "第三者" else
                  act_type)

    # 体験かどうかと、体験者が誰かは別。主語が不明でも体験候補として残す
    if act_type != "体験" or kind == "一般論" or tense == "未来":
        experience = "no"
    elif subj == "さくら":
        experience = "yes"
    elif subj == "unknown":
        experience = "possible"
    else:
        experience = "no"          # 読者・第三者の体験は本人の主張ではない

    claim = f"{target}を{value}{act}" if value else f"{target}を{act}"
    if act in ("留学した", "渡航した", "働いている"):
        claim = f"{target}へ{act}" if act != "働いている" else f"{target}として{act}"
        if value:
            claim = f"{target}へ{value}{act}"
    return {
        "claim": claim, "subject": subj, "act": act, "act_type": act_type,
        "target": target, "value": value, "tense": tense, "kind": kind_label,
        "subject_confidence": conf, "experience": experience,
        "sentence": sent[:200],
    }


def setting_hit(prop):
    """設定ファイルに、同じ対象と数値が出てくるか。文字列でも照合する。"""
    hits = []
    for f in SETTING_FILES:
        if not f.exists():
            continue
        try:
            t = re.sub(r"[,，]", "", f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if prop["target"] not in t:
            continue
        num = re.sub(r"[^0-9]", "", prop["value"])
        if num and num not in t:
            continue
        hits.append(f.name)
    return hits[:4]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    posts = _wa.published()
    print(f"公開中 {len(posts)}本から命題を抜き出す\n")

    props = defaultdict(lambda: {"rows": [], "posts": [], "variants": set()})
    excluded = defaultdict(int)
    samples = defaultdict(list)

    for p in posts:
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        html = p.get("content", {}).get("rendered", "")
        section_subj = None      # 同じ見出しの中で引き継ぐ主語
        for tag, reason, ss, rest in blocks(html):
            # 見出しが変われば話者が変わりうる。ここでだけリセットする。
            # CTAやリンクでは切らない（同じ節なら書き手は同じ）
            if tag in ("h2", "h3", "h4"):
                section_subj = None
            if reason:
                excluded[reason] += 1
                samples[reason].append((p["id"], p.get("link", ""), tag, rest[:160]))
                continue
            para_subj = None     # 同じ段落の中の引き継ぎ
            for i, sent in enumerate(ss):
                carried = (para_subj and (para_subj, "inherited_paragraph")) or \
                          (section_subj and (section_subj, "inherited_section"))
                pr = parse(sent, carried)
                if not pr:
                    continue
                if pr["subject_confidence"] == "explicit":
                    para_subj = section_subj = pr["subject"]
                # 統合キーは 対象＋行動＋正規化した数値
                key = f"{pr['target']}|{pr['act']}|{pr['value']}"
                d = props[key]
                ctx = " ".join(ss[max(0, i - 1):i + 2])[:260]
                d["rows"].append({**pr, "context": ctx, "html_tag": tag,
                                  "link_stripped": "yes" if rest != " ".join(ss) else "",
                                  "post_id": p["id"], "url": p.get("link", ""),
                                  "title": title})
                d["variants"].add(pr["sentence"][:60])
                if p["id"] not in d["posts"]:
                    d["posts"].append(p["id"])

    # 数値なしの命題は、数値ありの命題を包含している可能性がある。
    # 同じと断定せず、別命題として残したうえで関係だけ記録する。
    subsumes = defaultdict(list)
    for key in props:
        t, a, v = key.split("|")
        if v:
            continue
        for other in props:
            ot, oa, ov = other.split("|")
            if ot == t and oa == a and ov:
                subsumes[key].append(other)

    ordered = sorted(props.items(), key=lambda kv: -len(kv[1]["posts"]))
    rows = []
    for i, (key, d) in enumerate(ordered, start=1):
        r0 = d["rows"][0]
        t, a, v = key.split("|")
        claim = f"{t}を{v}{a}" if v else f"{t}を{a}"
        if a in ("留学した", "渡航した"):
            claim = f"{t}へ{v}{a}" if v else f"{t}へ{a}"
        if a == "働いている":
            claim = f"{t}として{a}"
        rows.append({
            "claim_id": f"C{i:03d}", "claim": claim,
            "subject": r0["subject"], "subject_confidence": r0["subject_confidence"],
            "act": a, "kind": r0["kind"],
            "target": t, "value": v or "", "tense": r0["tense"],
            "experience": r0["experience"],
            "html_tag": r0["html_tag"],
            "posts": len(d["posts"]),
            "post_ids": " ".join(str(x) for x in d["posts"][:12]),
            "urls": " ".join(sorted({x["url"] for x in d["rows"]})[:4]),
            "sentence": r0["sentence"], "context": r0["context"],
            "variants": " ／ ".join(sorted(d["variants"])[:4]),
            "subsumed_by": "",
            "setting_source": " ".join(setting_hit(r0)) or "（該当なし）",
            "needs": NEEDS.get(a, "本人の確認"),
            "confirmation": "",
            "_key": key,
        })

    idx = {r["_key"]: r["claim_id"] for r in rows}
    for r in rows:
        if r["_key"] in subsumes:
            r["subsumed_by"] = "包含: " + " ".join(idx[k] for k in subsumes[r["_key"]])
        r.pop("_key")

    with open(OUT / "CLAIMS.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["claim_id"])
        w.writeheader()
        w.writerows(rows)

    yes = [r for r in rows if r["experience"] == "yes"]
    pos = [r for r in rows if r["experience"] == "possible"]
    L = [f"# 体験主張の確認一覧（命題単位） {date.today().isoformat()}\n\n",
         f"公開中 {len(posts)}本 / 命題 **{len(rows)}件**\n\n"
         f"- 体験 **yes {len(yes)}件**（主語が確定した本人の体験）\n"
         f"- 体験 **possible {len(pos)}件**（体験表現だが主語が不明。監査対象に残す）\n\n",
         "**記事は一切修正していない。**\n\n",
         "### 抽出から外したブロック\n\n| 理由 | ブロック数 |\n|---|---|\n"]
    for k, n in sorted(excluded.items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {n} |\n")
    L.append("\n判定は文の形からの推測。**必ず原文を読んで確かめてから** "
             "`confirmation` を入れてください"
             "（verified / partially_verified / fictional / unknown）。\n\n---\n\n")

    for r in rows[:TOP]:
        L.append(f"## {r['claim_id']} {r['claim']}\n\n")
        L.append("| 項目 | 値 |\n|---|---|\n")
        L.append(f"| 正規化した命題 | **{r['claim']}** |\n")
        L.append(f"| 主語 | {r['subject']}（確信度: **{r['subject_confidence']}**） |\n")
        L.append(f"| 分類 | **{r['kind']}** |\n")
        L.append(f"| 行動・状態 | {r['act']} |\n| 対象 | {r['target']} |\n")
        L.append(f"| 数値と単位 | {r['value'] or '—'} |\n| 時制 | {r['tense']} |\n")
        L.append(f"| 体験判定 | **{r['experience']}** |\n")
        L.append(f"| 抽出元のHTML種別 | `<{r['html_tag']}>` |\n")
        L.append(f"| 登場記事数 | {r['posts']}本（{r['post_ids']}） |\n")
        L.append(f"| 同義統合した表現 | {r['variants']} |\n")
        L.append(f"| 包含関係 | {r['subsumed_by'] or '—'} |\n")
        L.append(f"| 設定ファイルの一致 | {r['setting_source']} |\n")
        L.append(f"| 事実確認に必要なもの | {r['needs']} |\n\n")
        L.append(f"**元文**\n\n> {r['sentence']}\n\n")
        L.append(f"**前後3文**\n\n> {r['context']}\n\n")
        L.append("**記事URL**\n\n")
        for u in r["urls"].split():
            L.append(f"- {u}\n")
        L.append("\n**confirmation**: （未記入）\n\n---\n\n")

    (OUT / "CLAIMS.md").write_text("".join(L), encoding="utf-8")

    # 除外しすぎていないかを確かめる一覧。偽陰性はここでしか見つからない
    NEED = "要確認: アフィリンク付きだが体験表現が残る"
    E = [f"# 抽出から外したブロック {date.today().isoformat()}\n\n",
         "誤抽出（偽陽性）だけでなく、**除外しすぎ（偽陰性）**を確かめるための一覧。\n\n",
         "## 理由別の件数\n\n| 理由 | ブロック数 |\n|---|---|\n"]
    for k, n in sorted(excluded.items(), key=lambda kv: -kv[1]):
        E.append(f"| {k} | {n} |\n")

    E.append(f"\n## ⚠️ 要確認（{len(samples.get(NEED, []))}件）\n\n"
             "アフィリンクを取り除いた本文に体験表現が残っているブロック。\n"
             "**体験主張が監査から漏れている可能性がある。**\n\n")
    for pid, url, tag, rest in samples.get(NEED, [])[:40]:
        E.append(f"- **[{pid}]** `<{tag}>` {url}\n  - {rest}\n")
    if not samples.get(NEED):
        E.append("（該当なし）\n")

    E.append("\n## 除外したブロックのサンプル（理由別・各5件）\n\n")
    for k in sorted(excluded, key=lambda x: -excluded[x]):
        if k == NEED:
            continue
        E.append(f"### {k}（{excluded[k]}件）\n\n")
        for pid, url, tag, rest in samples[k][:5]:
            E.append(f"- [{pid}] `<{tag}>` {rest[:120]}\n")
        E.append("\n")

    (OUT / "EXCLUDED.md").write_text("".join(E), encoding="utf-8")
    print(f"命題 {len(rows)}件（体験 yes {len(yes)}件 / possible {len(pos)}件）")
    print("除外したブロック:", dict(excluded))
    print(f"{'ID':6}{'記事':>3} {'体験':<9}{'主語':<8}{'確信度':<20} 命題")
    for r in rows[:TOP]:
        print(f"{r['claim_id']:6}{r['posts']:>3} {r['experience']:<9}"
              f"{r['subject']:<8}{r['subject_confidence']:<20} {r['claim']}")


if __name__ == "__main__":
    main()
