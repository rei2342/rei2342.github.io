#!/usr/bin/env python3
"""
social_stock.py
X と Threads の投稿ストックを**全部** 1か所へ集める。読むだけ。

  python social_stock.py

出力: workspace/social/
  SOCIAL_STOCK_ALL.md    全文
  SOCIAL_STOCK_ALL.csv   機械処理用
  SOCIAL_SCOPE.md        件数の検算と重複

**投稿・予約変更・削除・文面修正はしない。** ファイルを読んで並べるだけ。

数える単位は「投稿1本」。スレッド2連なら2件として数える。
セット1ファイルを1件にすると、Xの1投稿とThreadsのスレッドが
同じ重みになってしまい、検算が合わなくなる。
"""
import csv
import hashlib
import html as htmlmod
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
OUT = ROOT / "workspace/social"
TH = ROOT / "workspace/threads"
XP = ROOT / "workspace/x_promo"
DR = ROOT / "workspace/claims/drafts"
INS = ROOT / "workspace/threads_insights/history.jsonl"
XSTATE = ROOT / "workspace/x_state.json"

# 記事IDと、**今の**タイトル。ストックの中の題名は古いことがある
TITLES = {}
abc = ROOT / "workspace/seo/survey/ABC.csv"
if abc.exists():
    for r in csv.DictReader(abc.open(encoding="utf-8")):
        TITLES[r["post_id"]] = r["title"]
for f in sorted(DR.glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    TITLES.setdefault(str(d.get("id")), d.get("title", ""))

URLS = {
    "315": "https://sakura-eigo.com/cebu-island-one-month-study-abroad/",
    "521": "https://sakura-eigo.com/toeic-listening-325-to-improvement/",
    "526": "https://sakura-eigo.com/fast-verify-cost-time-travel/",
    "546": "https://sakura-eigo.com/online-english-lessons-90-days-success/",
    "583": "https://sakura-eigo.com/?p=583（下書き。公開URLはまだ無い）",
    "647": "https://sakura-eigo.com/?p=647（下書き）",
}

rows = []


def add(**kw):
    kw.setdefault("image", "なし")
    kw.setdefault("image_file", "")
    kw.setdefault("cta", "")
    kw.setdefault("link", "")
    kw.setdefault("hashtag", "なし")
    kw.setdefault("post_id", "")
    kw.setdefault("scheduled_at", "")
    rows.append(kw)


def strip_tags(h):
    return htmlmod.unescape(re.sub(r"\n{3,}", "\n\n",
                                   re.sub(r"<[^>]+>", "\n", h))).strip()


def blocks(text):
    """`## 見出し` ごとに切る。```で囲まれていれば中身だけ取る。"""
    out = []
    for m in re.finditer(r"^## (.+?)$\n(.*?)(?=^## |\Z)", text,
                         re.M | re.S):
        head, body = m.group(1).strip(), m.group(2).strip()
        fenced = re.findall(r"```(?:text)?\n(.*?)```", body, re.S)
        out.append((head, "\n\n".join(x.strip() for x in fenced)
                    if fenced else body))
    return out


# ── 1. Threads: セットファイル（drafter / cannon が書く）────────
for f in sorted(TH.glob("*.md")):
    if f.name == "README.md":
        continue
    src = f.read_text(encoding="utf-8")
    lines = src.split("\n")
    pid = ""
    m = re.search(r"\[(\d+)\]", src)
    if m:
        pid = m.group(1)
    title_line = ""
    tm = re.search(r"^元記事: (.+)$", src, re.M)
    if tm:
        title_line = tm.group(1).strip()
    hm = re.search(r"^# .*?— \[\d+\] (.+)$", src, re.M)
    if hm:
        title_line = hm.group(1).strip()
    gen = ("threads_builder.py（手動ワークフロー）" if f.name.startswith("built_")
           else "見本（人が作った）" if f.name.startswith("SAMPLE")
           else "daily-article-drafter.yml の Threads ステップ"
           if re.match(r"2026-08-0[478]", f.name)
           else "threads-note-cannon.yml（claude -p）")
    tmpl = ("scripts/threads_builder.py の RULES"
            if f.name.startswith("built_")
            else ".github/workflows/daily-article-drafter.yml L280-L410"
            if re.match(r"2026-08-0[478]", f.name)
            else ".github/workflows/threads-note-cannon.yml の claude -p"
            if f.name.startswith("2026")
            else "（見本・生成物ではない）")
    for head, body in blocks(src):
        if not body.strip():
            continue
        if head.startswith(("note", "ビジュアル", "アフィ")):
            continue
        n = re.match(r"[①②③]?\s*(\d)投稿目", head)
        idx = n.group(1) if n else "1"
        line_no = next((i + 1 for i, l in enumerate(lines)
                        if l.startswith("## ") and head in l), 1)
        link = ""
        lm = re.search(r"https?://sakura-eigo\.com/\S+", body)
        if lm:
            link = lm.group(0)
        add(platform="Threads",
            stock_id=f"TH-FILE-{f.stem}-{idx}",
            file=f"workspace/threads/{f.name}", line=line_no,
            post_id=pid, title=title_line, url=URLS.get(pid, ""),
            text=body, state="下書き（未投稿・手で貼る前提）",
            scheduled_at="なし（自動投稿の口が無い）",
            generator=gen, template=tmpl,
            link=link,
            cta=("記事へ送る一言あり" if re.search(r"ブログに(書いた|まとめた)|noteに書いた|記事に書いた", body) else "なし"),
            hashtag="あり" if "#" in body else "なし")

# ── 2. Threads: WordPress の【Threads用】メモ ────────────────
for f in sorted(DR.glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    if "Threads用" not in str(d.get("title", "")):
        continue
    pid = str(d["id"])
    raw = (DR / f"{pid}.raw.html")
    body = strip_tags(raw.read_text(encoding="utf-8")) if raw.exists() else ""
    src_title = ""
    sm = re.search(r"^元記事: (.+)$", body, re.M)
    if sm:
        src_title = sm.group(1).strip()
    parts = re.split(r"^[①②]\s*\d投稿目.*$", body, flags=re.M)
    for i, p in enumerate(parts[1:], 1):
        p = re.sub(r"^元記事:.*$", "", p, flags=re.M).strip()
        p = re.sub(r"^(note タイトル案|ビジュアル案)$[\s\S]*", "", p,
                   flags=re.M).strip()
        if not p:
            continue
        lm = re.search(r"https?://sakura-eigo\.com/\S+", p)
        add(platform="Threads",
            stock_id=f"TH-MEMO-{pid}-{i}",
            file=f"WordPress 下書き 記事ID {pid}（【Threads用】メモ）",
            line=i, post_id="", title=src_title, url="",
            text=p,
            state="WordPress下書き（メモ。公開しない）",
            scheduled_at="なし",
            generator=("threads_builder.py（メモ更新モード）"
                       if pid in ("547",) else
                       "daily-article-drafter.yml の Threads ステップ"),
            template=("scripts/threads_builder.py の RULES" if pid == "547"
                      else ".github/workflows/daily-article-drafter.yml L280-L410"),
            link=lm.group(0) if lm else "",
            cta=("記事へ送る一言あり"
                 if re.search(r"ブログに(書いた|まとめた)|記事に書いた|記事URL", p)
                 else "なし"),
            hashtag="あり" if "#" in p else "なし")

# ── 3. Threads: 実際に投稿済み（Threads API の実測）─────────────
if INS.exists():
    seen = {}
    for line in INS.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d.get("account") != "さくら":
            continue
        if "@sakura_eigo30" not in d.get("permalink", ""):
            continue          # 同じ設定名で別アカウントの分が混ざっている
        seen[d["id"]] = d
    for d in sorted(seen.values(), key=lambda x: x["posted_at"]):
        add(platform="Threads",
            stock_id=f"TH-LIVE-{d['id']}",
            file="workspace/threads_insights/history.jsonl", line="-",
            post_id="", title="（APIは記事IDを持たない）",
            url=d["permalink"],
            text=d["text"] + "  ※Threads APIの本文は先頭のみ返る（全文ではない）",
            state=f"投稿済み（表示{d['views']} いいね{d['likes']} 返信{d['replies']}）",
            scheduled_at=d["posted_at"],
            generator="人が手で貼った（Threads自動投稿は未接続）",
            template="上のストックのどれかを手で貼ったもの",
            hashtag="なし")

# ── 4. X: 記事告知のストック ─────────────────────────────────
for f in sorted(XP.glob("*.md")):
    src = f.read_text(encoding="utf-8")
    pid = re.search(r"\[(\d+)\]", src)
    pid = pid.group(1) if pid else ""
    title = re.search(r"^# X告知 — \[\d+\] (.+)$", src, re.M)
    for head, body in blocks(src):
        if not body.strip():
            continue
        idx = "1" if head.startswith("1") else "2"
        add(platform="X",
            stock_id=f"X-PROMO-{pid}-{idx}",
            file=f"workspace/x_promo/{f.name}",
            line=next((i + 1 for i, l in enumerate(src.split("\n"))
                       if l.startswith("## ") and head in l), 1),
            post_id=pid, title=title.group(1) if title else "",
            url=URLS.get(pid, ""),
            text=body.strip(),
            state="下書き（DRY RUN の出力。投稿していない）",
            scheduled_at="なし（x-promo.yml は手動実行のみ）",
            generator="scripts/x_promo.py（claude-opus-4-8）",
            template="scripts/x_promo.py の RULES",
            link=(body.strip() if body.strip().startswith("http") else ""),
            cta=("リンクのみ" if body.strip().startswith("http") else "なし"),
            hashtag="なし")

# ── 5. X: 直近の投稿済み1本（state に1本しか残らない）──────────
if XSTATE.exists():
    st = json.loads(XSTATE.read_text(encoding="utf-8"))
    if st.get("last_text"):
        add(platform="X",
            stock_id="X-LIVE-last",
            file="workspace/x_state.json", line=4,
            post_id="", title="（自動投稿は記事に紐付かない）", url="",
            text=st["last_text"],
            state="投稿済み（**残っているのは直近1本だけ**）",
            scheduled_at=st.get("last_post", ""),
            generator=".github/workflows/x-poster.yml（claude-haiku-4-5）",
            template=".github/workflows/x-poster.yml L110-L175 の prompt",
            hashtag="なし")

# ── 重複判定 ─────────────────────────────────────────────
def norm(t):
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"※Threads APIの本文.*", "", t)
    return re.sub(r"\s+", "", t)


for r in rows:
    r["norm"] = norm(r["text"])
    r["hash"] = hashlib.md5(r["norm"].encode()).hexdigest()[:8]
    r["chars"] = len(r["text"])

exact = {}
for r in rows:
    exact.setdefault(r["hash"], []).append(r["stock_id"])
for r in rows:
    same = [x for x in exact[r["hash"]] if x != r["stock_id"]]
    r["dup_exact"] = " ".join(same)


def contains(a, b):
    return len(a) > 40 and len(b) > 40 and (a in b or b in a)


for r in rows:
    near = [o["stock_id"] for o in rows
            if o is not r and not contains(r["norm"], o["norm"]) is True
            and o["hash"] != r["hash"] and contains(r["norm"], o["norm"])]
    r["dup_near"] = " ".join(near)

per_article = {}
for r in rows:
    key = r["post_id"] or r["title"]
    per_article.setdefault(key, []).append(r["stock_id"])
for r in rows:
    r["same_article_count"] = len(per_article[r["post_id"] or r["title"]])

OUT.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

FIELDS = ["platform", "stock_id", "file", "line", "post_id", "title", "url",
          "chars", "state", "scheduled_at", "generator", "template",
          "link", "cta", "hashtag", "image", "image_file",
          "same_article_count", "hash", "dup_exact", "dup_near", "text"]
with (OUT / "SOCIAL_STOCK_ALL.csv").open("w", encoding="utf-8",
                                         newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)

L = [f"# X・Threads 投稿ストック 全文一覧（{stamp}）\n\n",
     "**読むだけ。投稿・予約変更・削除・文面修正はしていない。**\n\n",
     f"全{len(rows)}件（X {sum(1 for r in rows if r['platform']=='X')} / "
     f"Threads {sum(1 for r in rows if r['platform']=='Threads')}）。\n"
     "数える単位は投稿1本。スレッド2連は2件。\n\n"]
for plat in ("X", "Threads"):
    L.append(f"\n---\n\n# {plat}\n")
    for r in [x for x in rows if x["platform"] == plat]:
        L.append(f"\n## {r['stock_id']}\n\n")
        L.append("| 項目 | 内容 |\n|---|---|\n")
        for k, label in (("file", "元ファイル"), ("line", "行"),
                         ("post_id", "記事ID"), ("title", "記事タイトル"),
                         ("url", "記事URL"), ("state", "状態"),
                         ("scheduled_at", "予約日時・投稿日時"),
                         ("generator", "生成元"),
                         ("template", "テンプレート・プロンプトの場所"),
                         ("cta", "CTA"), ("link", "リンク"),
                         ("hashtag", "ハッシュタグ"),
                         ("image", "画像"), ("image_file", "画像ファイル"),
                         ("chars", "文字数"),
                         ("same_article_count", "同じ記事から作られた本数"),
                         ("dup_exact", "完全一致の相手"),
                         ("dup_near", "包含関係の相手")):
            v = r.get(k, "")
            L.append(f"| {label} | {v if v != '' else '—'} |\n")
        L.append("\n```\n" + r["text"] + "\n```\n")
(OUT / "SOCIAL_STOCK_ALL.md").write_text("".join(L), encoding="utf-8")

nx = sum(1 for r in rows if r["platform"] == "X")
nt = len(rows) - nx
dup_pairs = sorted({tuple(sorted([r["stock_id"], o]))
                    for r in rows for o in r["dup_exact"].split() if o})
near_pairs = sorted({tuple(sorted([r["stock_id"], o]))
                     for r in rows for o in r["dup_near"].split() if o})
S = [f"# 数え方と検算（{stamp}）\n\n",
     "## 単位\n\n投稿1本を1件とする。スレッド2連は2件。\n"
     "セット1ファイルを1件にすると、Xの1投稿とThreadsのスレッドが同じ重みになる。\n\n",
     "## 検算\n\n",
     f"| 区分 | 件数 |\n|---|---|\n| X | {nx} |\n| Threads | {nt} |\n"
     f"| **合計** | **{nx + nt}** |\n\n",
     f"X {nx} ＋ Threads {nt} ＝ {nx + nt}。CSVの行数と一致する。\n\n",
     "## 内訳\n\n| 置き場 | 件数 |\n|---|---|\n"]
kinds = {}
for r in rows:
    k = r["stock_id"].rsplit("-", 1)[0] if r["stock_id"].count("-") < 2 \
        else "-".join(r["stock_id"].split("-")[:2])
    kinds[k] = kinds.get(k, 0) + 1
for k, v in sorted(kinds.items()):
    S.append(f"| {k} | {v} |\n")
S.append(f"\n## 重複\n\n完全一致 {len(dup_pairs)}組 / 包含 {len(near_pairs)}組\n\n")
if dup_pairs:
    S.append("### 完全一致（空白を除いて同一）\n\n| A | B |\n|---|---|\n")
    S += [f"| {a} | {b} |\n" for a, b in dup_pairs]
if near_pairs:
    S.append("\n### 片方がもう片方を丸ごと含む\n\n| A | B |\n|---|---|\n")
    S += [f"| {a} | {b} |\n" for a, b in near_pairs]
S.append("\n## この監査に含めなかったもの\n\n"
         "| 対象 | 理由 |\n|---|---|\n"
         "| `workspace/instagram/` | Instagramは今回の対象外（XとThreadsのみ）|\n"
         "| `outputs/`（Track A・転職） | 別人格・別アカウント |\n"
         "| Xの投稿済み履歴 | **保存していない。** x_state.json に直近1本だけ。"
         "x-poster.yml は投稿本文を記録せず、次回許可時刻だけ書く |\n"
         "| Threads投稿の全文 | Threads APIが本文を先頭だけ返す。"
         "実測13本は冒頭のみ |\n")
(OUT / "SOCIAL_SCOPE.md").write_text("".join(S), encoding="utf-8")

print(f"X {nx} / Threads {nt} / 合計 {len(rows)}")
print(f"完全一致 {len(dup_pairs)}組 / 包含 {len(near_pairs)}組")
print(f"→ {OUT}")
