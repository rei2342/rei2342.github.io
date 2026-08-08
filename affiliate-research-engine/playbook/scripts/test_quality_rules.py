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




def run_claim_parse():
    """命題の解析を、構造化結果の**完全一致**で検証する。

    「解析に失敗しなかった」だけでは、報告と実際がずれても気づけない
    （2026-08-08に、コードは正しいのに報告表だけ違う例があった）。
    target / normalized_action / tense / experience / 数値属性 /
    needs_review をすべて固定し、原文にない動詞を作っていないことも確かめる。
    """
    import claim_extractor as ce

    # 「受ける」から派生してよい行動。ここに無いものへ変えたら動詞の捏造
    ALLOWED_REFINE = {"受ける_未分類": {"受講", "受験", "相談", "診断", "受ける"}}

    CASES = [
        ("英語コーチングを25万円受けて、卒業した。",
         dict(target_surface="英語コーチング", target_normalized="英語コーチング",
              normalization_type="none", action_lemma="受ける_未分類",
              action_normalized="受ける", tense="unknown",
              experience="possible", attrs={"amount": "25万円"}, needs_review=True)),
        # 原文の語を保持しているか（授業→レッスンに置き換えない）
        ("私は授業を25分受けた。",
         dict(target_surface="授業", target_normalized="レッスン",
              normalization_type="exact_alias", action_lemma="受ける_未分類",
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
         dict(target_surface="コーチング", target_normalized="英語コーチング", normalization_type="context_enrichment", action_lemma="受ける_未分類", action_normalized="受ける", tense="past",
              experience="possible",
              attrs={"duration": "3ヶ月", "amount": "57万円"}, needs_review=True)),
        ("私はスクールに4万5000円を溶かした。",
         dict(target_surface="スクール", target_normalized="英会話スクール", normalization_type="context_enrichment", action_lemma="浪費", action_normalized="浪費", tense="past",
              experience="yes", attrs={"amount": "4万5000円"}, needs_review=False)),
        ("私はTOEICを600点で受けた。",
         dict(target_surface="TOEIC", target_normalized="TOEIC", normalization_type="none", action_lemma="受ける_未分類", action_normalized="受験", tense="past",
              experience="yes", attrs={"score": "600点"}, needs_review=False)),
        ("私はレッスンを25分受けた。",
         dict(target_surface="レッスン", target_normalized="レッスン", normalization_type="none", action_lemma="受ける_未分類", action_normalized="受講", tense="past",
              experience="yes", attrs={"time_per_session": "25分"}, needs_review=False)),
        ("週3回レッスンを受けている。",
         dict(target_surface="レッスン", target_normalized="レッスン", normalization_type="none", action_lemma="受ける_未分類", action_normalized="受講", tense="progressive",
              experience="possible", attrs={"frequency": "3回"}, needs_review=False)),
        ("留学情報館を受けた。",
         dict(target_surface="留学情報館", target_normalized="留学情報館", normalization_type="none", action_lemma="受ける_未分類", action_normalized="受ける", tense="past",
              experience="possible", attrs={}, needs_review=True)),
        ("私はオンライン英会話を3ヶ月続けた。",
         dict(target_surface="オンライン英会話", target_normalized="オンライン英会話", normalization_type="none", action_lemma="継続", action_normalized="継続", tense="past",
              experience="yes", attrs={"duration": "3ヶ月"}, needs_review=False)),
    ]

    ng = 0
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
            bases = {a for a, _t, _s, _p, _tn in ce.analyze(text)}
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
    ng += run_claim_parse()
    print()
    ng += run_claims()
    sys.exit(1 if ng else 0)
