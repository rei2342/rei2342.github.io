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

def _workspace(name):
    """台帳のパス。**カレントディレクトリに依らず引けるようにする。**

    相対パスのままだと、リポジトリのルート以外から呼んだときに
    ファイルが見つからず、_read_csv が空を返す。台帳が空だと
    「案件が台帳に無い」というブロッカーが全記事に出て、
    **台帳が読めていないのか、本当に行が無いのかが区別できない**
    （2026-08-09に49本中48本が誤ってブロッカー扱いになった）。
    """
    import os
    rel = f"affiliate-research-engine/playbook/workspace/{name}"
    if os.path.exists(rel):
        return rel
    here = os.path.dirname(os.path.abspath(__file__))    # .../playbook/scripts
    return os.path.join(os.path.dirname(here), "workspace", name)


EXPERIENCE_CSV = _workspace("experience.csv")
FACTS_CSV = _workspace("experience_facts.csv")

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

            # 3つの状態で、やるべきことが違う。区別して出す
            if not row:
                issues.append(f"{name}に体験表現「{verb}」。**台帳に未登録** "
                              "→ 台帳へ追加して事実を確認する")
                break
            if status in ("", "unknown"):
                issues.append(f"{name}に体験表現「{verb}」。**unknown（使用したか未確認）** "
                              "→ 運営者に確認する")
                break
            if status == "not_used":
                issues.append(f"{name}に体験表現「{verb}」。**未使用と確認済み** "
                              "→「調べた」「比較した」「候補にした」へ直す")
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
    r"|([0-9][0-9,]*)\s*万?円[^。]{0,10}?(?:溶かした|無駄|払った|使った)"
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


# ══════════════════════════════════════════════════════════════
# さくら固有の事実の封鎖（2026-08-08）
#
# **事実台帳で verified になっていない、さくら固有の過去・現在の事実を
#   生成しない。**
#
# これまでは「スコアを書くな」「金額を書くな」と個別に禁じてきたが、
# 記事ごとに別の履歴が生成される問題は止まらなかった。
# 実際、TOEICのスコアは5本の記事で互いに矛盾していた
# （385点・515点・545点・595点・600点が同時に「私のスコア」だった）。
#
# 禁止リストを足すのではなく、**根拠が無いものを全部止める**。
# 一人称の具体的な事実を書くには、verified な fact ID を付ける。
# 付いていなければ、一般論へ書き換えずに**生成・公開を失敗させる**。
# 機械が勝手に薄めると、何が消えたのか誰も分からなくなるため。
# ══════════════════════════════════════════════════════════════

# 一人称の合図。これが無い文は、第三者の話として扱う
SELF_RE = re.compile(r"私|自分|僕|うち(?:の|は)")

# 仮定・試算・引用は、さくら固有の事実の主張ではない
HYPOTHETICAL_RE = re.compile(
    r"例(?:として|えば|示)|試算|仮に|としたら|とすると|だとすれば|"
    r"と仮定|概算|シミュレーション|目安として")

# 出典。公式情報として書くなら、これと確認日が要る
SOURCE_URL_RE = re.compile(r"https?://|公式サイト|公式ページ|外務省|大使館|移民局")

# fact ID の付け方。HTMLコメントと data 属性の両方を受ける。
#   <!--fact:F001-->  /  <span data-fact="F001">…</span>
FACT_MARK_RE = re.compile(
    r"<!--\s*fact\s*:\s*([A-Za-z0-9_\-]+)\s*-->"
    r"|data-fact=\"([A-Za-z0-9_\-]+)\"")

# 封鎖する事実の種類。**一人称の合図が要るもの**は need_self=True。
# 第三者の台詞のように、一人称が無くても危ないものは False。
SELF_FACT_RULES = [
    ("TOEICスコア・受験日・増減", True, re.compile(
        r"TOEIC[^。]{0,15}?[0-9]{3}\s*点"
        r"|[0-9]{3}\s*点(?:から|まで|で|に|を|が)[^。]{0,10}?"
        r"(?:止ま|伸び|上が|下が|動|取っ|出|超え)"
        r"|[0-9]{1,3}\s*点(?:上が|下が|伸び|戻|動い|落ち)"
        r"|(?:受験|受け)(?:た|ました)[^。]{0,8}?TOEIC"
        r"|TOEIC[^。]{0,10}?(?:受験した|受けた|受けました)")),

    ("貯金・収入・支出", True, re.compile(
        r"(?:貯金|貯め|預金|手取り|年収|月収|給料)[^。]{0,12}?[0-9][0-9,]*\s*万?円"
        r"|[0-9][0-9,]*\s*万?円[^。]{0,12}?(?:貯め|貯金)"
        r"|[0-9][0-9,]*\s*万?円[^。]{0,12}?"
        r"(?:払った|払っていた|支払った|溶かした|課金し|使っていた|失った)")),

    ("サービスの登録・契約・無料体験・利用", True, re.compile(
        r"(?:登録|契約|申し込|申込|入会|課金|解約|退会)"
        r"(?:した|しました|んだ|んでいた|していた)"
        r"|(?:無料体験|無料トライアル|体験レッスン|カウンセリング)"
        r"[^。]{0,10}?(?:受けた|受けました|試した|申し込んだ|使った)"
        r"|(?:受講|利用)(?:した|しました|していた)")),

    ("利用期間・回数", True, re.compile(
        r"[0-9]+\s*(?:年|年間|ヶ月|か月|カ月|週間|日|日間|回|コマ)"
        r"[^。]{0,12}?(?:続けた|続けていた|通った|通っていた|受けた|使った|"
        r"やった|やっていた|回した|積んだ)"
        # 「英語を5年後回しにしてきた」も未確認の個人史。動詞を足さないと漏れる
        # （2026-08-08に実運用テストで判明）
        r"|[0-9]+\s*(?:年|年間|ヶ月|か月|カ月)"
        r"[^。]{0,10}?(?:後回しに|放置|止まって|停滞|閉じて|さぼって|"
        r"やめて|離れて|touch)")),

    # 「見に行った」「取りに行った」を渡航と読まないよう、場所を要求する。
    # 動詞の連用形＋に行く は移動の話ではない（2026-08-08に誤検出）
    ("留学・渡航・居住", True, re.compile(
        r"(?:留学|渡航|移住)(?:した|しました|していた)"
        r"|(?:海外|現地|語学学校|"
        + "|".join(COUNTRY) + r"|セブ島|セブ|ハワイ)"
        r"(?:に|へ)[^。]{0,6}?(?:行った|渡った|飛んだ|住んでいた|住んだ|滞在した)")),

    ("職歴・仕事内容", True, re.compile(
        r"(?:営業事務|経理|総務|人事|販売|事務職)(?:として|で)[^。]{0,10}?"
        r"(?:働いて|勤めて|やって)"
        r"|(?:転職|異動|昇進|昇給)(?:した|しました)"
        r"|(?:同期|上司|先輩|後輩|取引先|部署)[^。]{0,12}?"
        r"(?:だった|がいた|に言われ|から聞い)")),

    ("年齢・期限・将来計画", True, re.compile(
        r"[0-9]{2}\s*歳(?:の私|になる|だった|です|になった)"
        r"|(?:30歳|三十歳)(?:まで|になる前)に[^。]{0,14}?(?:行く|出発|渡航|申請)"
        r"|(?:来年|再来年|年内)[^。]{0,10}?(?:出発|渡航|申請|行く)")),

    ("実際の発言・会話", True, re.compile(
        r"[「『][^」』]{2,60}[」』][^。]{0,8}?"
        r"(?:と言った|と答えた|と返した|と伝えた|と口に出した|と聞いた)")),

    ("第三者から言われた言葉", False, re.compile(
        r"[「『][^」』]{2,60}[」』][^。]{0,10}?"
        r"(?:と言われ|と指摘され|と教えて|と返ってき|と褒められ|とすすめられ)")),

    ("成功・失敗・改善結果", True, re.compile(
        r"(?:話せるように|聞き取れるように|できるように|出るように)"
        r"(?:なった|なりました)"
        r"|(?:伸びた|上がった|動いた|改善した|減った|増えた)[^。]{0,6}$"
        r"|(?:やめた|閉じた|挫折した|続かなかった)[^。]{0,10}?"
        r"[0-9]+\s*(?:日|回|ページ|ヶ月)")),

    # 過去の心理・判断も、本人固有の事実になる。
    # 「鵜呑みにしかけた私が」は、さくらが実際そう考えたという未確認の主張
    # （2026-08-08に運営者から指摘。それまで「意見だから可」と誤判定していた）
    ("過去の心理・判断", True, re.compile(
        r"(?:思った|思っていた|信じた|信じていた|鵜呑みに(?:した|しかけた)"
        r"|迷った|迷っていた|悩んだ|悩んでいた|気づいた|気付いた"
        r"|決めた|決めていた|疑った|選んだ)"
        # 「何と何を比べた数字」は連体修飾で本人の行動ではない。
        # 「私は…比べた」の形だけ拾う
        r"|(?:私|自分)(?:は|が|も)[^。]{0,16}?比べた")),

    # 現在形の編集方針も一人称で書かない。「この記事では〜」へ寄せる。
    # 文末の「〜と考えている」は主語が無くても一人称の判断になる
    ("現在の判断・編集方針", False, re.compile(
        r"と(?:考えている|読んでいる|理解している|判断している|見ている|感じている)"
        r"[。、]|と(?:考えている|読んでいる|理解している|判断している)$")),

    # ⚠️ 2026-08-09に追加。**いちばん大きい穴だった。**
    #
    # 13分類は「TOEICのスコア」「貯金」のように、事実の種類を名指しで拾う形
    # だった。そのため「私はソファに沈み込んでいた」「手帳を開いて過去2週間を
    # 見返した」のような、種類に当てはまらない**地の語り**が丸ごと素通りしていた。
    # 文単位で13分類だけを直したら、改修25本に一人称の語りが569文残っていて、
    # 読者向けに直した文と混ざっていた。
    #
    # 台帳が空である以上、**一人称を主語にした過去の出来事は書けない**。
    # 種類を問わず、主語＋過去形の形そのものを止める。
    #
    # 「自分の条件で出す」「自分で置いた期限」のような、読者に向けた
    # 現在形・可能形は対象にしない（全文改修した6本はこの形だけを使っている）。
    ("未確認の一人称の語り", True, re.compile(
        r"(?:私|自分)(?:は|が|も|には|にも|の)[^。！？]{0,60}?"
        r"(?:った|いた|えた|けた|せた|べた|めた|ねた|でた|てきた|"
        r"かった|だった|ていた|ました|でした)[。、]")),

    ("固有の日付・場所・人物", True, re.compile(
        r"20[0-9]{2}\s*年\s*[0-9]{1,2}\s*月[^。]{0,10}?(?:私|受け|行っ|払っ)"
        r"|[0-9]{1,2}\s*月[0-9]{1,2}\s*日[^。]{0,10}?(?:私|受け|行っ|払っ)"
        r"|(?:月|火|水|木|金|土|日)曜(?:日)?の(?:夜|朝|昼)[^。]{0,10}?私")),
]


def verified_facts():
    """experience_facts.csv の verified=yes な行を fact_id 引きで返す。"""
    out = {}
    for r in _read_csv(FACTS_CSV):
        fid = (r.get("fact_id") or "").strip()
        ok = (r.get("verified") or "").strip().lower() in ("yes", "y", "true", "1")
        if fid and ok:
            out[fid] = r
    return out


def verified_fact_ids():
    """verified=yes な fact ID の集合。"""
    return set(verified_facts())


# 検出した種類 → 台帳の category として認めるもの。
# **ID が存在するだけでは通さない。**種類が違えば別の事実なので落とす。
CATEGORY_MAP = {
    "TOEICスコア・受験日・増減": {"toeic", "score"},
    "貯金・収入・支出": {"spending", "saving", "income"},
    "サービスの登録・契約・無料体験・利用": {"service"},
    "利用期間・回数": {"duration", "service"},
    "留学・渡航・居住": {"abroad", "travel"},
    "職歴・仕事内容": {"work", "work_english"},
    "年齢・期限・将来計画": {"age_plan", "profile"},
    "実際の発言・会話": {"utterance"},
    "第三者から言われた言葉": {"utterance"},
    "成功・失敗・改善結果": {"result", "setback"},
    "過去の心理・判断": {"mindset", "setback", "result"},
    "現在の判断・編集方針": {"mindset"},
    "固有の日付・場所・人物": {"datetime_place"},
}

# 文中の数値。台帳と突き合わせる
_NUM_IN_SENT = re.compile(
    r"[0-9][0-9,]*(?:万[0-9,]*)?\s*"
    r"(?:万円|円|万|点|年間|年|ヶ月|か月|カ月|週間|日間|日|時間|分|回|コマ|冊|校|社|歳)")


def _canon_num(x):
    """「4万5000円」「4,500円」を比べられる形にそろえる。"""
    x = re.sub(r"[,，\s]", "", x)
    return x.replace("か月", "ヶ月").replace("カ月", "ヶ月").replace("年間", "年")


def fact_mismatch(sent, matched, category, fact):
    """付いている fact ID が、この文の主張と合っているかを見る。

    **ID の存在確認だけでは足りない。** F001 が「TOEIC600点」なのに
    「TOEIC800点を取った」に F001 を付ければ通る、では意味がない。
    台帳の category / claim / value / period / allowed_claims と突き合わせる。

    合っていれば None、合っていなければ理由を返す。
    """
    fid = (fact.get("fact_id") or "").strip()
    cat = (fact.get("category") or "").strip().lower()
    ok_cats = CATEGORY_MAP.get(category, set())
    if ok_cats and cat not in ok_cats:
        return (f"{fid} は category={cat or '（空）'} で、"
                f"この主張の種類（{category}）と違う")

    # 台帳に書いてある文字列を全部つないで、照合の材料にする
    hay = " ".join(str(fact.get(k) or "") for k in
                   ("claim", "value", "period", "allowed_claims", "note"))
    hay_c = _canon_num(hay)

    # 数値。文に出てくる数値が台帳に無ければ、別の事実になっている
    for m in _NUM_IN_SENT.finditer(sent):
        v = _canon_num(m.group(0))
        if v in hay_c:
            continue
        digits = re.sub(r"[^0-9]", "", v)
        if digits and digits in re.sub(r"[^0-9]", "", hay_c):
            continue
        return f"{fid} の台帳に「{m.group(0)}」が無い"

    # サービス名。別サービスの ID を流用させない
    for name in SERVICE_NAMES:
        if name in sent and name not in hay:
            return f"{fid} は別のサービスの事実（台帳に「{name}」が無い）"

    # 発言・第三者の台詞・結果は、allowed_claims に書いてあるものだけ
    if category in ("実際の発言・会話", "第三者から言われた言葉",
                    "成功・失敗・改善結果"):
        allowed = str(fact.get("allowed_claims") or "")
        q = re.search(r"[「『]([^」』]{2,60})[」』]", sent)
        target = q.group(1) if q else matched
        if not allowed:
            return f"{fid} に allowed_claims が無い（具体的な発言・結果は書けない）"
        if target not in allowed:
            return f"{fid} の allowed_claims に「{target[:30]}」が無い"
    return None


def _blocks_with_marks(html):
    """(プレーン文, その文に効いている fact ID) の並びを返す。

    fact ID はブロック単位で効かせる。文の直後に書くのが基本だが、
    段落の先頭にまとめて置く書き方も通す。
    """
    out = []
    parts = re.split(r"(?i)(?=<(?:p|li|h[1-6]|td|blockquote)\b)", html) or [html]
    for part in parts:
        ids = {m.group(1) or m.group(2) for m in FACT_MARK_RE.finditer(part)}
        text = strip_tags(part)
        for s in re.split(r"(?<=[。？！])", text):
            if s.strip():
                out.append((s.strip(), ids))
    return out


def unverified_self_facts(html):
    """verified な fact ID の裏付けが無い、さくら固有の事実を返す。

    **自動で一般論へ書き換えない。** 該当文をそのまま返して、
    生成・公開を失敗させる。何が消えたか分からなくなるほうが危ない。
    """
    facts = verified_facts()
    ok_ids = set(facts)
    out = []
    for sent, ids in _blocks_with_marks(html):
        if HYPOTHETICAL_RE.search(sent):
            continue                      # 例・試算は事実の主張ではない
        has_self = bool(SELF_RE.search(sent))
        for name, need_self, pat in SELF_FACT_RULES:
            if need_self and not has_self:
                continue
            m = pat.search(sent)
            if not m:
                continue
            good = ids & ok_ids
            if good:
                # **存在確認だけでは通さない。**中身が合っているかまで見る。
                # どれか1つでも合っていれば、その文は裏付けありとする
                misses = [fact_mismatch(sent, m.group(0), name, facts[i])
                          for i in sorted(good)]
                if any(x is None for x in misses):
                    break
                reason = "／".join(x for x in misses if x)
            elif ids:
                reason = "付いている fact ID が台帳で verified ではない"
            else:
                reason = "fact ID が無い"
            out.append({
                "category": name,
                "matched": m.group(0)[:50],
                "sentence": sent[:180],
                "fact_ids": " ".join(sorted(ids)) if ids
                            else "（fact ID が付いていない）",
                "reason": reason,
            })
            break
    return out


# 公式料金・制度・サービス仕様は、出典URLと確認日が両方要る
OFFICIAL_SPEC_RE = re.compile(
    r"(?:月額|年額|料金|受講料|授業料|プラン|無料トライアル|無料体験)"
    r"[^。]{0,20}?[0-9][0-9,]*\s*万?円"
    r"|[0-9]+\s*(?:日間|ヶ月)[^。]{0,6}?(?:無料|トライアル)"
    # 回数・人数・期間・無制限も公式の仕様。金額と同じく出典と確認日が要る
    # （2026-08-08に「無料体験は2回まで」がURL無しで通過した）
    r"|(?:無料体験|無料トライアル|体験レッスン|レッスン|受講|相談)"
    r"[^。]{0,14}?[0-9]+\s*(?:回|名|人|コマ|枠)"
    r"|(?:回数|レッスン|受講|利用)[^。]{0,8}?無制限"
    r"|(?:認定校|正式認定|監修|提携校)[^。]{0,20}?(?:である|とされ|と案内)")

# 「月1,000円前後」「3万円ほど」は幅の話で、公式の提示額ではない。
# 出典を求めると、相場の説明が全部書けなくなる（2026-08-08に誤検出）
APPROX_RE = re.compile(r"[0-9][0-9,]*\s*万?円\s*(?:前後|程度|くらい|ぐらい|ほど|台|弱|強)"
                       r"|(?:およそ|約|おおよそ|だいたい)\s*[0-9][0-9,]*\s*万?円")


def _sentences_for_spec(html):
    """料金・仕様の検査に使う文。

    **ブロック単位で切ってから文に分ける。** 段落をつないでから切ると、
    句点で終わらないCTA行と次の見出しが1文になって誤爆する
    （2026-08-08に「7日間無料体験を見る」＋見出しで発生）。
    **リンクの文言は検査しない。** CTAは定型で、出典を書く場所ではない。
    """
    out = []
    parts = re.split(r"(?i)(?=<(?:p|li|h[1-6]|td|blockquote)\b)", html) or [html]
    for part in parts:
        body = re.sub(r"<a\b[^>]*>.*?</a>", " ", part, flags=re.DOTALL | re.I)
        for x in re.split(r"(?<=[。？！])", strip_tags(body)):
            if x.strip():
                out.append(x.strip())
    return out


def official_spec_without_source(html):
    """公式の料金・仕様なのに、出典URLか確認日が欠けている文を返す。

    出典は同じ段落にあれば足りる。リンクで示している場合もあるので、
    段落全体（リンクのhrefを含む）を見て判定する。
    """
    out = []
    parts = re.split(r"(?i)(?=<(?:p|li|h[1-6]|td|blockquote)\b)", html) or [html]
    ctx = {}
    for part in parts:
        for x in _sentences_for_spec(part):
            ctx[x] = part
    for s in _sentences_for_spec(html):
        s = s.strip()
        if not s or not OFFICIAL_SPEC_RE.search(s):
            continue
        if HYPOTHETICAL_RE.search(s):
            continue                      # 「例として月5,000円を試算」は対象外
        if APPROX_RE.search(s):
            continue                      # 「月1,000円前後」は幅の話
        if SELF_RE.search(s):
            continue    # 一人称の文は公式の仕様ではない。fact gate 側で見る
        # 出典は同じ段落にあればよい（リンクで示していることが多い）。
        # ただし**実URLを要求する。**「同公式サイト」という語だけでは通さない
        # （2026-08-08に「無料体験は2回まで（同公式サイト、8月8日時点）」が通過した）
        around = ctx.get(s, s)
        missing = []
        if not re.search(r"https?://", around):
            missing.append("出典URL")
        if not BASEDATE_RE.search(around):
            missing.append("確認日")
        if missing:
            out.append({"missing": "と".join(missing), "sentence": s[:180]})
    return out


def generation_blockers(html):
    """公開ブロッカーをまとめて返す。空なら公開してよい。"""
    issues = []
    for f in unverified_self_facts(html):
        issues.append(f"[{f['category']}] 台帳の裏付けが無い"
                      f"（{f['reason']}）: {f['matched']} … {f['sentence'][:70]}")
    for f in official_spec_without_source(html):
        issues.append(f"[公式の料金・仕様] {f['missing']}が無い: {f['sentence'][:70]}")
    # CTAの訴求は本文とは別に見る。リンク文言を素通りさせない
    for f in cta_claim_gate(html):
        issues.append(f"[CTAの訴求] {f['reason']}: 「{f['anchor'][:50]}」")
    # リンクの外（箱の見出し・注記）も見る。2026-08-09に穴が見つかった
    for f in cta_box_text_gate(html):
        issues.append(f"[CTAの見出し] {f['reason']}: 「{f['anchor'][:50]}」")
    return issues


# ══════════════════════════════════════════════════════════════
# CTAの訴求を検査する（2026-08-08）
#
# 本文の fact gate とは別に持つ。
# 料金・仕様の検査からリンク文言を外したので、そこを完全に素通りさせると
# 「無料トライアル」「初月無料」「今だけ半額」が再び入ってしまう。
# **CTAは読者が最後に見る約束**なので、未確認の訴求が一番害が大きい。
# ══════════════════════════════════════════════════════════════

CTA_CLAIMS_CSV = _workspace("cta_claims.csv")

# CTAに入っていたら、台帳との一致を要求する語
CTA_PROMO = ("無料", "割引", "返金", "成果保証", "保証", "限定",
             "キャンペーン", "半額", "初月", "今だけ", "最安", "0円")

# 期間・回数は数値とセットのときだけ訴求とみなす（「回数無制限」も拾う）
CTA_PROMO_NUM = (
    ("期間", re.compile(r"[0-9]+\s*(?:日間|日|週間|ヶ月|か月|カ月)")),
    ("回数", re.compile(r"[0-9]+\s*回|回数無制限|無制限")),
)

_A_TAG_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.I)


def _today():
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")


def load_cta_claims():
    """CTAで訴求してよい条件。verified=yes で、**まだ失効していない**行だけ。

    expires_on を過ぎた行は verified=yes でも落とす（2026-08-09に追加）。
    「8月31日まで初月99円」を9月に出し続けると、確認済みの記録が
    そのまま虚偽になる。人が消し忘れても機械が止まるようにする。
    """
    today = _today()
    out = []
    for r in _read_csv(CTA_CLAIMS_CSV):
        if (r.get("verified") or "").strip().lower() not in \
                ("yes", "y", "true", "1"):
            continue
        exp = (r.get("expires_on") or "").strip()
        if exp and exp < today:
            continue                       # 失効。台帳に無いのと同じ扱い
        out.append(r)
    return out


def expired_cta_claims():
    """失効した行を報告用に返す。黙って消すと気づけないため。"""
    today = _today()
    return [r for r in _read_csv(CTA_CLAIMS_CSV)
            if (r.get("expires_on") or "").strip()
            and (r.get("expires_on") or "").strip() < today]


# 一時非表示にしたCTA。コメントで包んであるので読者には出ない
HIDDEN_CTA_RE = re.compile(
    r"<!--\s*cta-hidden:START.*?<!--\s*cta-hidden:END\s*-->",
    re.DOTALL | re.IGNORECASE)

# ── CTAボックスの、リンク以外の文言 ────────────────────────
# 2026-08-09に見つけた穴。ゲートは `<a>` のアンカーしか見ていなかったので、
# 箱の見出し「▶ さくらが確かめた・次の一手（すべて無料）」が素通りしていた。
#
#  - 「さくらが確かめた」… 台帳に無い一人称の行動。主語が「私」ではなく
#    「さくら」だったので unverified_self_facts にも掛からなかった
#  - 「すべて無料」… 箱に入る**全案件**への訴求。案件ごとに確認している
#    cta_claims.csv の意味が消える
#
# 箱の中のリンク以外のテキストも見る。
CTA_BOX_RE = re.compile(
    r'<div style="background:#f9f9f9;border-left:4px solid #27ae60;[^"]*">'
    r'(.*?)</div>', re.DOTALL)

# 箱を使わずに、見出しの段落だけ置いている形もある。
# 改修済み18本が `<p>▶ 次の一手（すべて無料）</p>` を持っていた
# （styled div ではないので CTA_BOX_RE では拾えなかった。2026-08-09に追加）。
CTA_HEADING_P_RE = re.compile(
    r'<p[^>]*>\s*([▶▼■●➡→]\s*[^<]{0,80})</p>')

# 箱の見出しで使ってはいけない、運営者の行動表現。主語がどれでも止める
CTA_PERSONA_RE = re.compile(
    r"(?:さくら|私|自分|編集部|当サイト)(?:が|は|も)?"
    r"[^。<]{0,12}?"
    r"(?:確かめた|確認した|試した|使った|受けた|調べた|比べた|選んだ|体験した)")

# 「すべて無料」のような、案件を特定しない一括訴求
CTA_BLANKET_RE = re.compile(
    r"(?:すべて|全部|どれも|いずれも|全て)\s*"
    r"(?:無料|0円|割引|返金|保証|半額)")


# ── 制度の条件を、別の対象国から取り違えていないか ──────────────
# 2026-08-09にやった。GOV.UK の Youth Mobility Scheme のページは
# 「18〜35歳の国（豪・加・NZ・韓）」と「18〜30歳の国（日本ほか）」を
# 別々に載せていて、抽選は香港SAR旅券保持者と台湾の条項だった。
# 日本を含むリストの直後に抽選の文があったので、日本に掛かると読んでしまった。
#
# **公式ページの一部だけを読んで、別の対象国の条件を当てはめない。**
# 制度の条件を書くときは、その条件がどの国のものかを本文で明示させる。
INSTITUTION_COND_RE = re.compile(
    r"(?:抽選|ballot|年齢(?:条件|制限|上限)|申請時に\s*[0-9]{2}\s*歳|"
    r"[0-9]{2}\s*〜\s*[0-9]{2}\s*歳|[0-9]{2}\s*歳以下)")

# 条件文と同じ文に国名があるか。無ければどの国の話か分からない
COUNTRY_NAME_RE = re.compile(
    r"イギリス|英国|オーストラリア|豪州|カナダ|ニュージーランド|アイルランド|"
    r"韓国|台湾|香港|シンガポール|ドイツ|フランス|日本|ポーランド|"
    r"ハンガリー|スペイン|ポルトガル|チェコ|デンマーク|オランダ|"
    r"アルゼンチン|チリ|アイスランド|ノルウェー|オーストリア|リトアニア")


def institution_country_gate(html):
    """制度の条件を、対象国とセットで書いているかを見る。

    ⚠️ **公開ゲートには入れていない。**
    2026-08-09の取り違えは「日本からの申請には抽選がある」と、
    国名を**書いたうえで**間違えたものだった。文中に国名があるかを見ても
    この型は捕まらないし、「年齢条件は国ごとに違う」のような
    正しい書き方まで止めてしまう。

    本当の検査は照合の側（official_fact_check の country_conditions）に置いた。
    公式ページから**国と条件の対応表**を作って、人が対応を目で確かめる。
    この関数は補助で、条件を断定しているのに国名が無い文を拾うだけ。
    """
    out = []
    for sent in re.split(r"(?<=[。！？])", strip_tags(html)):
        sent = sent.strip()
        if not sent or not INSTITUTION_COND_RE.search(sent):
            continue
        if HYPOTHETICAL_RE.search(sent):
            continue
        # 読者への確認手順（「〜を確認する」）は条件の断定ではない
        if re.search(r"確認(?:する|項目|してほしい)|控える|調べる|見る。", sent):
            continue
        if not COUNTRY_NAME_RE.search(sent):
            out.append({"sentence": sent[:120],
                        "reason": "制度の条件に対象国が書かれていない。"
                                  "どの国の条件か分からない"})
    return out


def cta_box_text_gate(html):
    """CTAボックスの、アンカー以外の文言を見る。

    見出し・注記に運営者の行動や一括訴求が入っていないかを確認する。
    ここは読者が最後に見る場所なので、本文と同じ基準を当てる。
    """
    html = HIDDEN_CTA_RE.sub(" ", html)
    chunks = [_A_TAG_RE.sub(" ", m.group(1))       # リンクは cta_claim_gate の担当
              for m in CTA_BOX_RE.finditer(html)]
    # 矢印で始まる短い見出し段落。箱を使っていない形を拾う。
    # **リンクそのもの（→ で始まるアンカー）は除く。** あれは訴求の担当
    linkless = _A_TAG_RE.sub(" ", html)
    chunks += [m.group(1) for m in CTA_HEADING_P_RE.finditer(linkless)]

    out = []
    for chunk in chunks:
        text = strip_tags(chunk)
        for hit in CTA_PERSONA_RE.finditer(text):
            out.append({"anchor": hit.group(0), "term": "運営者の行動",
                        "reason": "CTAの見出しに、台帳に無い運営者の行動が入っている"})
        for hit in CTA_BLANKET_RE.finditer(text):
            out.append({"anchor": hit.group(0), "term": "一括訴求",
                        "reason": "案件を特定しない訴求。案件ごとに書く"})
    # 同じ箇所を箱と見出しの両方で拾うことがあるので重複を落とす
    seen, uniq = set(), []
    for o in out:
        k = (o["anchor"], o["term"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(o)
    return uniq


def cta_claim_gate(html):
    """アフィリエイトCTAの訴求が、台帳と公式情報で裏付けられているかを見る。

    アンカー文言に訴求の語が入っているのに、案件台帳に
    verified な行が無い／数値が違う／確認日が無い場合はブロックする。

    **一時非表示にしたCTAは対象外。** コメントで包んであって読者には
    表示されないので、訴求として機能していない（2026-08-08に追加）。
    """
    html = HIDDEN_CTA_RE.sub(" ", html)
    rows = load_cta_claims()
    out = []
    for m in _A_TAG_RE.finditer(html):
        href, anchor = m.group(1), strip_tags(m.group(2)).strip()
        if not AFFILIATE_LINK_RE.search(href) or not anchor:
            continue

        terms = [t for t in CTA_PROMO if t in anchor]
        for name, pat in CTA_PROMO_NUM:
            if pat.search(anchor):
                terms.append(name)
        if not terms:
            continue                      # 訴求していないCTAは対象外

        svc = next((s for s in SERVICE_NAMES if s in anchor), "")
        if not svc:
            out.append({"anchor": anchor, "term": "／".join(terms),
                        "reason": "CTAに案件名が無いので、台帳と照合できない"})
            continue

        mine = [r for r in rows if (r.get("service") or "").strip() == svc]
        if not mine:
            out.append({"anchor": anchor, "term": "／".join(terms),
                        "reason": f"{svc} が cta_claims.csv に無い"})
            continue

        for t in set(terms):
            hit = [r for r in mine if (r.get("promo_term") or "").strip() == t]
            if not hit:
                out.append({"anchor": anchor, "term": t,
                            "reason": f"{svc} の「{t}」が台帳で確認されていない"})
                continue
            r = hit[0]
            if not (r.get("official_url") or "").strip():
                out.append({"anchor": anchor, "term": t,
                            "reason": f"{svc} の「{t}」に出典URLが無い"})
            if not (r.get("checked_on") or "").strip():
                out.append({"anchor": anchor, "term": t,
                            "reason": f"{svc} の「{t}」に確認日が無い"})
            # 数値まで一致させる。「7日間」の台帳で「14日間」を訴求させない
            hay = _canon_num(str(r.get("claim") or ""))
            for nm in _NUM_IN_SENT.finditer(anchor):
                if _canon_num(nm.group(0)) not in hay:
                    out.append({
                        "anchor": anchor, "term": t,
                        "reason": f"{svc} の台帳に「{nm.group(0)}」が無い"
                                  f"（台帳: {r.get('claim')}）"})
    return out
