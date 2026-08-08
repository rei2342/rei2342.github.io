#!/usr/bin/env python3
"""
article_rewriter.py
Rewrites WordPress articles with unique structures per topic,
adds affiliate links, fixes 漢数字, and generates a change report.
"""
import os, sys, time, re, json
from pathlib import Path
import requests, anthropic
import urllib3
urllib3.disable_warnings()

WP_BASE  = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER  = "rei.00pt2342@gmail.com"
WP_PASS  = os.environ.get("WP_APP_PASSWORD", "")
CLAUDE   = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
DRY_RUN  = os.environ.get("DRY_RUN", "true").lower() == "true"
OUT_DIR  = Path("affiliate-research-engine/playbook/workspace/rewrites")

TARGET_IDS = [27, 67, 64, 61, 19, 18, 32, 42, 40, 41, 37, 33, 28, 23]

# 環境変数 TARGET_IDS で対象を上書きできる（例: "292,289,286"）。
# フェーズごとに対象を切り替えて流すため。
if os.environ.get("TARGET_IDS", "").strip():
    TARGET_IDS = [int(x) for x in os.environ["TARGET_IDS"].replace(" ", "").split(",") if x]

MODEL = os.environ.get("REWRITE_MODEL", "claude-opus-4-8")
MIN_CHARS = int(os.environ.get("MIN_CHARS", "4000"))

# ── Affiliate links（affiliate_inserter.py を単一の情報源として参照）──────────
# 却下・未承認の案件を混入させないため、リンク表とトピック分類はこちらに一本化する。
sys.path.insert(0, str(Path(__file__).parent))
import affiliate_inserter as _ai
import quality_rules as _q

LINKS      = {k: v[1] for k, v in _ai.LINKS.items()}
LINK_NAMES = {
    "speek": "speek（発音矯正）",
    "sptr": "スパトレ",
    "dmm": "DMM英会話",
    "phil_navi": "フィリピン留学ナビ",
    "cebridge": "CEBRIDGE",
    "ugaku": "U-GAKU（国内留学）",
    "johokan": "留学情報館",
    "nativecamp_ryugaku": "ネイティブキャンプ留学",
    "qq_english": "QQ English",
    "nativecamp": "ネイティブキャンプ",
    "rarejob": "レアジョブ英会話",
    "sapuri_nichijo": "スタディサプリENGLISH 新日常英会話コース",
    "sapuri_setplan": "スタディサプリENGLISH 新日常英会話セットプラン",
}

TOPIC_PROGRAMS = {k: list(v) for k, v in _ai.TOPIC_MAP.items()}



# ── Structure types ───────────────────────────────────────────────────────────
STRUCTURES = {
    "toeic": """**スコア実験記録型**
「27歳・TOEIC3回分のスコア変化を記録して見えたこと」一次記録形式。
月別スコア・具体的な失敗シーン・気づきを軸に展開。上位記事批判は最小限に。""",

    "coaching": """**診断分岐型**
「英語コーチングが向いている人・向いていない人」診断的入口で始める。
「向いていない人」を先に出す逆説で引きつけ、向いている人の条件を絞り込む。""",

    "hours_2000": """**時間配分解剖型**
「2000時間の使い方で到達点が3倍変わる話」数字軸で展開。
時間の量より質（何に使うか）を可視化する形式。""",

    "work_english": """**職務文設計型**
「営業事務が実際に詰まる10場面と、そこで使う英文の作り方」シナリオ分岐形式。
抽象的英語力論より具体的な職務文の反復設計を軸に。""",

    "habit": """**摩擦設計型**
「続かない理由を摩擦コストの収支表で解剖する」形式。
心理論ではなく設計問題として扱い、摩擦の種類別に削り方を提示する。""",

    "philippines": """**比較検証型**
「フィリピン留学を真剣に検討した2ヶ月で比較した5校の記録」形式。
費用・授業・英語効果を具体的な数字で比較して展開する。""",

    "agent_general": """**決断強制型**
「この3タイプの人はエージェント比較を続けるべきではない」逆説的入口で始める。
比較行為のコスト（時間・年齢消費）をワーホリ年齢制限と掛け合わせて可視化する。""",

    "agent_free": """**インセンティブ解剖型**
「エージェントのKPIを分解すると見えること」財務的切り口で始める。
報酬発生点・スコープ外・成果側の空白を数字で可視化する形式で展開。""",

    "cost": """**機会費用試算型**
「行かなかった5年の費用を計算すると怖い話」逆算的入口で始める。
機会費用（失う給与）を具体的な数字で可視化し、先送りのコストを表に出す。""",

    "default": """**問題解体型**
よくある解決策を一つずつ「なぜ効かないか」で解体し、
本当に機能する一手を最後に提示する形式で書く。""",
}

# ── 漢数字 fix ─────────────────────────────────────────────────────────────────
KANJI_MAP = [
    (r'三十歳', '30歳'), (r'二十七歳', '27歳'), (r'二十五歳', '25歳'),
    (r'二十歳', '20歳'), (r'二十代', '20代'), (r'三十代', '30代'),
    (r'三十万', '30万'), (r'二十五万', '25万'), (r'二十万', '20万'),
    (r'百二十万', '120万'), (r'百八十万', '180万'), (r'三百万', '300万'),
    (r'百万', '100万'), (r'四万五千円', '4万5千円'),
    (r'三ヶ月', '3ヶ月'), (r'六ヶ月', '6ヶ月'), (r'三か月', '3か月'),
    (r'六か月', '6か月'), (r'一ヶ月', '1ヶ月'), (r'二ヶ月', '2ヶ月'),
    (r'五年間', '5年間'), (r'三年間', '3年間'), (r'二年間', '2年間'),
    (r'一年間', '1年間'), (r'五年', '5年'), (r'三年', '3年'),
    (r'二年', '2年'), (r'一年', '1年'), (r'半年間', '6ヶ月間'),
    (r'二千時間', '2000時間'), (r'一千時間', '1000時間'),
    (r'二百時間', '200時間'), (r'三百時間', '300時間'),
]

# 助数詞つきの漢数字を機械的にアラビア数字へ直す。
# 「分」は「十分（じゅうぶん）」と「10分」の区別がつかないので対象外。
# 「人」は「一人で」が自然な日本語なので対象外。どちらも監査側でも見逃す。
_K_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9}
_COUNTERS = ("時半", "時", "月", "日", "歳", "年", "回", "割", "週間",
             "ページ", "点", "個", "万", "円", "ヶ月", "か月", "パーセント", "分")
_K_RE = re.compile(r"([一二三四五六七八九十百千]+)(" + "|".join(_COUNTERS) + ")")
# 数詞ではなく慣用句として使われるもの（変換すると不自然になる）。
# 「十分」だけは「じゅうぶん」と「10分」の判別がつかないので必ず素通しする。
# 「一時」は「いっとき」と「1時」、「十分」は「じゅうぶん」と「10分」の
# 区別が文脈なしにはつかない。壊すより素通しするほうが害が小さい。
_K_SKIP = {"十分", "一時", "一時的", "一点張り", "一年生", "一日中", "百点満点"}


def _k2i(s):
    """漢数字の文字列を整数にする（千の位まで）。読めなければ None。"""
    total, section, digit = 0, 0, 0
    for ch in s:
        if ch in _K_DIGIT:
            digit = _K_DIGIT[ch]
        elif ch in ("十", "百", "千"):
            unit = {"十": 10, "百": 100, "千": 1000}[ch]
            section += (digit or 1) * unit
            digit = 0
        else:
            return None
    total = section + digit
    return total or None


def fix_kanji(text):
    # 短い語を先に当てると長い語を壊す（「百二十万」に「二十万」が先に当たって
    # 「百20万」になっていた）。必ず長いパターンから適用する。
    for pat, rep in sorted(KANJI_MAP, key=lambda kv: -len(kv[0])):
        text = re.sub(pat, rep, text)

    def repl(m):
        whole = m.group(0)
        if any(whole.startswith(s) or s.startswith(whole) for s in _K_SKIP):
            return whole
        n = _k2i(m.group(1))
        return f"{n}{m.group(2)}" if n is not None else whole

    return _K_RE.sub(repl, text)

def strip_html(html):
    return re.sub(r'<[^>]+>', '', html)

def classify(title, content_snippet):
    """affiliate_inserter と同じ分類を使う。

    classify() はタイトルのキーワードで判定するが、2026-08-02に
    タイトルを「短い一人称＋数字」型へ書き換えた結果、判定に使う語
    （フィリピン・ワーホリ等）がタイトルから消えた。
    既定値に落ちたら本文で判定し直す。ここを誤ると構成タイプも
    アフィリエイト案件も間違ったものが入る。
    """
    return _ai.classify_full(title, content_snippet or "")


def existing_links(content):
    """本文に既に入っている案件を検出する（リンク重複を避けるため）。"""
    found = set()
    for key, html in LINKS.items():
        m = re.search(r'a_id=(\d+)', html) or re.search(r'a8mat=([A-Z0-9+]+)', html)
        if m and m.group(1) in content:
            found.add(key)
    return found


def build_link_block(programs, already_present=None):
    """挿入すべきリンクを列挙する。

    以前は「元の本文にリンクがあれば重複を避けてテキストのみ言及」と
    指示していたが、リライトは本文を丸ごと作り直すので元のリンクは
    残らない。その結果、リンクが1本も入らない記事ができていた
    （289・288が該当）。全面書き換えである以上、毎回入れさせる。
    """
    lines = []
    for prog in programs[:3]:
        lines.append(
            f"- {LINK_NAMES[prog]}: 本文で言及した直後にこのHTMLをそのまま挿入:\n  {LINKS[prog]}")
    return "\n".join(lines)

def rewrite(title, content_html, topic, retry_issues=None):
    structure  = STRUCTURES.get(topic, STRUCTURES["default"])
    programs   = TOPIC_PROGRAMS.get(topic, ["speek"])
    already    = existing_links(content_html)
    link_block = build_link_block(programs, already)
    snippet    = strip_html(content_html)[:2000]

    # 目標字数からH2の本数と1セクションあたりの分量を逆算して示す。
    # 「N字以上」とだけ言うと届かないので、達成できる割り方を渡す。
    h2_hint = "4〜6" if MIN_CHARS <= 5000 else "6〜7"
    per_h2 = MIN_CHARS // (5 if MIN_CHARS <= 5000 else 6)

    prompt = f"""以下の記事を完全にリライトしてください。

タイトル（変更禁止）: {title}
構成タイプ: {structure}

現在の記事の要旨（参考のみ・構成をそのままコピーしないこと）:
{snippet}

## 要件
1. **タグを除いた本文が{MIN_CHARS}字以上**のHTML（<h2>/<h3>/<p>/<hr>タグのみ）。
   これは下限であって目安ではない。**{MIN_CHARS}字に届かない原稿は不合格**として弾かれる。
   H2を{h2_hint}本立て、各H2の中身を{per_h2}字前後にすれば自然に届く。
   薄いまま終わらせず、各セクションに「実際の場面の描写」「具体的な数字」「読者が今日できる手順」を入れて厚みを出すこと
2. **現在の記事と異なるH2テーマ**を使う
3. さくらのエピソードは現在の記事と**別のシーン・別の失敗**を使う
4. **数字はすべてアラビア数字**。漢数字は一切使わない。
   時刻も日付も回数も同じ（×木曜の夜十時半 ○木曜の夜22時半／×五月 ○5月／
   ×三回 ○3回／×一日 ○1日／×十分 ○10分／×二十五分 ○25分／×九割 ○9割）
5. **さくら本人の一人称で書く**。「田中さくらは〜した」のように外から名前で描写しない。
   一人称は「私」。三人称の地の文が1箇所でもあると視点が壊れる
6. アフィリエイトリンク:
{link_block}

## ★読者が判断に使えるものを渡す（2026-08-06追加）
感情だけの体験談にも、人格のないSEO解説にも寄せない。「調べて動いた当事者の記録」にする。
- **記事に1つ、読者が持ち帰る判断基準を置く**。「◯◯が大事」ではなく、次に見る場所を渡す。
  例:「留学先は国名より1日の会話コマ数で見る」「費用は総額ではなく1会話時間あたりで見る」
- **数字を単独で置かない**。必ず比較の相手とセットにする。
  ×「4週間で32万円」 ○「4週間で32万円、授業は117時間。1時間あたり2700円」
  「高い・安い・早い・効果的」と書くときは、何と比べてそう言えるのかを必ず添える
- **料金・制度・年齢条件・研究結果は、書くなら『2026年◯月◯日時点』と確認日をセットにする**。
  制度は政府・大使館、料金と授業内容は公式サイト、学習時間の目安は試験団体の公表値を優先する。
  確認できない事実は書かない。目安（約200時間など）を全員に必要な確定値として扱わない
- **推測は推測として書く**。「〜の可能性がある」「私はこう判断した」と、事実と区別する
- **禁止する断定**: 「本当の原因」「唯一の方法」「間違いなく」「誰でも必ず」「絶対に伸びる」。
  機械で検出して不合格にする

## ★アフィリエイトの置き方
- 先に読者の課題と判断基準を確定し、**その条件に合う場合だけ**案件を出す。
  商品を結論に決めてから根拠を後付けしない
- 商品名を出す前に「なぜその機能が要るのか」を1行で書く
- **合わない人か注意点を最低1つ書く**。良いことだけの紹介は判断材料にならない（機械で検査する）
- さくらが実際に使っていないサービスは、**利用体験を装わない**。
  「調べた」「候補に入れた」「問い合わせた」と、事実の粒度で書く
- 読者に取ってほしい次の行動は1つに絞る

## ★AIっぽさ排除（既存53本の実測から策定・最優先で守る）
既存記事を計測したら、53本すべてが同じ語彙・同じ骨格でできていた。これが最大の弱点。
- **「ではなく」「〜のほうだ」は記事全体で3回まで**（既存は1本あたり平均11回、最多22回だった）。
  これが最も直りにくい癖なので、書き終えたら**自分で数えて**、超えていたら下のように言い換えてから出力する:
  「AではなくB」→「Aより先にB」「Aだけでは足りない。B」「Aに見えてB」「Aと思っていた。実際はB」
  「Bのほうだ」→「効くのはBだ」「問題はBにある」「本当に要るのはB」
  そもそも対比で書かず、**具体的な場面・行動・数字をそのまま描写する**のが一番いい。
  「〇〇ではなく△△が大事」と書きたくなったら、△△を実際にやっている場面を1つ描写して済ませる
- **「設計」「構造」「物差し」「本質」は各1回まで**（既存は「設計」が1本で最多22回）
- **『「〈検索キーワード〉」で検索する人は…』という書き出しを使わない**（既存は49/53本がこの型）。
  情景・数字・体験の一場面から始める。読者がいる具体的な場面を1行目に置く
- **H2の本数を固定しない。内容に応じて4〜7本で決める**（既存は3本か6本の2種類しかなかった）。
  H3の数も各H2で揃えず、必要な数だけ置く
- 見出しに「H2-1｜」のような**採番ラベルを付けない**
- **スクールで4.5万円溶かした話は記事全体で1回まで**（全記事共通のプロフィールなので使い回すと同じ顔になる）
- **「上位記事はXと言うが本当はYだ」という論法だけで押し切らない**。
  体験ログ型・比較検証型・失敗告白型・手順型・**体験×検証型**など、記事ごとに骨格そのものを変える。
  体験×検証型を選ぶ場合はこの順で書く:
  ①さくらが迷った具体的な場面 →②世間の定説かサービス側の訴求 →③費用・期間・学習時間・条件を
  一次情報で調べる →④単位を揃えて比較する →⑤定説が当てはまる人と当てはまらない人を分ける
  →⑥さくら自身が選んだ順番か次の一歩
- 「つまり」「結局」「一行も」「そのものが」を多用しない
- 同じ段落構造（短い断定→逆接→言い換え）を繰り返さない。段落の長さに緩急をつける

HTMLのみ出力。前置き・説明・```マーカー不要。"""

    if retry_issues:
        prompt += (
            "\n\n## 直前の生成は以下の理由で不合格だった。今度は必ず守ること\n"
            + "\n".join(f"- {i}" for i in retry_issues)
            + "\n\n特に対比構文（ではなく/のほうだ）は機械的に数えられて判定される。"
            "書き終えたあとに自分で全文を走査して該当箇所を数え、上限を超えていたら"
            "上に挙げた言い換え、または具体的な場面描写に置き換えてから出力すること。"
        )

    msg = CLAUDE.messages.create(
        model=MODEL,
        max_tokens=16000,
        system="アフィリエイトブログ「sakura-eigo.com」ライター。ペルソナ: 田中さくら/27歳/営業事務/東京/英語5年後回し/スクール失敗4.5万/30歳タイムリミット。NG: 「〜について」禁止/箇条書き逃げ禁止/同語尾3連続禁止/冒頭挨拶禁止/漢数字禁止/誇大虚偽禁止/「——」(emダッシュ)禁止。視点は必ずさくら本人の一人称「私」（「田中さくらは〜」と外から書かない）。漢数字は時刻・日付・回数も含め一切使わずアラビア数字（○22時半・5月・3回・25分・9割）。★AIっぽさ排除を最優先: 「ではなく」「〜のほうだ」は記事全体で3回まで、「設計」「構造」「物差し」「本質」は各1回まで、検索キーワードのかぎ括弧で書き出さない、H2の本数を固定せず内容に応じて4〜7本、4.5万円のスクール失敗談は1回まで、「上位記事はXと言うが本当はYだ」の論法だけで押し切らない。",
        messages=[{"role": "user", "content": prompt}]
    )
    result = msg.content[0].text.strip()
    result = re.sub(r'^```html?\n?', '', result)
    result = re.sub(r'\n?```$', '', result)
    return fix_kanji(result)

def audit(html):
    """生成物がAIっぽさ排除ルールを守れているか検査する。
    守れていない項目を文字列のリストで返す（空なら合格）。"""
    # CTAボックスは全記事共通の定型文なので、文体の検査対象から外す。
    # 箱の中の「さくらが確かめた・次の一手」を三人称と誤検知していた。
    text = strip_html(_ai.strip_box(html))
    issues = []

    # 対比構文は密度で測る。旧記事は390字に1回という異常な密度だった。
    # 1000字に1回（最低3回は許容）なら日本語として自然な範囲に収まる。
    n = text.count("ではなく") + text.count("のほうだ")
    limit = max(3, len(text) // 1000)
    if n > limit:
        issues.append(f"対比構文が{n}回（{len(text)}字なので上限{limit}）")

    for w in ("設計", "構造", "物差し", "本質"):
        c = text.count(w)
        if c > 1:
            issues.append(f"「{w}」が{c}回（上限1）")

    c = text.count("4.5万") + text.count("4万5千")
    if c > 1:
        issues.append(f"スクール失敗談が{c}回（上限1）")

    h2 = len(re.findall(r"<h2", html))
    if not 4 <= h2 <= 7:
        issues.append(f"H2が{h2}本（4〜7本の範囲外）")

    first = re.search(r"<p>(.+?)</p>", html, re.DOTALL)
    if first and strip_html(first.group(1)).lstrip().startswith("「"):
        issues.append("検索キーワードのかぎ括弧で書き出している")

    if re.search(r"<h[23][^>]*>\s*H\d", html):
        issues.append("見出しに採番ラベルが付いている")

    if "——" in text:
        issues.append("emダッシュが混入")

    # 漢数字。KANJI_MAPは決まった語しか置換できないので、残りをここで検出する。
    # fix_kanji で機械変換した後の取りこぼしを拾う。
    # 「分（十分＝じゅうぶん）」「人（一人で）」「本・点（一本/一点）」は
    # 慣用と数詞の区別がつかないので検査対象から外す。
    kanji = [
        m for m in re.findall(
            r"[一二三四五六七八九十百千]+(?:時半|時|月|日|歳|年|回|割|週間"
            r"|ページ|個|万|円|ヶ月|か月|パーセント)", text)
        if m not in _K_SKIP  # 「一時（いっとき）」等は数詞と判別できないので数えない
    ]
    if kanji:
        issues.append(f"漢数字が{len(kanji)}件（例: {'・'.join(sorted(set(kanji))[:5])}）")

    # 視点。さくら本人の一人称記事なので、外から名前で描写してはいけない。
    third = re.findall(r"(?:田中)?さくら(?:は|が|の|も|に|を)", text)
    if third:
        issues.append(f"三人称視点が{len(third)}件（さくら本人の一人称で書く）")

    if len(text) < MIN_CHARS * 0.85:
        issues.append(f"本文{len(text)}字（目標{MIN_CHARS}字に対して不足）")

    # 収益導線が無い記事を作っても意味がないので、リンクの有無も見る。
    links = len(re.findall(r"af\.moshimo\.com/af/c/click|px\.a8\.net/svt/ejp", html))
    if links == 0:
        issues.append("アフィリエイトリンクが1本も入っていない")

    # ── ここから下は公開後の点検（wp_audit）と同じ基準を使う ──
    # 以前は料金の基準日を週次点検でしか見ておらず、生成時は素通りしていた。
    # 公開してから直すより、作った時点で弾くほうが安い。
    qtext = _q.strip_tags(_ai.strip_box(html))

    price = _q.price_without_basedate(qtext)
    if price:
        issues.append(f"料金（{price}）があるのに基準日がない")

    hype = _q.hype_words(qtext)
    if hype:
        issues.append(f"根拠を超える断定: {'・'.join(hype)}")

    if _q.institutional_without_source(qtext):
        issues.append("制度・年齢条件の話があるのに確認日も出典もない")

    if _q.missing_caveat(html, qtext):
        issues.append("案件を紹介しているのに、合わない人も注意点も書いていない")

    if _q.lone_numbers(qtext) < 2:
        issues.append("判断材料になる数字が2つ未満")

    plan = _q.personal_plan(qtext)
    if plan:
        issues.append(f"さくら個人の実現しない予定がある（{plan}）。読者の悩みとして書く")

    tsf = _q.time_sensitive_fact(qtext)
    if tsf:
        issues.append(f"制度の断定に根拠が足りない: {tsf}")

    for e in _q.experience_claims(qtext)[:3]:
        issues.append(f"体験表現が台帳と合わない: {e}")

    return issues


def get_post(post_id):
    r = requests.get(f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        headers={"User-Agent": "Mozilla/5.0"}, verify=False)
    return r.json() if r.status_code == 200 else None

def update_post(post_id, content):
    r = requests.post(f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"content": content},
        headers={"User-Agent": "Mozilla/5.0"}, verify=False)
    return r.status_code in (200, 201)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = [f"# Article Rewrite Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]

    for post_id in TARGET_IDS:
        print(f"\n[{post_id}] Fetching...")
        post = get_post(post_id)
        if not post:
            print(f"  ✗ Fetch failed"); report.append(f"- [{post_id}] FETCH FAILED\n"); continue

        title   = post["title"]["rendered"]
        content = post["content"]["rendered"]
        topic   = classify(title, strip_html(content))

        print(f"  {title}  →  topic={topic}")
        try:
            new_content = rewrite(title, content, topic)
        except Exception as e:
            print(f"  ✗ Rewrite error: {e}"); report.append(f"- [{post_id}] {title} — ERROR: {e}\n"); continue

        # AIっぽさ検査。落ちたら指摘を渡して1回だけ書き直させる。
        issues = audit(new_content)
        if issues:
            print(f"  ! 検査NG: {' / '.join(issues)} → 再生成")
            try:
                new_content = rewrite(title, content, topic, retry_issues=issues)
                issues = audit(new_content)
            except Exception as e:
                print(f"  ✗ 再生成エラー: {e}")

        out = OUT_DIR / f"{post_id}_{topic}.html"
        # 分類が変わると別名のファイルができ、古い分類のものが残る。
        # 名前順で拾うと古い方を反映してしまうので、1記事1ファイルに保つ。
        for stale in OUT_DIR.glob(f"{post_id}_*.html"):
            if stale != out:
                stale.unlink()
                print(f"  - 旧分類のファイルを削除: {stale.name}")
        out.write_text(f"<!-- {post_id} | {title} | {topic} -->\n" + new_content)
        print(f"  ✓ Saved {out.name}")

        if issues:
            # 2回試して基準未達のものはWPに触らせない（劣化を防ぐ）
            print(f"  ✗ 検査NGのまま: {' / '.join(issues)} — WP更新をスキップ")
            report.append(f"- [{post_id}] {title} ({topic}) — SKIPPED 検査NG: {' / '.join(issues)}\n")
            time.sleep(8)
            continue

        print("  ✓ 検査OK")

        if not DRY_RUN:
            ok = update_post(post_id, new_content)
            status = "✓ UPDATED" if ok else "✗ WP FAILED"
        else:
            status = "DRY RUN"

        report.append(f"- [{post_id}] {title} ({topic}) — {status}\n")
        print(f"  {status}")
        time.sleep(8)

    # Note impact (Track A = 転職, Track B = 英語/留学 → no overlap expected)
    report.append("\n## noteへの影響\nsakura-eigo.com は Track B（英語/留学）専用。Track A（転職/キャリア）のnote資産との内容重複なし。影響なし。\n")
    # アイキャッチ: titles are not changed, so no アイキャッチ update needed
    report.append("\n## アイキャッチ更新\nタイトル（WP title フィールド）は変更しないため、アイキャッチ更新は不要。\n")

    (OUT_DIR / "REPORT.md").write_text("".join(report))
    print("\n✓ Done. Report saved.")

if __name__ == "__main__":
    main()
