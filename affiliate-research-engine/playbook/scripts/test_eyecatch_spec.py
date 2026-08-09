#!/usr/bin/env python3
"""
test_eyecatch_spec.py
共通仕様が**唯一の正本であり続けている**ことを検査する。

3つ見る。

  1. 直書き検査
     Python側とTypeScript側のコードに、人物設定・画風・禁止事項・比率が
     直接書かれていないか。片方だけにルールが増えると、また食い違う

  2. 差分検出
     同じYAMLから、Python側とTypeScript側が**同じ文字列**を出すか。
     Node が無い環境では、TypeScript の組み立て順を写した
     参照実装と比べる（順番が変わったら落ちる）

  3. 仕様の中身
     必須キーがそろっているか。廃止した要素が復活していないか

  python test_eyecatch_spec.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import eyecatch_spec as es

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "scripts/eyecatch_spec.py"
TS = ROOT / "config/eyecatch/adapters/eyecatchPrompt.ts"
SPEC = ROOT / "config/eyecatch/sakura-v1.yaml"
ARTICLES = ROOT / "config/eyecatch/articles-ai-cluster.yaml"

fails = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "NG  ") + name + (f" … {detail}" if detail else ""))
    if not ok:
        fails.append(name)


# ── 1. 直書き検査 ────────────────────────────────────
# 仕様の実体がコードに現れていないか。YAMLのキー名は出てよい
BANNED_IN_CODE = [
    ("ちびアニメ調の指定", r"chibi anime|Kawaii chibi"),
    ("固定小物", r"bunny plush|pink mug|pens in a pink holder"),
    ("時計と？の吹き出し", r"clock icon|speech bubble with"),
    ("比率の直書き", r'"16:9"|1200\s*[x×]\s*675|1920\s*[x×]\s*1080'),
    ("髪色の直書き", r"brown hair with|sakura hair clip"),
    ("禁止文の直書き", r"No letters, no words, no numbers"),
]
for path in (PY, TS):
    src = path.read_text(encoding="utf-8")
    # docstring と行コメントを外してから見る。説明文に語が出るのは許す
    body = re.sub(r'"""[\s\S]*?"""|/\*[\s\S]*?\*/|^\s*(#|//|\*).*$', "",
                  src, flags=re.M)
    for label, pat in BANNED_IN_CODE:
        hit = re.search(pat, body, re.I)
        check(f"{path.name}: {label}が直書きされていない", not hit,
              hit.group(0) if hit else "")

# ── 2. 差分検出（Python vs TypeScript）──────────────
spec = es.load_spec(SPEC)
doc = es.load_articles(ARTICLES)
py_out = {str(a["post_id"]): es.build_prompt(spec, a, doc["category"])
          for a in doc["articles"]}

# npx があっても、オフラインだと tsx を取ってこられない。
# **実行できたときは文字列で比べ、できないときは構造で比べる。**
# どちらの場合も素通りさせない
ran_ts = False
if shutil.which("npx"):
    probe = subprocess.run(
        ["npx", "--yes", "tsx", str(TS), str(ARTICLES),
         str(doc["articles"][0]["post_id"])],
        capture_output=True, text=True, cwd=str(ROOT))
    ran_ts = probe.returncode == 0
    if not ran_ts:
        print("--  TypeScriptを実行できない（"
              + probe.stderr.strip().splitlines()[-1][:80]
              + "）。構造の比較へ切り替える")
if ran_ts:
    for pid in py_out:
        r = subprocess.run(
            ["npx", "--yes", "tsx", str(TS), str(ARTICLES), pid],
            capture_output=True, text=True, cwd=str(ROOT))
        check(f"記事{pid}: PythonとTypeScriptの出力が一致",
              r.returncode == 0 and r.stdout.strip() == py_out[pid].strip())
else:
    # Node が無い環境。**素通ししない。**
    # TypeScript側の組み立て順をソースから抜き出して、Python側と比べる
    ts_src = TS.read_text(encoding="utf-8")
    ts_order = re.findall(r'parts\.push\(\s*\n?\s*"([A-Z][A-Z ()a-z]+):', ts_src)
    py_src = PY.read_text(encoding="utf-8")
    py_order = re.findall(r'parts\.append\(\s*\n?\s*[f]?"([A-Z][A-Z ()a-z]+):',
                          py_src)
    check("TypeScriptを実行せず、組み立て順で比べた",
          True, f"{len(ts_order)}段落")
    check("段落の順番と見出しが一致", ts_order == py_order,
          f"py={py_order} ts={ts_order}")
    # 両方が同じキーを読んでいるか
    keys = ["character", "style", "composition", "negative_prompt",
            "category_colors", "master_size", "master_aspect_ratio"]
    for k in keys:
        check(f"両方が spec.{k} を読んでいる",
              k in py_src and k in ts_src)

# ── 3. 仕様の中身 ────────────────────────────────────
required = ["version", "status", "master_aspect_ratio", "blog_export",
            "note_export", "character", "style", "composition",
            "appearance_policy", "category_colors", "text_overlay",
            "negative_prompt", "reference_assets", "article_specific_fields",
            "quality_checks"]
for k in required:
    check(f"仕様に {k} がある", k in spec)

check("マスターに文字を載せない設定になっている",
      spec.get("master_has_text") is False)
check("noteは文字なし", spec["note_export"]["text_overlay"] is False)
check("ブログは文字を合成する", spec["blog_export"]["text_overlay"] is True)
check("禁止文が必ず付く",
      "No letters" in spec["negative_prompt"]["always_append"])
check("ちびキャラが禁止に入っている",
      any("chibi" in x for x in spec["style"]["forbidden"]))
check("固定小物が禁止に入っている",
      any("rabbit plush" in x for x in spec["character"]["forbidden"]))
check("参照画像に優先順位がある",
      len(spec["reference_assets"]["priority_order"]) >= 3)
check("人物の割合が固定の数値になっていない",
      "balance_is_not_a_quota" in spec["appearance_policy"])

# 参照画像の使い分けが、プロンプトへそのまま入るか
ref = spec["reference_assets"]
check("参照の指示文がある（人物あり・なしの2種）",
      set(ref.get("directive", {})) == {"with_person", "without_person"})
check("顔が521から離れたら不合格、と書いてある",
      "521" in ref.get("reject_rule", ""))
for pid, out in py_out.items():
    art = next(a for a in doc["articles"] if str(a["post_id"]) == pid)
    check(f"記事{pid}: プロンプトにREFERENCESがある", "REFERENCES:" in out)
    if art["with_person"]:
        check(f"記事{pid}: 521が顔の最優先参照と書いてある",
              "521 as the primary identity reference" in out)
        check(f"記事{pid}: 273は髪と桜だけ", "273 only for" in out)
        check(f"記事{pid}: 297は塗りと光だけ", "297 only for" in out)
        check(f"記事{pid}: 297の顔・目・パーカーを引き継がない",
              "Do not copy its face" in out and "pink hoodie" in out)
    else:
        check(f"記事{pid}: 人物なしと明記", "No person appears" in out)
        check(f"記事{pid}: 人物なしなのに521を参照していない",
              "521" not in out.split("REFERENCES:")[1])

# 承認された人物の割り当てどおりか。ここを変えたら気づけるようにする
APPROVED = {"993": False, "995": False, "997": True,
            "999": True, "1001": True, "1003": False}
for a in doc["articles"]:
    pid = str(a["post_id"])
    check(f"記事{pid}: 人物の有無が承認どおり",
          a["with_person"] is APPROVED[pid],
          f"承認={APPROVED[pid]} 実際={a['with_person']}")
check("人物あり3・なし3",
      sum(1 for a in doc["articles"] if a["with_person"]) == 3)

# 仕様は完成画像の承認まで proposal のまま
check("仕様が proposal のまま", spec["status"] == "proposal")

# 記事側
for a in doc["articles"]:
    pid = a["post_id"]
    check(f"記事{pid}: 人物の有無に理由がある",
          bool(a.get("person_reason", "").strip()))
    check(f"記事{pid}: リード文が2行以内",
          len(a["lead_text"].split("\n")) <= spec["text_overlay"]["lead"]["max_lines"])
    for line in a["lead_text"].split("\n"):
        check(f"記事{pid}: リード1行が{spec['text_overlay']['lead']['max_chars_per_line']}字以内",
              len(line) <= spec["text_overlay"]["lead"]["max_chars_per_line"],
              line)
    check(f"記事{pid}: 補助文が{spec['text_overlay']['sub']['max_chars']}字以内",
          len(a["sub_text"]) <= spec["text_overlay"]["sub"]["max_chars"],
          a["sub_text"])
    check(f"記事{pid}: 画像内文言に数字が入っていない",
          not re.search(r"[0-9０-９]", a["lead_text"] + a["sub_text"]),
          a["lead_text"] + a["sub_text"])
    check(f"記事{pid}: 場面に読める文字を描かせていない",
          not re.search(r'"[^"]{2,}"|written|text saying', a["scene"], re.I))
    check(f"記事{pid}: ファイル名が半角英数とハイフン",
          bool(re.fullmatch(r"[a-z0-9\-]+\.jpg", a["filename"])), a["filename"])

print()
if fails:
    print(f"失敗 {len(fails)}件")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("失敗 0件")
