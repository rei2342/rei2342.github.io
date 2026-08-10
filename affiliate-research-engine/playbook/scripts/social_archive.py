#!/usr/bin/env python3
"""
social_archive.py
未投稿の旧ストックを、監査用アーカイブへ移して運用から外す。

  python social_archive.py            … 何を移すか出すだけ
  python social_archive.py --apply    … 実際に移す

**投稿済みには触らない。** X 1件・Threads 13件は残す。
**WordPressのメモも消さない。** リポジトリ側の在庫から外すだけで、
サイト上の下書きを削除するかは別の判断にする。
"""
import argparse
import csv
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import social_spec as ss

JST = timezone(timedelta(hours=9))
SRC_CSV = ROOT / "workspace/social/SOCIAL_STOCK_ALL.csv"

MOVE_DIRS = [
    ("workspace/threads", "threads"),
    ("workspace/x_promo", "x_promo"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    spec = ss.load_spec()
    stamp = datetime.now(JST).strftime("%Y-%m-%d")
    dest = ROOT / spec["paths"]["archive"] / stamp

    rows = list(csv.DictReader(SRC_CSV.open(encoding="utf-8")))
    unposted = [r for r in rows if "投稿済み" not in r["state"]]
    posted = [r for r in rows if "投稿済み" in r["state"]]

    print(f"棚卸し {len(rows)}件 = 未投稿 {len(unposted)} + 投稿済み {len(posted)}")
    print(f"未投稿の内訳: "
          f"X-PROMO {sum(1 for r in unposted if r['stock_id'].startswith('X-PROMO'))} / "
          f"TH-FILE {sum(1 for r in unposted if r['stock_id'].startswith('TH-FILE'))} / "
          f"TH-MEMO {sum(1 for r in unposted if r['stock_id'].startswith('TH-MEMO'))}")
    print(f"投稿済み（触らない）: "
          f"X {sum(1 for r in posted if r['platform'] == 'X')} / "
          f"Threads {sum(1 for r in posted if r['platform'] == 'Threads')}")

    files = []
    for rel, _ in MOVE_DIRS:
        d = ROOT / rel
        if d.exists():
            files += [p for p in sorted(d.glob("*.md"))
                      if p.name != "README.md"]
    memos = sorted({r["file"] for r in unposted
                    if r["stock_id"].startswith("TH-MEMO")})

    print(f"\n移すファイル {len(files)}本")
    for p in files:
        print(f"  {p.relative_to(ROOT)}")
    print(f"\nWordPress側のメモ {len(memos)}件は**消さない**。"
          f"運用在庫から外すだけ:")
    for m in memos:
        print(f"  {m}")

    if not a.apply:
        print("\n--apply が無いので、ここで終わり。**何も移していない。**")
        return

    (dest / "files").mkdir(parents=True, exist_ok=True)
    for p in files:
        sub = dest / "files" / p.parent.name
        sub.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(sub / p.name))
    # 棚卸しの表もそのまま添える。あとから「何を捨てたか」を追えるように
    for f in ("SOCIAL_STOCK_ALL.md", "SOCIAL_STOCK_ALL.csv",
              "SOCIAL_QUALITY_AUDIT.md"):
        src = ROOT / "workspace/social" / f
        if src.exists():
            shutil.copyfile(src, dest / f)

    note = [f"# 旧ストックのアーカイブ（{stamp}）\n\n",
            "**運用在庫から外しただけ。消していない。**\n\n",
            f"- 棚卸し {len(rows)}件 = 未投稿 {len(unposted)} + "
            f"投稿済み {len(posted)}\n",
            f"- ここへ移したファイル {len(files)}本"
            f"（`workspace/threads/` と `workspace/x_promo/`）\n",
            f"- 投稿済み {len(posted)}件はどこも触っていない\n",
            f"- WordPressの【Threads用】メモ {len(memos)}件も消していない。"
            "サイト上の下書きを削除するかは別の判断\n\n",
            "## 外した理由\n\n",
            "改稿前の記事タイトルと本文を参照している／台帳に無い一人称の事実が"
            "多数ある／URLだけの投稿・プレースホルダー・生成区切り文字が混ざる／"
            "同じ記事の二重・三重在庫がある。部分修正のほうが監査に手間がかかる。\n\n",
            "## 中身\n\n| stock_id | 置き場 | 判定 |\n|---|---|---|\n"]
    note += [f"| {r['stock_id']} | `{r['file']}` | {r.get('verdict', '')} |\n"
             for r in unposted]
    (dest / "README.md").write_text("".join(note), encoding="utf-8")
    print(f"\n→ {dest}")
    print(f"移した {len(files)}本 / 投稿済み {len(posted)}件は触っていない")


if __name__ == "__main__":
    main()
