#!/usr/bin/env python3
"""
quality_rules.py
記事の品質ルールを1か所にまとめる。

生成時（article_rewriter.audit）と公開後（wp_audit）で同じ基準を使いたいが、
それぞれに正規表現を書くと片方だけ直して食い違う。実際、料金の検出は
wp_audit だけが持っていて、生成時には素通りしていた。

ここに置くのは「機械で確定できるもの」だけにする。
体験の捏造や論理の後付けは機械では判定できないので、
プロンプト側の指示と人間の目視に残す。
"""
import re

# ── 料金と基準日 ─────────────────────────────────────────────
# 料金・制度は改定される。日付が無いと、改定後は訂正ではなく虚偽になる。
# ただし「1円も残らなかった」のような修辞は料金ではないので拾わない。
PRICE_RE = re.compile(
    # 「月額1,848円」「受講料は25万円」のように、価格を指す語のあとに来る額
    r"(?:月額|年額|税込|税抜|料金|価格|受講料|授業料|総額|費用|月)"
    r"[はがのも、\s]{0,3}[0-9０-９][0-9０-９,，\.]*\s*万?円"
    # 「5,980円／月」のように単位が後ろに付く形
    r"|[0-9０-９][0-9０-９,，\.]*\s*万?円\s*(?:／|/)\s*(?:月|年|回|人)"
    # 桁区切りのある具体額（171,600円）。修辞では出てこない書き方
    r"|[0-9０-９]{1,3}(?:[,，][0-9０-９]{3})+\s*円"
)

BASEDATE_RE = re.compile(
    r"20[0-9]{2}年\s*[0-9]{1,2}\s*月.{0,6}時点"
    r"|20[0-9]{2}[-/][0-9]{1,2}[-/][0-9]{1,2}\s*時点"
)

# ── 根拠を超える断定 ─────────────────────────────────────────
# 「調べて書いている当事者」であって専門家ではない。言い切れないことを
# 言い切ると、読者への実害になるうえ景表法にも近づく。
# 日常的に使う「必ず」「絶対」単体は入れない。誤検知で原稿を弾いても意味がない。
HYPE = (
    "本当の原因", "唯一の方法", "唯一の答え", "間違いなく", "100%確実",
    "誰でも必ず", "絶対に伸びる", "必ず伸びる", "確実に伸びる", "誰でも話せる",
)

# ── 制度・数値の主張。出典が要る種類の話 ─────────────────────
# これらの語が出てくる記事は、一次情報の確認日を書いていないと危ない。
INSTITUTIONAL = (
    "ビザ", "ワーキングホリデー", "年齢制限", "在学", "卒業要件",
    "協定", "上限年齢", "申請条件",
)

# ── アフィリエイトの誠実さ ───────────────────────────────────
# 良いことだけ書いた紹介は、読者にとって判断材料にならない。
# 「合わない人」か「注意点」が最低1つ要る。
CAVEAT = (
    "向いていない", "向かない", "合わない", "おすすめしない", "注意点",
    "デメリット", "ただし", "弱点", "見送", "避けたほうが",
)

AFFILIATE_LINK_RE = re.compile(r"af\.moshimo\.com/af/c/click|px\.a8\.net/svt/ejp")

# ── さくら個人の、実現しない予定 ──────────────────────────
# 「30歳までに必ず行く」「あと3年」のような、本人の進行中の計画を
# 記事の芯に置くと、時間が経ったときに説明できなくなる。
# 焦りは読者自身の問題として扱う（×私はあと3年 ○年齢条件がある選択肢を逃したくない）。
# 過去の体験（3日でやめた・4.5万溶かした）は残してよい。消すのは未来の宣言だけ。
PERSONAL_PLAN = re.compile(
    r"(?:30歳|三十歳)(?:まで|になる前)に(?:は)?[^。]{0,12}(?:必ず|絶対|きっと)"
    r"|私は[^。]{0,10}(?:必ず|絶対)[^。]{0,8}(?:行く|出発|渡航|申請する)"
    r"|(?:あと|残り)\s*[0-9]\s*年(?:しかない|で(?:期限|タイムリミット))"
    r"|来年(?:こそ|は)私(?:は|が)[^。]{0,12}(?:行く|出発|渡航)"
    r"|今年中に[^。]{0,10}(?:必ず|絶対)[^。]{0,8}(?:行く|出発|渡航)"
)


def personal_plan(text):
    """さくら本人の、実現しない予定の宣言を返す。**未来の宣言だけ**を見る。

    体験（experience_claim）とも、制度情報（time_sensitive_fact）とも別物。
    混ぜると「3日でやめた」まで消してしまう。
    """
    m = PERSONAL_PLAN.search(text)
    return m.group(0).strip() if m else None


# ── 体験の主張 ──────────────────────────────────────────
# 運営者が実際にやったことだけ「使った」「試した」と書ける。
# 使っていないサービスに体験表現を付けたら、それは捏造。
# どのサービスを実際に使ったかは機械には分からないので、
# workspace/experience.csv に人が書く。書いていないサービスに
# 体験表現が付いていたら報告する（自動で消さない。判断は人がする）。
EXPERIENCE_VERBS = (
    "使った", "使ってみた", "試した", "続けた", "受けた", "通った",
    "申し込んだ", "契約した", "解約した", "払った", "受講した",
    "使って分かった", "体験した", "自腹",
)
EXPERIENCE_PATH = "affiliate-research-engine/playbook/workspace/experience.csv"


def _used_services():
    """実際に使ったサービス名の一覧。ファイルが無ければ空。"""
    import csv
    import os
    if not os.path.exists(EXPERIENCE_PATH):
        return None          # 未整備。判定しない（誤検知で原稿を弾かない）
    names = set()
    with open(EXPERIENCE_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(l for l in f if not l.startswith("#")):
            if (row.get("used") or "").strip().lower() in ("yes", "y", "true", "1"):
                names.add((row.get("service") or "").strip())
    return {n for n in names if n}


def experience_claims(text, service_names):
    """体験表現が付いているのに、実際には使っていないサービスを返す。

    service_names … その記事が触れている案件名のリスト（呼び出し側が渡す）。
    実使用リストが未整備なら None を返し、判定しない。
    """
    used = _used_services()
    if used is None:
        return None
    hits = []
    for name in service_names:
        if not name or name in used:
            continue
        # サービス名の前後60字に体験表現があるか
        for m in re.finditer(re.escape(name), text):
            around = text[max(0, m.start() - 60):m.end() + 60]
            for v in EXPERIENCE_VERBS:
                if v in around:
                    hits.append((name, v, around.strip()[:80]))
                    break
    return hits


# ── 時限情報（制度・ビザ・年齢条件・料金）────────────────
# 「ワーホリの年齢上限は30歳」は、国・国籍・いつ時点かで変わる。
# 一般化して書くと、personal_plan は通っても事実として危ない。
# **対象国／確認日／出典**が揃っている場合だけ通す。
COUNTRY = ("オーストラリア", "豪州", "カナダ", "ニュージーランド", "イギリス", "英国",
           "アイルランド", "フランス", "ドイツ", "韓国", "台湾", "シンガポール",
           "フィリピン", "アメリカ", "米国", "スペイン", "イタリア", "ポーランド",
           "デンマーク", "ノルウェー", "オランダ", "オーストリア", "チェコ",
           "ハンガリー", "ポルトガル", "スロバキア", "アイスランド", "リトアニア",
           "スウェーデン", "エストニア", "ウルグアイ", "アルゼンチン", "チリ")
SOURCE = ("外務省", "大使館", "領事館", "移民局", "公式サイト", "公式ページ",
          "公表", "https://", "http://")
# 制度の数値を断定している形。ここに引っかかったものだけ厳しく見る
INSTITUTIONAL_CLAIM = re.compile(
    r"(?:年齢(?:制限|上限)|上限年齢|申請条件|ビザ|査証|滞在期間|就労|在学|卒業要件)"
    r"[^。]{0,40}?(?:[0-9０-９]{1,2}\s*歳|[0-9０-９]{1,2}\s*(?:年|ヶ月|か月|週間))")


def time_sensitive_fact(text):
    """制度・条件を断定しているのに、国・確認日・出典が揃っていない箇所を返す。

    3つのうち1つでも欠けたら報告する。読者が実際に申請するときに
    条件が違っていたら実害が出るため、料金より厳しく見る。
    """
    m = INSTITUTIONAL_CLAIM.search(text)
    if not m:
        return None
    missing = []
    if not any(c in text for c in COUNTRY):
        missing.append("対象国")
    if not BASEDATE_RE.search(text):
        missing.append("確認日")
    if not any(sform in text for sform in SOURCE):
        missing.append("出典")
    if not missing:
        return None
    return f"{m.group(0).strip()[:40]}（{'・'.join(missing)}がない）"


def strip_tags(html):
    """タグを空白で置き換える。詰めて消すと別セルの数字が繋がって偽の金額になる
    （<td>5</td><td>980円</td> → 5980円）。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def price_without_basedate(text):
    """料金を書いているのに基準日が無ければ、その料金表記を返す。"""
    if BASEDATE_RE.search(text):
        return None
    m = PRICE_RE.search(text)
    return m.group(0).strip() if m else None


def hype_words(text):
    """根拠を超える断定を列挙する。"""
    return [w for w in HYPE if w in text]


def institutional_without_source(text):
    """制度の話をしているのに、確認日も出典も無ければ True。

    「2026年8月時点」という基準日か、URL・省庁名のような出典があればよい。
    """
    if not any(k in text for k in INSTITUTIONAL):
        return False
    if BASEDATE_RE.search(text):
        return False
    return not re.search(r"https?://|外務省|大使館|公式サイト|公式ページ", text)


def missing_caveat(html, text):
    """アフィリエイトリンクがあるのに、合わない人も注意点も書いていなければ True。"""
    if not AFFILIATE_LINK_RE.search(html):
        return False
    return not any(w in text for w in CAVEAT)


def lone_numbers(text):
    """比較の相手がいない数字だらけになっていないかの目安を返す。

    「32万円」だけ置くのと「32万円で授業117時間」では読者の判断材料が違う。
    厳密な判定は無理なので、記事全体で数字が2つ未満なら薄いと見なす程度にする。
    """
    return len(set(re.findall(r"[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?", text)))
