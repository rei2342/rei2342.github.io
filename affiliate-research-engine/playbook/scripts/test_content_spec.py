#!/usr/bin/env python3
"""
test_content_spec.py
記事の自動生成が、2026-08-16の仕様どおりに動くかを検査する。

  python test_content_spec.py

守るもの
  1. 狙うKWが、タイトル生成の工程まで届いている
     （届いていなかったのが26本のKW無しタイトルの原因）
  2. タイトル規則が正本と生成プロンプトで食い違っていない
  3. アフィリエイトリンクに rel="sponsored nofollow noopener" が付く
  4. PR表記が消えていない
  5. 全トピックに行き先のカテゴリがある（Uncategorizedに溜めない）
  6. 既存スラッグを変えない
"""
import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(Path(__file__).parent))

fails = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "NG  ") + name + (f" … {detail}" if detail else ""))
    if not ok:
        fails.append(name)


spec = yaml.safe_load(
    (ROOT / "config/content/sakura-content-v1.yaml").read_text(encoding="utf-8"))
DRAFTER = REPO / ".github/workflows/daily-article-drafter.yml"
wf = DRAFTER.read_text(encoding="utf-8")

# ── 1. 正本にタイトル規則がある ──────────────────────
for k in ("title", "meta_description", "keyword_strategy", "categories",
          "slug", "affiliate_link"):
    check(f"正本に {k} がある", k in spec)

t = spec["title"]
check("KWをタイトルに入れることが必須", t["keyword_required"] is True)
check("KWの位置が冒頭20文字以内", "20" in t["keyword_position"])
check("タイトルの長さが28〜40字（2026-08-16夜の決定）",
      (t["length"]["min"], t["length"]["max"]) == (28, 40), str(t["length"]))
check("止める条件と通す条件を分けている",
      set(t["gate"]) == {"stop", "warn"}, str(sorted(t.get("gate", {}))))
check("長さは警告であって門ではない",
      any("28〜40" in w for w in t["gate"]["warn"]))
check("KW未渡しは門", any("KWが渡っていない" in s for s in t["gate"]["stop"]))
check("旧タイトル型を明示的に置き換えている",
      "使わない" in t["supersedes"] and "2026-08-01" in t["supersedes"])

# ── 2. KWが工程の外へ出ている（今回の根本原因）────────
check("生成プロンプトが keyword: をフロントマターへ書かせる",
      "keyword:" in wf and "フロントマター" in wf)
check("生成プロンプトが description: も書かせる", "description:" in wf)
check("フロントマターから keyword を読んでいる",
      re.search(r"\^keyword:\\\\s\*\(\.\+\)\$", wf) is not None
      or r"^keyword:\s*(.+)$" in wf)
check("スラッグ生成へKWを渡している", "make_slug(title, keyword)" in wf,
      "make_slug(title) のままなら未修正")
check("KWを渡さない古い呼び出しが残っていない",
      "make_slug(title)\n" not in wf and "make_slug(title)," not in wf)

# ── 3. タイトル規則が正本とプロンプトで一致 ────────────
check("プロンプトに「冒頭20文字以内」がある", "冒頭20文字以内" in wf)
check("プロンプトに「全角28〜40文字」がある", "28〜40" in wf)
check("プロンプトが疑問形を優先している", "疑問形" in wf)
check("プロンプトが旧型（30〜45字の一人称+数字型）を捨てている",
      "30〜45字の短い一人称+数字型" not in wf.replace(
          "**2026-08-01の『30〜45字の一人称+数字型』は使わない。**", ""),
      "旧規則が残っている")
check("プロンプトが正本を参照している",
      "sakura-content-v1.yaml" in wf)
for ng in t["forbidden"]:
    key = ng.split("（")[0].split("(")[0][:6]
    if key in ("年号", "体言止め"):
        check(f"プロンプトが禁止している: {key}", key in wf)

# ── 4. 埋め込みPythonの検査ロジック ────────────────────
steps = yaml.safe_load(wf)["jobs"]["draft"]["steps"] \
    if "draft" in yaml.safe_load(wf)["jobs"] else \
    list(yaml.safe_load(wf)["jobs"].values())[0]["steps"]
wp_step = [s for s in steps if "WordPress" in (s.get("name") or "")]
check("WordPressへ送る手順がある", bool(wp_step))
if wp_step:
    body = wp_step[0]["run"].split("<< 'PYEOF'", 1)[1].rsplit("PYEOF", 1)[0]
    try:
        ast.parse(body)
        check("埋め込みPythonが構文として通る", True)
    except SyntaxError as e:
        check("埋め込みPythonが構文として通る", False, str(e))
    check("タイトル検査が入っている", "TITLE_CHECK" in body)
    check("KWが無いときも気づける", "keyword:" in body or "keyword" in body)
    # **下書きは捨てない。** タイトルが規則から外れても投稿はする
    idx_check = body.index("TITLE_CHECK")
    idx_post = body.index("requests.post(")
    check("規則違反でも下書きは投稿する（本文を捨てない）", idx_check < idx_post)
    check("規則違反で exit していない",
          "sys.exit" not in body[idx_check:idx_post])

# ── 4-2. メタ ────────────────────────────────────────
md = spec["meta_description"]
check("メタの長さが110〜130字",
      (md["length"]["min"], md["length"]["max"]) == (110, 130), str(md["length"]))
check("メタの反映先が Rank Math", "rankmath" in md["write_to"]["endpoint"])
check("反映を確認して1回だけ再送する、と書いてある",
      "1回だけ" in md["write_to"]["verify"])
check("プロンプトが110〜130を指示している", "110〜130" in wf)

import rankmath_meta as rm
_ok = ("英語コーチングは意味ないと感じる原因は4つに分かれます。料金が高いかどうかでは"
       "なく、どこで手が止まっているかで見直す場所が変わります。高額なプランを払う前に、"
       "自分がどの型に当てはまるかを確認して、次に見る場所を決められます。")
check("正しいメタは通る", not rm.check(_ok, "英語コーチング 意味ない"),
      str(rm.check(_ok, "英語コーチング 意味ない")))
check("短いメタは落ちる", bool(rm.check("英語コーチングは意味ないのか。", "英語コーチング")))
check("「〜について解説します」は落ちる",
      any("解説" in b for b in rm.check("あ"*100 + "英語について詳しく解説します。", "")))
check("煽りは落ちる", any("煽り" in b for b in rm.check("あ"*100 + "必見の内容です。", "")))
check("名詞止めは落ちる",
      any("体言止め" in b for b in rm.check("あ"*100 + "確認する4つのポイント", "")))
check("述語で終わるものは体言止め扱いしない",
      not any("体言止め" in b for b in rm.check("あ"*100 + "次に見る場所が分かる", "")))
check("送る前に必ず検査する（--write が無ければ送らない）",
      "--write が無いので送っていない" in
      (ROOT / "scripts/rankmath_meta.py").read_text(encoding="utf-8"))
check("メタ以外を送っていない",
      '"content"' not in (ROOT / "scripts/rankmath_meta.py").read_text(encoding="utf-8")
      and '"slug"' not in (ROOT / "scripts/rankmath_meta.py").read_text(encoding="utf-8"))

# ── 4-3. 内部リンク（孤立記事を作らない）──────────────
il = spec["internal_links"]
check("主軸が8本", len(il["hubs"]) == 8, str([h["id"] for h in il["hubs"]]))
check("997（AI英語学習）が主軸に入っている",
      997 in [h["id"] for h in il["hubs"]])
check("公開時に主軸→子記事のリンクを必須にしている",
      any("主軸記事 →" in r for r in il["on_publish_required"]))
check("ハブブロックはアフィリンクより後ろ",
      "後ろ" in il["hub_block"]["position"])
check("プロンプトが主軸へのリンクを指示している",
      "主軸" in wf and "hub_link" in wf)
check("孤立0がベースラインとして記録されている",
      il["baseline_2026_08_16"]["orphans"] == 0)

# ── 5. アフィリエイトリンク ────────────────────────────
ai = (ROOT / "scripts/affiliate_inserter.py").read_text(encoding="utf-8")
rels = set(re.findall(r'rel="([^"]*)"', ai))
check("rel が sponsored nofollow noopener に統一されている",
      rels == {"sponsored nofollow noopener"}, str(sorted(rels)))
check("正本の rel と一致している",
      spec["affiliate_link"]["rel"] in ai, spec["affiliate_link"]["rel"])
check("PR表記が消えていない",
      "アフィリエイトリンクが含まれます（PR）" in ai)
check("料金改定の注意が入っている", "改定される" in ai)
check("1記事あたりの上限が2件", spec["affiliate_link"]["max_per_article"] == 2)

# 実HTMLの整合。**href と img src の a8mat が一致していること**
import re as _re
import affiliate_inserter as af
for key, (name, htm) in af.LINKS.items():
    mats = _re.findall(r"a8mat=([A-Z0-9+]+)", htm)
    check(f"{key}: href と img の a8mat が同じ",
          len(mats) == 2 and mats[0] == mats[1], str(mats))
    check(f"{key}: rel が付いている", 'rel="sponsored nofollow noopener"' in htm)
    check(f"{key}: target=_blank", 'target="_blank"' in htm)

# **台帳で裏が取れていない訴求語をアンカーへ書いていない**
import quality_rules as _q
for topic in af.TOPIC_MAP:
    cta, progs = af.build_cta(topic)
    ng = _q.cta_claim_gate(cta)
    check(f"CTA台帳: {topic}", not ng,
          ng[0]["reason"] if ng else "")

for topic, progs in af.TOPIC_MAP.items():
    check(f"トピック {topic}: 案件が2件以内", len(progs) <= 2, str(progs))

# ── 6. カテゴリ ────────────────────────────────────────
import wp_categorizer as wc
want = {c["name"] for c in spec["categories"]["list"]}
check("正本のカテゴリが8つ", len(spec["categories"]["list"]) == 8)
check("行き先が正本の8つに収まっている",
      set(wc.TOPIC_CATEGORY.values()) <= want,
      str(sorted(set(wc.TOPIC_CATEGORY.values()) - want)))
missing = [t for t in af.TOPIC_MAP if t not in wc.TOPIC_CATEGORY]
check("全トピックに行き先がある（Uncategorizedに溜めない）", not missing,
      str(missing))
check("TOEICが専用カテゴリへ行く",
      wc.TOPIC_CATEGORY["toeic"] == "TOEIC・スコア",
      wc.TOPIC_CATEGORY["toeic"])

# ── 7. スラッグ ────────────────────────────────────────
check("既存スラッグを変えない方針が正本にある",
      "変更しない" in spec["slug"]["existing"])
check("記事更新の口が slug を送っていない",
      '"slug"' not in (ROOT / "scripts/social_ops.py").read_text(encoding="utf-8")
      .split("def article_apply")[1].split("requests.post")[1][:400])

print()
if fails:
    print(f"失敗 {len(fails)}件")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("失敗 0件")
