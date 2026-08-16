#!/usr/bin/env python3
"""
affiliate_inserter.py
Appends relevant affiliate CTAs to existing WordPress articles.
No Claude rewrite — lightweight, classification-only.
"""
import os, re, time
from pathlib import Path
import requests, urllib3
urllib3.disable_warnings()

WP_BASE = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER = "rei.00pt2342@gmail.com"
WP_PASS = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
OUT_DIR = Path("affiliate-research-engine/playbook/workspace/affiliate_inserts")

_DEFAULT_IDS = [27, 67, 64, 61, 19, 18, 32, 42, 40, 41, 37, 33, 28, 23]
_env_ids = os.environ.get("POST_IDS", "")
if _env_ids.strip().upper() == "ALL":
    TARGET_IDS = []                      # main() が get_all_post_ids() を使う
elif _env_ids.strip():
    TARGET_IDS = [int(x) for x in _env_ids.split(",") if x.strip()]
else:
    TARGET_IDS = _DEFAULT_IDS

# ── Affiliate links ──────────────────────────────────────────────────
# ── Affiliate links ──────────────────────────────────────────────────
# **A8の実HTML（2026-08-16に本番57記事へ入っているもの）。**
# href と img src は必ず同じ a8mat を使う。片方だけ差し替えると成果が付かない。
# rel は A8 の発行コードに入っていないので、こちらで必ず付ける。
#
# アンカー文言に「無料」「保証」「回数」などの訴求語を書けるのは、
# **workspace/cta_claims.csv に verified な行がある案件だけ。**
# 台帳に無い案件は中立の文言にしてある（cta_claim_gate が落とすため）。
LINKS = {
    "nativecamp": (
        "ネイティブキャンプ",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+28DJG2+35VG+6LWTE" rel="sponsored nofollow noopener" target="_blank">→ ネイティブキャンプの7日間無料体験を試す</a><img border="0" width="1" height="1" src="https://www11.a8.net/0.gif?a8mat=4B9W9D+28DJG2+35VG+6LWTE" alt="" loading="lazy">',
    ),
    "nativecamp_unlimited": (
        "ネイティブキャンプ",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+28DJG2+35VG+64JTE" rel="sponsored nofollow noopener" target="_blank">→ ネイティブキャンプ（予約不要・レッスン回数無制限）の無料体験を試す</a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B9W9D+28DJG2+35VG+64JTE" alt="" loading="lazy">',
    ),
    "best_teacher": (
        "ベストティーチャー",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4BA75B+5L8J8Y+2ZIK+6HES2" rel="sponsored nofollow noopener" target="_blank">→ ベストティーチャー公式サイトで「書いてから話す」進め方を確認する</a><img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=4BA75B+5L8J8Y+2ZIK+6HES2" alt="" loading="lazy">',
    ),
    "sakura_mobile": (
        "SakuraMobile",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4BA75B+7118VM+3Z3Y+C0IZM" rel="sponsored nofollow noopener" target="_blank">→ SakuraMobile 海外WiFi公式サイトで料金と対応国を確認する</a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4BA75B+7118VM+3Z3Y+C0IZM" alt="" loading="lazy">',
    ),
    "rizap_english": (
        "RIZAP ENGLISH",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4BA75B+6OJ56A+CW6+BR2ER6" rel="sponsored nofollow noopener" target="_blank">→ RIZAP ENGLISH公式サイトでカウンセリングの内容を確認する</a><img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=4BA75B+6OJ56A+CW6+BR2ER6" alt="" loading="lazy">',
    ),
    "bizmates_coaching": (
        "Bizmates Coaching",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4BA75B+4TULF6+2QEI+NTJWY" rel="sponsored nofollow noopener" target="_blank">→ Bizmates Coaching公式サイトでビジネス特化の進め方を確認する</a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4BA75B+4TULF6+2QEI+NTJWY" alt="" loading="lazy">',
    ),
    "nativecamp_ryugaku": (
        "ネイティブキャンプ留学",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+27S3UA+35VG+BWVTE" rel="sponsored nofollow noopener" target="_blank">→ ネイティブキャンプ留学で留学費用の無料見積もりを取る</a><img border="0" width="1" height="1" src="https://www15.a8.net/0.gif?a8mat=4B9W9D+27S3UA+35VG+BWVTE" alt="" loading="lazy">',
    ),
    "nativecamp_ryugaku_price": (
        "ネイティブキャンプ留学",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+27S3UA+35VG+BX3J6" rel="sponsored nofollow noopener" target="_blank">→ ネイティブキャンプ留学公式サイトで費用の内訳を確認する</a><img border="0" width="1" height="1" src="https://www16.a8.net/0.gif?a8mat=4B9W9D+27S3UA+35VG+BX3J6" alt="" loading="lazy">',
    ),
    "qq_english": (
        "QQ English",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+2IHWQA+4HHM+669JM" rel="sponsored nofollow noopener" target="_blank">→ QQ English公式サイトでレッスンの内容と料金を確認する</a><img border="0" width="1" height="1" src="https://www18.a8.net/0.gif?a8mat=4B9W9D+2IHWQA+4HHM+669JM" alt="" loading="lazy">',
    ),
    "notta": (
        "Notta",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9YLD+EAFAQ+5988+5ZEMQ" rel="sponsored nofollow noopener" target="_blank">→ Notta公式サイトで文字起こしの機能と料金を確認する</a><img border="0" width="1" height="1" src="https://www19.a8.net/0.gif?a8mat=4B9YLD+EAFAQ+5988+5ZEMQ" alt="" loading="lazy">',
    ),
    "rarejob": (
        "レアジョブ英会話",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+1LR2GI+1SVU+686ZM" rel="sponsored nofollow noopener" target="_blank">→ レアジョブ英会話の7日間無料体験を試す</a><img border="0" width="1" height="1" src="https://www14.a8.net/0.gif?a8mat=4B9W9D+1LR2GI+1SVU+686ZM" alt="" loading="lazy">',
    ),
}

# ── Topic → max 2 programs, priority order ────────────────────────────────────
# ── トピック → 案件（2026-08-16に本番の設置実績へ合わせた）──────
# **報酬額で決めない。** 決め方は3段:
#   1. 記事の結論と地続きか      ← 第一条件
#   2. 無料の入口があるか
#   3. 同点なら報酬額と確定率
# RIZAP ENGLISH は高単価だが EPC も確定率も未取得なので、
# コーチング系の記事から広げない（ASP_RECORD_UNVERIFIED 扱い）。
TOPIC_MAP = {
    "coaching":       ["rizap_english", "bizmates_coaching"],
    "work_english":   ["bizmates_coaching", "notta"],
    "eikaiwa":        ["nativecamp_unlimited"],
    "training":       ["best_teacher", "nativecamp"],
    "pronunciation":  ["best_teacher", "nativecamp"],
    "toeic":          ["rarejob", "nativecamp"],
    "agent":          ["nativecamp_ryugaku_price"],
    "study_abroad":   ["nativecamp_ryugaku_price"],
    "philippines":    ["qq_english", "sakura_mobile"],
    "workingholiday": ["sakura_mobile", "nativecamp_ryugaku"],
    "domestic":       ["nativecamp_ryugaku_price"],
    "recording":      ["notta", "bizmates_coaching"],
    "default":        ["nativecamp", "best_teacher"],
}


def classify(title):
    t = title
    if any(k in t for k in ["フィリピン", "セブ", "CEBRIDGE"]):
        return "philippines"
    if any(k in t for k in ["ワーホリ", "ワーキングホリデー"]):
        return "workingholiday"
    if any(k in t for k in ["留学エージェント", "留学 費用", "留学 社会人"]):
        return "agent"
    if any(k in t for k in ["留学", "海外移住"]):
        return "study_abroad"
    if "コーチング" in t:
        return "coaching"
    if any(k in t for k in ["TOEIC", "toeic"]):
        return "toeic"
    if any(k in t for k in ["発音", "スピーキング", "speaking"]):
        return "pronunciation"
    if any(k in t for k in ["オンライン英会話", "英会話", "DMM", "ネイティブ", "毎日 英語"]):
        return "eikaiwa"
    # 職場で実際に手が止まる場面。学習意図ではないので Notta を出す。
    # 「ビジネス英語」「仕事 英語」は学習したい意図なので eikaiwa に残す
    # 録音・聞き直しの話は work_english より先に見る（会議と重なるため）
    if any(k in t for k in ["録音", "聞き直", "ボイスレコーダー", "レコーダー", "録って"]):
        return "recording"
    if any(k in t for k in ["会議", "議事録", "電話対応", "商談", "打ち合わせ",
                            "社内英語", "職場 英語", "営業事務"]):
        return "work_english"
    if any(k in t for k in ["ビジネス英語", "仕事 英語"]):
        return "eikaiwa"
    if any(k in t for k in ["スパトレ", "トレーニング", "第二言語習得", "独学", "続かない", "アプリ",
                            "モチベ", "ゼロから", "勉強法", "やり直し"]):
        return "training"
    if any(k in t for k in ["国内", "短期集中"]):
        return "domestic"
    return "default"


# 留学系はこのサイトの主力（ネイティブキャンプ留学・フィリピン留学ナビ等）。
# ここを取り違えると案件も構成も外れるので、本文の証拠で救済する。
_RYUGAKU = {"philippines", "workingholiday", "study_abroad", "agent", "domestic"}
_RYUGAKU_SIGNALS = ("フィリピン", "セブ", "ワーホリ", "ワーキングホリデー",
                    "留学エージェント", "語学学校", "海外移住")


def classify_full(title, body=""):
    """タイトルと本文の両方を見て分類する。

    classify() はタイトルのキーワードだけを見る。2026-08-02に
    タイトルを「短い一人称＋数字」型へ書き換えたことで判定語が
    タイトルから消え、以下の2種類の取り違えが起きた。

      1. 判定語がなく default に落ちる
         例「帰国後の床がないまま、5校を比べた2ヶ月を捨てた」→ 実際はフィリピン留学
      2. 別トピックの語を拾って誤判定する
         例「TOEIC600点より先に…」→ toeic と出るが実際はワーホリ記事

    本文は書き換えていないので判定語が残っている。本文を根拠に補正する。
    """
    topic = classify(title)
    if not body:
        return topic

    text = re.sub(r"<[^>]+>", " ", body)[:4000]

    if topic == "default":
        return classify(text)

    # 本文に留学系の語が繰り返し出るのに留学系でないなら、本文を採る。
    # 1回だけの言及で乗っ取られないよう3回以上を条件にする。
    if topic not in _RYUGAKU:
        hits = sum(text.count(k) for k in _RYUGAKU_SIGNALS)
        if hits >= 3:
            body_topic = classify(text)
            if body_topic in _RYUGAKU:
                return body_topic
    return topic

# 既存CTAボックス（先頭の<hr>含む）を丸ごと除去する正規表現
_BOX_RE = re.compile(
    r'(?:\s*<hr\s*/?>)?\s*'
    r'<div style="background:#f9f9f9;border-left:4px solid #27ae60;[^"]*">.*?</div>',
    re.DOTALL,
)

def strip_box(content):
    """既存のCTAボックスを除去（あれば）。"""
    return _BOX_RE.sub('', content).rstrip()

# ⚠️ 2026-08-09に見出しを差し替えた。
# 旧: 「▶ さくらが確かめた・次の一手（すべて無料）」
#   - 「さくらが確かめた」は**台帳に無い一人称の行動**。QQ English・speek と同じ型のミスで、
#     本文のゲートは通るのにCTAの箱だけ素通りしていた
#   - 「すべて無料」は箱に入る案件すべてへの訴求になる。cta_claims.csv で
#     案件ごとに確認しているのに、箱の見出しが一括で「無料」と言ってしまう
# 新しい見出しは行動も訴求も主張しない。**リンク先が公式であることだけ**を言う。
CTA_HEADING = "▶ 公式サイトで内容と料金を確認する"
# **PR表記は消さない。** 景品表示法のステマ規制。
# 消費者庁の指針では冒頭が望ましく、末尾のみは次善策になる。
# 文面の正本は config/content/sakura-content-v1.yaml の affiliate_link.pr_notice
CTA_NOTE = ("料金・キャンペーンは改定されるため、申し込む前に"
            "各公式サイトの最新表示を確認してください。")

def build_cta(topic):
    """そのトピックの全案件（最大2件）を1つの箱にまとめて返す。"""
    programs = TOPIC_MAP.get(topic, ["speek"])[:2]
    items = '\n'.join(f'<p>{LINKS[p][1]}</p>' for p in programs)
    block = (
        '\n<hr>\n'
        '<div style="background:#f9f9f9;border-left:4px solid #27ae60;padding:16px 20px;margin:32px 0">\n'
        f'<p style="margin-top:0;font-weight:bold">{CTA_HEADING}</p>\n'
        + items +
        f'\n<p style="margin-bottom:0;font-size:0.8em;color:#999">{CTA_NOTE}<br>'
        '※本記事にはアフィリエイトリンクが含まれます（PR）</p>\n'
        '</div>'
    )
    return block, programs

def get_post(post_id):
    r = requests.get(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False, timeout=30
    )
    return r.json() if r.status_code == 200 else None

def update_post(post_id, content):
    r = requests.post(
        f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"content": content},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False, timeout=30
    )
    return r.status_code in (200, 201)

def get_all_post_ids():
    ids, page = [], 1
    while True:
        r = requests.get(
            f"{WP_BASE}/posts", auth=(WP_USER, WP_PASS),
            params={"per_page": 100, "page": page,
                    "status": "publish,draft,pending,future,private", "_fields": "id"},
            headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=30)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        ids += [p["id"] for p in batch]
        if len(batch) < 100:
            break
        page += 1
    return ids

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = [f"# Affiliate Insert Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]

    if _env_ids.strip().upper() == "ALL":
        ids = get_all_post_ids()
        print(f"ALL mode: {len(ids)} posts")
    else:
        ids = TARGET_IDS

    for post_id in ids:
        print(f"\n[{post_id}] Fetching...")
        post = get_post(post_id)
        if not post:
            print("  ✗ Fetch failed")
            report.append(f"- [{post_id}] FETCH FAILED\n")
            continue

        title   = post["title"]["rendered"]
        content = post["content"]["rendered"]

        # 内部メモ（Threads投稿文の下書き等）は記事ではないのでCTAを入れない
        if any(mark in title for mark in ("【Threads用】", "【メモ】", "【社内")):
            print(f"  - スキップ（内部メモ）: {title}")
            report.append(f"- [{post_id}] {title} — SKIPPED (内部メモ)\n")
            continue

        topic = classify_full(title, content)

        # 既存ボックスを除去 → そのトピックの全案件で1つの箱を作り直す（冪等・統合）
        base = strip_box(content)
        cta_block, progs = build_cta(topic)
        new_content = base + cta_block

        print(f"  {title}\n  topic={topic}  programs={progs}")

        if new_content == content:
            print("  → 既に最新の統合ボックス、変更なし")
            report.append(f"- [{post_id}] {title} ({topic}) — NO CHANGE\n")
            continue

        (OUT_DIR / f"{post_id}_{topic}.html").write_text(
            f"<!-- {post_id} | {title} | {topic} -->\n{cta_block}")

        if not DRY_RUN:
            status = "✓ UPDATED" if update_post(post_id, new_content) else "✗ WP FAILED"
        else:
            status = "DRY RUN"

        report.append(f"- [{post_id}] {title} ({topic}) — box: {', '.join(progs)} — {status}\n")
        print(f"  {status}")
        time.sleep(5)

    (OUT_DIR / "REPORT.md").write_text("".join(report))
    print("\n✓ Done. Report saved.")

if __name__ == "__main__":
    main()
