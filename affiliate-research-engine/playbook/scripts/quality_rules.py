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
# ただし「使った」だけでは粗すぎる。無料体験を2回しただけのサービスに
# 「3ヶ月使った」「4.5万円払った」と書けてしまう。
# 台帳には期間・金額・実際にしたことまで登録し、**その範囲を超えたら警告**する。
#
# 空欄と、台帳に無いサービスは unknown として扱う（スキップしない）。
EXPERIENCE_VERBS = (
    "使った", "使ってみた", "試した", "続けた", "受けた", "通った",
    "申し込んだ", "契約した", "解約した", "払った", "受講した",
    "使って分かった", "体験した", "自腹", "始めた", "やってみた",
    "試してみ", "使ってみ", "受けてみ", "続けてみ", "登録した", "無料体験",
)
EXPERIENCE_CSV = "affiliate-research-engine/playbook/workspace/experience.csv"
FACTS_CSV = "affiliate-research-engine/playbook/workspace/experience_facts.csv"

# 記事に出てくるサービス名。台帳のキーと揃える
SERVICE_NAMES = (
    "speek", "スパトレ", "DMM英会話", "ネイティブキャンプ留学", "ネイティブキャンプ",
    "QQ English", "レアジョブ英会話", "スタディサプリ", "スタサプ",
    "Notta Memo", "Notta", "U-GAKU", "留学情報館", "フィリピン留学ナビ", "CEBRIDGE",
)


def _read_csv(path):
    import csv
    import os
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(l for l in f if not l.lstrip().startswith("#")))


def load_experience():
    """サービス名 → 台帳の1行。台帳に無いものは呼び出し側で unknown 扱いにする。"""
    return {(r.get("service") or "").strip(): r
            for r in _read_csv(EXPERIENCE_CSV) if (r.get("service") or "").strip()}


def _months(start, end):
    """登録された利用期間を月数で返す。読めなければ None。"""
    m1 = re.match(r"(20\d{2})-(\d{1,2})", (start or "").strip())
    if not m1:
        return None
    if (end or "").strip().lower() in ("ongoing", "継続中"):
        return 999
    m2 = re.match(r"(20\d{2})-(\d{1,2})", (end or "").strip())
    if not m2:
        return None
    return (int(m2.group(1)) - int(m1.group(1))) * 12 + int(m2.group(2)) - int(m1.group(2)) + 1


def experience_claims(text):
    """体験表現の使い方が台帳と合っているかを見る。問題を文字列で返す。

    自動修正はしない。監査一覧に出して、人が判断する。
    """
    ledger = load_experience()
    issues = []
    for name in SERVICE_NAMES:
        for m in re.finditer(re.escape(name), text):
            around = text[max(0, m.start() - 70):m.end() + 70]
            verb = next((v for v in EXPERIENCE_VERBS if v in around), None)
            if not verb:
                continue

            row = ledger.get(name)
            status = ((row or {}).get("status") or "").strip().lower()

            if not row:
                issues.append(f"{name}に体験表現「{verb}」。台帳に無い（unknown）")
                break
            if status in ("", "unknown"):
                issues.append(f"{name}に体験表現「{verb}」。台帳が未記入（unknown）")
                break
            if status == "not_used":
                issues.append(f"{name}は未使用なのに体験表現「{verb}」。"
                              "「調べた」「比較した」「候補にした」へ直す")
                break

            # used。登録した範囲を超えていないか
            paid = re.sub(r"[^0-9]", "", (row.get("amount_paid") or ""))
            if paid:
                for am in re.finditer(r"([0-9][0-9,]*)\s*(万?)円", around):
                    v = int(am.group(1).replace(",", "")) * (10000 if am.group(2) else 1)
                    if v > int(paid):
                        issues.append(f"{name}に「{am.group(0)}」。"
                                      f"台帳の支払額は{paid}円。超えている")
            mo = _months(row.get("start_date"), row.get("end_date"))
            if mo:
                for pm in re.finditer(r"([0-9]+)\s*(ヶ月|か月|カ月|年)", around):
                    v = int(pm.group(1)) * (12 if pm.group(2) == "年" else 1)
                    if v > mo:
                        issues.append(f"{name}に「{pm.group(0)}」。"
                                      f"台帳の利用期間は{mo}ヶ月。超えている")
            break
    return issues


def load_facts():
    """サービス利用以外の実体験。verified=yes のものだけ返す。"""
    return [r for r in _read_csv(FACTS_CSV)
            if (r.get("verified") or "").strip().lower() in ("yes", "y", "true", "1")]


# 一人称の具体的な主張。台帳と突き合わせる対象
FACT_CLAIM_RE = re.compile(
    r"TOEIC[^。]{0,12}?([0-9]{3})\s*点"
    r"|([0-9]+)\s*年(?:間)?[^。]{0,8}?(?:後回し|放置|やらなかった|止まって|停滞)"
    r"|([0-9][0-9,]*)\s*万?円[^。]{0,10}?(?:溶かした|무駄|払った|使った)"
    r"|([0-9]+)\s*時間[^。]{0,8}?(?:勉強|学習|やった)")


def fact_claims(text):
    """一人称の具体的な主張を拾い、台帳に根拠があるかを返す。

    台帳が空なら「未登録」として全部返す。自動修正はしない。
    """
    facts = load_facts()
    values = " ".join((f.get("value") or "") + (f.get("claim") or "") for f in facts)
    out = []
    for m in FACT_CLAIM_RE.finditer(text):
        claim = m.group(0).strip()
        num = next((g for g in m.groups() if g), "")
        if num and num in values:
            continue
        out.append(claim[:40])
    return out


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
