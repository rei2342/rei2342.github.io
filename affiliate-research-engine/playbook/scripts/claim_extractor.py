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

# ── 行動・状態 ──────────────────────────────────────────
# 動詞は形態素解析で**辞書形**に戻して判定する。
# 「受けました」「契約しました」を個別に列挙すると必ず漏れる
# （2026-08-08に「受けました」を取りこぼした）。
from janome.tokenizer import Tokenizer  # noqa: E402

_T = Tokenizer()

# 辞書形 → (正規化した行動, 種別)
LEMMA_ACT = {
    "留学": ("留学", "体験"), "渡航": ("渡航", "体験"),
    "通う": ("通学", "体験"), "使う": ("利用", "体験"), "利用": ("利用", "体験"),
    "試す": ("試用", "体験"), "続ける": ("継続", "体験"), "継続": ("継続", "体験"),
    "やめる": ("中断", "体験"), "止める": ("中断", "体験"), "挫折": ("中断", "体験"),
    "受ける": ("受講", "体験"), "受講": ("受講", "体験"), "受験": ("受験", "体験"),
    "登録": ("登録", "体験"), "申し込む": ("登録", "体験"), "契約": ("契約", "体験"),
    "解約": ("解約", "体験"), "退会": ("解約", "体験"),
    "払う": ("支払", "体験"), "支払う": ("支払", "体験"), "支払": ("支払", "体験"),
    "始める": ("開始", "体験"), "開始": ("開始", "体験"),
    "溶かす": ("浪費", "体験"), "働く": ("就業", "体験"),
    "後回し": ("後回し", "体験"), "停滞": ("停滞", "体験"),
    "調べる": ("調査", "調査"), "調査": ("調査", "調査"),
    "比べる": ("比較", "調査"), "比較": ("比較", "調査"),
    "探す": ("探索", "調査"), "検討": ("検討", "調査"), "検索": ("検索", "調査"),
    "問い合わせる": ("問合せ", "調査"),
}

# 述語の後ろに付いて時制を決めるもの
AUX_BASE = {"ます", "た", "だ", "です", "ない", "ぬ", "う", "よう", "たい", "らしい"}
AUX_VERB = {"いる", "ある", "みる", "しまう", "くる", "おく", "ほしい",
            "する", "できる", "なる"}
COND_SURF = {"ば", "たら", "なら", "れば"}


def analyze(sent):
    """文から (行動, 種別, 開始位置, 述語の表層, 時制) を取り出す。

    時制は**その述語に付いた助動詞**から決める。文中のどこかに
    「なら」があるだけで条件扱いしない。
    """
    toks, pos, spans = list(_T.tokenize(sent)), 0, []
    for t in toks:
        spans.append((pos, pos + len(t.surface), t))
        pos += len(t.surface)

    out = []
    for i, (bs, be, t) in enumerate(spans):
        base = t.base_form if t.base_form != "*" else t.surface
        if base not in LEMMA_ACT:
            continue
        pos1 = t.part_of_speech.split(",")[0]
        skip = 0
        if pos1 == "名詞":
            # サ変名詞は「する」が続くときだけ動詞として扱う。
            # 「後回しにする」のように助詞を挟む形もある
            for k in (1, 2):
                nxt = spans[i + k][2] if i + k < len(spans) else None
                if nxt and (nxt.base_form in ("する", "できる")
                            or nxt.surface in ("し", "する", "さ")):
                    skip = k
                    break
            if not skip:
                continue
        elif pos1 != "動詞":
            continue

        action, atype = LEMMA_ACT[base]
        past = polite = prog = cond = vol = nonpast = False
        end, te = be, False
        j = i + 1 + skip
        while j < len(spans):
            tk = spans[j][2]
            b, sf = (tk.base_form if tk.base_form != "*" else tk.surface), tk.surface
            p1 = tk.part_of_speech.split(",")[0]
            # 条件は品詞に頼らない。「なら」は助動詞と解析されることがある
            if sf in COND_SURF or sf in ("なら", "たら", "れば", "ば"):
                cond = True
            elif p1 == "助詞" and sf in ("て", "で"):
                te = True
            elif p1 == "助動詞" and b in AUX_BASE:
                if b == "た":
                    past = True
                elif b == "ます":
                    polite = True
                elif b in ("う", "よう", "たい"):
                    vol = True
                elif b == "だ" and tk.surface in ("だ", "な"):
                    past = past or tk.surface == "だ"
            elif p1 == "動詞" and b in AUX_VERB:
                if b == "いる" and te:
                    prog = True
                if b == "する":
                    pass
            else:
                break
            end = spans[j][1]
            j += 1

        if cond:
            tense = "conditional"
        elif past:
            tense = "past"
        elif prog:
            tense = "progressive"
        elif vol:
            tense = "future"
        elif polite:
            tense = "future"
        elif spans[j - 1][2].part_of_speech.split(",")[1:2] == ["自立"] or nonpast:
            tense = "present"
        else:
            tense = "present" if j == i + 1 else "unknown"

        out.append((action, atype, bs, sent[bs:end], tense))
    return out


# 表示に使う語尾。時制が unknown のときは原文の述語をそのまま出す
ACTION_FORM = {
    "留学": ("留学した", "留学する", "留学している"),
    "渡航": ("渡航した", "渡航する", "渡航している"),
    "通学": ("通った", "通う", "通っている"),
    "利用": ("使った", "使う", "使っている"),
    "試用": ("試した", "試す", "試している"),
    "継続": ("続けた", "続ける", "続けている"),
    "中断": ("やめた", "やめる", "やめている"),
    "受講": ("受けた", "受ける", "受けている"),
    "受験": ("受験した", "受験する", "受験している"),
    "登録": ("登録した", "登録する", "登録している"),
    "契約": ("契約した", "契約する", "契約している"),
    "解約": ("解約した", "解約する", "解約している"),
    "支払": ("払った", "払う", "払っている"),
    "開始": ("始めた", "始める", "始めている"),
    "浪費": ("溶かした", "溶かす", "溶かしている"),
    "就業": ("働いていた", "働く", "働いている"),
    "後回し": ("後回しにした", "後回しにする", "後回しにしている"),
    "停滞": ("止まっていた", "止まる", "止まっている"),
    "調査": ("調べた", "調べる", "調べている"),
    "比較": ("比較した", "比較する", "比較している"),
    "探索": ("探した", "探す", "探している"),
    "検討": ("検討した", "検討する", "検討している"),
    "検索": ("検索した", "検索する", "検索している"),
    "問合せ": ("問い合わせた", "問い合わせる", "問い合わせている"),
}
GENERAL_MARK = r"と言われ|一般的に|多くの人|人によって|とされ|らしい|そうだ|だろう|かもしれない"


def quote_spans(sent):
    """「」で囲まれた範囲。中の述語だけで本人の体験を確定しない。"""
    spans, depth, start = [], 0, None
    for i, ch in enumerate(sent):
        if ch in "「『":
            if depth == 0:
                start = i
            depth += 1
        elif ch in "」』" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, i + 1))
    return spans


# 同じ節でも、別の主語・情報源が出たら継承を上書き／停止する
SUBJ_OTHER = [
    ("読者",   r"あなた(?:は|が|も)|読者(?:は|が)|みなさん"),
    ("第三者", r"利用者(?:は|が)|初心者(?:は|が)|受講生(?:は|が)|多くの人(?:は|が)"
               r"|という人(?:は|が)|経験者(?:は|が)"),
    ("情報源", r"口コミでは|レビューでは|公式(?:サイト|ページ)では|公式には|調査では"),
]

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
            # 体験表現の判定は形態素解析に任せる。単語リストだと
            # 丁寧形（受けました）を取りこぼす（2026-08-08に実例）
            if any(at == "体験" for _a, at, *_ in analyze(rest)):
                # 体験が書かれている段落。リンクだけ除いて本文は拾う
                ss = [x.strip() for x in re.split(r"(?<=[。？！])", rest) if x.strip()]
                out.append((tag, None, ss, rest, True))
                continue
            reason = "アフィリエイト導線"
        if not reason and re.search(r"<a\b", inner) and len(_q.strip_tags(inner)) < 40:
            reason = "リンクだけの行"
        text = _q.strip_tags(inner)
        if not text:
            continue
        ss = [x.strip() for x in re.split(r"(?<=[。？！])", text) if x.strip()]
        out.append((tag, reason, ss, rest or text, False))
    return out


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[。？！\n])", text) if s.strip()]


def scan_subject(sent):
    """文から主語だけを拾う。命題にならない文でも主語は取れる。

    別の主語・情報源が出たら、そちらを返す。さくらの継承を上書きするため。
    """
    for name, pat in SUBJ_OTHER:
        if re.search(pat, sent):
            return name
    if re.search(SUBJ_SELF, sent):
        return "さくら"
    return None


def detect_tense(sent):
    body = sent.rstrip()
    for name, pat in TENSE_RE:
        if re.search(pat, body):
            return name
    return "unknown"


def parse(sent, carried=None, from_aff=False):
    """1文から命題を取り出す。取れなければ None。"""
    general = bool(re.search(GENERAL_MARK, sent))
    quotes = quote_spans(sent)

    cands = analyze(sent)
    if not cands:
        return None
    # 引用の外にある述語を優先する。無ければ引用内のものを使い、印を付ける
    outside = [c for c in cands if not any(a <= c[2] < b for a, b in quotes)]
    ordered_cands = outside + [c for c in cands if c not in outside]

    # 述語ごとに目的語を探し、取れたものを採用する。
    # 最初の候補に目的語が無いだけで諦めない
    picked = None
    for cand in ordered_cands:
        _a, _t, vstart, _p, _tn = cand
        in_quote = any(a <= vstart < b for a, b in quotes)
        best = None
        for n, tpat in TARGETS:
            for tm in re.finditer(tpat, sent):
                if tm.end() > vstart:
                    continue
                if any(a <= tm.start() < b for a, b in quotes) and not in_quote:
                    continue      # 引用内の語を、引用外の述語の目的語にしない
                tail = sent[tm.end():tm.end() + 2]
                score = (vstart - tm.end()) - (30 if re.match(r"[をにへで]", tail) else 0)
                if best is None or score < best[0]:
                    best = (score, n)
        if best:
            picked = (cand, best[1], in_quote)
            break
    if not picked:
        return None
    (action, atype, vstart, pred, tense), target, quoted = picked

    nm = NUM_RE.search(sent[:vstart]) or NUM_RE.search(sent)
    value = canon_value(nm.group(1), nm.group(2)) if nm else ""

    subj_here = scan_subject(sent)
    if subj_here == "情報源":
        subj, conf = "第三者", "explicit"
    elif subj_here:
        subj, conf = subj_here, "explicit"
    elif general:
        subj, conf = "第三者", "explicit"
    elif carried and carried[0] in ("さくら", "読者", "第三者"):
        subj, conf = carried[0], carried[1]
    else:
        subj, conf = "unknown", "unknown"

    # 分類と体験判定は必ず整合させる
    if quoted:
        kind, experience = "引用", "no"
    elif general or subj == "第三者":
        kind, experience = "一般論", "no"
    elif tense in ("future", "conditional"):
        kind, experience = ("予定" if tense == "future" else "条件"), "no"
    elif atype == "調査":
        kind, experience = "調査", "no"
    elif subj == "さくら":
        kind, experience = "体験", "yes"
    elif subj == "読者":
        kind, experience = "読者の想定", "no"
    else:
        kind, experience = "体験", "possible"

    forms = ACTION_FORM.get(action)
    if tense == "past":
        verb = forms[0]
    elif tense in ("future", "conditional", "present"):
        verb = forms[1]
    elif tense == "progressive":
        verb = forms[2]
    else:
        verb = pred          # unknown は原文の述語をそのまま出す

    claim = f"{target}を{value}{verb}" if value else f"{target}を{verb}"
    if action in ("留学", "渡航"):
        claim = f"{target}へ{value}{verb}" if value else f"{target}へ{verb}"
    if action == "就業":
        claim = f"{target}として{verb}"

    return {
        "claim": claim, "subject": subj, "subject_confidence": conf,
        "normalized_action": action, "original_predicate": pred,
        "act_type": atype, "target": target, "value": value,
        "tense": tense, "kind": kind, "experience": experience,
        "quoted": "yes" if quoted else "",
        "from_affiliate_block": "yes" if from_aff else "",
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
        for tag, reason, ss, rest, from_aff in blocks(html):
            # 見出しが変われば話者が変わりうる。ここでだけリセットする。
            # CTAやリンクでは切らない（同じ節なら書き手は同じ）
            if tag in ("h2", "h3", "h4"):
                section_subj = None
            if reason:
                excluded[reason] += 1
                samples[reason].append((p["id"], p.get("link", ""), tag, rest[:160]))
                continue
            para_subj = None     # 段落が変われば、第三者・読者の継承は切れる
            for i, sent in enumerate(ss):
                # 主語だけ先に見る。命題にならない文からも拾う。
                # 別の主語・情報源が出たら、そこで継承を上書きする
                sh = scan_subject(sent)
                if sh == "情報源":
                    para_subj = section_subj = None   # 一時停止
                elif sh == "さくら":
                    para_subj = section_subj = sh     # 筆者は節内で継続
                elif sh:
                    # 第三者・読者は段落内だけ。次の段落で筆者に戻ることが多く、
                    # 節末まで残すと逆方向の誤判定になる（2026-08-08に実例）
                    para_subj = sh
                    section_subj = None

                carried = (para_subj and (para_subj, "inherited_paragraph")) or \
                          (section_subj and (section_subj, "inherited_section"))
                pr = parse(sent, carried, from_aff)
                if not pr:
                    continue
                # 統合キーは 対象＋行動＋正規化した数値
                key = (f"{pr['target']}|{pr['normalized_action']}|"
                       f"{pr['value']}|{pr['tense']}")
                d = props[key]
                ctx = " ".join(ss[max(0, i - 1):i + 2])[:260]
                d["rows"].append({**pr, "context": ctx, "html_tag": tag,

                                  "post_id": p["id"], "url": p.get("link", ""),
                                  "title": title})
                d["variants"].add(pr["sentence"][:60])
                if p["id"] not in d["posts"]:
                    d["posts"].append(p["id"])

    # 数値なしの命題は、数値ありの命題を包含している可能性がある。
    # 同じと断定せず、別命題として残したうえで関係だけ記録する。
    subsumes = defaultdict(list)
    for key in props:
        t, a, v, _tense = key.split("|")
        if v:
            continue
        for other in props:
            ot, oa, ov, otn = other.split("|")
            if ot == t and oa == a and otn == _tense and ov:
                subsumes[key].append(other)

    ordered = sorted(props.items(), key=lambda kv: -len(kv[1]["posts"]))
    rows = []
    for i, (key, d) in enumerate(ordered, start=1):
        r0 = d["rows"][0]
        t, a, v, _tense = key.split("|")
        claim = r0["claim"]      # 表示は行動と時制から作った文字列を使う
        rows.append({
            "claim_id": f"C{i:03d}", "claim": claim,
            "subject": r0["subject"], "subject_confidence": r0["subject_confidence"],
            "normalized_action": r0["normalized_action"],
            "original_predicate": r0["original_predicate"],
            "act": a, "kind": r0["kind"],
            "target": t, "value": v or "", "tense": r0["tense"],
            "experience": r0["experience"],
            "quoted": r0["quoted"], "from_affiliate_block": r0["from_affiliate_block"],
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

    # 分類が「体験」なのに experience=no は矛盾。出したら気づけるようにする
    bad = [r for r in rows
           if (r["kind"] == "体験") != (r["experience"] in ("yes", "possible"))]
    if bad:
        print(f"⚠️ 整合しない命題が{len(bad)}件あります:")
        for r in bad[:5]:
            print(f"   {r['claim_id']} kind={r['kind']} experience={r['experience']}"
                  f" tense={r['tense']} {r['claim']}")

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

    # 出現数の多い命題は似たものに偏る。弱点は層別サンプルのほうが見つかる
    STRATA = [
        ("explicit かつ experience=yes",
         lambda r: r["subject_confidence"] == "explicit" and r["experience"] == "yes"),
        ("inherited_section", lambda r: r["subject_confidence"] == "inherited_section"),
        ("subject=unknown かつ possible",
         lambda r: r["subject"] == "unknown" and r["experience"] == "possible"),
        ("conditional", lambda r: r["tense"] == "conditional"),
        ("from_affiliate_block=yes", lambda r: r["from_affiliate_block"] == "yes"),
        ("quoted=yes", lambda r: r["quoted"] == "yes"),
    ]

    def detail(r):
        out = [f"### {r['claim_id']} {r['claim']}\n\n"]
        out.append(f"- 主語: **{r['subject']}**（{r['subject_confidence']}） / "
                   f"分類: **{r['kind']}** / 体験: **{r['experience']}**\n")
        out.append(f"- 行動: {r['normalized_action']} / 時制: **{r['tense']}** / "
                   f"述語: `{r['original_predicate']}`\n")
        out.append(f"- 引用: {r['quoted'] or '—'} / "
                   f"アフィ段落由来: {r['from_affiliate_block'] or '—'} / "
                   f"`<{r['html_tag']}>` / {r['posts']}本\n")
        out.append(f"- **元文**: {r['sentence']}\n")
        out.append(f"- **前後3文**: {r['context']}\n")
        out.append(f"- 記事: {r['urls'].split()[0] if r['urls'] else '—'}\n\n")
        return "".join(out)

    L.append("# 層別サンプル（各5件）\n\n")
    for name, cond in STRATA:
        sel = [r for r in rows if cond(r)]
        L.append(f"## {name}（該当 {len(sel)}件）\n\n")
        if not sel:
            L.append("（該当なし）\n\n")
        for r in sel[:5]:
            L.append(detail(r))
    L.append("\n---\n\n# 出現数の多い順（上位10件）\n\n")

    for r in rows[:TOP]:
        L.append(f"## {r['claim_id']} {r['claim']}\n\n")
        L.append("| 項目 | 値 |\n|---|---|\n")
        L.append(f"| 正規化した命題 | **{r['claim']}** |\n")
        L.append(f"| 主語 | {r['subject']}（確信度: **{r['subject_confidence']}**） |\n")
        L.append(f"| 分類 | **{r['kind']}** |\n")
        L.append(f"| 行動・状態 | {r['act']} |\n| 対象 | {r['target']} |\n")
        L.append(f"| 数値と単位 | {r['value'] or '—'} |\n")
        L.append(f"| 原文の述語 | `{r['original_predicate']}` |\n")
        L.append(f"| 正規化した行動 | {r['normalized_action']} |\n")
        L.append(f"| 時制 | **{r['tense']}** |\n")
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
    print(f"矛盾: {len(bad)}件")
    print("除外したブロック:", dict(excluded))
    print(f"{'ID':6}{'記事':>3} {'体験':<9}{'主語':<8}{'確信度':<20} 命題")
    for r in rows[:TOP]:
        print(f"{r['claim_id']:6}{r['posts']:>3} {r['experience']:<9}"
              f"{r['subject']:<8}{r['subject_confidence']:<20} {r['claim']}")


if __name__ == "__main__":
    main()
