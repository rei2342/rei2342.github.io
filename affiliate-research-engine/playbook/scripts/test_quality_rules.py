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


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
