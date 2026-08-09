#!/usr/bin/env python3
"""
eyecatch_batch.py
画像生成側へ渡す**単独で完結したパッケージ**を組み立て、ZIPにする。

  eyecatch-generation-batch/<バッチ>/        ← 作業用の実体
  eyecatch-generation-batch/<パッケージ名>.zip
      └ <パッケージ名>/                        ← ZIP内のルート

受け取る側はリポジトリを読まない。参照画像・プロンプト・見本・仕様・
手順・返し方をすべてZIPへ入れる。

**画像は生成しない。生成後の処理も動かさない。**
それらは scripts/eyecatch_finish.py にあるが、マスターが置かれるまで走らない。

  python eyecatch_batch.py --batch next20
"""
import argparse
import shutil
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import eyecatch_spec as es

JST = timezone(timedelta(hours=9))
SRC_IMG = ROOT / "workspace/seo/eyecatch"
SURVEY = ROOT / "workspace/seo/survey"
BATCH = ROOT / "eyecatch-generation-batch"
# ── バッチの定義 ────────────────────────────────────
# 記事の束ごとに、記事データ・出力先・ZIP名・見本を変える。
# **プロンプトの組み立て方は共通**（sakura-v1.yaml のアダプター）
BATCHES = {
    "ai6": {
        "articles": "config/eyecatch/articles-ai-cluster.yaml",
        "dir": "ai-6",
        "package": "sakura-eyecatch-ai6-generation-package",
        "label": "AI英語学習6本",
        "previews": [
            ("REFERENCE_COMPARE.jpg", "reference-comparison.jpg",
             "参照3枚の比較。全体と顔の拡大、採るもの／採らないもの"),
            ("AI6_CONTACT.jpg", "existing-ai6-contact-sheet.jpg",
             "並びの見本。中身は既存画像の流用で、目指す完成形ではない"),
        ],
        "split": False,
    },
    "next20": {
        "articles": "config/eyecatch/articles-next20.yaml",
        "dir": "next-20",
        "package": "sakura-eyecatch-next20-generation-package",
        "label": "文字カード型20本の差し替え",
        "previews": [],          # 20本は見本を同梱しない
        "split": True,           # manifest を batch_1 / batch_2 に分ける
    },
}


def ref_line(article, refs):
    """人物ありは3枚、人物なしは画風の1枚だけ。"""
    by_slot = {r["slot"]: r for r in refs}
    if article["with_person"]:
        return [
            (f"references/{by_slot['face_and_age']['source_post']}.jpg",
             "**顔・年齢感・頭身の最優先参照**"),
            (f"references/{by_slot['hair_and_sakura']['source_post']}.jpg",
             "長い茶髪と桜クリップ**だけ**"),
            (f"references/{by_slot['style_light_texture']['source_post']}.jpg",
             "水彩の塗り・光・空気感**だけ**"),
        ]
    return [(f"references/{by_slot['style_light_texture']['source_post']}.jpg",
             "水彩の塗り・光・空気感**だけ**")]


def reject_lines(article, spec):
    """不合格条件。人物の有無で変える。"""
    common = [
        "文字・数字・ロゴ・透かしが1つでも描かれている",
        "画面やアプリのUI、ブランド名、点数、価格、日付、期間が写っている",
        "左半分に人物・主要な小物・強いコントラストがある"
        "（あとから日本語を載せられない）",
        f"{spec['master_size'][0]}×{spec['master_size'][1]}・"
        f"{spec['master_aspect_ratio']} になっていない",
        "写真調・3D・ちびアニメ調・フラットベクターになっている",
        "未確認のサービスをさくらが使っているように見える",
    ]
    if article["with_person"]:
        return [
            "**521と別人に見える。** 顔立ち・年齢感・頭身が離れていたら作り直す",
            "297の顔・大きな目・ちび頭身・ピンクのパーカーを引き継いでいる",
            "10代に見える、またはちび頭身になっている",
        ] + common
    return ["人物が描かれている（この記事は人物なし）"] + common


def write_prompt(path, spec, article, category, refs):
    """そのファイルだけで生成できる形にする。"""
    pid = str(article["post_id"])
    used = ref_line(article, refs)
    w, h = spec["master_size"]
    box = spec["composition"]["text_safe_area"]["box"]
    body = [
        f"# 記事{pid}｜{article['title']}\n\n",
        "> 画像制作専用の一時データ。公開コンテンツではない。\n"
        "> 生成 → 反映 → 検査が通ったら削除する。失敗したら残す。\n\n",
        "## この1枚について\n\n",
        "| 項目 | 内容 |\n|---|---|\n",
        f"| 記事ID | {pid} |\n",
        f"| 記事タイトル | {article['title']} |\n",
        f"| 検索意図 | {article['search_intent']} |\n",
        f"| 記事の役割 | {article['role']} |\n",
        f"| **人物** | **{'あり' if article['with_person'] else 'なし'}**"
        f"（{' '.join(article['person_reason'].split())}） |\n",
        f"| **他の19本と何が違うか** | "
        f"{' '.join(article['uniqueness_reason'].split())} |\n",
        f"| 描く場面 | {' '.join(article['scene'].split())} |\n",
        f"| 表情 | {' '.join(article['expression'].split())} |\n",
        f"| ポーズ | {' '.join(article['pose'].split())} |\n",
        f"| 小物 | {'、'.join(article['props'])} |\n",
        f"| 背景 | {article['background']} |\n",
        f"| カメラ距離 | {article['camera_distance']} |\n",
        f"| 配色 | {' '.join(article['palette'].split())} |\n",
        f"| サイズ | **{w}×{h}**（{spec['master_aspect_ratio']}）・PNG・"
        f"**文字なし** |\n",
        f"| 文字用セーフエリア | **左50%**（x={box[0]}〜{box[2]}）は静かに空ける。"
        f"あとから日本語を載せる |\n",
        f"| 主題の位置 | **中央から右**（{spec['composition']['subject_anchor']}） |\n",
        "| 画風 | 大人向けのやわらかい水彩・色鉛筆調 |\n",
        f"| 保存名 | `masters/{pid}.png` |\n",
        f"| 完成ファイル名（こちらで付ける） | `{article['filename']}` |\n",
        f"| alt（こちらで付ける） | {article['alt']} |\n\n",
        "## 使用する参照画像\n\n",
        "| ファイル | 何を採るか |\n|---|---|\n",
    ]
    body += [f"| `{f}` | {why} |\n" for f, why in used]
    if not article["with_person"]:
        body.append("\n**この記事では 521 と 273 を使わない。**"
                    "人物を描かないため、顔と髪の参照は渡さない。\n")
    body += [
        "\n## プロンプト（そのまま貼る）\n\n```text\n",
        es.build_prompt(spec, article, category),
        "\n```\n\n## 不合格条件（1つでも当てはまったら返さず作り直す）\n\n",
    ]
    body += [f"- {x}\n" for x in reject_lines(article, spec)]
    body += [
        "\n## 生成後にこちらで載せる文字（画像AIには描かせない）\n\n",
        f"- リード（2行）: {article['lead_text'].replace(chr(10), ' / ')}\n",
        f"- 補助（1行）: {article['sub_text']}\n\n",
        "この2つは、こちらが左のセーフエリアへ合成する。"
        "**画像の中に描かない。**\n",
    ]
    path.write_text("".join(body), encoding="utf-8")
    return used


def generation_instructions(spec, items, stamp, cfg, previews):
    w, h = spec["master_size"]
    n = len(items)
    rows = "".join(
        f"| {i['post_id']} | {i.get('batch', 1)} | "
        f"{'あり' if i['with_person'] else 'なし'} | "
        f"`{i['prompt_file']}` | "
        f"{' '.join(x.split('/')[-1] for x in i['references'])} |\n"
        for i in items)
    no_person = " ".join(str(i["post_id"]) for i in items
                         if not i["with_person"])
    preview_block = ("\n## 見本\n\n" + "".join(
        f"- `{p['file']}` … {p['note']}\n" for p in previews)) if previews else ""
    split_block = ""
    if cfg["split"]:
        b1 = " ".join(str(i["post_id"]) for i in items if i.get("batch") == 1)
        b2 = " ".join(str(i["post_id"]) for i in items if i.get("batch") == 2)
        split_block = f"""
## 2回に分ける

品質を確かめやすいよう、**batch_1 を先に返してほしい**。

| 束 | 記事ID |
|---|---|
| batch_1 | {b1} |
| batch_2 | {b2} |

batch_1 を見て画風が合っていることを確かめてから batch_2 に入る。
"""
    return f"""# 生成手順（{cfg['label']}・{stamp}）

さくら（sakura-eigo.com）のアイキャッチ用に、**文字なしのマスター画像を{n}枚**作る。
文字はこちらで後から合成する。**画像の中に文字を描かない。**

## 手順

1. **参照画像と、その記事のプロンプトを同時に入力する**
   （`references/` の指定ファイルと `prompts/<記事ID>.md` のプロンプト）
2. **1記事につき、文字なしマスターを1枚生成する**
3. **{w}×{h} の PNG で保存する**（{spec['master_aspect_ratio']}）
4. **ファイル名を `<記事ID>.png` にする**（例 `{items[0]['post_id']}.png`）
5. **{n}枚を `masters/` フォルダにまとめて返す**
6. **文字・数字・ロゴが出た画像は返さない。** 作り直す
7. **人物ありの画像は、521と同一人物に見えるか確認する。**
   別人に見えたら作り直す
8. **左半分に重要な人物・小物を置かない。**
   あとから日本語を載せるので、左は静かに空ける
{split_block}
## {n}枚の一覧

| 記事ID | 束 | 人物 | プロンプト | 渡す参照 |
|---|---|---|---|---|
{rows}
## 参照画像の使い分け（3枚を均等に混ぜない）

| 優先 | ファイル | 採る | 採らない |
|---|---|---|---|
| 1 | `references/521.jpg` | **顔・年齢感・頭身** | まとめ髪・電車の場面 |
| 2 | `references/273.jpg` | 長い茶髪・桜クリップ | 顔の角度 |
| 3 | `references/297.jpg` | 水彩の塗り・光・空気感 | **顔・大きな目・ちび頭身・ピンクのパーカー** |

**人物なしの記事（{no_person}）には 521 と 273 を渡さない。**
{preview_block}
## 場面の使い回しをしない

{n}本すべてで場面・小物・カメラ距離が違う。各プロンプトの
「他と何が違うか」に、その1枚だけの要素が書いてある。
**同じ机・同じノート・同じマグ・同じ頬杖・同じ右向きの上半身を繰り返さない。**

## 全{n}枚に共通で入っている禁止文

```text
{spec['negative_prompt']['always_append']}
```

## 仕様の原本

`sakura-v1.yaml`（status: {spec['status']}）。
プロンプトはこの仕様から機械的に組み立てている。
プロンプトと仕様が食い違って見えたら、**プロンプトのほうを正とし、こちらへ知らせてほしい**。
"""


def return_instructions(items, stamp, cfg):
    n = len(items)
    files = "\n".join(f"  {i['post_id']}.png" for i in items)
    unit = ("batch_1 の10枚がそろった時点で一度返してほしい。"
            "残りは確認のあとで構わない。" if cfg["split"]
            else f"{n}枚そろってから渡してほしい")
    return f"""# 返し方と、受領後の処理（{cfg['label']}・{stamp}）

## 返してもらう構成

```
masters/
{files}
```

これだけでよい。JPEGへの変換・リサイズ・文字入れは**しない**。
{unit}（**枚数が足りないと受領処理は止まる**）。

## 受領後に、こちらが実行すること

`masters/` を `eyecatch-generation-batch/{cfg['dir']}/masters/` へ置き、次を1回走らせる。

```bash
python affiliate-research-engine/playbook/scripts/eyecatch_finish.py --batch {cfg['key']}
```

これで下の4つまで一度に出る。**追加の判断は要らない。**

| 段 | 中身 | 出力 |
|---|---|---|
| 1 | **文字合成** … 左のセーフエリアへリードと補助を載せ、1200×675 のJPEGにする | `out/<完成ファイル名>.jpg` |
| 2 | **note用クロップ** … 右寄せで 1200×628（1.91:1）に切る。**文字は載せない** | `out/<完成ファイル名>-note.jpg` |
| 3 | **13項目検査** … サイズ・比率・重さ・ファイル名・文字の有無・顔の一致など | `CHECKS.md` |
| 4 | **コンタクトシート** … マスター・ブログ用・note用の3種を並べる | `out/CONTACT.jpg` |

不合格になった画像だけを `CHECKS.md` の末尾に一覧化する（記事IDと落ちた項目）。
**機械で判定できない項目は自動で合格にせず、`—` として人が見る。**

## そのあと（承認後にだけ動かす）

```bash
python affiliate-research-engine/playbook/scripts/eyecatch_apply.py --batch {cfg['key']} --approve
```

`--approve` を付けない限り、何が起きるかの一覧を出すだけで**サイトは触らない**。
付けたときの順番は次のとおり。

1. 全記事のバックアップ（今の `featured_media` と画像URL）
2. メディアへアップロード（ファイル名は半角英数・altを設定）
3. `featured_media` を差し替え
4. 公開画面・OGP・alt・メディアの対応を確認
5. ロールバック手順を `backups/` へ記録

**今の画像も、参照に使っている旧521・273・297も削除しない。**
差し替えは featured_media を向け替えるだけで、古いメディアはそのまま残す。

`eyecatch_finish.py` は**WordPressへ一切送らない**。
サイトへ触るのは `eyecatch_apply.py --approve` だけ。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="next20", choices=sorted(BATCHES),
                    help="どの束を組み立てるか")
    args = ap.parse_args()
    cfg = dict(BATCHES[args.batch], key=args.batch)

    out = BATCH / cfg["dir"]
    pkg = cfg["package"]
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    spec = es.load_spec()
    doc = es.load_articles(ROOT / cfg["articles"])
    cat = doc["category"]

    for d in ("references", "prompts", "previews", "masters"):
        (out / d).mkdir(parents=True, exist_ok=True)

    # ── 参照画像 ────────────────────────────────
    refs = spec["reference_assets"]["priority_order"]
    ref_rows = []
    for r in refs:
        pid = str(r["source_post"])
        src = SRC_IMG / f"{pid}.jpg"
        if not src.exists() or src.stat().st_size == 0:
            # 1枚でも欠けたら止める。2枚だけ渡すと顔の基準が無いまま生成される
            print(f"参照画像が無い、または空: {src}")
            print("**3枚そろわないと顔の基準が決まらない。** ここで止める。")
            sys.exit(1)
        shutil.copyfile(src, out / "references" / f"{pid}.jpg")
        ref_rows.append({
            "slot": r["slot"], "post_id": r["source_post"],
            "media_id": r["source_media_id"],
            "file": f"references/{pid}.jpg",
            "take": r["take"], "do_not_take": r["do_not_take"],
        })

    # ── 見本（無い束もある）──────────────────────
    preview_rows = []
    for src_name, dst_name, why in cfg["previews"]:
        src = SURVEY / src_name
        if not src.exists() or src.stat().st_size == 0:
            print(f"見本が無い、または空: {src}")
            sys.exit(1)
        shutil.copyfile(src, out / "previews" / dst_name)
        preview_rows.append({"file": f"previews/{dst_name}",
                             "note": " ".join(why.split())})

    shutil.copyfile(ROOT / "config/eyecatch/sakura-v1.yaml",
                    out / "sakura-v1.yaml")

    # ── プロンプト ──────────────────────────────
    items = []
    for a in doc["articles"]:
        pid = str(a["post_id"])
        used = write_prompt(out / "prompts" / f"{pid}.md", spec, a, cat, refs)
        row = {
            "post_id": a["post_id"],
            "batch": a.get("batch", 1),
            "slug": a["slug"],
            "title": a["title"],
            "search_intent": a["search_intent"],
            "role": a["role"],
            "category": a.get("category", cat),
            "prompt_file": f"prompts/{pid}.md",
            "with_person": a["with_person"],
            "person_reason": " ".join(a["person_reason"].split()),
            "uniqueness_reason": " ".join(a["uniqueness_reason"].split()),
            "references": [f for f, _ in used],
            "camera_distance": a["camera_distance"],
            "expression": " ".join(a["expression"].split()),
            "pose": " ".join(a["pose"].split()),
            "props": a["props"],
            "background": a["background"],
            "palette": " ".join(a["palette"].split()),
            "scene": " ".join(a["scene"].split()),
            "master_file": f"masters/{pid}.png",
            "blog_output": a["filename"],
            "note_output": a["filename"].replace(".jpg", "-note.jpg"),
            "alt": a["alt"],
            "lead_text": a["lead_text"],
            "sub_text": a["sub_text"],
            "status": "awaiting_generation",
        }
        if "current_featured_media" in a:
            # **差し替え前の控え。** ここが無いと戻せない
            row["current_featured_media"] = a["current_featured_media"]
            row["current_media_url"] = a["current_media_url"]
            row["pre_card_media_id"] = a["pre_card_media_id"]
            row["verify_after_replace"] = [
                "featured_media が新しいメディアIDになっている",
                "alt が設定されている",
                "ファイル名が半角英数とハイフンだけ",
                "記事ページのOGP画像が新しい画像を指している",
                "サムネイルで読める",
                "旧メディアが消えていない（戻せる）",
            ]
        items.append(row)

    items.sort(key=lambda x: (x["batch"], -x["post_id"]))
    manifest = {
        "package": pkg,
        "batch": cfg["dir"],
        "label": cfg["label"],
        "spec_file": "sakura-v1.yaml",
        "spec_status": spec["status"],
        "generated_at": stamp,
        "master": {
            "size": spec["master_size"],
            "aspect_ratio": spec["master_aspect_ratio"],
            "has_text": spec["master_has_text"],
            "format": "png",
            "filename_pattern": "masters/<post_id>.png",
        },
        "text_safe_area": spec["composition"]["text_safe_area"],
        "subject_anchor": spec["composition"]["subject_anchor"],
        "blog_export": spec["blog_export"],
        "note_export": spec["note_export"],
        "always_append": spec["negative_prompt"]["always_append"],
        "references": ref_rows,
        "reference_priority": [r["slot"] for r in refs],
        "reject_rule": " ".join(
            spec["reference_assets"]["reject_rule"].split()),
        "previews": preview_rows,
        "count": len(items),
        "with_person_count": sum(1 for i in items if i["with_person"]),
        "without_person_count": sum(1 for i in items if not i["with_person"]),
        "post_ids": [i["post_id"] for i in items],
    }
    if cfg["split"]:
        # 10本ずつに分ける。**batch_1 を先に確認してから batch_2 に入る**
        manifest["batch_1"] = [i for i in items if i["batch"] == 1]
        manifest["batch_2"] = [i for i in items if i["batch"] == 2]
        manifest["items"] = items
    else:
        manifest["items"] = items
    (out / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False,
                       width=100), encoding="utf-8")

    (out / "GENERATION_INSTRUCTIONS.md").write_text(
        generation_instructions(spec, items, stamp, cfg, preview_rows),
        encoding="utf-8")
    (out / "RETURN_INSTRUCTIONS.md").write_text(
        return_instructions(items, stamp, cfg), encoding="utf-8")
    (out / "masters" / ".gitkeep").write_text("", encoding="utf-8")

    # ── ZIP ─────────────────────────────────────
    members = ([f"references/{r['post_id']}.jpg" for r in ref_rows]
               + [i["prompt_file"] for i in items]
               + [p["file"] for p in preview_rows]
               + ["manifest.yaml", "sakura-v1.yaml",
                  "GENERATION_INSTRUCTIONS.md", "RETURN_INSTRUCTIONS.md"])
    missing = [m for m in members if not (out / m).exists()]
    if missing:
        print("ZIPへ入れるファイルが足りない: " + " ".join(missing))
        sys.exit(1)
    zip_path = BATCH / f"{pkg}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for m in members:
            z.write(out / m, f"{pkg}/{m}")

    print(f"→ {out}")
    print(f"→ {zip_path}  ({zip_path.stat().st_size // 1024}KB / "
          f"{len(members)}ファイル)")
    print(f"  references {len(ref_rows)}枚 / prompts {len(items)}本 / "
          f"previews {len(preview_rows)}枚")
    print(f"  人物あり {manifest['with_person_count']} / "
          f"なし {manifest['without_person_count']}")
    if cfg["split"]:
        print(f"  batch_1 {len(manifest['batch_1'])}本 / "
              f"batch_2 {len(manifest['batch_2'])}本")


if __name__ == "__main__":
    main()
