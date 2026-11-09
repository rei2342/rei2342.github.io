"""Muse（Meta のパーソナルAI）で集めた「読者の生の悩み」と「AKIRA のストーリーズ書き起こし」を取り込み、
generate のネタ元（シード）として最優先で使う。

置き場所: data/muse_inbox/
  - <account_key>__<任意>.csv|tsv|json|md   … ファイル名の先頭でアカウントを指定
  - <account_key>/<任意>.csv               … サブフォルダでも可
  - 表の中に account 列があれば行ごとにそちらを優先（ラベル「さくら」でも key でも可）
  - ファイル名に stories / story / ストーリー を含むものは「本人のストーリーズ書き起こし」として扱う

取り込んだ行は data/muse/<account_key>/items.jsonl に正規化して貯め、未使用のものから順に generate に渡す。
取り込み済みのファイルは sha256 で覚えるので、同じファイルを置き直しても二重には入らない。

他人の投稿から拾った悩みは「場面の言い換え」として使う。原文の引用・@ハンドル・個人名は原稿に載せない
（引用文は quote 欄に残すが、@ハンドルとURLはここで落とす）。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from core import config as C

INBOX = C.DATA_DIR / "muse_inbox"
STORE = C.DATA_DIR / "muse"
STATE = INBOX / ".ingested.json"
EXTS = {".csv", ".tsv", ".json", ".jsonl", ".md", ".txt"}

# 列名の揺れ（Muse が日本語/英語どちらで返しても拾う）
ALIASES: dict[str, list[str]] = {
    "account": ["account", "アカウント", "account_key"],
    "platform": ["platform", "媒体", "プラットフォーム", "sns"],
    "date": ["date", "日付", "投稿日", "posted_at"],
    "post_url": ["post_url", "url", "投稿url", "リンク", "source_url"],
    "scene": ["scene", "困っている場面", "場面", "悩みの場面", "situation", "pain", "悩み"],
    "tried_failed": ["tried_failed", "試してダメだったこと", "試したこと", "うまくいかなかったこと", "tried", "failed_attempts"],
    "open_question": ["open_question", "未解決の疑問", "疑問", "知りたいこと", "question", "unresolved_question"],
    "quote": ["quote", "原文", "引用", "投稿の一部", "excerpt", "text"],
    "engagement": ["engagement", "反応", "反応数", "いいね", "likes", "reactions"],
    "transcript": ["transcript", "書き起こし", "本文", "話した内容"],
    "topic": ["topic", "テーマ", "話題"],
    "story_no": ["story_no", "番号", "no", "#"],
}
STORY_HINT = re.compile(r"stor(y|ies)|ストーリー", re.I)


def _canon(col: str) -> str | None:
    c = re.sub(r"[\s　（）()【】\[\]・:：]", "", str(col or "")).lower()
    for key, names in ALIASES.items():
        for n in names:
            if c == re.sub(r"[\s　（）()【】\[\]・:：]", "", n).lower():
                return key
    return None


def _clean(s: Any, limit: int = 400) -> str:
    s = re.sub(r"https?://\S+", "", str(s or ""))
    s = re.sub(r"@[A-Za-z0-9_.]{2,}", "@…", s)
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _engagement(v: Any) -> float:
    m = re.search(r"[\d.,]+", str(v or ""))
    if not m:
        return 0.0
    n = float(m.group(0).replace(",", ""))
    return n * (10000 if "万" in str(v) else 1000 if re.search(r"[kK千]", str(v)) else 1)


# ---------------------------------------------------------------- 表の読み取り
def parse_table(text: str, suffix: str = "") -> list[dict]:
    """CSV / TSV / JSON / JSONL / Markdown 表 を、列名を正規化した dict の配列にする。"""
    t = (text or "").strip().lstrip("\ufeff")
    if not t:
        return []
    fence = re.search(r"```(?:\w+)?\n([\s\S]*?)```", t)
    if fence:                                   # Muse がコードブロックで返した場合
        t = fence.group(1).strip()
    rows: list[dict] = []
    if t[:1] in "[{":
        try:
            data = json.loads(t)
        except json.JSONDecodeError:
            data = [json.loads(line) for line in t.splitlines() if line.strip().startswith("{")]
        if isinstance(data, dict):
            data = data.get("items") or data.get("rows") or data.get("data") or [data]
        rows = [r for r in data if isinstance(r, dict)]
    elif re.search(r"^\s*\|.+\|\s*$", t, re.M):    # Markdown 表
        lines = [ln.strip() for ln in t.splitlines() if ln.strip().startswith("|")]
        lines = [ln for ln in lines if not re.fullmatch(r"\|[\s:\-|]+\|", ln)]
        cells = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines]
        if cells:
            head = cells[0]
            rows = [dict(zip(head, r)) for r in cells[1:]]
    else:
        delim = "\t" if (suffix == ".tsv" or t.splitlines()[0].count("\t") > t.splitlines()[0].count(",")) else ","
        rows = list(csv.DictReader(io.StringIO(t), delimiter=delim))
    out = []
    for r in rows:
        n: dict[str, Any] = {}
        for k, v in r.items():
            ck = _canon(k)
            if ck and v not in (None, "") and ck not in n:
                n[ck] = v
        out.append(n)
    return out


def _resolve_account(value: str | None, master: dict | None = None) -> str | None:
    from core.account_loader import get_accounts

    if not value:
        return None
    v = str(value).strip().lstrip("@")
    for a in get_accounts(master):
        handles = {str(h).lstrip("@").lower() for h in (a.handle(p) for p in a.platforms) if h}
        if v in (a.key, a.label) or v.lower() in handles:
            return a.key
    return None


def _file_account(path: Path, master: dict | None) -> str | None:
    rel = path.relative_to(INBOX)
    if len(rel.parts) > 1:
        return _resolve_account(rel.parts[0], master)
    return _resolve_account(path.stem.split("__")[0], master)


def normalize(row: dict, account_key: str, kind: str, source_file: str) -> dict | None:
    if kind == "own_story":
        tr = _clean(row.get("transcript") or row.get("quote"), 1200)
        if not tr:
            return None
        item = {"kind": kind, "transcript": tr, "topic": _clean(row.get("topic"), 120),
                "scene": _clean(row.get("scene") or row.get("topic"), 200), "tried_failed": _clean(row.get("tried_failed"), 200),
                "open_question": _clean(row.get("open_question"), 200), "date": str(row.get("date") or "")[:20],
                "story_no": str(row.get("story_no") or "")}
    else:
        scene = _clean(row.get("scene"), 300)
        q = _clean(row.get("open_question"), 300)
        if not (scene or q):
            return None
        item = {"kind": "audience_pain", "scene": scene, "tried_failed": _clean(row.get("tried_failed"), 300),
                "open_question": q, "quote": _clean(row.get("quote"), 160),
                "platform": _clean(row.get("platform"), 20).lower(), "date": str(row.get("date") or "")[:20],
                "post_url": str(row.get("post_url") or "")[:300], "engagement": _engagement(row.get("engagement"))}
    key = (item.get("scene", "") + "|" + item.get("open_question", "") + "|" + item.get("transcript", "")[:80])
    item["id"] = hashlib.sha1(f"{account_key}|{key}".encode()).hexdigest()[:12]
    item.update(account_key=account_key, source_file=source_file, ingested_at=C.now_iso(), used_by=[])
    return item


# ---------------------------------------------------------------- 保存・取り出し
def _items_path(account_key: str) -> Path:
    return STORE / account_key / "items.jsonl"


def load_items(account_key: str) -> list[dict]:
    p = _items_path(account_key)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _save_items(account_key: str, items: list[dict]) -> None:
    p = _items_path(account_key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")


def ingest_text(text: str, account_key: str | None, source_file: str, kind: str | None = None,
                master: dict | None = None) -> dict[str, int]:
    """表テキストを取り込む。戻り値は {account_key: 追加件数}。"""
    kind = kind or ("own_story" if STORY_HINT.search(source_file) else "audience_pain")
    added: dict[str, int] = {}
    buckets: dict[str, list[dict]] = {}
    for row in parse_table(text, Path(source_file).suffix.lower()):
        acct = _resolve_account(row.get("account"), master) or account_key
        if not acct:
            continue
        it = normalize(row, acct, kind, source_file)
        if it:
            buckets.setdefault(acct, []).append(it)
    for acct, new in buckets.items():
        cur = load_items(acct)
        have = {i["id"] for i in cur}
        fresh = [i for i in new if i["id"] not in have and not have.add(i["id"])]
        if fresh:
            _save_items(acct, cur + fresh)
        added[acct] = len(fresh)
    return added


def ingest_inbox(master: dict | None = None) -> dict[str, Any]:
    """data/muse_inbox/ の未取り込みファイルを全部取り込む。generate の前に毎回呼ばれる。"""
    INBOX.mkdir(parents=True, exist_ok=True)
    state = C.read_json(STATE, {}) or {}
    report: dict[str, Any] = {"files": [], "skipped": []}
    for p in sorted(INBOX.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in EXTS or p.name.startswith("."):
            continue
        raw = p.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        rel = str(p.relative_to(INBOX))
        if state.get(rel, {}).get("sha256") == sha:
            continue
        acct = _file_account(p, master)
        added = ingest_text(raw.decode("utf-8", errors="replace"), acct, rel, master=master)
        if not added:
            report["skipped"].append({"file": rel, "reason": "アカウントを特定できない、または読める行が無い"
                                      "（ファイル名を <account_key>__xxx.csv にするか account 列を入れる）"})
        state[rel] = {"sha256": sha, "ingested_at": C.now_iso(), "added": added}
        report["files"].append({"file": rel, "added": added})
    C.write_json(STATE, state)
    return report


def save_paste(text: str, account_key: str, kind: str = "audience_pain") -> Path:
    """ダッシュボードから貼り付けた表を inbox にファイルとして置く（取り込みは ingest_inbox）。"""
    INBOX.mkdir(parents=True, exist_ok=True)
    t = (text or "").strip()
    suffix = ".json" if t[:1] in "[{" else ".md" if re.search(r"^\s*\|", t, re.M) else ".csv"
    tag = "stories" if kind == "own_story" else "pain"
    p = INBOX / f"{account_key}__{tag}_{C.now_iso().replace(':', '').replace('+0000', '')[:15]}{suffix}"
    p.write_text(t + "\n", encoding="utf-8")
    return p


def pending(account_key: str) -> list[dict]:
    return [i for i in load_items(account_key) if not i.get("used_by")]


def next_seed(account_key: str) -> dict | None:
    """未使用のシードを1つ。悩み（他人の投稿）は反応の大きいもの・新しいものから、無ければストーリーズ。"""
    items = pending(account_key)
    pains = sorted((i for i in items if i["kind"] == "audience_pain"),
                   key=lambda i: (i.get("engagement", 0), i.get("date", "")), reverse=True)
    stories = sorted((i for i in items if i["kind"] == "own_story"), key=lambda i: i.get("date", ""), reverse=True)
    seed = (pains or stories or [None])[0]
    if seed:
        # 同じ場面の別の声（最大3件）を補強材料として添える
        related = [i for i in pains if i["id"] != seed["id"]][:3]
        seed = {**seed, "related": [{k: r.get(k) for k in ("scene", "tried_failed", "open_question")} for r in related]}
        if seed["kind"] == "audience_pain" and stories:
            seed["own_story_hint"] = {k: stories[0].get(k) for k in ("topic", "transcript", "date")}
    return seed


def mark_used(account_key: str, item_id: str, draft_id: str) -> None:
    items = load_items(account_key)
    for i in items:
        if i["id"] == item_id:
            i.setdefault("used_by", []).append(draft_id)
    _save_items(account_key, items)


def stats() -> dict[str, dict[str, int]]:
    out = {}
    if STORE.exists():
        for d in STORE.iterdir():
            if d.is_dir():
                items = load_items(d.name)
                out[d.name] = {"total": len(items), "pending": sum(1 for i in items if not i.get("used_by")),
                               "stories": sum(1 for i in items if i["kind"] == "own_story")}
    return out


# ---------------------------------------------------------------- Muse に投げる調査プロンプト
PAIN_HEADER = "account,platform,date,post_url,scene,tried_failed,open_question,quote,engagement"
STORY_HEADER = "account,date,story_no,topic,transcript,scene,tried_failed,open_question"


def research_prompt(acct, days: int = 30, n: int = 20) -> str:
    p = acct.persona
    plats = [x for x in ("threads", "instagram") if x in acct.platforms] or ["threads", "instagram"]
    return f"""あなたは市場調査のアシスタントです。Threads と Instagram の公開投稿・コメントから、次の読者層の「生の悩み」を調べてください。

【調べる読者層】
{p.get('observed_target_audience') or acct.label + 'の読者'}

【テーマの範囲】
{p.get('core_theme') or ''}

【条件】
- 期間: 直近{days}日以内の投稿・コメント（{'/'.join(plats)}）
- 本人が自分の状況として書いている投稿だけ。広告・PR・アフィリエイト・業者・インフルエンサーの宣伝は除外
- 「困っている場面」「試してダメだったこと」「まだ解決していない疑問」が読み取れるものを優先
- 同じ人の投稿は1件まで。似た悩みは反応の大きい1件に絞る
- 個人名・@ハンドル・顔写真の説明は書かない。quote は60字以内の抜粋
- 推測で埋めない。読み取れない欄は空欄にする

【出力】
CSV だけを返してください（説明文やコードブロックは不要）。1行目は次のヘッダーをそのまま使い、{n}行出してください。
{PAIN_HEADER}

- account は「{acct.key}」で固定
- platform は threads / instagram
- date は YYYY-MM-DD
- scene: どんな場面で困っているか（例: 「〜しようとしたら〜で止まった」）
- tried_failed: すでに試してうまくいかなかったこと
- open_question: まだ答えが出ていない疑問（本人の言葉に近い形で）
- engagement: いいね＋コメントの合計（分かる範囲で数字）
- 値にカンマを含むときはダブルクォートで囲む"""


def stories_prompt(acct, days: int = 30) -> str:
    return f"""@{acct.handle('instagram') or acct.key} の Instagram ストーリーズ（直近{days}日）を、話した内容がわかるように書き起こしてください。

【条件】
- 1ストーリー＝1行。話していない（画像だけの）ストーリーは topic だけ書いて transcript は空欄
- 言い直しや言いよどみは削ってよいが、内容を足したり要約で言い換えたりしない
- 他人の名前・顔・個人が特定できる情報は書かない

【出力】
CSV だけを返してください。1行目は次のヘッダーをそのまま使う。
{STORY_HEADER}

- account は「{acct.key}」で固定
- scene / tried_failed / open_question は、話の中に「視聴者の困りごと」「試してダメだったこと」「答えていない疑問」が出てきた場合だけ書く"""
