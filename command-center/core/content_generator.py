"""実データ（Astra のペルソナ + クロール実測 + 登録媒体一致の案件）から、
そのアカウントが持っている媒体分だけ原稿を一括生成する。"""
from __future__ import annotations

import json
from typing import Any

from core import config as C
from core import drafts, guards
from core.account_loader import FORMAT_BY_PLATFORM, Account, affiliate_pool, get_account

SPECS = {
    "wordpress": "WordPress記事。HTML（h2/h3/p/ul/table/blockquote）。検索意図に答える結論→比較軸→手順→注意点→CTAの順。2500〜5000字。script禁止。",
    "note": "note記事。Markdown（## 見出し、箇条書き）。体験の断定ではなく『整理・確認の手帖』として読める構成。2000〜4000字。",
    "x": "Xスレッド。1投稿は重み付き280以内（日本語なら140字以内目安）。1投稿目は読者の迷いを代弁＋判断基準、2〜4投稿目で具体的な確認方法、最後に誘導先URL。3〜6投稿。",
    "threads": "Threadsツリー。1投稿500字以内。単体で役立つ本文→記事固有の手順や表→最終投稿の末尾にURL。Xと同じ文を使い回さない。2〜4投稿。",
    "instagram": "IGカルーセル。5〜10枚。1枚目は保存したくなるフック、2枚目以降は1枚1論点（見出し15字以内・本文80字以内）、最後はプロフィール誘導。キャプションはURLを入れずプロフィールリンクへ誘導。ハッシュタグ3〜5個。",
}

PLATFORM_SCHEMAS: dict[str, dict] = {
    "wordpress": {"type": "object", "additionalProperties": False,
                  "required": ["title", "slug", "excerpt", "meta_description", "html", "affiliate_program_ids"],
                  "properties": {"title": {"type": "string"}, "slug": {"type": "string"}, "excerpt": {"type": "string"},
                                 "meta_description": {"type": "string"}, "html": {"type": "string"},
                                 "affiliate_program_ids": {"type": "array", "items": {"type": "string"}}}},
    "note": {"type": "object", "additionalProperties": False,
             "required": ["title", "markdown", "hashtags", "affiliate_program_ids"],
             "properties": {"title": {"type": "string"}, "markdown": {"type": "string"},
                            "hashtags": {"type": "array", "items": {"type": "string"}},
                            "affiliate_program_ids": {"type": "array", "items": {"type": "string"}}}},
    "x": {"type": "object", "additionalProperties": False, "required": ["posts", "buzz_followup"],
          "properties": {"posts": {"type": "array", "items": {"type": "string"}},
                         "buzz_followup": {"type": "string"}}},
    "threads": {"type": "object", "additionalProperties": False, "required": ["posts", "buzz_followup"],
                "properties": {"posts": {"type": "array", "items": {"type": "string"}},
                               "buzz_followup": {"type": "string"}}},
    "instagram": {"type": "object", "additionalProperties": False, "required": ["slides", "caption", "hashtags"],
                  "properties": {"slides": {"type": "array", "items": {
                      "type": "object", "additionalProperties": False, "required": ["headline", "body"],
                      "properties": {"headline": {"type": "string"}, "body": {"type": "string"}}}},
                      "caption": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}}}},
}

SYSTEM = """あなたは日本語SNS・ブログ運用の編集者。対象アカウントの「実際の運用データ」に合わせて原稿を書く。
発想は常にマーケットイン：書き手が言いたいことではなく、読者が今どこで迷っていて、何を確認すれば一歩進めるかから書く。

厳守:
- 提示された実投稿の文体（書き出し・改行・語尾・一人称・絵文字の頻度）に寄せる。文章そのものはコピーしない。
- プロフィールの経歴・実績・体験は「検証済みの事実」ではない。体験談の断定（「私も〜でした」「実際に使ってみて」）や数字の実績を作らない。
- URLは「使ってよいURL」に列挙されたものだけを一字一句そのまま使う。改変・短縮・推測URLは禁止。
- アフィリエイトURLを入れる投稿・記事には必ず「{pr}」表記を入れる（ステマ規制）。各媒体で許可された案件だけを使う。
- 価格・条件は提示された案件情報の範囲だけ。無い数字は書かず「公式で要確認」と書く。
- 誇大表現（必ず・絶対・誰でも・100%）を使わない。占い・恋愛・出会い・お金のテーマは不安を煽らない。
- X と Threads で同じ文章を使い回さない。
- buzz_followup は、その投稿が伸びたときにリプライ欄へぶら下げる1投稿（誘導先URLを1つ含める）。"""


def _persona_block(acct: Account) -> str:
    p = acct.persona
    cal = acct.calibration()
    samples = [f"- [{s.get('kind')}] {s.get('text')}" for s in (p.get("content_samples") or [])[:10]]
    crawled = []
    for plat, d in (cal.get("platforms") or {}).items():
        for post in (d.get("posts") or [])[:4]:
            t = (post.get("title") + "\n" if post.get("title") else "") + (post.get("text") or "")[:400]
            crawled.append(f"[{plat}] {t}")
    return json.dumps({
        "label": acct.label,
        "handles": {k: v.get("handle") for k, v in acct.platforms.items() if v.get("handle")},
        "display_names": {k: v.get("display_name") for k, v in acct.platforms.items() if v.get("display_name")},
        "bio": p.get("actual_bio"),
        "core_theme": p.get("core_theme"),
        "target_audience_observed": p.get("observed_target_audience"),
        "tone_note_by_astra": p.get("tone_and_style"),
        "first_person_observed": p.get("first_person_observed"),
        "limits": acct.conflicts,
        "funnel": acct.funnel_summary(),
        "measured_style": cal.get("style_metrics"),
        "measured_style_by_platform": cal.get("style_by_platform"),
        "tone_summary": cal.get("tone_summary"),
        "recent_titles_to_avoid_duplicating": cal.get("recent_titles", [])[:20],
    }, ensure_ascii=False, indent=1) + "\n\nAstraが採取した標本:\n" + "\n".join(samples) + \
        ("\n\nクロールで取得した直近の実投稿:\n" + "\n---\n".join(crawled[:16]) if crawled else "")


def build_context(acct: Account, platforms: list[str], settings: dict, affiliate_ids: list[str] | None,
                  source_urls: list[str]) -> dict[str, Any]:
    own = acct.own_destinations()
    own_urls = [d["url"] for d in own]
    per: dict[str, Any] = {}
    for p in platforms:
        target = acct.platform(p).get("url")
        pool = affiliate_pool(acct, target, settings)
        usable = [a for a in pool if a["usable"] and (not affiliate_ids or a["program_id"] in affiliate_ids)]
        allowed = sorted(set(own_urls + [a["affiliate_url"] for a in usable] + source_urls + [target]))
        per[p] = {"target_url": target, "affiliates": usable, "blocked_affiliates": [a for a in pool if not a["usable"]],
                  "allowed_urls": allowed, "affiliate_urls": [a["affiliate_url"] for a in usable]}
    return {"own_destinations": own, "per_platform": per}


def generate(account_key: str, topic: str, platforms: list[str] | None = None, affiliate_ids: list[str] | None = None,
             notes: str = "", source_urls: list[str] | None = None, render_images: bool = True) -> dict:
    settings = C.load_settings()
    acct = get_account(account_key)
    active = acct.active_platforms()
    targets = [p for p in (platforms or active) if p in active and p in PLATFORM_SCHEMAS]
    if not targets:
        raise ValueError(f"{acct.label}: 生成できる稼働媒体が無い（active={active}）")
    source_urls = source_urls or []
    ctx = build_context(acct, targets, settings, affiliate_ids, source_urls)
    pr = settings.get("affiliate", {}).get("pr_label", "PR")

    spec_lines = []
    for p in targets:
        c = ctx["per_platform"][p]
        affs = [{k: a[k] for k in ("program_id", "program_name", "unit_price", "affiliate_url", "appeal_point",
                                   "conversion_conditions", "fit_warning")} for a in c["affiliates"]]
        spec_lines.append(f"## {p} ({FORMAT_BY_PLATFORM[p]})\n{SPECS[p]}\n配信先: {c['target_url']}\n"
                          f"この媒体で使ってよいURL: {json.dumps(c['allowed_urls'], ensure_ascii=False)}\n"
                          f"この媒体で使ってよいアフィリエイト案件（テーマに合うものだけ。合わなければ使わない）: "
                          f"{json.dumps(affs, ensure_ascii=False) if affs else 'なし（自分のnote/WP/LINEへの誘導だけ）'}")
    user = (f"# アカウント実データ\n{_persona_block(acct)}\n\n"
            f"# 誘導先（自分の資産）\n{json.dumps(ctx['own_destinations'], ensure_ascii=False)}\n\n"
            f"# 今回のテーマ\n{topic}\n{('補足: ' + notes) if notes else ''}\n"
            f"{('参照してよい一次情報URL: ' + ', '.join(source_urls)) if source_urls else ''}\n\n"
            f"# 出力する媒体\n" + "\n\n".join(spec_lines) +
            "\n\n先に reader_problem（読者の迷い）と angle（このアカウントならではの切り口）を決め、全媒体で一貫させる。")

    schema = {"type": "object", "additionalProperties": False,
              "required": ["reader_problem", "angle", "outputs"],
              "properties": {"reader_problem": {"type": "string"}, "angle": {"type": "string"},
                             "outputs": {"type": "object", "additionalProperties": False, "required": targets,
                                         "properties": {p: PLATFORM_SCHEMAS[p] for p in targets}}}}
    from core.llm import generate_json

    result = generate_json(SYSTEM.replace("{pr}", pr), user, schema, settings)
    return finalize_draft(acct, topic, targets, result, ctx, settings, render_images)


def finalize_draft(acct: Account, topic: str, targets: list[str], result: dict, ctx: dict, settings: dict,
                   render_images: bool = True) -> dict:
    limits = settings.get("platform_limits", {})
    aff_cfg = settings.get("affiliate", {})
    issues = []
    for p in targets:
        c = ctx["per_platform"][p]
        body = result["outputs"].get(p) or {}
        issues += guards.check_platform(p, body, {"allowed_urls": c["allowed_urls"], "affiliate_urls": c["affiliate_urls"],
                                                  "pr_label": aff_cfg.get("pr_label", "PR"),
                                                  "pr_label_required": aff_cfg.get("pr_label_required", True)}, limits)
    draft_id = drafts.new_id(acct.key)
    d = {
        "id": draft_id, "account_key": acct.key, "account_label": acct.label, "topic": topic,
        "created_at": C.now_iso(), "reader_problem": result.get("reader_problem"), "angle": result.get("angle"),
        "outputs": result["outputs"], "context": ctx, "issues": issues,
        "platform_status": {p: "draft" for p in targets}, "history": [{"at": C.now_iso(), "event": "generated"}],
    }
    if render_images and "instagram" in result["outputs"]:
        from core.image_renderer import render_carousel

        media = C.ROOT / settings.get("publishing", {}).get("instagram", {}).get("media_dir", "data/media") / draft_id
        d["outputs"]["instagram"]["image_paths"] = render_carousel(
            result["outputs"]["instagram"].get("slides", []), media, acct.key, acct.handle("instagram"))
    return drafts.save(d)


def revalidate(draft_id: str) -> dict:
    """ダッシュボードで本文を手直ししたあとの再検査。"""
    settings = C.load_settings()
    d = drafts.get(draft_id)
    aff_cfg = settings.get("affiliate", {})
    issues = []
    for p, body in d["outputs"].items():
        c = d["context"]["per_platform"].get(p, {})
        issues += guards.check_platform(p, body, {"allowed_urls": c.get("allowed_urls", []),
                                                  "affiliate_urls": c.get("affiliate_urls", []),
                                                  "pr_label": aff_cfg.get("pr_label", "PR"),
                                                  "pr_label_required": aff_cfg.get("pr_label_required", True)},
                                        settings.get("platform_limits", {}))
    d["issues"] = issues
    return drafts.save(d)
