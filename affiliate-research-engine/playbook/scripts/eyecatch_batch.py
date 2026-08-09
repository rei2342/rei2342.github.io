#!/usr/bin/env python3
"""
eyecatch_batch.py
画像生成へ渡す一式を、**1つのフォルダにまとめて書き出す。**

手で6回コピーする運用にしない。参照画像・プロンプト・対応表・手順を
同じ場所に置き、フォルダごと画像生成へ持っていけるようにする。

  eyecatch-generation-batch/ai-6/
    references/  521.jpg 273.jpg 297.jpg
    prompts/     993.md 995.md 997.md 999.md 1001.md 1003.md
    manifest.yaml
    README.md

**画像は生成しない。生成後の処理（文字合成・クロップ・検査・反映）も動かさない。**
それらは scripts/eyecatch_finish.py に用意してあるが、
マスターが置かれるまで実行しない。

  python eyecatch_batch.py
"""
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import eyecatch_spec as es

JST = timezone(timedelta(hours=9))
SRC_IMG = ROOT / "workspace/seo/eyecatch"
OUT = ROOT / "eyecatch-generation-batch/ai-6"
ARTICLES = ROOT / "config/eyecatch/articles-ai-cluster.yaml"


def main():
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    spec = es.load_spec()
    doc = es.load_articles(ARTICLES)
    cat = doc["category"]

    (OUT / "references").mkdir(parents=True, exist_ok=True)
    (OUT / "prompts").mkdir(parents=True, exist_ok=True)
    (OUT / "masters").mkdir(parents=True, exist_ok=True)

    # 参照画像を置く
    refs = spec["reference_assets"]["priority_order"]
    ref_rows = []
    for r in refs:
        pid = str(r["source_post"])
        src = SRC_IMG / f"{pid}.jpg"
        dst = OUT / "references" / f"{pid}.jpg"
        if not src.exists():
            # 参照が1枚でも欠けたら止める。2枚だけ渡すと
            # 顔の基準が無いまま生成されてしまう
            print(f"参照画像が無い: {src}")
            print("**3枚そろわないと顔の基準が決まらない。** ここで止める。")
            sys.exit(1)
        shutil.copyfile(src, dst)
        ref_rows.append({
            "slot": r["slot"], "post_id": r["source_post"],
            "media_id": r["source_media_id"],
            "file": f"references/{pid}.jpg",
            "take": r["take"], "do_not_take": r["do_not_take"],
        })

    # プロンプトを書き出す
    items = []
    for a in doc["articles"]:
        pid = str(a["post_id"])
        prompt = es.build_prompt(spec, a, cat)
        used = ["references/521.jpg", "references/273.jpg",
                "references/297.jpg"] if a["with_person"] \
            else ["references/297.jpg"]
        body = [
            f"# {pid} {a['title']}\n\n",
            "> 画像制作専用の一時データ。公開コンテンツではない。\n"
            "> 生成 → 反映 → 検査が通ったら削除する。失敗したら残す。\n\n",
            f"- 人物: **{'あり' if a['with_person'] else 'なし'}**"
            f"（{' '.join(a['person_reason'].split())}）\n",
            f"- 使う参照: {', '.join(used)}\n",
            f"- 出力: `masters/{pid}.png`（"
            f"{spec['master_size'][0]}×{spec['master_size'][1]}・文字なし）\n",
            f"- 完成ファイル名: `{a['filename']}`\n",
            f"- alt: {a['alt']}\n\n",
            "## プロンプト\n\n```text\n", prompt, "\n```\n\n",
            "## 生成後にこちらで入れる文字（画像AIには描かせない）\n\n",
            f"- リード: {a['lead_text']}\n",
            f"- 補助: {a['sub_text']}\n",
        ]
        (OUT / "prompts" / f"{pid}.md").write_text("".join(body),
                                                   encoding="utf-8")
        items.append({
            "post_id": a["post_id"],
            "slug": a["slug"],
            "title": a["title"],
            "prompt_file": f"prompts/{pid}.md",
            "with_person": a["with_person"],
            "person_reason": " ".join(a["person_reason"].split()),
            "references": used,
            "master_file": f"masters/{pid}.png",
            "blog_output": a["filename"],
            "note_output": a["filename"].replace(".jpg", "-note.jpg"),
            "alt": a["alt"],
            "lead_text": a["lead_text"],
            "sub_text": a["sub_text"],
            "status": "awaiting_generation",
        })

    manifest = {
        "batch": "ai-6",
        "spec": "config/eyecatch/sakura-v1.yaml",
        "spec_status": spec["status"],
        "category": cat,
        "generated_at": stamp,
        "master": {
            "size": spec["master_size"],
            "aspect_ratio": spec["master_aspect_ratio"],
            "has_text": spec["master_has_text"],
            "format": "png",
        },
        "blog_export": spec["blog_export"],
        "note_export": spec["note_export"],
        "references": ref_rows,
        "reference_priority": [r["slot"] for r in refs],
        "reject_rule": " ".join(
            spec["reference_assets"]["reject_rule"].split()),
        "with_person_count": sum(1 for i in items if i["with_person"]),
        "without_person_count": sum(1 for i in items if not i["with_person"]),
        "items": items,
    }
    (OUT / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False,
                       width=100), encoding="utf-8")

    readme = f"""# AI英語学習6本 画像生成バッチ（{stamp}）

このフォルダごと画像生成へ渡す。**手で6回コピーしない。**

```
references/   参照画像3枚。優先順位は manifest.yaml の reference_priority
prompts/      記事ごとのプロンプト（そのまま貼る）
masters/      ここへ生成した文字なしマスターを置く（<記事ID>.png）
manifest.yaml 記事ID・プロンプト・人物有無・参照・完成ファイル名の対応表
```

## 参照画像の使い分け（均等に混ぜない）

| 優先 | ファイル | 採るもの | 採らないもの |
|---|---|---|---|
""" + "".join(
        f"| {i + 1}. {r['slot']} | `{r['file']}` | {r['take']} | "
        f"{r['do_not_take']} |\n" for i, r in enumerate(ref_rows)) + f"""
**{manifest['reject_rule']}**

## 手順

1. `prompts/<記事ID>.md` のプロンプトを画像生成AIへ貼る
2. `references/` の指定された画像を参照として渡す
   （人物ありは3枚、人物なしは297だけ）
3. 出てきた画像を `masters/<記事ID>.png` として保存する
   （{spec['master_size'][0]}×{spec['master_size'][1]}・**文字なし**）
4. 6枚そろったら次を実行する

```bash
python affiliate-research-engine/playbook/scripts/eyecatch_finish.py
```

これで文字合成・noteクロップ・13項目の検査・コンタクトシートまで出る。
**WordPressへは送らない。** 反映はコンタクトシートの承認後。

## 人物の割り当て

| 記事 | 人物 | 理由 |
|---|---|---|
""" + "".join(
        f"| {i['post_id']} | {'あり' if i['with_person'] else 'なし'} | "
        f"{i['person_reason']} |\n" for i in items) + f"""
人物あり{manifest['with_person_count']} / なし{manifest['without_person_count']}。

## 守ること

- {spec['master_size'][0]}×{spec['master_size'][1]}・16:9・**文字なし**
- 左50%は文字用の静かな余白。人物・主要な小物・強いコントラストを置かない
- 主題は中央から右
- 大人向けのやわらかい水彩・色鉛筆調
- `{spec['negative_prompt']['always_append']}`
- 人物ありは521を最優先の顔参照にする
- 未確認のサービス利用を描かない
- 記事ごとに場面と小物を変える
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    (OUT / "masters" / ".gitkeep").write_text("", encoding="utf-8")

    print(f"→ {OUT}")
    print(f"  references {len(ref_rows)}枚 / prompts {len(items)}本")
    print(f"  人物あり {manifest['with_person_count']} / "
          f"なし {manifest['without_person_count']}")


if __name__ == "__main__":
    main()
