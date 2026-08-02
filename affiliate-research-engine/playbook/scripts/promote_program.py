#!/usr/bin/env python3
"""
promote_program.py — 承認された案件を1コマンドで「稼働中」へ昇格させる。

承認のたびに手で3ファイル触る作業をまとめたもの。実行すると:
  1. affiliate_inserter.py の LINKS にアフィリエイトリンクを追加
  2. affiliate_inserter.py の TOPIC_MAP の該当トピックに案件キーを差し込む
  3. CLAUDE.md の「もしも承認済み」リストへ稼働中として追記
  4. program_candidates.csv の apply_status を candidate → approved に更新
  5. keywords.csv にその案件が刺さるキーワードを補充（--keywords 指定時）

使い方:
  python promote_program.py \
    --key sapuri_toeic \
    --name "スタディサプリENGLISH TOEIC" \
    --asp A8 --reward 3000 --topic toeic \
    --link '<a href="...">→ 無料体験を見る</a>' \
    --keywords "TOEIC 800点 社会人 独学,TOEIC 参考書 やめた"

  # 何が変わるか見るだけ（ファイルは書き換えない）
  python promote_program.py ... --dry-run
"""
import argparse
import csv
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]          # affiliate-research-engine/
INSERTER = BASE / "playbook" / "scripts" / "affiliate_inserter.py"
CLAUDE_MD = BASE / "CLAUDE.md"
CANDIDATES = BASE / "playbook" / "workspace" / "program_candidates.csv"
KEYWORDS = BASE / "playbook" / "workspace" / "keywords.csv"

VALID_TOPICS = [
    "philippines", "workingholiday", "study_abroad", "agent", "coaching",
    "toeic", "pronunciation", "training", "eikaiwa", "domestic", "default",
]


def fail(msg: str) -> None:
    print(f"[エラー] {msg}", file=sys.stderr)
    sys.exit(1)


def add_to_links(src: str, key: str, ident: str, link_html: str) -> str:
    """LINKS dict の末尾に新しいエントリを追加する。"""
    if f'"{key}"' in src:
        print(f"  - LINKS: {key} は既に存在 → スキップ")
        return src

    start = src.index("LINKS = {")
    end = src.index("\n}", start)                    # LINKS を閉じる行
    esc = link_html.replace("\\", "\\\\").replace("'", "\\'")
    entry = f'\n    "{key}": (\n        "{ident}",\n        \'{esc}\'\n    ),'
    print(f"  + LINKS: {key} を追加")
    return src[:end] + entry + src[end:]


def add_to_topic_map(src: str, key: str, topic: str) -> str:
    """TOPIC_MAP の該当トピック先頭に案件キーを差し込む（最大2件に保つ）。"""
    m = re.search(rf'^(\s*"{topic}":\s*)\[(.*?)\](,.*)$', src, re.MULTILINE)
    if not m:
        fail(f"TOPIC_MAP に {topic} が見つかりません")

    current = [p.strip().strip('"') for p in m.group(2).split(",") if p.strip()]
    if key in current:
        print(f"  - TOPIC_MAP[{topic}]: 既に登録済み → スキップ")
        return src

    updated = ([key] + current)[:2]                  # 新案件を主力に、最大2件
    new_line = m.group(1) + "[" + ", ".join(f'"{p}"' for p in updated) + "]" + m.group(3)
    print(f"  + TOPIC_MAP[{topic}]: {current} → {updated}")
    return src[:m.start()] + new_line + src[m.end():]


def add_to_claude_md(name: str, asp: str, reward: str, ident: str, note: str) -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")
    if name in text:
        print(f"  - CLAUDE.md: {name} は既に記載あり → スキップ")
        return

    lines = text.split("\n")
    anchor = [i for i, l in enumerate(lines) if "← **稼働中**" in l]
    if not anchor:
        fail("CLAUDE.md に稼働中リストが見つかりません")

    tail = f" / {note}" if note else ""
    entry = (f"    - {name}（{asp}）¥{reward} ← **稼働中**"
             f"（{ident}{tail}）")
    lines.insert(anchor[-1] + 1, entry)
    CLAUDE_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"  + CLAUDE.md: 稼働中リストに追記")


def mark_candidate_approved(name: str) -> None:
    if not CANDIDATES.exists():
        return
    rows = list(csv.reader(CANDIDATES.open(encoding="utf-8")))
    if not rows:
        return

    header, hit = rows[0], False
    try:
        status_i = header.index("apply_status")
    except ValueError:
        return

    for r in rows[1:]:
        if len(r) > status_i and name.split("（")[0] in r[0]:
            r[status_i] = "approved"
            hit = True

    if hit:
        with CANDIDATES.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
        print(f"  + program_candidates.csv: apply_status → approved")
    else:
        print(f"  - program_candidates.csv: 該当行なし（候補リスト外の案件）")


def add_keywords(name: str, asp: str, keywords: list[str], today: str) -> None:
    if not keywords:
        return
    existing = KEYWORDS.read_text(encoding="utf-8")
    added = 0
    with KEYWORDS.open("a", encoding="utf-8") as f:
        for kw in keywords:
            kw = kw.strip()
            if not kw or kw in existing:
                continue
            f.write(f"{kw},,{asp},{name},todo,,{today}\n")
            added += 1
    print(f"  + keywords.csv: {added}件のキーワードを追加（status=todo）")


def main() -> None:
    p = argparse.ArgumentParser(description="承認された案件を稼働中へ昇格させる")
    p.add_argument("--key", required=True, help="内部キー（例: sapuri_toeic）")
    p.add_argument("--name", required=True, help="案件名（例: スタディサプリENGLISH TOEIC）")
    p.add_argument("--link", required=True, help="アフィリエイトリンクのHTML全文")
    p.add_argument("--topic", required=True, choices=VALID_TOPICS, help="紐付けるトピック")
    p.add_argument("--asp", default="もしも", help="ASP名")
    p.add_argument("--reward", default="0", help="成果報酬（円）")
    p.add_argument("--ident", default="", help="a_id等の識別子。未指定なら--keyを使う")
    p.add_argument("--note", default="", help="CLAUDE.mdに残す補足")
    p.add_argument("--keywords", default="", help="補充するキーワード（カンマ区切り）")
    p.add_argument("--date", default="", help="記録日 YYYY-MM-DD（未指定なら本日）")
    p.add_argument("--dry-run", action="store_true", help="書き換えずに差分だけ表示")
    args = p.parse_args()

    if args.date:
        today = args.date
    else:
        from datetime import date
        today = date.today().isoformat()

    ident = args.ident or args.key

    print(f"\n昇格: {args.name}  [{args.asp}] → topic={args.topic}")
    print("=" * 60)

    src = INSERTER.read_text(encoding="utf-8")
    updated = add_to_links(src, args.key, ident, args.link)
    updated = add_to_topic_map(updated, args.key, args.topic)

    if args.dry_run:
        print("\n[DRY RUN] ファイルは変更していません")
        return

    INSERTER.write_text(updated, encoding="utf-8")

    add_to_claude_md(args.name, args.asp, args.reward, ident, args.note)
    mark_candidate_approved(args.name)
    add_keywords(args.name, args.asp,
                 [k for k in args.keywords.split(",") if k.strip()], today)

    print("=" * 60)
    print("完了。次の記事生成からこの案件のリンクが自動で入ります。")
    print("  確認: python -c \"import affiliate_inserter as a; print(a.build_cta('%s')[1])\"\n" % args.topic)


if __name__ == "__main__":
    main()
