"""生成物の検査。落ちたら配信しない（error）／人が見る（warn）。"""
from __future__ import annotations

import re
from typing import Any

URL_RE = re.compile(r"https?://[^\s<>\"'）)\]」]+")

# 実体験の裏付けが無い共感・体験の断定（マスター: bio の経験談は検証済み経歴として扱わない）
FABRICATED_EXPERIENCE = [
    "私もそうでした", "僕もそうでした", "わかります、", "実際に使ってみて", "使ってみた結果",
    "私が試した", "僕が試した", "受講してみた", "購入してみた", "絶対に稼げ", "誰でも簡単に",
    "100%", "必ず痩せ", "必ず復縁",
]


def x_weighted_len(text: str) -> int:
    """X の重み付き文字数（URL は 23、CJK 等は 2）。"""
    n = 0
    rest = URL_RE.sub("", text)
    n += 23 * len(URL_RE.findall(text))
    for ch in rest:
        cp = ord(ch)
        if cp <= 4351 or 8192 <= cp <= 8205 or 8208 <= cp <= 8223 or 8242 <= cp <= 8247:
            n += 1
        else:
            n += 2
    return n


def urls_in(text: str) -> list[str]:
    return [u.rstrip(".,、。") for u in URL_RE.findall(text or "")]


def _texts(platform: str, body: dict) -> list[tuple[str, str]]:
    """(位置, テキスト) の一覧。"""
    if platform == "wordpress":
        return [("title", body.get("title", "")), ("html", body.get("html", ""))]
    if platform == "note":
        return [("title", body.get("title", "")), ("markdown", body.get("markdown", ""))]
    if platform in ("x", "threads"):
        return [(f"post[{i}]", p) for i, p in enumerate(body.get("posts", []))]
    if platform == "instagram":
        out = [("caption", body.get("caption", ""))]
        for i, sl in enumerate(body.get("slides", [])):
            out.append((f"slide[{i}]", f"{sl.get('headline', '')}\n{sl.get('body', '')}"))
        return out
    return []


def check_platform(platform: str, body: dict, ctx: dict[str, Any], limits: dict) -> list[dict]:
    issues: list[dict] = []
    allowed = set(ctx.get("allowed_urls", []))
    affiliate = set(ctx.get("affiliate_urls", []))
    pr = ctx.get("pr_label", "PR")

    def add(level, where, msg):
        issues.append({"platform": platform, "level": level, "where": where, "msg": msg})

    texts = _texts(platform, body)
    joined = "\n".join(t for _, t in texts)
    for where, t in texts:
        for u in urls_in(t):
            if u not in allowed:
                add("error", where, f"許可リスト外のURL: {u}（URLの捏造・改変・別媒体用コードの流用）")
        for w in FABRICATED_EXPERIENCE:
            if w in t:
                add("warn", where, f"裏付けの無い体験・断定表現: 「{w}」")
    has_aff = any(u in affiliate for u in urls_in(joined))
    if has_aff and ctx.get("pr_label_required", True):
        if platform in ("x", "threads"):
            for where, t in texts:
                if any(u in affiliate for u in urls_in(t)) and pr not in t:
                    add("error", where, f"アフィリンクを含む投稿に「{pr}」表記が無い（ステマ規制）")
        elif pr not in joined and "広告" not in joined and "プロモーション" not in joined:
            add("error", "body", f"アフィリンクを含むのに {pr}/広告 表記が無い（ステマ規制）")

    if platform == "x":
        lim = int(limits.get("x_weighted_chars", 280))
        posts = body.get("posts", [])
        if not posts:
            add("error", "posts", "投稿が空")
        for i, p in enumerate(posts):
            w = x_weighted_len(p)
            if w > lim:
                add("error", f"post[{i}]", f"X の文字数超過 {w}/{lim}（重み付き）")
    elif platform == "threads":
        lim = int(limits.get("threads_chars", 500))
        for i, p in enumerate(body.get("posts", [])):
            if len(p) > lim:
                add("error", f"post[{i}]", f"Threads の文字数超過 {len(p)}/{lim}")
        if not body.get("posts"):
            add("error", "posts", "投稿が空")
    elif platform == "instagram":
        cap = body.get("caption", "")
        if len(cap) > int(limits.get("ig_caption_chars", 2200)):
            add("error", "caption", "キャプション文字数超過")
        tags = re.findall(r"#\S+", cap) + [t if t.startswith("#") else "#" + t for t in body.get("hashtags", [])]
        if len(set(tags)) > int(limits.get("ig_hashtags_max", 5)):
            add("warn", "hashtags", f"ハッシュタグ {len(set(tags))} 個（推奨 {limits.get('ig_hashtags_max', 5)} 個以下）")
        n = len(body.get("slides", []))
        if not (int(limits.get("ig_carousel_slides_min", 5)) <= n <= int(limits.get("ig_carousel_slides_max", 10))):
            add("error", "slides", f"カルーセル枚数 {n}（5〜10枚）")
        if urls_in(cap):
            add("warn", "caption", "IG キャプションのURLはリンクにならない。プロフィール誘導の文言に置き換える")
    elif platform == "wordpress":
        if len(re.sub(r"<[^>]+>", "", body.get("html", ""))) < 1500:
            add("warn", "html", "本文が1500字未満")
        if "<script" in body.get("html", "").lower():
            add("error", "html", "script タグは入れない")
    elif platform == "note":
        if len(body.get("markdown", "")) < 1200:
            add("warn", "markdown", "本文が1200字未満")
    return issues


def check_bundle(bundle: dict, ctx: dict, limits: dict) -> list[dict]:
    issues = []
    for p, body in (bundle.get("outputs") or {}).items():
        if body:
            issues.extend(check_platform(p, body, ctx, limits))
    return issues


def has_errors(issues: list[dict]) -> bool:
    return any(i["level"] == "error" for i in issues)
