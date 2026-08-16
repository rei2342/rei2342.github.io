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
check("タイトルの長さが32〜40字",
      (t["length"]["min"], t["length"]["max"]) == (32, 40), str(t["length"]))
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
check("プロンプトに「全角32〜40文字」がある", "32〜40" in wf)
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

import affiliate_inserter as af
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
