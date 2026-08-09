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
check("仕様が承認済み", spec["status"] == "approved")
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
       "body": "確認項目。音声を1つ聞いたあと、内容を1文で言えるかを試す。"
               "3つの項目を並べる。2週間の組み方。"}
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
check("在庫に approved 済みが無い（まだ承認していない）",
      not [s for _, s in rows if s["state"] in ("approved", "scheduled",
                                                "posted")],
      " ".join(s["stock_id"] for _, s in rows
               if s["state"] in ("approved", "scheduled", "posted")))
for _, s in rows:
    check(f"{s['stock_id']}: ゲート全通過",
          all(g["ok"] for g in s["gate_results"]),
          "; ".join(g["id"] for g in s["gate_results"] if not g["ok"]))

print()
if fails:
    print(f"失敗 {len(fails)}件")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("失敗 0件")
