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
    "受ける": ("受ける_未分類", "体験"),
    "受講": ("受講", "体験"), "受験": ("受験", "体験"),
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

# 可能の形。「受けられる」はできるという話で、受けた事実ではない
POTENTIAL_V = {"られる", "れる", "得る", "うる"}

# 複合動詞の後ろ側。前の動詞に付いて相を足すだけで、目的語は取らない
COMPOUND_V2 = {"続ける", "始める", "終える", "直す", "切る", "出す", "込む",
               "きる", "つづける", "はじめる"}

# 問いの文。「〜たどり着けるのか。」はやった事実の記述ではない
QUESTION_RE = re.compile(r"(?:のか|だろうか|でしょうか|ますか|ですか)[。？]?\s*$")

# 連体修飾の主名詞。「本契約しなかった人は」の主語はさくらではない
RELATIVE_HEAD_RE = re.compile(r"^[^。、]{0,6}?(人|方|者|層|タイプ)(?:は|が|も|の|に|、)")


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
                            or nxt.surface in ("し", "する", "さ", "せ")):
                    skip = k
                    break
            if not skip:
                continue
        elif pos1 != "動詞":
            continue

        # 複合動詞の後ろ側（言い**続ける**・調べ**始める**）は、
        # 目的語を自分では取らない。「ワーホリで海外に行きたいと言い続けて」を
        # 「ワーホリを続けた」にしてしまうため、後ろ側からは命題を作らない。
        # 前側（言う）が LEMMA_ACT にあるなら、そちらが同じ対象を拾う
        if base in COMPOUND_V2 and i > 0:
            pv = spans[i - 1][2]
            if pv.part_of_speech.split(",")[0] == "動詞" \
                    and "連用" in getattr(pv, "infl_form", ""):
                continue

        # 連用形＋名詞は複合名詞。「払い損になる」は払った事実ではないし、
        # 「使い方」「言い訳」も同じ形をしている
        if "連用" in getattr(t, "infl_form", "") and i + 1 < len(spans):
            nv = spans[i + 1][2]
            if nv.part_of_speech.split(",")[0] == "名詞" \
                    and nv.part_of_speech.split(",")[1] != "非自立":
                continue

        action, atype = LEMMA_ACT[base]
        past = polite = prog = cond = vol = nonpast = False
        negative = potential = False
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
                elif b in ("ない", "ぬ"):
                    negative = True
                elif b == "だ" and tk.surface in ("だ", "な"):
                    past = past or tk.surface == "だ"
            elif p1 == "助詞" and sf in ("ず", "ずに"):
                negative = True
            elif b in POTENTIAL_V:
                # 「オンラインで受けられる」「すぐ始められる」は、
                # できるという話であって、やった事実ではない
                potential = True
            elif p1 == "動詞" and b in COMPOUND_V2:
                # 「使い続けた」の「た」は続けるの後ろに付く。
                # ここで切ると前側の動詞が現在形に見えてしまう
                pass
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

        # 法性。助言・必要・可能・意志は、本人がやった事実ではない
        after = sent[bs:bs + 40]
        if re.search(r"必要(?:は|が|も)?ない|必要が?ある|べき|なければ|なくてもい", after):
            modality = "necessity"
        elif re.search(r"なくても|ないでも|ずとも", after):
            # 「TOEICを毎月受けなくても〜できる」は、受けなかった事実ではない
            modality = "concessive"
        elif potential or re.search(r"かもしれ|できる|得る|可能", after):
            modality = "possibility"
        elif vol:
            modality = "intention"
        elif cond:
            modality = "conditional"
        elif re.search(r"つもり", after):
            modality = "intention"     # 「相談してみるつもりだ」＝まだやっていない
        elif re.search(r"ほしい|ましょう|おすすめ|といい|してみて"
                       r"|て(?:も)?いい|ていて?いい", after):
            modality = "advice"
        elif re.search(r"^[^。]{0,8}前に", after[len(sent[bs:end]):] or after):
            modality = "prospective"     # 「払う前に」＝まだやっていない
        elif QUESTION_RE.search(sent):
            # 「たどり着けるのか。」は問いであって、やった事実の記述ではない
            modality = "question"
        else:
            modality = "factual"

        # 「英語しか使わない」は英語を使わなかった話ではない。
        # 「しか」は否定の形で肯定を言う構文なので、極性を反転させない
        if re.search(r"しか", sent[max(0, bs - 30):bs]):
            negative = False
        polarity = "negative" if negative else "affirmative"
        out.append((action, atype, bs, sent[bs:end], tense, polarity, modality))
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
    "相談": ("相談した", "相談する", "相談している"),
    "診断": ("診断を受けた", "診断を受ける", "診断を受けている"),
    "受ける": ("受けた", "受ける", "受けている"),
    "受ける_未分類": ("受けた", "受ける", "受けている"),
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
# (正規化した名前, [(原文の表記, 変換の種類), ...])
#
# 変換の種類:
#   none                … 変換なし
#   exact_alias         … 表記違い・ほぼ同義（授業→レッスン）
#   generalization      … 上位概念化（単語帳→教材）。事実認定に使わない
#   context_enrichment  … 文脈補完（スクール→英会話スクール）。事実認定に使わない
#
# **人が見る命題には必ず原文の表記（target_surface）を出す。**
# 正規化名は重複整理・検索・カテゴリ分類にだけ使う。
TARGETS = [
    ("フィリピン", [(r"フィリピン", "none")]),
    ("セブ島", [(r"セブ島", "none"), (r"セブ", "exact_alias")]),
    ("オーストラリア", [(r"オーストラリア", "none"), (r"豪州", "exact_alias")]),
    ("カナダ", [(r"カナダ", "none")]),
    ("ニュージーランド", [(r"ニュージーランド", "none")]),
    ("シンガポール", [(r"シンガポール", "none")]),
    ("イギリス", [(r"イギリス", "none"), (r"英国", "exact_alias")]),
    ("台湾", [(r"台湾", "none")]), ("韓国", [(r"韓国", "none")]),
    ("ハワイ", [(r"ハワイ", "none")]),
    ("国内留学", [(r"国内留学", "none")]),
    ("英語学習", [(r"英語学習", "none"),
                (r"英語の勉強", "exact_alias"), (r"英語を勉強", "exact_alias")]),
    ("TOEIC", [(r"TOEIC", "none")]),
    ("ワーホリ", [(r"ワーホリ", "none"), (r"ワーキングホリデー", "exact_alias")]),
    ("オンライン英会話", [(r"オンライン英会話", "none")]),
    ("英会話スクール", [(r"英会話スクール", "none"), (r"スクール", "context_enrichment")]),
    ("英語コーチング", [(r"英語コーチング", "none"), (r"コーチング", "context_enrichment")]),
    ("営業事務", [(r"営業事務", "none")]),
    ("仕事の英語", [(r"仕事で英語", "exact_alias"), (r"会議", "generalization"),
                (r"議事録", "generalization"), (r"電話対応", "generalization")]),
    ("発音矯正アプリ", [(r"発音矯正アプリ", "none"),
                  (r"発音矯正(?:の)?(?:サービス|ツール)", "exact_alias"),
                  (r"発音矯正", "context_enrichment")]),
    ("英語アプリ", [(r"英語(?:学習)?アプリ", "exact_alias"),
                (r"アプリ", "context_enrichment")]),
    ("教材", [(r"教材", "none"), (r"参考書", "generalization"),
            (r"単語帳", "generalization"), (r"問題集", "generalization")]),
    ("無料体験", [(r"無料体験", "none"), (r"体験レッスン", "exact_alias")]),
    ("レッスン", [(r"レッスン", "none"), (r"授業", "exact_alias"),
              (r"講座", "exact_alias")]),
    ("英語", [(r"英語", "none")]),
]
# サービス名は表記そのまま。変換しない
for _n in _q.SERVICE_NAMES:
    TARGETS.insert(0, (_n, [(re.escape(_n), "none")]))

NUM_RE = re.compile(r"([0-9][0-9,\.]*(?:万[0-9,]*)?(?:千[0-9,]*)?)\s*"
                    r"(年間|年|ヶ月|か月|カ月|週間|日間|日|時間|分|"
                    r"回|点|万円|円|コマ|本|ページ|社|校|件|人|歳)")

# 「5年間」と「5年」、「3ヶ月」と「3か月」は同じ。表記を1つに寄せる
UNIT_CANON = {"年間": "年", "か月": "ヶ月", "カ月": "ヶ月", "日間": "日"}

# 数値は命題本文に混ぜず、属性として分ける。
# 「TOEICを600点受ける」のような、意味の壊れた命題を作らないため。
UNIT_KIND = {
    "回": "count", "社": "count", "校": "count", "件": "count",
    "本": "count", "コマ": "count", "ページ": "count", "人": "count",
    "年": "duration", "ヶ月": "duration", "日": "duration",
    "週間": "duration", "時間": "duration",
    "点": "score", "円": "amount", "万円": "amount",
    "分": "time_per_session", "歳": "age",
}


def classify_number(num, unit, before):
    """数値を属性の種類に分ける。頻度は直前の語で判断する。"""
    kind = UNIT_KIND.get(unit, "unknown_numeric")
    if unit == "回" and re.search(r"(?:週|月|日|毎週|毎月|毎日)\s*$", before):
        kind = "frequency"
    return kind


def canon_value(num, unit):
    n = num.replace(",", "").rstrip(".")
    return f"{n}{UNIT_CANON.get(unit, unit)}"

# 事実確認に何を見ればよいか。キーは action_normalized（LEMMA_ACT の値）。
# 表示用の活用形をキーにしていた頃は1件も一致していなかった（2026-08-08に修正）
NEEDS = {
    "留学": "パスポートの出入国記録", "渡航": "パスポートの出入国記録",
    "受験": "TOEIC公式マイページのスコアと受験日",
    "支払": "クレジットカード・銀行の明細", "浪費": "クレジットカード・銀行の明細",
    "契約": "契約書・申込確認メール", "解約": "解約完了メール",
    "利用": "サービスのアカウント履歴", "継続": "サービスのアカウント履歴",
    "試用": "サービスのアカウント履歴", "開始": "サービスのアカウント履歴",
    "登録": "サービスのアカウント履歴", "中断": "サービスのアカウント履歴",
    "通学": "受講記録・領収書", "受講": "受講記録・領収書",
    "受ける": "何を受けたのかを先に確定する", "相談": "予約確認メール",
    "診断": "診断結果の画面",
    "就業": "職務経歴（本人の申告で足りる）",
    "後回し": "本人の記憶で足りる", "停滞": "TOEIC公式マイページ",
    "調査": "本人の記憶で足りる", "比較": "本人の記憶で足りる",
    "探索": "本人の記憶で足りる", "検討": "本人の記憶で足りる",
    "検索": "本人の記憶で足りる", "問合せ": "問い合わせメール",
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


# 目次・ナビ・関連記事は本文ではない。文字列（Toggle等）ではなく構造で外す
CONTAINER_RE = re.compile(
    r'<(div|nav|aside|section)\b[^>]*(?:id|class)="[^"]*'
    r'(toc|ez-toc|widget|sidebar|related|breadcrumb|nav|footer|share)[^"]*"[^>]*>',
    re.IGNORECASE)


def strip_containers(html):
    """目次などのコンテナを、入れ子を数えて丸ごと落とす。"""
    while True:
        m = CONTAINER_RE.search(html)
        if not m:
            return html
        tag, i, depth = m.group(1), m.end(), 1
        pat = re.compile(rf"</?{tag}\b", re.IGNORECASE)
        while depth and i < len(html):
            n = pat.search(html, i)
            if not n:
                i = len(html)
                break
            depth += -1 if n.group(0).startswith("</") else 1
            i = n.end()
        html = html[:m.start()] + html[i:]


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
    html = strip_containers(_ai2.strip_box(html))
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


def _one(sent, cand, quotes, carried, from_aff, general):
    """1つの述語から命題を作る。作れなければ None。"""
    action, atype, vstart, pred, tense, polarity, modality = cand
    in_quote = any(a <= vstart < b for a, b in quotes)

    best = None
    for n, variants in TARGETS:
        for tpat, ntype in variants:
            for tm in re.finditer(tpat, sent):
                if tm.end() > vstart:
                    continue
                if any(a <= tm.start() < b for a, b in quotes) and not in_quote:
                    continue
                tail = sent[tm.end():tm.end() + 2]
                score = (vstart - tm.end()) - (30 if re.match(r"[をにへで]", tail) else 0)
                if best is None or score < best[0]:
                    best = (score, n, tm.group(0), ntype, tm.start(), tm.end())
    if not best:
        return None
    _sc, target_norm, target_surface, ntype, tstart, tend = best

    # **不変条件**: 原文の該当位置に、その語が実在すること。
    # 位置と文字列がずれていたら、別ブロックとの誤結合か状態の持ち越し
    needs_review = ""
    if sent[tstart:tend] != target_surface:
        return {"_invalid": f"target_surface が原文の位置と一致しない "
                            f"（{target_surface!r} vs {sent[tstart:tend]!r}）"}

    action_lemma = "受ける" if action == "受ける_未分類" else action
    normalization_status = "classified"
    action_reason = ""
    if action == "受ける_未分類":
        normalization_status = "unclassified"
        near = sent[max(0, vstart - 60):vstart + 20]
        if target_norm == "TOEIC" or re.search(r"試験|テスト|受験", near):
            action, action_reason = "受験", "対象がTOEIC／周辺に試験・受験がある"
            normalization_status = "classified"
        elif target_norm in ("レッスン", "無料体験") or re.search(r"レッスン|授業|講座", near):
            action, action_reason = "受講", "対象がレッスン／周辺に授業・講座がある"
            normalization_status = "classified"
        elif re.search(r"カウンセリング|無料相談|相談", near):
            action, action_reason = "相談", "周辺にカウンセリング・相談がある"
            normalization_status = "classified"
        elif re.search(r"診断|チェック", near):
            action, action_reason = "診断", "周辺に診断・チェックがある"
            normalization_status = "classified"
        else:
            action, action_reason = "受ける", "対象・周辺語から意味を特定できない"
            needs_review = "「受ける」の意味を特定できない"

    zone = sent[tend:vstart]
    attrs = {}
    for nm in NUM_RE.finditer(zone):
        attrs.setdefault(classify_number(nm.group(1), nm.group(2), zone[:nm.start()]),
                         canon_value(nm.group(1), nm.group(2)))
    head = re.split(r"[、。]", sent[max(0, tstart - 20):tstart])[-1]
    for nm in NUM_RE.finditer(head):
        attrs.setdefault(classify_number(nm.group(1), nm.group(2), head[:nm.start()]),
                         canon_value(nm.group(1), nm.group(2)))

    if attrs.get("amount") and action not in ("支払", "浪費"):
        needs_review = (needs_review + " / " if needs_review else "") + \
            "金額があるが支払いの動詞ではない（対象と金額の関係を確認）"

    # 連体修飾なら、その述語の主語は直後の名詞。
    # 「無料体験だけで本契約しなかった人は」を、さくらの体験にしない
    rel = RELATIVE_HEAD_RE.match(sent[vstart + len(pred):])

    subj_here = scan_subject(sent)
    if rel:
        subj, conf = "第三者", "explicit"
    elif subj_here == "情報源":
        subj, conf = "第三者", "explicit"
    elif subj_here:
        subj, conf = subj_here, "explicit"
    elif general:
        subj, conf = "第三者", "explicit"
    elif carried and carried[0] in ("さくら", "読者", "第三者"):
        subj, conf = carried[0], carried[1]
    else:
        subj, conf = "unknown", "unknown"

    # 否定でも本人の体験事実はある（私は契約しなかった）。
    # 体験でなくなるのは、必要・可能・意志・助言・条件のとき
    if in_quote:
        kind, experience = "引用", "no"
    elif general or subj == "第三者":
        kind, experience = "一般論", "no"
    elif modality in ("necessity", "possibility", "intention", "advice",
                      "prospective", "concessive", "question"):
        kind, experience = modality, "no"
    elif modality == "conditional" or tense in ("future", "conditional"):
        kind, experience = ("条件" if modality == "conditional" else "予定"), "no"
    elif atype == "調査":
        kind, experience = "調査", "no"
    elif subj == "さくら":
        kind, experience = "体験", "yes"
    elif subj == "読者":
        kind, experience = "読者の想定", "no"
    else:
        kind, experience = "体験", "possible"

    forms = ACTION_FORM.get(action, ("した", "する", "している"))
    if tense == "past":
        verb = forms[0]
    elif tense in ("future", "conditional", "present"):
        verb = forms[1]
    elif tense == "progressive":
        verb = forms[2]
    else:
        verb = pred
    if polarity == "negative":
        verb += "（否定）"

    claim = f"{target_surface}を{verb}"
    if action in ("留学", "渡航"):
        claim = f"{target_surface}へ{verb}"
    if action == "就業":
        claim = f"{target_surface}として{verb}"
    # 「英語しか使わない」を「英語を使わない」と表示すると意味が逆に読める。
    # 極性を反転させない構文なので、助詞も原文のまま出す
    if re.search(r"しか", sent[max(0, vstart - 30):vstart]):
        claim = f"{target_surface}しか{pred}"

    return {
        "claim": claim, "subject": subj, "subject_confidence": conf,
        "target_surface": target_surface, "target_normalized": target_norm,
        "normalization_type": ntype,
        "target_start": tstart, "target_end": tend,
        "action_surface": pred, "action_lemma": action_lemma,
        "action_normalized": action, "action_normalization_reason": action_reason,
        "normalization_status": normalization_status,
        "polarity": polarity, "modality": modality,
        "normalized_action": action, "original_predicate": pred,
        "act_type": atype, "target": target_surface, "value": "",
        "tense": tense, "kind": kind, "experience": experience,
        "attrs": attrs, "needs_review": needs_review,
        "quoted": "yes" if in_quote else "",
        "from_affiliate_block": "yes" if from_aff else "",
        "sentence": sent[:200], "source_text": sent,
    }


def parse_all(sent, carried=None, from_aff=False):
    """1文から命題を全部取り出す。「契約せずに比較した」は2件になる。"""
    general = bool(re.search(GENERAL_MARK, sent))
    quotes = quote_spans(sent)
    out, bad = [], []
    for cand in analyze(sent):
        r = _one(sent, cand, quotes, carried, from_aff, general)
        if not r:
            continue
        if r.get("_invalid"):
            bad.append(r["_invalid"])
            continue
        out.append(r)
    # 同じ対象×同じ行動が重複したら1つにする
    seen, uniq = set(), []
    for r in out:
        k = (r["target_surface"], r["action_normalized"], r["polarity"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq, bad


def parse(sent, carried=None, from_aff=False):
    """先頭の命題だけ返す（テスト用）。"""
    got, _ = parse_all(sent, carried, from_aff)
    return got[0] if got else None


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

    props = defaultdict(lambda: {"rows": [], "posts": [], "variants": set(),
                                 "attrs": {}, "needs_review": ""})
    broken = []   # 不変条件に違反した抽出
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
                prs, invalids = parse_all(sent, carried, from_aff)
                for msg in invalids:
                    broken.append((p["id"], msg, sent[:80]))
                for pr in prs:
                    tkey = (pr["target_normalized"]
                            if pr["normalization_type"] in ("none", "exact_alias")
                            else pr["target_surface"])
                    key = (f"{tkey}|{pr['action_normalized']}|{pr['tense']}"
                           f"|{pr['polarity']}")
                    d = props[key]
                    ctx = " ".join(ss[max(0, i - 1):i + 2])[:260]
                    d["rows"].append({**pr, "context": ctx, "html_tag": tag,
                                      "post_id": p["id"], "url": p.get("link", ""),
                                      "title": title})
                    d["variants"].add(pr["sentence"][:60])
                    for k, v in pr["attrs"].items():
                        d.setdefault("attrs", {}).setdefault(k, set()).add(v)
                    if pr["needs_review"]:
                        d["needs_review"] = pr["needs_review"]
                    if p["id"] not in d["posts"]:
                        d["posts"].append(p["id"])

    # 数値なしの命題は、数値ありの命題を包含している可能性がある。
    # 同じと断定せず、別命題として残したうえで関係だけ記録する。
    subsumes = defaultdict(list)
    for key in props:
        # 数値は属性になったので、包含関係は「時制ちがい」だけを見る
        t, a, tn, pol = key.split("|")
        for other in props:
            ot, oa, otn, opol = other.split("|")
            if ot == t and oa == a and (otn, opol) != (tn, pol):
                subsumes[key].append(other)

    ordered = sorted(props.items(), key=lambda kv: -len(kv[1]["posts"]))
    rows = []
    for i, (key, d) in enumerate(ordered, start=1):
        r0 = d["rows"][0]
        # この命題の行動。包含関係のループで使った a を読むと、
        # 全行が最後の1件の値になる（2026-08-08まで全181行が「開始」だった）
        akey = key.split("|")[1]
        claim = r0["claim"]      # 表示は行動と時制から作った文字列を使う
        rows.append({
            "claim_id": f"C{i:03d}", "claim": claim,
            "subject": r0["subject"], "subject_confidence": r0["subject_confidence"],
            "normalized_action": r0["normalized_action"],
            "original_predicate": r0["original_predicate"],
            "act": akey, "kind": r0["kind"],
            "target": r0["target_surface"],
            "target_normalized": r0["target_normalized"],
            "normalization_type": r0["normalization_type"],
            "action_surface": r0["action_surface"],
            "action_lemma": r0["action_lemma"],
            "action_normalized": r0["action_normalized"],
            "action_normalization_reason": r0["action_normalization_reason"],
            "normalization_status": r0["normalization_status"],
            "polarity": r0["polarity"], "modality": r0["modality"],
            "target_start": r0["target_start"], "target_end": r0["target_end"],
            "value": "", "tense": r0["tense"],
            "experience": r0["experience"],
            "quoted": r0["quoted"], "from_affiliate_block": r0["from_affiliate_block"],
            "attributes": " / ".join(f"{k}={'・'.join(sorted(vs))}"
                                     for k, vs in sorted(d.get("attrs", {}).items())),
            "needs_review": d.get("needs_review", ""),
            "html_tag": r0["html_tag"],
            "posts": len(d["posts"]),
            "post_ids": " ".join(str(x) for x in d["posts"][:12]),
            "urls": " ".join(sorted({x["url"] for x in d["rows"]})[:4]),
            "sentence": r0["sentence"], "context": r0["context"],
            "variants": " ／ ".join(sorted(d["variants"])[:4]),
            "subsumed_by": "",
            "setting_source": " ".join(setting_hit(r0)) or "（該当なし）",
            "needs": NEEDS.get(akey, "本人の確認"),
            "confirmation": "", "related_claims": "",
            "_key": key,
        })

    # 上位概念化・文脈補完は統合しないが、関連としては紐づける
    bynorm = defaultdict(list)
    for r in rows:
        bynorm[(r["target_normalized"], r["action_normalized"])].append(r["claim_id"])
    for r in rows:
        r["related_claims"] = " ".join(
            [c for c in bynorm[(r["target_normalized"], r["action_normalized"])]
             if c != r["claim_id"]][:6])

    idx = {r["_key"]: r["claim_id"] for r in rows}
    for r in rows:
        if r["_key"] in subsumes:
            r["subsumed_by"] = "包含: " + " ".join(idx[k] for k in subsumes[r["_key"]])
        r.pop("_key")

    # 分類が「体験」なのに experience=no は矛盾。出したら気づけるようにする
    # 以前「要確認」で見つかった記事の体験主張が、いまも取れているか
    have = {q for r in rows for q in r["post_ids"].split()}
    missing = {"282", "283", "286", "138"} - have
    # 自己テストは1本しか流さないので、そこでは回帰を見ない
    if missing and len(posts) > 10:
        print(f"⚠️ 回帰: 記事 {sorted(missing)} から命題が1件も取れていない")
    if broken:
        print(f"⚠️ 不変条件違反 {len(broken)}件:")
        for pid, msg, ex in broken[:5]:
            print(f"   [{pid}] {msg} / {ex}")

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
        ("normalization_type=generalization",
         lambda r: r["normalization_type"] == "generalization"),
        ("normalization_type=context_enrichment",
         lambda r: r["normalization_type"] == "context_enrichment"),
    ]

    def detail(r):
        out = [f"### {r['claim_id']} {r['claim']}\n\n"]
        out.append(f"- 主語: **{r['subject']}**（{r['subject_confidence']}） / "
                   f"分類: **{r['kind']}** / 体験: **{r['experience']}**\n")
        out.append(f"- 対象: **{r['target']}**（原文） / 正規化: {r['target_normalized']}"
                   f" / 変換: **{r['normalization_type']}**\n")
        out.append(f"- 行動: 原文`{r['action_surface']}` / 辞書形 {r['action_lemma']}"
                   f" / 正規化 **{r['action_normalized']}**"
                   + (f"（{r['action_normalization_reason']}）"
                      if r['action_normalization_reason'] else "") + "\n")
        out.append(f"- 時制: **{r['tense']}**\n")
        out.append(f"- 数値属性: {r['attributes'] or '—'}"
                   + (f" / ⚠️ {r['needs_review']}" if r['needs_review'] else "") + "\n")
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
