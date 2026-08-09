#!/usr/bin/env python3
"""
eyecatch_package_verify.py
引き渡しパッケージを**渡す前に**機械で確かめる。

  python eyecatch_package_verify.py

9項目を見る。1つでも落ちたら終了コード1。
ZIPは別の一時フォルダへ展開して読み直す（相対パスの取りこぼしを見つけるため）。
"""
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BATCH = ROOT / "eyecatch-generation-batch"
PKG_NAME = "sakura-eyecatch-ai6-generation-package"
ZIP = BATCH / f"{PKG_NAME}.zip"
APPROVED = {993: False, 995: False, 997: True,
            999: True, 1001: True, 1003: False}
MUST_APPEND = [
    "No letters, no words, no numbers, no logos, no watermarks.",
    "Do not render any interface text, application logo, brand name, score,"
    " price, date, duration, or numerical label.",
    "Keep the entire left half visually quiet and uncluttered for later"
    " Japanese typography.",
    "Do not depict Sakura using a service unless that usage is verified.",
]

fails = []


def check(name, ok, detail=""):
    print(("OK  " if ok else "NG  ") + name + (f" … {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def main():
    if not ZIP.exists():
        print(f"ZIPが無い: {ZIP}")
        sys.exit(1)

    # **ZIPを別の一時フォルダへ展開して、そこだけを読む。**
    # 作業フォルダを見てしまうと「ZIPに入れ忘れた」を見逃す
    tmp = Path(tempfile.mkdtemp(prefix="eyecatch-pkg-"))
    try:
        with zipfile.ZipFile(ZIP) as z:
            bad = [n for n in z.namelist()
                   if n.startswith("/") or ".." in Path(n).parts]
            check("ZIP内に絶対パス・上位参照が無い", not bad, " ".join(bad))
            z.extractall(tmp)
        P = tmp / PKG_NAME
        check("展開したフォルダを読める", P.is_dir(), str(P))

        # 1. 参照画像3枚が実在し、0バイトでない
        for pid in (521, 273, 297):
            f = P / f"references/{pid}.jpg"
            check(f"参照 {pid}.jpg がある・0バイトでない",
                  f.exists() and f.stat().st_size > 0,
                  f"{f.stat().st_size}B" if f.exists() else "無い")

        # 2. プロンプト6本が実在する
        prompts = {}
        for pid in APPROVED:
            f = P / f"prompts/{pid}.md"
            ok = f.exists() and f.stat().st_size > 0
            check(f"プロンプト {pid}.md がある", ok)
            if ok:
                prompts[pid] = f.read_text(encoding="utf-8")

        # 見本・仕様・手順書
        for rel in ("previews/reference-comparison.jpg",
                    "previews/existing-ai6-contact-sheet.jpg",
                    "manifest.yaml", "sakura-v1.yaml",
                    "GENERATION_INSTRUCTIONS.md", "RETURN_INSTRUCTIONS.md"):
            f = P / rel
            check(f"{rel} がある・0バイトでない",
                  f.exists() and f.stat().st_size > 0)

        man = yaml.safe_load((P / "manifest.yaml").read_text(encoding="utf-8"))
        spec = yaml.safe_load((P / "sakura-v1.yaml").read_text(encoding="utf-8"))

        # 3. manifest と記事IDが一致する
        m_ids = sorted(i["post_id"] for i in man["items"])
        check("manifestの記事IDが6本そろっている",
              m_ids == sorted(APPROVED), str(m_ids))
        check("manifestの記事IDとプロンプトのファイル名が一致",
              m_ids == sorted(int(p.stem) for p in (P / "prompts").glob("*.md")))
        for i in man["items"]:
            check(f"manifest {i['post_id']}: プロンプトの記事IDが本文と一致",
                  f"記事{i['post_id']}｜" in prompts.get(i["post_id"], ""))

        # 4. 人物割り当てが承認表と一致する
        for i in man["items"]:
            check(f"manifest {i['post_id']}: 人物が承認どおり",
                  i["with_person"] is APPROVED[i["post_id"]],
                  f"承認={APPROVED[i['post_id']]} 実際={i['with_person']}")
        for pid, txt in prompts.items():
            if APPROVED[pid]:
                check(f"プロンプト {pid}: 521を最優先の顔参照と書いてある",
                      "521 as the primary identity reference" in txt)
                check(f"プロンプト {pid}: 521と別人なら不合格と書いてある",
                      "521と別人に見える" in txt)
            else:
                ref = txt.split("REFERENCES:")[1]
                check(f"プロンプト {pid}: 人物なしなので521・273を渡していない",
                      "521" not in ref and "273" not in ref)
                check(f"プロンプト {pid}: 人物を描かないと明記",
                      "Do NOT show any person" in txt)

        # 5. 数字・文字を描かせる指示が無い
        # 「文字を描け」と読める語が prompts に無いか。
        # 禁止文の中の language は除いてから見る
        for pid, txt in prompts.items():
            block = txt.split("```text")[1].split("```")[0]
            body = "\n".join(l for l in block.splitlines()
                             if not l.startswith(("No letters", "Do not ",
                                                  "- ", "Never:")))
            hit = re.search(r'\bwritten\b|\btext saying\b|\breading\s+"'
                            r'|\bthe word\b|\blabel(l?ed)?\s+"|"[^"]{2,}"',
                            body, re.I)
            check(f"プロンプト {pid}: 文字を描かせる指示が無い",
                  not hit, hit.group(0) if hit else "")
            # 見出しラベル（「2行」「1行」）は文言ではないので外してから見る
            overlay = "".join(
                l.split("）: ", 1)[1] for l in txt.splitlines()
                if l.startswith(("- リード（2行）:", "- 補助（1行）:")))
            check(f"プロンプト {pid}: 画像へ焼く文言に数字が無い",
                  not re.search(r"[0-9０-９]", overlay), overlay[:60])

        # 6. 禁止文が6本すべてに入っている
        for pid, txt in prompts.items():
            for line in MUST_APPEND:
                check(f"プロンプト {pid}: 禁止文「{line[:24]}…」がある",
                      line in " ".join(txt.split()) or line in txt)

        # 7. 出力ファイル名が重複していない
        blog = [i["blog_output"] for i in man["items"]]
        note = [i["note_output"] for i in man["items"]]
        mast = [i["master_file"] for i in man["items"]]
        check("完成ファイル名が重複していない", len(set(blog)) == len(blog))
        check("note用ファイル名が重複していない", len(set(note)) == len(note))
        check("マスターのファイル名が重複していない", len(set(mast)) == len(mast))
        for n in blog + note:
            check(f"ファイル名が半角英数とハイフン: {n}",
                  bool(re.fullmatch(r"[a-z0-9\-]+\.jpg", n)))

        # 8. リポジトリ外・環境依存のパスを参照していない
        docs = {rel: (P / rel).read_text(encoding="utf-8")
                for rel in ("GENERATION_INSTRUCTIONS.md",
                            "RETURN_INSTRUCTIONS.md", "manifest.yaml")}
        docs.update({f"prompts/{k}.md": v for k, v in prompts.items()})
        for rel, txt in docs.items():
            hit = re.search(r"/home/|/Users/|[A-Z]:\\\\|file://|"
                            + re.escape(str(REPO)), txt)
            check(f"{rel}: 絶対パスを書いていない",
                  not hit, hit.group(0) if hit else "")

        # 9. 展開先だけで読み切れるか。参照しているファイルが全部ある
        refd = set()
        for txt in list(prompts.values()) + [docs["GENERATION_INSTRUCTIONS.md"]]:
            # `prompts/<記事ID>.md` のような書き方は実ファイルではないので外す
            refd |= {m for m in re.findall(
                r"`((?:references|previews|prompts)/[^`]+)`", txt)
                if "<" not in m}
        for rel in sorted(refd):
            check(f"参照している {rel} が展開先にある", (P / rel).exists())

        # 仕様の中身も、同梱した写しで確かめる
        check("同梱した仕様が proposal のまま", spec["status"] == "proposal")
        check("同梱した仕様の禁止文が4行そろっている",
              all(l in spec["negative_prompt"]["always_append"]
                  for l in MUST_APPEND))
        check("マスターに文字を載せない設定", spec["master_has_text"] is False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if fails:
        print(f"失敗 {len(fails)}件")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print(f"失敗 0件 … {ZIP.name} は単独で使える")


if __name__ == "__main__":
    main()
