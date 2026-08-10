#!/usr/bin/env python3
"""
test_social_spec.py
SNS側の仕様とゲートを検査する。

  python test_social_spec.py

見るもの
  1. 直書き検査 … 5経路のどこにも仕様の実体が残っていないか
  2. 仕様の中身 … 必須キーと、XとThreadsが別物になっているか
  3. ゲート    … 落とすべきものが落ち、通すべきものが通るか
  4. 在庫      … 状態遷移が決まりどおりか
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss
import social_gate as sg
import social_inventory as inv

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
fails = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "NG  ") + name + (f" … {detail}" if detail else ""))
    if not ok:
        fails.append(name)


spec = ss.load_spec()

# ── 1. 直書き検査 ────────────────────────────────────
# 旧5経路に、仕様の実体（ペルソナ・実測例・長さ・お手本）が残っていないか
HARDCODED = [
    ("旧ペルソナ", r"27歳・営業事務|4\.5万円を溶かした|5年後回し"),
    ("実測例の直書き", r"（54回）|（40回）|（38回）|（37回）"),
    ("お手本の直書き", r"3日、4日、2日|歯みがきのあと"),
    ("長さの直書き", r"60〜90字|300字以内|1行は20字"),
    ("句点禁止の直書き", r"句点（。）を使わない|句点を使わない"),
    ("固定の締め", r"続きはnoteに書いた"),
]
# daily-article-drafter.yml は Instagram のキャプションも作る。
# **そこは今回の対象外**（XとThreadsだけ）なので、直書き検査からは外し、
# 代わりに「SNS文を作っていないこと」だけを見る。
TARGETS = [
    REPO / ".github/workflows/x-poster.yml",
    REPO / ".github/workflows/threads-note-cannon.yml",
    ROOT / "scripts/x_promo.py",
    ROOT / "scripts/threads_builder.py",
]
for path in TARGETS:
    if not path.exists():
        check(f"{path.name}: 廃止されている", True, "ファイルが無い")
        continue
    src = path.read_text(encoding="utf-8")
    # 説明コメントに語が出るのは許す。実行される行だけ見る
    body = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    for label, pat in HARDCODED:
        m = re.search(pat, body)
        check(f"{path.name}: {label}が残っていない", not m,
              m.group(0) if m else "")

# 記事ドラフターが SNS文とWordPressメモを作らなくなっているか
drafter = (REPO / ".github/workflows/daily-article-drafter.yml") \
    .read_text(encoding="utf-8")
check("drafter: Threads文を作っていない",
      "THREADS_1" not in drafter and "workspace/threads" not in drafter)
check("drafter: 【Threads用】メモを作っていない",
      "【Threads用】" not in drafter)
check("drafter: SNSの生成は公開後に回す、と書いてある",
      "social_generate.py" in drafter)
check("drafter: Instagramにも旧ペルソナが残っていない",
      "27歳・営業事務" not in drafter)
check("drafter: Instagramが正本の persona を読んでいる",
      "social_spec" in drafter and 'persona' in drafter)

# 投稿の口は social_post.py だけ
posters = [p for p in (REPO / ".github/workflows").glob("*.yml")
           if "create_tweet" in p.read_text(encoding="utf-8")]
check("ワークフローが直接ツイートしていない", not posters,
      " ".join(p.name for p in posters))
x_poster = (REPO / ".github/workflows/x-poster.yml").read_text(encoding="utf-8")
check("x-poster は social_post.py を呼ぶだけ",
      "social_post.py" in x_poster and "anthropic" not in x_poster)
check("x-poster のスロットが1日1枠",
      x_poster.count("cron:") == 1, f"{x_poster.count('cron:')}枠")

# アダプターにも直書きが無いこと
adapter = (ROOT / "scripts/social_spec.py").read_text(encoding="utf-8")
adapter_body = re.sub(r'"""[\s\S]*?"""|^\s*#.*$', "", adapter, flags=re.M)
for label, pat in HARDCODED:
    m = re.search(pat, adapter_body)
    check(f"social_spec.py: {label}が直書きされていない", not m,
          m.group(0) if m else "")

# ── 2. 仕様の中身 ────────────────────────────────────
for k in ("persona", "facts", "style", "forbidden", "extraction", "x",
          "threads", "lifecycle", "publish_gates", "rollout", "frequency",
          "paths", "duplicate"):
    check(f"仕様に {k} がある", k in spec)
check("仕様が pilot（試作の承認まで approved にしない）",
      spec["status"] == "pilot", spec["status"])
check("XとThreadsで使う素材が違う",
      set(spec["extraction"]["x_uses"]) &
      set(spec["extraction"]["threads_uses"]) == set(),
      f"X={spec['extraction']['x_uses']} "
      f"Threads={spec['extraction']['threads_uses']}")
check("Threadsで句点を禁止していない", spec["threads"]["kuten"] == "使ってよい")
check("Xは同じ投稿にURLを置く",
      spec["x"]["url"]["reply_url_post"] is False)
check("Xのランダムテーマを禁止している", spec["x"]["no_random_theme"] is True)
check("最初の段階は人が承認",
      spec["rollout"]["stages"][0]["x"] == "人が承認"
      and spec["rollout"]["stages"][0]["threads"] == "人が承認")
check("1日1件までにしている", spec["frequency"]["posts_per_day_max"] == 1)

# ── 3. ゲート ────────────────────────────────────────
ART = {"id": "521", "title": "テスト記事", "status": "publish",
       "modified_gmt": "2026-08-09T11:10:13",
       "url": "https://sakura-eigo.com/toeic-listening-325-to-improvement/",
       "body": "確認項目：音声を1つ聞いたあと、設問を見ずに内容を1文で言えるかを"
               "試す。音そのものが拾えていない場合と、拾えているのに設問まで"
               "残らない場合とでは、次にやることが変わる。"
               "確認項目：意味が一拍遅れる感覚があるかを確かめる。"
               "確認項目：自分の音を録って、お手本と比べられる手段があるかを見る。"
               "流し終わったあとに内容を1文で言えるかを試す。"
               "言えない回が多いなら、その時間は入力になっていない可能性がある。"
               "記録するのは再生時間ではなく、言えた回数のほう。"
               "最初の2週間の組み方を3つの確認項目として並べる。"}
U = ART["url"] + "?utm_source=x"
UT = ART["url"] + "?utm_source=threads"


def gate_ids(res):
    return {g for g, ok, _ in res if not ok}


def x_parts(body):
    return [body.rstrip() + "\n" + U]


good_x = ("リスニングだけ動かないとき、教材を増やす前に見る場所があります。\n"
          "音声を1つ聞いたあと、設問を見ずに内容を1文で言えるか試すと、"
          "聞き取りの問題か保持の問題かを分けられます。\n\n"
          "止まっている場所を切り分ける3つの確認項目をまとめました")
check("正しいX投稿は通る",
      sg.passed(sg.run_gates(spec, "x", x_parts(good_x), ART)),
      sg.fmt(sg.run_gates(spec, "x", x_parts(good_x), ART)))

CASES = [
    ("架空の年齢", "27歳になって英語をやり直しました。まず音声を1つ聞いて、"
                   "内容を1文で言えるかを試してみてください。\n\n"
                   "確認項目をまとめました", "fact_gate"),
    ("架空の点数", "私はTOEICで600点を取りました。音声を1つ聞いて内容を"
                   "1文で言えるかを試してください。\n\n確認項目をまとめました",
     "fact_gate"),
    ("架空の金額", "私はスクールに45000円を払いました。音声を1つ聞いて内容を"
                   "1文で言えるか試してください。\n\n確認項目をまとめました",
     "fact_gate"),
    ("架空の期間", "私は3ヶ月間このやり方を続けました。音声を1つ聞いて内容を"
                   "1文で言えるか試してください。\n\n確認項目をまとめました",
     "fact_gate"),
    ("記事に無い数字", "リスニングが動かないとき、まず見る場所があります。\n"
                       "1日90分を12週続けると変わります。\n\n"
                       "確認項目をまとめました", "subset_gate"),
    ("プレースホルダー", "リスニングが動かないときに見る場所があります。\n"
                         "（記事URLを貼る）を見てください。\n\n"
                         "確認項目をまとめました", "broken_output"),
    ("生成区切り文字", "===THREADS_2===\nリスニングが動かないときに見る場所が"
                       "あります。\n\n確認項目をまとめました", "broken_output"),
]
for name, body, want in CASES:
    res = sg.run_gates(spec, "x", x_parts(body), ART)
    check(f"落とす: {name}", want in gate_ids(res),
          " ".join(sorted(gate_ids(res))))

# URLまわり
res = sg.run_gates(spec, "x", [good_x], ART)
check("落とす: XにURLが無い", "link_gate" in gate_ids(res))
res = sg.run_gates(spec, "x", [good_x + "\n" + ART["url"]], ART)
check("落とす: utmが無い", "link_gate" in gate_ids(res))
res = sg.run_gates(spec, "x", [good_x + "\nhttps://example.com/"], ART)
check("落とす: example.com", "link_gate" in gate_ids(res)
      or "broken_output" in gate_ids(res))
res = sg.run_gates(spec, "x", [good_x + "\nhttps://sakura-eigo.com/?p=583"],
                   ART)
check("落とす: 下書きURL", "link_gate" in gate_ids(res))
res = sg.run_gates(spec, "x", [U], ART)
check("落とす: URLだけの投稿", "style_gate" in gate_ids(res))

# 記事の状態
draft = dict(ART, status="draft")
check("落とす: 記事が下書き",
      "article_published" in gate_ids(
          sg.run_gates(spec, "x", x_parts(good_x), draft)))
check("落とす: 記事が改稿された",
      "article_unchanged" in gate_ids(
          sg.run_gates(spec, "x", x_parts(good_x), ART,
                       stock_modified="2026-08-01T00:00:00")))

# Threads
th1 = ("TOEICのリスニングだけが動かないとき、参考書を替える前に見る場所が"
       "あります。\n\n同じ「聞けない」でも、音そのものが拾えていない場合と、"
       "拾えているのに設問まで残らない場合では、次にやることが変わります。"
       "まず音声を1つ聞いて、設問を見ずに内容を1文で言えるかを試して"
       "みてください。")
th2 = ("切り分けが済んだら、次の3つを順に確かめます。\n\n"
       "・流し終わったあとに内容を1文で言えるか\n"
       "・意味が一拍遅れる感覚があるか\n"
       "・自分の音を録って、お手本と比べられるか\n\n"
       "言えない回が多い時間は、再生時間としては積み上がっていても、"
       "入力にはなっていない可能性があります。記録するのは再生時間ではなく、"
       "言えた回数のほうです。\n\n"
       "3つの確認項目と、最初の2週間の組み方は記事にまとめています。")
tparts = [th1, th2.rstrip() + "\n" + UT]
res = sg.run_gates(spec, "threads", tparts, ART)
check("句点のある自然なThreads文は通る", sg.passed(res), sg.fmt(res))
check("落とす: Threadsの最終投稿にURLが無い",
      "link_gate" in gate_ids(sg.run_gates(spec, "threads", [th1, th2], ART)))
check("落とす: 矢印で終わる1投稿目",
      "style_gate" in gate_ids(
          sg.run_gates(spec, "threads", [th1 + "\n\n理由はこれ↓",
                                         th2.rstrip() + "\n" + UT], ART)))
check("絵文字0個でも通る", sg.passed(res))

# ── 3b. leak_patterns は止めすぎない ────────────────
# **数字があるだけで落とさない。** 主語・事実の種類・出典・fact ID を見る
PASS_CASES = [
    ("出典つきの公式料金",
     "受講料は公式サイトで月17600円と案内されています（2026年8月9日時点）。"),
    ("一般的な年齢条件",
     "ワーキングホリデーの年齢の上限は国ごとに決まっていて、30歳までの国が多いです。"),
    ("仮定の試算",
     "例えば4週間で100時間なら、1時間あたりの費用はこの割り算で出せます。"),
    ("fact IDつきの一人称",
     "私はTOEIC600点を取りました。<!--fact:F001-->"),
    ("読者に向けた年数の話",
     "英語を3年やっていない人でも、確かめるところは同じです。"),
]
for name, sent in PASS_CASES:
    ok, detail = sg.fact_gate(spec, sent)
    # fact IDつきは台帳が空なので落ちてよい。**理由が「台帳に無い」であること**を見る
    if name == "fact IDつきの一人称":
        check(f"通す/落とす理由が正しい: {name}",
              (not ok) and "F001" in detail or ok, detail)
    else:
        check(f"通す: {name}", ok, detail)

BLOCK_CASES = [
    ("自分の年齢", "私は27歳から英語をやり直しました。"),
    ("自分のスコア", "私のTOEICは600点でした。"),
    ("自分の支払い", "私はスクールに45000円を払いました。"),
    ("利用の告白", "オンライン英会話に登録しました。"),
    ("心理の告白", "そのとき、意志の問題ではないと気づいた。"),
]
for name, sent in BLOCK_CASES:
    ok, detail = sg.fact_gate(spec, sent)
    check(f"落とす: {name}", not ok, detail)

# ── 3c. 加重文字数 ──────────────────────────────────
w = spec["x"]["weighted"]
check("URLは長さによらず23で数える",
      sg.weighted_len(spec, "https://sakura-eigo.com/a-very-long-slug/"
                            "?utm_source=x") == w["url_weight"])
check("全角は2・半角は1で数える",
      sg.weighted_len(spec, "あいう") == 6
      and sg.weighted_len(spec, "abc") == 3)
long_x = "あ" * 130 + "\n" + U
check("加重で上限を超えたら落とす",
      "length_gate" in gate_ids(sg.run_gates(spec, "x", [long_x], ART)),
      f"加重{sg.weighted_len(spec, long_x)}")

# ── 3d. 命題の照合 ──────────────────────────────────
ART2 = dict(ART, body="確認項目：音声を1つ聞いたあと、設問を見ずに内容を1文で"
                      "言えるかを試す。言えるのに設問で落とすなら保持の問題、"
                      "言えないなら聞き取りの問題の可能性がある。")
over = ("リスニングが止まる原因は保持です。音声を1つ聞いて、"
        "内容を1文で言えるかを試してください。\n\n確認項目をまとめました")
check("落とす: 記事が可能性としているのに言い切っている",
      "subset_gate" in gate_ids(
          sg.run_gates(spec, "x", x_parts(over), ART2)))
hedged = ("リスニングが止まるのは、保持のほうかもしれません。"
          "音声を1つ聞いて、内容を1文で言えるかを試してください。\n\n"
          "確認項目をまとめました")
check("通す: 同じ内容を可能性として書いたもの",
      "subset_gate" not in gate_ids(
          sg.run_gates(spec, "x", x_parts(hedged), ART2)))

# ── 3e. 型の重なり ──────────────────────────────────
recent = [{"template_ids": ["matomemashita"]} for _ in range(2)]
_, warn = sg.template_gate(spec, ["確認項目をまとめました"], recent)
check("同じ締めが3件目になったら警告", bool(warn), " ".join(warn))
_, warn0 = sg.template_gate(spec, ["確認項目をまとめました"], recent[:1])
check("2件目までは警告しない", not warn0)

# 重複
hist = [{"text": good_x, "stock_id": "X-999-a"}]
check("落とす: 同じ本文",
      "duplicate_gate" in gate_ids(
          sg.run_gates(spec, "x", x_parts(good_x), ART, history=hist)))
check("落とす: XとThreadsが同文",
      "cross_platform_gate" in gate_ids(
          sg.run_gates(spec, "x", x_parts(good_x), ART,
                       other_text="\n\n".join(x_parts(good_x)))))
check("XとThreadsが別文なら通る",
      "cross_platform_gate" not in gate_ids(
          sg.run_gates(spec, "x", x_parts(good_x), ART,
                       other_text="\n\n".join(tparts))))

# ── 4. 在庫の状態遷移 ────────────────────────────────
st = inv.new_stock(spec, "x", ART, x_parts(good_x), {}, [])
try:
    inv.transition(spec, st, "posted")
    check("generated から posted へ飛べない", False, "飛べてしまった")
except ValueError:
    check("generated から posted へ飛べない", True)
inv.transition(spec, st, "gated")
inv.transition(spec, st, "awaiting_approval")
inv.transition(spec, st, "approved")
inv.transition(spec, st, "scheduled")
inv.transition(spec, st, "posted")
check("決められた順なら posted まで行ける", st["state"] == "posted")

# ── 5. 実際の在庫 ────────────────────────────────────
rows = inv.all_stock(spec)
# 2026-08-10 の最終調整で10件すべてが承認され、そのうち X-546-b だけを
# 実投稿テストに出した。**残りは approved のまま動かさない。**
_live = [s for _, s in rows if s["state"] != "stale"]
check("退役を除いた在庫が10件", len(_live) == 10, str(len(_live)))
check("approved か posted のどちらかしか無い",
      all(s["state"] in ("approved", "posted") for s in _live),
      str(sorted({s["state"] for s in _live})))
# **scheduled のまま止まっているものが無い。**
# 投稿に失敗したのに予約済みで残っていると、次の実行で二重に出る
check("scheduled で止まっているものが無い",
      not [s for s in _live if s["state"] == "scheduled"])
_posted = [s for s in _live if s["state"] == "posted"]
check("実投稿テストで出したのは1件だけ", len(_posted) == 1,
      " / ".join(s["stock_id"] for s in _posted))
for s in _posted:
    check(f"{s['stock_id']}: 投稿IDと投稿時刻が入っている",
          bool(s.get("posted_id")) and bool(s.get("posted_at")),
          f"{s.get('posted_id')} / {s.get('posted_at')}")
    _hist = [r for r in inv.read_history(spec, s["platform"])
             if r.get("stock_id") == s["stock_id"] and r.get("result") == "ok"]
    check(f"{s['stock_id']}: 履歴に成功が1本だけ残っている", len(_hist) == 1,
          f"{len(_hist)}本")
    check(f"{s['stock_id']}: 名指しで選んだ記録が残っている",
          _hist and _hist[-1].get("selected_by") == "stock_id")
# 取り消しは履歴に残っていること。**黙って戻さない**
revoked = [s for _, s in rows if s.get("revoked_reason")]
check("承認の取り消しに理由が残っている", len(revoked) >= 3,
      f"{len(revoked)}件")
for _, s in rows:
    check(f"{s['stock_id']}: ゲート全通過",
          all(g["ok"] for g in s["gate_results"]),
          "; ".join(g["id"] for g in s["gate_results"] if not g["ok"]))

# ── 6. 試作の在庫 ────────────────────────────────────
rows = [s for _, s in inv.all_stock(spec)]
types = {s["article_id"]: s.get("post_type") for s in rows}
# 仕様の規則は「直近10本で同じ型が3件以上続いたら別の型を選ぶ」。
# 「全部違う」は試作のあいだの思い込みだった。規則のほうに合わせる
from collections import Counter as _C
_tc = _C(types.values())
check(f"同じ型が3件以上ない（上限{spec['post_types']['max_same'] if 'max_same' in spec['post_types'] else 2}）",
      all(n <= 2 for n in _tc.values()), str(dict(_tc)))
for s in rows:
    check(f"{s['stock_id']}: 型を選んだ理由がある",
          bool(s.get("post_type_reason")))
    # 警告が出ていても、**理由が書いてあれば例外**として通す。
    # 指定された本文を書き換えないための逃げ道を、記録つきで用意する
    check(f"{s['stock_id']}: 文型の警告が無い、または理由つきの例外",
          not s.get("template_warnings")
          or bool(s.get("template_exception_reason")),
          " ".join(s.get("template_warnings") or []))
    if s["platform"] == "x":
        check(f"{s['stock_id']}: 加重が上限内",
              s.get("weighted_len", 0) <= spec["x"]["weighted"]["hard_limit"],
              str(s.get("weighted_len")))

# ── 7. 判定の分離 ────────────────────────────────────
import social_claims as sc
ART3 = dict(ART, body="無料期間は自分の生活で無理なく使えるかを確かめる時間にもできる。")
short_plain = "手帳に書きます。"
short_risky = "月額だけでは決まりません。"
r1 = sc.check(spec, [short_plain], ART3)[0]
r2 = sc.check(spec, [short_risky], ART3)[0]
check("内容語の少ない文を ok にしない", r1["verdict"] == "unjudged",
      r1["verdict"])
check("短くても言い切りで危うい話題は人へ回す",
      r2["verdict"] == "needs_human_review", r2["verdict"])
c = sc.counts([r1, r2])
check("supported に unjudged を混ぜていない", c["supported"] == 0, str(c))
check("counts が4つに分かれている",
      set(c) == {"supported", "unsupported", "unjudged",
                 "needs_human_review", "total"})
for _, st in inv.all_stock(spec):
    cc = st.get("claim_counts") or {}
    check(f"{st['stock_id']}: unsupported 0", cc.get("unsupported") == 0,
          str(cc))

# ── 7. 温度と会話（2026-08-10 追加）──────────────────
# 温度を上げるゲートは、**通すべきものまで落としやすい。**
# 実際に誤爆した4つを、そのまま検査として残す
check("架空の共感は落とす",
      not sg.empathy_without_evidence(spec, "私も3日でやめました。")[0])
check("相づちだけの共感も落とす",
      not sg.empathy_without_evidence(spec, "その気持ち、わかります。")[0])
check("「〜が分かります」は落とさない（2026-08-10に誤爆）",
      sg.empathy_without_evidence(
          spec, "1回だけ数えてみると、どこで手が止まるかが分かります。")[0])
check("fact ID があれば通す",
      sg.empathy_without_evidence(
          spec, "私も3日でやめました。<!--fact:F001-->")[0])

check("命令と否定が続くと警告",
      sg.cold_tone_warning(
          spec, "確かめてください。これは原因ではありません。"
                "次に見てください。"))
check("1回までなら警告しない",
      not sg.cold_tone_warning(spec, "一度だけ確かめてみてください。"))

check("同じ語尾が3文続くと警告",
      sg.sentence_height(spec, ["朝に開きます。昼に開きます。夜に開きます。"]))
check("絵文字があっても語尾を数える（2026-08-10に数え落とした）",
      sg.sentence_height(spec, ["朝に開きます。昼に開きます。夜に開きます🌿"]))
check("役割の無い絵文字は警告",
      sg.emoji_role(spec, ["音を聞いてみます🎧"]))
check("役割のある絵文字は警告しない",
      not sg.emoji_role(spec, ["音を聞いてみます🌿"]))

TQ = [{"platform": "threads", "text": "問いはありません。"}] * 4
check("Threadsの直近5本に問いかけが無いと警告",
      sg.conversation_mix(spec, "threads", ["問いはありません。"], TQ))
check("utmの`?`を問いかけと数えない（2026-08-10に誤爆）",
      sg.conversation_mix(
          spec, "threads",
          ["問いはありません。\nhttps://x.test/a?utm_source=threads"],
          [{"platform": "threads",
            "text": "問いはありません。https://x.test/b?utm_source=threads"}] * 4))

check("参考投稿の記録がある", not sg.market_reference_gate(spec),
      " / ".join(sg.market_reference_gate(spec)))
check("外部観測の未記録が0件",
      len((__import__("yaml").safe_load(
          (ROOT / spec["market_reference"]["file"]).read_text(
              encoding="utf-8")) or {}).get("references") or []) >= 6)

# 形の比較。**同じ記事を割っただけのA/B案を作らない**
_rows = [s for _, s in inv.all_stock(spec)]
check("Threadsが1投稿型2本・2投稿型3本",
      not sg.format_mix_gate(spec, _rows),
      " / ".join(sg.format_mix_gate(spec, _rows)))
for _s in _rows:
    check(f"{_s['stock_id']}: 投稿後に比べる欄がある",
          set(_s.get("metrics") or {}) ==
          set(spec["threads"]["metrics"]["fields"]))
    check(f"{_s['stock_id']}: 数値がまだ入っていない",
          all(v is None for v in (_s.get("metrics") or {}).values()))
check("役割の無い絵文字が在庫に残っていない",
      not [w for _s in _rows for w in (_s.get("tone_warnings") or [])
           if "役割の無い絵文字" in w],
      " / ".join(w for _s in _rows for w in (_s.get("tone_warnings") or [])
                 if "役割の無い絵文字" in w))

# 引用された世間の言い方を、書き手の主張として照合しない
q, was = sc.strip_attribution(
    "「現地に行けば早く伸びる」と聞くと、留学の総額も正当化したくなります。")
check("引用は主張から外す", was and "伸びる" not in q, q)
check("引用でない鉤括弧は外さない",
      not sc.strip_attribution("「予定した日に開けたか」を見ます。")[1])

# 冒頭の型は冒頭の行だけで見る
_, tw = sg.template_gate(
    spec, ["場面を置きます。\n今日ためせるのは、この順番です。"],
    [{"template_ids": ["topic_open"]}] * 3)
check("本文中の一文を「冒頭の型」に数えない（2026-08-10に誤検知）", not tw,
      " / ".join(tw))

for _, st in inv.all_stock(spec):
    check(f"{st['stock_id']}: 温度の検査を記録している",
          "tone_warnings" in st)

# ── 12. 投稿対象の名指し（--stock-id）─────────────────
# 2026-08-10 に追加。**他の在庫を revoke せずに1件だけ試せること**を守る。
# ここで守るのは「選び方」と「止まり方」で、実投稿はしない（--approve を付けない）
import hashlib as _hl
import social_post as sp


def _fingerprint():
    """全在庫の中身。1バイトでも変わったら分かるようにしておく。"""
    return {s["stock_id"]: _hl.sha256(
        p.read_bytes()).hexdigest() for p, s in inv.all_stock(spec)}


_before = _fingerprint()

# 名指しで1件だけ選ぶ
# **投稿済みでない在庫で試す。** X-546-b は 2026-08-10 の実投稿テストで
# posted になったので、名指しの対象としては approved の別件を使う
_TARGET = "X-526-b"
_s, _why = sp.pick_by_id(spec, "x", _TARGET)
check("名指しした在庫だけを選ぶ", _s is not None and _s["stock_id"] == _TARGET,
      _why)
check("投稿済みの stock_id は名指しでも投稿しない",
      sp.pick_by_id(spec, "x", "X-546-b")[0] is None,
      sp.pick_by_id(spec, "x", "X-546-b")[1])
check("名指しは最古の承認済みを選ばない",
      _s is not None and _s["stock_id"] != "X-23-a")

# 無い stock_id
_s2, _why2 = sp.pick_by_id(spec, "x", "X-9999-z")
check("stock_id が無ければ止まる", _s2 is None and "無い" in _why2, _why2)

# platform 違い
_s3, _why3 = sp.pick_by_id(spec, "x", "THREADS-546-b")
check("platform が違えば止まる", _s3 is None and "threads" in _why3, _why3)

# approved 以外
_s4, _why4 = sp.pick_by_id(spec, "x", "X-546-a")   # stale
check("approved 以外なら止まる", _s4 is None and "stale" in _why4, _why4)

# 表示した本文と送る本文のハッシュ
_txt = _s["text"]
check("同じ本文なら同じハッシュ", sp.text_hash(_txt) == sp.text_hash(_txt))
check("1文字でも違えば別のハッシュ",
      sp.text_hash(_txt) != sp.text_hash(_txt + "。"))

# 表示した本文と送る本文が違えば止まる
_h = sp.text_hash(_txt)
check("表示と送信が同じなら通る", sp.verify_unchanged(spec, _s, _h, _txt)[0],
      sp.verify_unchanged(spec, _s, _h, _txt)[1])
check("送る本文が1文字でも違えば止まる",
      not sp.verify_unchanged(spec, _s, _h, _txt + "。")[0])
check("表示したハッシュが違えば止まる",
      not sp.verify_unchanged(spec, _s, "0" * 64, _txt)[0])
_tamper = dict(_s, text=_txt + "追記")
check("表示後に在庫ファイルが書き換わったら止まる",
      not sp.verify_unchanged(spec, _tamper, sp.text_hash(_tamper["text"]),
                              _tamper["text"])[0])
check("本文と content_hash が合わなければ止まる",
      not sp.verify_unchanged(spec, dict(_s, content_hash="deadbeef"),
                              _h, _txt)[0])

# --approve が無ければプレビューだけ。**1件も状態が動かない**
_run = subprocess.run(
    [sys.executable, str(ROOT / "scripts/social_post.py"),
     "--platform", "x", "--stock-id", _TARGET],
    capture_output=True, text=True, cwd=str(ROOT))
check("--approve が無ければプレビューで終わる",
      _run.returncode == 0 and "投稿していない" in _run.stdout,
      _run.stdout[-200:] + _run.stderr[-200:])
check("プレビューに本文が全文出る", _txt.strip() in _run.stdout)

# 止まる側も subprocess で見る（終了コード1で、投稿へ進まない）
for _sid, _label in [("X-9999-z", "存在しない"), ("THREADS-546-b", "媒体違い"),
                     ("X-546-a", "approved以外")]:
    _r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/social_post.py"),
         "--platform", "x", "--stock-id", _sid, "--approve"],
        capture_output=True, text=True, cwd=str(ROOT))
    check(f"{_label}の stock_id は --approve でも投稿しない",
          _r.returncode == 1 and "投稿しない" in _r.stdout,
          _r.stdout[-200:] + _r.stderr[-200:])

check("名指しの実行で他の在庫が1件も変わらない", _fingerprint() == _before,
      " / ".join(k for k, v in _fingerprint().items()
                 if _before.get(k) != v))

# API が失敗したら approved のまま。**投稿していないのに状態を動かさない**
# （実際に API を叩けないので、順序と失敗時の分岐をソースで見る）
_src = (ROOT / "scripts/social_post.py").read_text(encoding="utf-8")
_src = _src[_src.index("def main("):]     # mark_posted（手貼り記録）とは分ける
_i_post = _src.index("pid = post_to_x(")
_i_sched = _src.index('inv.transition(spec, s, "scheduled", scheduled_at')
check("API を呼ぶ前に scheduled へ進めない", _i_post < _i_sched)
_err = _src[_src.index("except Exception as e:"):_i_sched]
check("API 失敗時に stale へ落とさない（approved のまま）",
      "stale" not in _err, _err[:120])
check("API 失敗を履歴に残す", '"result": "error"' in _err)
check("成功したときだけ posted へ動かす",
      _src.index('inv.transition(spec, s, "posted"') > _i_post)

# URLの差し替えは、クエリだけ。**本文には触らせない**（2026-08-10）
import copy as _cp
import social_retag as sr

_base = _s["article_url"].split("?")[0]
_okurl = _base + "?utm_source=x&utm_medium=social&utm_content=retag_test"
_r, _w = sr.retag(spec, _cp.deepcopy(_s), _okurl, "テスト")
check("URLのクエリを差し替えられる", _r is not None and _okurl in _r["text"], _w)
check("差し替えでURL以外が変わらない",
      _r is not None and
      [sg.URL.sub("<URL>", p) for p in _r["thread_parts"]] ==
      [sg.URL.sub("<URL>", p) for p in _s["thread_parts"]])
check("差し替えで content_hash を取り直す",
      _r is not None and _r["content_hash"] == inv.content_hash(_r["thread_parts"])
      and _r["content_hash"] != _s["content_hash"])
check("差し替えても state は approved のまま",
      _r is not None and _r["state"] == "approved")
check("差し替えの記録（旧URL・旧ハッシュ・理由）を残す",
      _r is not None and _r["prior_links"][-1]["old_content_hash"]
      == _s["content_hash"] and _r["prior_links"][-1]["reason"] == "テスト")
check("別の記事URLへは差し替えられない",
      sr.retag(spec, _cp.deepcopy(_s),
               "https://sakura-eigo.com/other/?utm_source=x", "x")[0] is None)
check("utm_source が消えるURLへは差し替えられない",
      sr.retag(spec, _cp.deepcopy(_s), _base + "?utm_medium=social", "x")[0]
      is None)
check("approved 以外は差し替えない",
      sr.retag(spec, dict(_cp.deepcopy(_s), state="stale"), _okurl, "x")[0]
      is None)

# 送る直前に見るもの: URLが200・X加重が上限以下
check("送る前にURLを実際に叩く", "def check_url_live" in
      (ROOT / "scripts/social_post.py").read_text(encoding="utf-8"))
_i_url = _src.index("check_url_live(sent_text)")
check("URLの確認は投稿より前", _i_url < _i_post)
check("X加重の再計算も投稿より前",
      _src.index("sg.weighted_len(spec, sent_text)") < _i_post)

# 実際に出す2件が、今の本文で上限内か
for _sid in ("X-546-b", _TARGET):
    _st = [x for _, x in inv.all_stock(spec) if x["stock_id"] == _sid][0]
    _w2 = sg.weighted_len(spec, _st["text"])
    check(f"{_sid}: X加重が上限以下", _w2 <= spec["x"]["weighted"]["hard_limit"],
          f"{_w2} / {spec['x']['weighted']['hard_limit']}")
for _sid in ("X-546-b", "THREADS-546-b"):
    _st = [x for _, x in inv.all_stock(spec) if x["stock_id"] == _sid][0]
    check(f"{_sid}: utm_content で在庫まで追える",
          "utm_content=" in _st["text"] and "utm_campaign=" in _st["text"])
    check(f"{_sid}: 本文と content_hash が合っている",
          inv.content_hash(_st["thread_parts"]) == _st["content_hash"])

# 手貼りのThreadsは、貼る本文と、貼った先のURLの記録（2026-08-10）
_th = [x for _, x in inv.all_stock(spec) if x["stock_id"] == "THREADS-546-b"][0]
check("1投稿目に記事URLを入れない", not sg.URL.findall(_th["thread_parts"][0]),
      " ".join(sg.URL.findall(_th["thread_parts"][0])))
check("記事URLは2投稿目だけ",
      len(sg.URL.findall(_th["thread_parts"][1])) == 1)
_LABEL = re.compile(r"【\s*\d+\s*投稿目\s*】|===")
check("本文に投稿ラベルが混ざっていない",
      not [p for p in _th["thread_parts"] if _LABEL.search(p)])

_r2 = subprocess.run(
    [sys.executable, str(ROOT / "scripts/social_post.py"),
     "--platform", "threads", "--stock-id", "THREADS-546-b"],
    capture_output=True, text=True, cwd=str(ROOT))
check("Threadsは貼る本文を出すだけで投稿しない",
      _r2.returncode == 0 and "create_tweet" not in _r2.stdout,
      _r2.stderr[-200:])
for _i, _p in enumerate(_th["thread_parts"], 1):
    check(f"貼る本文{_i}が全文出る", _p.strip() in _r2.stdout)
check("貼る順（新規／返信）が出る",
      "新規投稿" in _r2.stdout and "への返信" in _r2.stdout)
check("出力にラベルを混ぜていない", not _LABEL.search(_r2.stdout))

check("Threads投稿URLから投稿IDを取れる",
      sp.post_id_from_url(
          "https://www.threads.com/@sakura_eigo30/post/DAbc-1_2") == "DAbc-1_2")
check("投稿URLでないものは投稿IDにしない",
      not sp.post_id_from_url("https://www.threads.com/@sakura_eigo30"))
check("記録に親投稿と返信の両方を受ける",
      "--reply-url" in _src and "--posted-url" in _src)
_mp = (ROOT / "scripts/social_post.py").read_text(encoding="utf-8")
_mp = _mp[_mp.index("def mark_posted("):_mp.index("def main(")]
check("2投稿構成で片方だけのURLは記録しない", "両方が要る" in _mp)
check("親と返信が同じURLなら記録しない", "貼り間違い" in _mp)
check("承認済み以外は手貼りでも記録しない", "承認済みでないものは記録しない" in _mp)

# 定期運用の自動選択は残っている（cron 用）
_ready = sorted([s for _, s in inv.all_stock(spec, "x")
                 if s["state"] == "approved"],
                key=lambda y: y["approved_at"] or "")
check("最古の承認済みを選ぶ経路は残してある", bool(_ready),
      _ready[0]["stock_id"] if _ready else "")

# ワークフロー側にも stock_id の入口がある
_wf = (REPO / ".github/workflows/x-poster.yml").read_text(encoding="utf-8")
check("workflow_dispatch に stock_id がある", "stock_id:" in _wf)
check("workflow が --stock-id を渡す", "--stock-id" in _wf)
check("定期実行では stock_id が空（自動選択のまま）",
      'if [ -n "$STOCK_ID" ]' in _wf)
check("在庫の書き戻し先が main に固定されていない",
      "HEAD:main" not in _wf, "在庫は作業ブランチにしか無い")

print()
if fails:
    print(f"失敗 {len(fails)}件")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("失敗 0件")
