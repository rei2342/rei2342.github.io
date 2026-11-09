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


AUTO_TOPIC = ("（未指定）上の実投稿・既存記事タイトル・誘導先・案件から、このアカウントの読者が今いちばん迷っていそうなことを1つ選ぶ。"
              "既存記事と同じテーマは避け、誘導先（noteの有料記事・WP記事・LINE・案件）に自然につながるものにする。")


FUNNEL = """# 構成（悩み解決型ファネル。全媒体共通）
1. フック: 読者が「困っている場面」「試してダメだったこと」「まだ解けていない疑問」のどれかを、読者側の言葉で1行目に置く。
   - pain_hook.hook_line をそのまま X の1投稿目の1行目・Threads の1投稿目の1行目・WP 記事の導入（PR表記の直後の最初の段落）・
     note の本文1段落目に入れる（媒体ごとの言い回しの調整は2行目以降で）。
   - 案件名・商品名・価格からは書き始めない。
2. 共感と原因: 試したことがなぜうまくいかなかったのかを、判断基準の形で示す（読者を責めない）。
3. 解き方: 自分で今日できる確認・手順を先に渡す（ここだけでも役に立つこと）。
4. 解決策の提示: 手順で足りない人に向けて、許可された案件（WP）・有料note・LINE などを「この場面ならこれ」という順で1〜2個だけ示す。
   案件のスペック紹介を主にしない。合う案件が無ければ案件は使わず、自分のnote/WP/LINEへの誘導だけにする。
5. CTA: 次の一歩を1つに絞る。"""

SEED_RULES = """# Muse 調査のシード（最優先のネタ元）
下の seed は Muse で Threads/Instagram から集めた実在の読者の声（または本人のストーリーズ書き起こし）。
- reader_problem と pain_hook は seed から作る。seed に無い悩みや体験を足さない。
- 他人の投稿の原文（quote）をそのまま引用しない。個人が分かる情報・@ハンドル・URLは書かない。場面として言い換える。
- kind=own_story は本人が実際に話した内容。話した範囲の言い換えは使ってよいが、話していない経歴・数字・体験は足さない。
- pain_hook.source には seed の id を入れる。"""

PAIN_HOOK_SCHEMA = {"type": "object", "additionalProperties": False,
                    "required": ["scene", "tried_failed", "open_question", "hook_line", "source"],
                    "properties": {"scene": {"type": "string"}, "tried_failed": {"type": "string"},
                                   "open_question": {"type": "string"}, "hook_line": {"type": "string"},
                                   "source": {"type": "string"}}}


def _norm_text(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>|[\s　#*>「」『』、。,.!！?？…・|｜]", "", s or "")


def check_hook(result: dict) -> list[dict]:
    """pain_hook.hook_line が各媒体の冒頭に入っているか（悩み解決型の1行目ルール）。"""
    hook = (result.get("pain_hook") or {}).get("hook_line") or ""
    key = _norm_text(hook)[:14]
    if not key:
        return [{"level": "error", "platform": "all", "where": "pain_hook", "msg": "pain_hook.hook_line が空"}]
    outs = result.get("outputs", {})
    heads = {}
    if (outs.get("x") or {}).get("posts"):
        heads["x"] = outs["x"]["posts"][0][:200]
    if (outs.get("threads") or {}).get("posts"):
        heads["threads"] = outs["threads"]["posts"][0][:300]
    if "wordpress" in outs:
        heads["wordpress"] = (outs["wordpress"].get("html") or "")[:900]
    if "note" in outs:
        heads["note"] = (outs["note"].get("markdown") or "")[:600]
    issues = []
    for p, head in heads.items():
        if key not in _norm_text(head):
            issues.append({"level": "error", "platform": p, "where": "冒頭",
                           "msg": f"フック「{hook[:30]}」が冒頭に入っていない（悩み解決型の1行目ルール）"})
    return issues


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
    # クッション導線: SNS/note には広告リンクを貼らず、自前WPの記事へ送り、WP記事の中で広告リンクを踏ませる。
    # 媒体一致の判定は WP 側で済んでいるので、SNS 側に渡すのは「WPに何の案件があるか」と誘導先URLだけ。
    wp_url = acct.platform("wordpress").get("url") if acct.is_active("wordpress") else None
    if wp_url and settings.get("affiliate", {}).get("cushion_via_wordpress", True):
        wp_pool = [a for a in affiliate_pool(acct, wp_url, settings) if a["usable"]]
        if affiliate_ids:
            wp_pool = [a for a in wp_pool if a["program_id"] in affiliate_ids]
        for p, c in per.items():
            if p == "wordpress" or not wp_pool:
                continue
            c["cushion"] = {"via_url": wp_url, "via_platform": "wordpress",
                            "programs": [{"program_id": a["program_id"], "program_name": a["program_name"]} for a in wp_pool]}
            if wp_url not in c["allowed_urls"]:
                c["allowed_urls"] = sorted(set(c["allowed_urls"] + [wp_url]))
    return {"own_destinations": own, "per_platform": per}


def generate(account_key: str, topic: str, platforms: list[str] | None = None, affiliate_ids: list[str] | None = None,
             notes: str = "", source_urls: list[str] | None = None, render_images: bool = True,
             use_muse: bool = True) -> dict:
    settings = C.load_settings()
    acct = get_account(account_key)
    seed = None
    if use_muse:
        from core import muse_ingestor

        muse_ingestor.ingest_inbox()            # inbox に置かれた新しいファイルを先に取り込む
        seed = muse_ingestor.next_seed(acct.key)
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
                          f"{json.dumps(affs, ensure_ascii=False) if affs else 'なし（自分のnote/WP/LINEへの誘導だけ）'}"
                          + (f"\nクッション導線: この媒体には広告リンクを貼らず、自分のWP（{c['cushion']['via_url']}）の記事へ誘導する。"
                             f"WP記事側で扱える案件: {json.dumps([x['program_name'] for x in c['cushion']['programs']][:15], ensure_ascii=False)}。"
                             "WPの記事テーマとつながる場合だけ、WPへの誘導文を入れる（案件名や成果条件をSNS側で断定しない）"
                             if c.get("cushion") else ""))
    user = (f"# アカウント実データ\n{_persona_block(acct)}\n\n"
            f"# 誘導先（自分の資産）\n{json.dumps(ctx['own_destinations'], ensure_ascii=False)}\n\n"
            f"{FUNNEL}\n\n"
            + (f"{SEED_RULES}\nseed: {json.dumps(seed, ensure_ascii=False)}\n\n" if seed else "")
            + f"# 今回のテーマ\n{topic or ('（Muse のシードから決める）' if seed else AUTO_TOPIC)}\n{('補足: ' + notes) if notes else ''}\n"
            f"{('参照してよい一次情報URL: ' + ', '.join(source_urls)) if source_urls else ''}\n\n"
            f"# 出力する媒体\n" + "\n\n".join(spec_lines) +
            "\n\n先に reader_problem（読者の迷い）・pain_hook（場面・試してダメだったこと・未解決の疑問・1行目）・"
            "angle（このアカウントならではの切り口）を決め、全媒体で一貫させる。")

    schema = {"type": "object", "additionalProperties": False,
              "required": ["reader_problem", "pain_hook", "angle", "outputs"],
              "properties": {"reader_problem": {"type": "string"}, "pain_hook": PAIN_HOOK_SCHEMA, "angle": {"type": "string"},
                             "outputs": {"type": "object", "additionalProperties": False, "required": targets,
                                         "properties": {p: PLATFORM_SCHEMAS[p] for p in targets}}}}
    from core import llm

    result = llm.generate_json(SYSTEM.replace("{pr}", pr), user, schema, settings)
    hook_issues = check_hook(result)
    if hook_issues:                             # 1行目ルールを外したら1回だけ作り直す
        fix = "\n\n# 前回の出力の不備（直して全体を出し直す）\n" + "\n".join(f"- {i['platform']}: {i['msg']}" for i in hook_issues)
        result = llm.generate_json(SYSTEM.replace("{pr}", pr), user + fix, schema, settings)
    result["_llm_backend"] = llm.last_backend
    result["_muse_seed"] = seed
    label = topic or (f"[Muse] {result.get('reader_problem', '')}" if seed else f"[自動] {result.get('reader_problem', '')}")
    d = finalize_draft(acct, label, targets, result, ctx, settings, render_images)
    if seed:
        from core import muse_ingestor

        muse_ingestor.mark_used(acct.key, seed["id"], d["id"])
    return d


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
    issues += check_hook(result)
    draft_id = drafts.new_id(acct.key)
    d = {
        "id": draft_id, "account_key": acct.key, "account_label": acct.label, "topic": topic,
        "created_at": C.now_iso(), "reader_problem": result.get("reader_problem"), "angle": result.get("angle"),
        "pain_hook": result.get("pain_hook"), "muse_seed": result.get("_muse_seed"),
        "outputs": result["outputs"], "context": ctx, "issues": issues, "llm_backend": result.get("_llm_backend"),
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
    if d.get("pain_hook"):
        issues += check_hook({"pain_hook": d["pain_hook"], "outputs": d["outputs"]})
    d["issues"] = issues
    return drafts.save(d)
