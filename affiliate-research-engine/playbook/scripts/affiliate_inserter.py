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
TARGET_IDS = [int(x) for x in _env_ids.split(",") if x.strip()] if _env_ids else _DEFAULT_IDS

# ── Affiliate links ──────────────────────────────────────────────────
LINKS = {
    "speek": (
        "speek",
        '<a href="//af.moshimo.com/af/c/click?a_id=5640991&p_id=4940&pc_id=13178&pl_id=65056&url=https%3A%2F%2Fwww.speek.jp%2F"'
        ' rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>'
        '→ speek（英語発音矯正）の無料トライアルを見る</a>'
        '<img src="//i.moshimo.com/af/i/impression?a_id=5640991&p_id=4940&pc_id=13178&pl_id=65056"'
        ' width="1" height="1" style="border:none;" alt="" loading="lazy">'
    ),
    "phil_navi": (
        "5640986",
        '<a href="//af.moshimo.com/af/c/click?a_id=5640986&p_id=6385&pc_id=18040&pl_id=83663"'
        ' rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>'
        '<img src="//image.moshimo.com/af-img/6196/000000083663.png" width="300" height="250" style="border:none;" alt="フィリピン留学ナビ"></a>'
        '<img src="//i.moshimo.com/af/i/impression?a_id=5640986&p_id=6385&pc_id=18040&pl_id=83663"'
        ' width="1" height="1" style="border:none;" loading="lazy">'
    ),
    "ugaku": (
        "5640988",
        '<a href="//af.moshimo.com/af/c/click?a_id=5640988&p_id=4449&pc_id=11553&pl_id=59973&url=https%3A%2F%2Fu-gaku.jp%2F%3Futm_source%3Dmoshimo%26utm_medium%3Daffiliate%26utm_campaign%3Dimg01"'
        ' rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>'
        '→ 国内英語留学U-GAKUで無料オンライン個別相談を予約する</a>'
        '<img src="//i.moshimo.com/af/i/impression?a_id=5640988&p_id=4449&pc_id=11553&pl_id=59973"'
        ' width="1" height="1" style="border:none;" alt="" loading="lazy">'
    ),
    "johokan": (
        "5640990",
        '<a href="//af.moshimo.com/af/c/click?a_id=5640990&p_id=4347&pc_id=11168&pl_id=58884&url=https%3A%2F%2Fwww.ryugaku-johokan.com%2Findex_mr.php%3Futm_source%3Dmoshimo%26utm_medium%3Daffiliate%26utm_campaign%3Dcounseling"'
        ' rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>'
        '→ 留学情報館で無料カウンセリングを申し込む</a>'
        '<img src="//i.moshimo.com/af/i/impression?a_id=5640990&p_id=4347&pc_id=11168&pl_id=58884"'
        ' width="1" height="1" style="border:none;" alt="" loading="lazy">'
    ),
    "cebridge": (
        "5640987",
        '<a href="//af.moshimo.com/af/c/click?a_id=5640987&p_id=4201&pc_id=10658&pl_id=57293&url=https%3A%2F%2Fcebridge.jp%2F"'
        ' rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>'
        '→ CEBRIDGEでフィリピン留学の無料カウンセリングを予約する</a>'
        '<img src="//i.moshimo.com/af/i/impression?a_id=5640987&p_id=4201&pc_id=10658&pl_id=57293"'
        ' width="1" height="1" style="border:none;" alt="" loading="lazy">'
    ),
    "sptr": (
        "5640981",
        '<a href="//af.moshimo.com/af/c/click?a_id=5640981&p_id=2409&pc_id=5246&pl_id=31559&url=https%3A%2F%2Fsptr.jp"'
        ' rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>'
        '→ スパトレ（第二言語習得論ベースの英語トレーニング）の7日間無料体験を見る</a>'
        '<img src="//i.moshimo.com/af/i/impression?a_id=5640981&p_id=2409&pc_id=5246&pl_id=31559"'
        ' width="1" height="1" style="border:none;" alt="" loading="lazy">'
    ),
}

# ── Topic → max 2 programs, priority order ────────────────────────────────────
TOPIC_MAP = {
    "philippines":    ["phil_navi", "cebridge"],
    "workingholiday": ["johokan", "ugaku"],
    "study_abroad":   ["johokan", "ugaku"],
    "agent":          ["johokan", "ugaku"],
    "coaching":       ["speek", "sptr"],
    "toeic":          ["speek", "sptr"],
    "pronunciation":  ["speek", "sptr"],
    "training":       ["sptr", "speek"],
    "domestic":       ["ugaku"],
    "default":        ["speek", "sptr"],
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
    if any(k in t for k in ["スパトレ", "トレーニング", "第二言語習得", "独学", "続かない", "アプリ"]):
        return "training"
    if any(k in t for k in ["国内", "短期集中"]):
        return "domestic"
    return "default"

def detect_existing(content):
    present = set()
    for key, (aid, _) in LINKS.items():
        if aid in content:
            present.add(key)
    return present

def build_cta(topic, existing):
    programs = TOPIC_MAP.get(topic, ["speek"])
    new_progs = [p for p in programs if p not in existing]
    if not new_progs:
        return None, []

    items = []
    for p in new_progs[:2]:
        items.append(f'<p>{LINKS[p][1]}</p>')

    block = (
        '\n<hr>\n'
        '<div style="background:#f9f9f9;border-left:4px solid #27ae60;padding:16px 20px;margin:32px 0">\n'
        '<p style="margin-top:0;font-weight:bold">▶ さくらが確かめた・次の一手（すべて無料）</p>\n'
        + '\n'.join(items) +
        '\n<p style="margin-bottom:0;font-size:0.8em;color:#999">※本記事にはアフィリエイトリンクが含まれます（PR）</p>\n'
        '</div>'
    )
    return block, new_progs

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

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = [f"# Affiliate Insert Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]

    for post_id in TARGET_IDS:
        print(f"\n[{post_id}] Fetching...")
        post = get_post(post_id)
        if not post:
            print("  ✗ Fetch failed")
            report.append(f"- [{post_id}] FETCH FAILED\n")
            continue

        title   = post["title"]["rendered"]
        content = post["content"]["rendered"]
        topic   = classify(title)
        existing = detect_existing(content)

        print(f"  {title}")
        print(f"  topic={topic}  existing={existing or 'none'}")

        cta_block, inserted = build_cta(topic, existing)
        if cta_block is None:
            print("  → all relevant links already present, skip")
            report.append(f"- [{post_id}] {title} ({topic}) — SKIPPED (links present)\n")
            continue

        new_content = content + cta_block

        # Save preview
        out = OUT_DIR / f"{post_id}_{topic}.html"
        out.write_text(f"<!-- {post_id} | {title} | {topic} -->\n{cta_block}")
        print(f"  ✓ CTA saved: {', '.join(inserted)}")

        if not DRY_RUN:
            ok = update_post(post_id, new_content)
            status = "✓ UPDATED" if ok else "✗ WP FAILED"
        else:
            status = "DRY RUN"

        report.append(f"- [{post_id}] {title} ({topic}) — inserted: {', '.join(inserted)} — {status}\n")
        print(f"  {status}")
        time.sleep(5)

    (OUT_DIR / "REPORT.md").write_text("".join(report))
    print("\n✓ Done. Report saved.")

if __name__ == "__main__":
    main()
