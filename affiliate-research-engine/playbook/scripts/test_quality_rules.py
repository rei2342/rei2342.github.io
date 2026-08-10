#!/usr/bin/env python3
"""
test_quality_rules.py
検査ルールのテスト。**テスト用の事実はここにしか置かない。**

本番の台帳（experience.csv）にテストデータを入れると、
実際には使っていないサービスが「使用済み」として通ってしまう。
台帳はモンキーパッチで差し替える。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as q

# 差し替える前の本物。テストの途中でモンキーパッチが残ると、
# あとのテストが実装ではなくラムダを検査してしまう
REAL_LOAD_CTA_CLAIMS = q.load_cta_claims

# テスト専用の台帳。本番ファイルには一切書かない
LEDGER = {
    "DMM英会話": {"service": "DMM英会話", "status": "used", "usage_type": "free_trial",
                  "start_date": "2026-01", "end_date": "2026-01", "amount_paid": "0"},
    "speek": {"service": "speek", "status": "not_used"},
    "Notta": {"service": "Notta", "status": "unknown"},
    # スパトレは台帳に載せない（未登録のケース）
}


def run():
    q.load_experience = lambda: LEDGER
    cases = [
        ("DMM英会話の無料体験を2回受けた", None),
        ("DMM英会話を3ヶ月使った", "超えている"),
        ("DMM英会話に4万5000円払った", "超えている"),
        ("speekを試してみた", "未使用と確認済み"),
        ("speekを調べて比較した", None),
        ("Nottaを使ってみた", "unknown"),
        ("スパトレを続けた", "台帳に未登録"),
    ]
    ng = 0
    for text, expect in cases:
        got = q.experience_claims(text)
        hit = got[0] if got else None
        ok = (expect is None and not got) or (expect and hit and expect in hit)
        print(("OK  " if ok else "NG  ") + text)
        if hit:
            print("      " + hit)
        ng += 0 if ok else 1

    # 制度の断定
    for text, expect in [
        ("ワーホリの年齢上限は30歳です", True),
        ("オーストラリアのワーホリは申請時30歳以下（外務省の公表内容・2026年8月時点）", False),
    ]:
        got = q.time_sensitive_fact(text)
        ok = bool(got) is expect
        print(("OK  " if ok else "NG  ") + text[:40])
        ng += 0 if ok else 1

    print(f"\n失敗 {ng}件")
    return ng




def run_blockers():
    """生成側の封鎖。**verified な fact ID が無い一人称の事実を止める。**

    自動で一般論へ書き換えず、該当文を報告して失敗させることを確かめる。
    """
    # テスト専用の台帳。本番には1行も書かない
    LEDGER = {
        "F001": {"fact_id": "F001", "category": "toeic",
                 "claim": "TOEICで600点を取った", "value": "600点",
                 "period": "2025-11", "allowed_claims": "", "note": ""},
        "F010": {"fact_id": "F010", "category": "service",
                 "claim": "DMM英会話の無料体験を2回受けた", "value": "2回",
                 "period": "2026-01", "allowed_claims": "", "note": ""},
        "F020": {"fact_id": "F020", "category": "utterance",
                 "claim": "講師から発音の指摘を受けた", "value": "",
                 "period": "2026-02",
                 "allowed_claims": "アクセントの位置が違う", "note": ""},
        "F030": {"fact_id": "F030", "category": "result",
                 "claim": "2週間続いた", "value": "", "period": "2026-02",
                 "allowed_claims": "", "note": "具体的な結果は登録していない"},
    }
    q.verified_facts = lambda: LEDGER
    q.verified_fact_ids = lambda: set(LEDGER)

    CASES = [
        # (本文, ブロックされるべきか, 説明)
        ("<p>私はTOEIC600点を取った。</p>", True, "台帳にないTOEICスコア"),
        ("<p>私の貯金は50万円だった。</p>", True, "台帳にない貯金"),
        ("<p>私はDMM英会話の無料体験を受けた。</p>", True, "台帳にないサービス利用"),
        ("<p>私はセブ島へ留学した。</p>", True, "台帳にない留学"),
        ("<p>講師に「アクセントの位置が違う」と言われた。</p>", True,
         "台帳にない第三者の台詞"),
        ("<p>私はオンライン英会話を3ヶ月続けた。</p>", True, "台帳にない利用期間"),
        ("<p>私は営業事務として働いていた。</p>", True, "台帳にない職歴"),
        ("<p>私は27歳の私で、30歳までに必ず渡航する。</p>", True, "年齢・将来計画"),
        ("<p>スパトレの料金は月5,980円（公式サイト https://sptr.jp/ ・"
         "2026年8月8日時点）。</p>", False, "出典と確認日つきの公式料金"),
        ("<p>例として月5,000円を試算すると、年間6万円になる。</p>", False,
         "例・試算と明記した数字"),
        ("<p>私はTOEIC600点を取った。<!--fact:F001--></p>", False,
         "verified な fact ID つきの体験"),
        ("<p><span data-fact=\"F001\">私はTOEIC600点を取った。</span></p>", False,
         "data-fact でも通る"),
        ("<p>私はTOEIC600点を取った。<!--fact:F999--></p>", True,
         "台帳に無い fact ID は通さない"),
        ("<p>月額5,980円で毎日レッスンが受けられる。</p>", True,
         "公式料金に出典も確認日も無い"),

        # 実運用テストで漏れた型（2026-08-08）
        ("<p>英語を5年後回しにしてきた私が、会議で息苦しさを手放せた。</p>", True,
         "「5年後回しにしてきた」は未確認の個人史 → ブロック"),
        ("<p>私は2年間、英語から離れていた。</p>", True,
         "「2年間離れていた」→ ブロック"),

        # 誤検出の型。ゲートが強すぎて普通の文を止めた実例を固定する
        ("<p>表の数字は自分で見に行ったほうが確実だ。</p>", False,
         "「見に行った」は渡航ではない → 通過"),
        ("<p>私はカナダに行った。</p>", True, "場所つきの移動 → ブロック"),
        ("<p>無料プランや月1,000円前後のアプリが多い。</p>", False,
         "「月1,000円前後」は幅の話 → 通過"),
        ("<p>セブの語学学校はおよそ18万円かかる。</p>", False,
         "「およそ18万円」は相場 → 通過"),

        # ── fact ID と主張内容の照合（2026-08-08 追加）──
        # **ID を付けるだけで別の事実を書けてはいけない**
        ("<p>私はTOEIC600点を取った。<!--fact:F001--></p>", False,
         "F001=600点 に 600点 → 通過"),
        ("<p>私はTOEIC800点を取った。<!--fact:F001--></p>", True,
         "F001=600点 に 800点 → ブロック"),
        ("<p>私はDMM英会話の無料体験を2回受けた。<!--fact:F010--></p>", False,
         "F010 の登録どおりの利用 → 通過"),
        ("<p>私はDMM英会話の無料体験を2回受けて、3ヶ月続けた。"
         "<!--fact:F010--></p>", True,
         "F010 に無い利用期間を足す → ブロック"),
        ("<p>私はDMM英会話に4万5000円払った。<!--fact:F010--></p>", True,
         "F010 に無い金額を足す → ブロック"),
        ("<p>私はスパトレの無料体験を2回受けた。<!--fact:F010--></p>", True,
         "別サービスに F010 を流用 → ブロック"),
        ("<p>私はTOEIC600点を取った。<!--fact:F010--></p>", True,
         "category違いの fact ID → ブロック"),
        ("<p>講師に「アクセントの位置が違う」と言われた。<!--fact:F020--></p>",
         False, "allowed_claims にある台詞 → 通過"),
        ("<p>講師に「発音は完璧だ」と言われた。<!--fact:F020--></p>", True,
         "allowed_claims に無い台詞 → ブロック"),
        ("<p>私は話せるようになった。<!--fact:F030--></p>", True,
         "allowed_claims の無い fact で結果を書く → ブロック"),

        # ── 未確認の一人称の語り（2026-08-09 追加）──
        # 13分類は事実の「種類」を名指しで拾う形だったので、
        # 種類に当てはまらない地の語りが丸ごと素通りしていた
        ("<p>私はソファに沈み込んでいた。</p>", True,
         "種類に当てはまらない一人称の語り → ブロック"),
        ("<p>手帳を開くと、私の言い分がぐらついた。</p>", True,
         "主語＋過去形の語り → ブロック"),
        ("<p>私はずっと、自分には向いていないと感じてきた。</p>", True,
         "「〜してきた」の語り → ブロック"),
        ("<p>あの夜、私は開こうとしてやめた。</p>", True,
         "場面の語り → ブロック"),
        ("<p>自分の条件で出す。</p>", False,
         "読者に向けた現在形 → 通過"),
        ("<p>自分で置いた期限までに間に合うかを数える。</p>", False,
         "「自分で置いた期限」は読者の手順 → 通過"),
        ("<p>自分が月に何回話せるかで決まる。</p>", False,
         "読者への問い → 通過"),
        ("<p>例として、私は月5,000円を試算した。</p>", False,
         "試算と明記した文は事実の主張ではない → 通過"),
    ]
    ng = 0
    for html, want, why in CASES:
        got = q.generation_blockers(html)
        ok = bool(got) == want
        print(("OK  " if ok else "NG  ") + f"{why}")
        if not ok:
            print(f"      期待: {'ブロック' if want else '通過'} / "
                  f"実際: {got if got else '通過'}")
            ng += 1
        elif want:
            print(f"      → {got[0][:88]}")

    print(f"\n公開ブロッカーの失敗 {ng}件")
    return ng


def run_cta_gate():
    """CTAの訴求。**リンク文言を素通りさせない。**"""
    LEDGER = [
        {"service": "スパトレ", "promo_term": "無料", "claim": "7日間の無料期間",
         "official_url": "https://sptr.jp/", "checked_on": "2026-08-08"},
        {"service": "スパトレ", "promo_term": "期間", "claim": "7日間の無料期間",
         "official_url": "https://sptr.jp/", "checked_on": "2026-08-08"},
    ]
    q.load_cta_claims = lambda: LEDGER
    A = ('<a href="//af.moshimo.com/af/c/click?a_id=1&url=x">{}</a>')

    CASES = [
        ("→ スパトレの7日間無料体験を見る", False, "台帳どおりの無料期間 → 通過"),
        ("→ スパトレの14日間無料体験を見る", True, "台帳は7日間なのに14日間 → ブロック"),
        ("→ speekの無料トライアルを見る", True, "speek は台帳に無い → ブロック"),
        ("→ speek公式サイトで発音矯正スクールの内容を確認する", False,
         "訴求の語が無いCTA → 通過"),
        ("→ 今だけ半額キャンペーンを見る", True, "案件名も台帳も無い → ブロック"),
        ("→ スパトレの初月無料を見る", True, "「初月」は台帳に無い → ブロック"),
        ("→ スパトレなら必ず上達、返金保証つき", True, "返金保証は台帳に無い → ブロック"),
    ]
    ng = 0
    for anchor, want, why in CASES:
        got = q.cta_claim_gate(A.format(anchor))
        ok = bool(got) == want
        print(("OK  " if ok else "NG  ") + why)
        if not ok:
            print(f"      期待: {'ブロック' if want else '通過'} / 実際: {got}")
            ng += 1
        elif want:
            print(f"      → {got[0]['reason'][:80]}")
    # 一時非表示にしたCTAは、読者に出ないので対象外
    hidden = ('<!-- cta-hidden:START x --><p>'
              '<a href="//af.moshimo.com/af/c/click?a_id=1">'
              '→ speekの無料トライアルを見る</a></p><!-- cta-hidden:END -->')
    ok_hidden = not q.cta_claim_gate(hidden)
    print(("OK  " if ok_hidden else "NG  ") + "非表示にしたCTAは検査しない")
    if not ok_hidden:
        ng += 1

    print(f"\nCTAゲートの失敗 {ng}件")
    return ng


def run_cta_box():
    """CTAボックスの、**リンク以外**の文言。

    2026-08-09に見つけた穴。ゲートは `<a>` しか見ていなかったので、
    箱の見出し「▶ さくらが確かめた・次の一手（すべて無料）」が素通りし、
    生成される全記事に入り続けていた。主語が「私」ではなく「さくら」
    だったので unverified_self_facts にも掛からなかった。
    """
    BOX = ('<div style="background:#f9f9f9;border-left:4px solid #27ae60;'
           'padding:16px 20px;margin:32px 0">\n'
           '<p style="margin-top:0;font-weight:bold">{}</p>\n'
           '<p><a href="//af.moshimo.com/af/c/click?a_id=1&url=x">'
           '→ 公式サイトで内容を確認する</a></p>\n</div>')

    CASES = [
        ("▶ さくらが確かめた・次の一手（すべて無料）", True,
         "旧見出し。運営者の行動＋一括訴求 → ブロック"),
        ("▶ さくらが確かめた・次の一手", True,
         "運営者の行動だけでもブロック"),
        ("▶ 次の一手（すべて無料）", True,
         "案件を特定しない一括訴求だけでもブロック"),
        ("▶ 私が試したサービス", True, "主語が「私」でもブロック"),
        ("▶ 当サイトが比べたサービス", True, "主語が「当サイト」でもブロック"),
        ("▶ 公式サイトで内容と料金を確認する", False,
         "新しい見出し。行動も訴求も主張していない → 通過"),
        ("▶ このテーマで見られる公式サイト", False, "案内だけ → 通過"),
    ]
    ng = 0
    for heading, want, why in CASES:
        got = q.cta_box_text_gate(BOX.format(heading))
        ok = bool(got) == want
        print(("OK  " if ok else "NG  ") + why)
        if not ok:
            print(f"      期待: {'ブロック' if want else '通過'} / 実際: {got}")
            ng += 1
        elif want:
            print(f"      → {got[0]['reason'][:60]}")

    # 箱の外の普通の本文は対象外。ここまで止めると記事が書けなくなる
    outside = "<p>公式サイトで確認する方法は次のとおり。すべて無料で試せる場合もある。</p>"
    ok_out = not q.cta_box_text_gate(outside)
    print(("OK  " if ok_out else "NG  ") + "箱の外の本文は対象外")
    if not ok_out:
        ng += 1

    # 箱を使わず見出しの段落だけ置いている形（改修済み18本がこれだった）
    BARE = ('<p>▶ 次の一手（すべて無料）</p>'
            '<p><a href="//af.moshimo.com/af/c/click?a_id=1&url=x">'
            '→ スパトレの7日間無料体験を見る</a></p>')
    ok_bare = bool(q.cta_box_text_gate(BARE))
    print(("OK  " if ok_bare else "NG  ")
          + "**styled div を使わない見出し段落も検査する**")
    if not ok_bare:
        ng += 1

    # 「→」で始まるアンカーそのものは、この関数の担当ではない
    # （訴求は cta_claim_gate が台帳と照合する）
    anchor_only = ('<p><a href="//af.moshimo.com/af/c/click?a_id=1&url=x">'
                   '→ スパトレの7日間無料体験を見る</a></p>')
    ok_anchor = not q.cta_box_text_gate(anchor_only)
    print(("OK  " if ok_anchor else "NG  ")
          + "アンカー文言は cta_claim_gate の担当なので二重に止めない")
    if not ok_anchor:
        ng += 1

    # 一時非表示にした箱も対象外
    hidden = "<!-- cta-hidden:START -->" + \
        BOX.format("▶ さくらが確かめた・次の一手（すべて無料）") + \
        "<!-- cta-hidden:END -->"
    ok_hidden = not q.cta_box_text_gate(hidden)
    print(("OK  " if ok_hidden else "NG  ") + "非表示にした箱は検査しない")
    if not ok_hidden:
        ng += 1

    print(f"\nCTA見出しゲートの失敗 {ng}件")
    return ng


def run_country_cond():
    """制度の条件を、別の対象国から取り違えていないか。

    2026-08-09に実際にやった。GOV.UK の Youth Mobility Scheme のページは
    「18〜35歳の国（豪・加・NZ・韓）」と「18〜30歳の国（日本ほか）」を
    別々に載せていて、抽選は香港SAR旅券保持者と台湾の条項だった。
    日本を含むリストの直後に抽選の文があったので、日本に掛かると読み、
    記事238と289に「日本人は抽選で選ばれる必要がある」と書いてしまった。
    """
    CASES = [
        ("<p>抽選が必要な対象として掲載されているのは、"
         "香港SAR旅券保持者と台湾です。</p>", False,
         "国名つきの抽選の条件 → 通過"),
        ("<p>日本は18〜30歳の対象国として掲載されている。</p>", False,
         "国名つきの年齢条件 → 通過"),
        ("<p>申請には抽選がある。抽選に通らなければ申請できない。</p>", True,
         "**国名の無い抽選の断定 → ブロック**（今回の誤りの型）"),
        ("<p>年齢制限は申請時に30歳以下だ。</p>", True,
         "国名の無い年齢条件 → ブロック"),
        ("<p>イギリスでは申請時に30歳以下であることが条件になる。</p>", False,
         "国名つき → 通過"),
        ("<p>確認項目：行きたい国の公式ページで年齢条件を確認する。</p>", False,
         "読者への確認手順は条件の断定ではない → 通過"),
        # 2026-08-10 に直した誤検知。**条件の中身を言っていない文まで
        # 止めていた。** この関数の説明文じたいが、下2つを
        # 「正しい書き方」として挙げている
        ("<p>提案：年齢条件がある制度を使うなら、遅れること自体が"
         "リスクになる。</p>", False,
         "「年齢条件がある制度」は条件の中身を言っていない → 通過"),
        ("<p>ワーキングホリデーの年齢条件は国ごとに違う。</p>", False,
         "「国ごとに違う」は正しい書き方 → 通過"),
        ("<p>年齢の条件は制度と国によって違う。</p>", False,
         "同上 → 通過"),
        ("<p>ワーホリの年齢上限は30歳である。</p>", True,
         "**歳数を断定していて国名が無い → ブロック**（直したあとも残す）"),
    ]
    ng = 0
    for html, want, why in CASES:
        got = q.institution_country_gate(html)
        ok = bool(got) == want
        print(("OK  " if ok else "NG  ") + why)
        if not ok:
            print(f"      期待: {'ブロック' if want else '通過'} / 実際: {got}")
            ng += 1
    print(f"\n対象国ゲートの失敗 {ng}件")
    return ng


def run_cta_expiry():
    """期間限定の訴求が、失効日を過ぎたら自動で不合格になるか。

    「8月31日まで初月99円」を9月に出し続けると、
    確認済みの記録がそのまま虚偽になる。人の消し忘れを機械で止める。
    """
    import csv as _csv
    import tempfile
    ROWS = [
        # 恒久的な内容。expires_on 空欄 → いつでも通る
        {"service": "スパトレ", "promo_term": "無料", "claim": "7日間の無料期間",
         "official_url": "https://sptr.jp/", "checked_on": "2026-08-08",
         "expires_on": "", "landing_check": "", "verified": "yes", "note": ""},
        {"service": "スパトレ", "promo_term": "期間", "claim": "7日間の無料期間",
         "official_url": "https://sptr.jp/", "checked_on": "2026-08-08",
         "expires_on": "", "landing_check": "", "verified": "yes", "note": ""},
        # 失効済み
        {"service": "QQ English", "promo_term": "初月", "claim": "初月99円",
         "official_url": "https://www.qqeng.com/", "checked_on": "2026-08-09",
         "expires_on": "2026-08-31", "landing_check": "", "verified": "yes",
         "note": ""},
        # まだ有効
        {"service": "DMM英会話", "promo_term": "無料", "claim": "無料体験レッスン",
         "official_url": "https://eikaiwa.dmm.com/", "checked_on": "2026-08-09",
         "expires_on": "2099-12-31", "landing_check": "needs_japan_check",
         "verified": "yes", "note": ""},
    ]
    fd = Path(tempfile.mkdtemp()) / "cta.csv"
    with open(fd, "w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=list(ROWS[0].keys()))
        w.writeheader()
        w.writerows(ROWS)
    old_path, old_today = q.CTA_CLAIMS_CSV, q._today
    old_load = q.load_cta_claims
    q.CTA_CLAIMS_CSV = str(fd)
    # run_cta_gate が load_cta_claims をラムダに差し替えたままなので戻す。
    # ここは**本物の読み込み処理**を通さないと失効判定を検査できない
    q.load_cta_claims = REAL_LOAD_CTA_CLAIMS

    A = '<a href="//af.moshimo.com/af/c/click?a_id=1&url=x">{}</a>'
    CASES = [
        ("2026-08-15", "→ QQ Englishの初月99円を見る", False,
         "失効日前なら通る"),
        ("2026-09-01", "→ QQ Englishの初月99円を見る", True,
         "**失効日を過ぎたら verified=yes でもブロック**"),
        ("2026-09-01", "→ スパトレの7日間無料体験を見る", False,
         "expires_on が空欄なら失効しない"),
        ("2026-09-01", "→ DMM英会話の無料体験レッスンを試す", False,
         "失効日が先ならまだ通る"),
    ]
    ng = 0
    for today, anchor, want, why in CASES:
        q._today = lambda t=today: t
        got = q.cta_claim_gate(A.format(anchor))
        ok = bool(got) == want
        print(("OK  " if ok else "NG  ") + f"[{today}] " + why)
        if not ok:
            print(f"      期待: {'ブロック' if want else '通過'} / 実際: {got}")
            ng += 1

    q._today = lambda: "2026-09-01"
    exp = q.expired_cta_claims()
    ok_rep = len(exp) == 1 and exp[0]["service"] == "QQ English"
    print(("OK  " if ok_rep else "NG  ") + "失効した行は報告用に取り出せる")
    if not ok_rep:
        ng += 1

    # landing_check は訴求の裏取りとは別。値が入っていてもブロックしない
    q._today = lambda: "2026-08-15"
    ok_land = not q.cta_claim_gate(A.format("→ DMM英会話の無料体験レッスンを試す"))
    print(("OK  " if ok_land else "NG  ")
          + "needs_japan_check は着地確認の話なので訴求は止めない")
    if not ok_land:
        ng += 1

    q.CTA_CLAIMS_CSV, q._today, q.load_cta_claims = old_path, old_today, old_load
    print(f"\n失効ゲートの失敗 {ng}件")
    return ng


def run_claim_parse():
    """命題の解析を、構造化結果の**完全一致**で検証する。

    「解析に失敗しなかった」だけでは、報告と実際がずれても気づけない
    （2026-08-08に、コードは正しいのに報告表だけ違う例があった）。
    target / normalized_action / tense / experience / 数値属性 /
    needs_review をすべて固定し、原文にない動詞を作っていないことも確かめる。
    """
    import claim_extractor as ce

    # 「受ける」から派生してよい行動。ここに無いものへ変えたら動詞の捏造
    ALLOWED_REFINE = {"受ける_未分類": {"受講", "受験", "相談", "診断", "受ける"},
                      "受ける": {"受講", "受験", "相談", "診断", "受ける"}}

    CASES = [
        ("英語コーチングを25万円受けて、卒業した。",
         dict(target_surface="英語コーチング", target_normalized="英語コーチング",
              normalization_type="none", action_lemma="受ける",
              action_normalized="受ける", tense="unknown",
              experience="possible", attrs={"amount": "25万円"}, needs_review=True)),
        # 原文の語を保持しているか（授業→レッスンに置き換えない）
        ("私は授業を25分受けた。",
         dict(target_surface="授業", target_normalized="レッスン",
              normalization_type="exact_alias", action_lemma="受ける",
              action_normalized="受講", tense="past", experience="yes",
              attrs={"time_per_session": "25分"}, needs_review=False)),
        ("私はスクールに4万5000円を払った。",
         dict(target_surface="スクール", target_normalized="英会話スクール",
              normalization_type="context_enrichment", action_lemma="支払",
              action_normalized="支払", tense="past", experience="yes",
              attrs={"amount": "4万5000円"}, needs_review=False)),
        ("私は英語コーチングに25万円払った。",
         dict(target_surface="英語コーチング", target_normalized="英語コーチング", normalization_type="none", action_lemma="支払", action_normalized="支払", tense="past",
              experience="yes", attrs={"amount": "25万円"}, needs_review=False)),
        ("3ヶ月57万円のコーチングを受けた。",
         dict(target_surface="コーチング", target_normalized="英語コーチング", normalization_type="context_enrichment", action_lemma="受ける", action_normalized="受ける", tense="past",
              experience="possible",
              attrs={"duration": "3ヶ月", "amount": "57万円"}, needs_review=True)),
        ("私はスクールに4万5000円を溶かした。",
         dict(target_surface="スクール", target_normalized="英会話スクール", normalization_type="context_enrichment", action_lemma="浪費", action_normalized="浪費", tense="past",
              experience="yes", attrs={"amount": "4万5000円"}, needs_review=False)),
        ("私はTOEICを600点で受けた。",
         dict(target_surface="TOEIC", target_normalized="TOEIC", normalization_type="none", action_lemma="受ける", action_normalized="受験", tense="past",
              experience="yes", attrs={"score": "600点"}, needs_review=False)),
        ("私はレッスンを25分受けた。",
         dict(target_surface="レッスン", target_normalized="レッスン", normalization_type="none", action_lemma="受ける", action_normalized="受講", tense="past",
              experience="yes", attrs={"time_per_session": "25分"}, needs_review=False)),
        ("週3回レッスンを受けている。",
         dict(target_surface="レッスン", target_normalized="レッスン", normalization_type="none", action_lemma="受ける", action_normalized="受講", tense="progressive",
              experience="possible", attrs={"frequency": "3回"}, needs_review=False)),
        ("留学情報館を受けた。",
         dict(target_surface="留学情報館", target_normalized="留学情報館", normalization_type="none", action_lemma="受ける", action_normalized="受ける", tense="past",
              experience="possible", attrs={}, needs_review=True)),
        ("私はオンライン英会話を3ヶ月続けた。",
         dict(target_surface="オンライン英会話", target_normalized="オンライン英会話", normalization_type="none", action_lemma="継続", action_normalized="継続", tense="past",
              experience="yes", attrs={"duration": "3ヶ月"}, needs_review=False)),
    ]

    # 否定・法性の検証。否定でも本人の体験事実はある
    POLARITY_CASES = [
        ("私は英語コーチングを契約しなかった。", "negative", "factual", "yes"),
        ("その場で契約する必要もない。", None, None, None),          # 命題を作らない
        ("セブに大金を払う前に自分の部屋で味わえた。", "affirmative", "prospective", "no"),
        ("私はスパトレを試した。", "affirmative", "factual", "yes"),
        # 2026-08-08 の9周目で本番に出た誤りを、そのまま型として固定する
        # 「必要もない」を必要ないと読めず、体験にしてしまっていた
        ("英語ゼロに近い状態でも相談していいし、その場で契約する必要もない。",
         "affirmative", "necessity", "no"),
        # 「〜しなくても」は、しなかった事実の記述ではない
        ("TOEICを毎月受けなくても、自分で判定できる。",
         "negative", "concessive", "no"),
        # 「英語しか使わない」は、英語を使わなかった話ではない
        ("私は日中の1時間だけは英語しか使わないとルールを引く。",
         "affirmative", "factual", "yes"),
        # 可能・意志・許可は、やった事実ではない。
        # 案件名が主語のとき、ここを落とすと未使用サービスの体験談になる
        ("QQ Englishは、日本にいる間はオンラインで受けられて、地続きになる。",
         "affirmative", "possibility", "no"),
        ("ネイティブキャンプは予約なしなので、夜でもすぐ始められる。",
         "affirmative", "possibility", "no"),
        ("私は留学情報館の無料カウンセリングに申し込んで、相談してみるつもりだ。",
         "affirmative", "intention", "no"),
        # て形の節は文末に支配される。述語からの窓では「つもり」に届かない
        ("私は留学情報館に申し込んで、費用はどれくらいか、いつまでに何を"
         "準備すればいいかを相談してみるつもりだ。",
         "affirmative", "intention", "no"),
        ("留学情報館の無料カウンセリングは、行き先が決まっていない段階で受けていい。",
         "affirmative", "advice", "no"),
        # 問いは、やった事実の記述ではない
        ("私は渡航する日までに、英語を溶かさずに済む状態へたどり着けるのか。",
         "negative", "question", "no"),
    ]

    # 複合動詞の後ろ側から命題を作らない。
    # 「ワーホリで海外に行きたいと言い続けて」を「ワーホリを続けた」にしていた
    COMPOUND_CASES = [
        # (原文, その対象×行動の命題が出てよいか)
        ("27歳の私が、いつかワーホリで海外に行きたいと言い続けて、5年が過ぎた。",
         ("ワーホリ", "継続"), False),
        # 前側が行動語なら、そちらから正しく取れる
        ("私は3年間、英語を使い続けた。", ("英語", "利用"), True),
        # 連用形＋名詞は複合名詞。「払い損」は払った事実ではない
        ("単価が同じなら、受けきれない授業は払い損になる。", ("授業", "支払"), False),
        ("私はスクールに4万5000円を払った。", ("スクール", "支払"), True),
    ]

    # 連体修飾の主語。「〜しなかった人は」はさくらの体験ではない
    RELATIVE_CASES = [
        ("無料体験だけで本契約しなかった人は、そもそも分母に入っていない。",
         "第三者", "no"),
    ]
    ng = 0
    for text, pol, mod, exp in POLARITY_CASES:
        got, _ = ce.parse_all(text)
        r = got[0] if got else None
        if pol is None:
            ok = not got
        else:
            ok = bool(r) and (r["polarity"], r["modality"], r["experience"]) == (pol, mod, exp)
        print(("OK  " if ok else "NG  ") + text)
        if not ok:
            print(f"      期待: {pol}/{mod}/{exp}  実際: "
                  + (f"{r['polarity']}/{r['modality']}/{r['experience']}" if r else "(命題なし)"))
            ng += 1

    for text, (tgt, act), want in COMPOUND_CASES:
        got, _ = ce.parse_all(text)
        hit = any(r["target_surface"] == tgt and r["action_normalized"] == act
                  for r in got)
        ok = hit == want
        print(("OK  " if ok else "NG  ") + text)
        if not ok:
            print(f"      「{tgt}を{act}」は {'出るはず' if want else '出てはいけない'}"
                  f"  実際: {[(r['target_surface'], r['action_normalized']) for r in got]}")
            ng += 1

    for text, subj, exp in RELATIVE_CASES:
        # 直前の段落でさくらが主語だった状況を再現する
        got, _ = ce.parse_all(text, ("さくら", "inherited_paragraph"))
        r = got[0] if got else None
        ok = bool(r) and (r["subject"], r["experience"]) == (subj, exp)
        print(("OK  " if ok else "NG  ") + text)
        if not ok:
            print(f"      期待: {subj}/{exp}  実際: "
                  + (f"{r['subject']}/{r['experience']}" if r else "(命題なし)"))
            ng += 1

    for text, want in CASES:
        r = ce.parse(text)
        diffs = []
        if not r:
            diffs.append("命題が取れない")
        else:
            for k in ("target_surface", "target_normalized", "normalization_type",
                      "action_lemma", "action_normalized", "tense",
                      "experience", "attrs"):
                if r[k] != want[k]:
                    diffs.append(f"{k}: 期待={want[k]!r} 実際={r[k]!r}")
            if bool(r["needs_review"]) != want["needs_review"]:
                diffs.append(f"needs_review: 期待={want['needs_review']} "
                             f"実際={bool(r['needs_review'])}")
            # 原文にない動詞を作っていないか
            bases = {c[0] for c in ce.analyze(text)}
            act = r["action_normalized"]
            if act not in bases:
                if not any(act in ALLOWED_REFINE.get(b, set()) for b in bases):
                    diffs.append(f"原文にない動詞を生成: {act}（原文の行動: {bases}）")

        print(("OK  " if not diffs else "NG  ") + text)
        for d in diffs:
            print("      " + d)
        ng += 1 if diffs else 0

    print(f"\n命題解析の失敗 {ng}件")
    return ng


def run_claims():
    """抽出ツールを、WPを叩かずに1本ぶんの記事で通す。

    構文チェックだけでは実行時エラーを見つけられない
    （2026-08-08にキー分解の不一致で本番が落ちた）。
    """
    import pathlib
    import wp_audit
    wp_audit.published = lambda: [{
        "id": 1, "link": "https://example.test/a", "title": {"rendered": "テスト"},
        "content": {"rendered": (
            "<h2>見出しA</h2><p>私はスパトレを試した。</p>"
            "<p>利用者は無料体験を受けている。</p>"
            "<p>また英語学習を5年間後回しにしてきた。</p>"
            "<h2>見出しB</h2><p>無料体験に登録するなら条件を見る。</p>"
            "<blockquote>使ってみて良かったという口コミ。</blockquote>"
            "<p>私は無料体験を2回受けました。"
            "<a href='//af.moshimo.com/af/c/click?a_id=1'>公式</a></p>")}}]
    import claim_extractor as ce
    ce.OUT = pathlib.Path("/tmp/claims_selftest")
    ce.OUT.mkdir(exist_ok=True)
    ce.main()
    print("claim_extractor: 実行できた")
    return 0


if __name__ == "__main__":
    ng = run()
    print()
    ng += run_blockers()
    print()
    ng += run_cta_gate()
    print()
    ng += run_cta_box()
    print()
    ng += run_cta_expiry()
    print()
    ng += run_country_cond()
    print()
    ng += run_claim_parse()
    print()
    ng += run_claims()
    sys.exit(1 if ng else 0)
