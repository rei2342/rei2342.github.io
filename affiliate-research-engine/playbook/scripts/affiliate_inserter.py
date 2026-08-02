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
    "dmm": (
        "5640982",
        '<a href="//af.moshimo.com/af/c/click?a_id=5640982&p_id=6652&pc_id=18969&pl_id=84962"'
        ' rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>'
        '→ DMM英会話のオンライン無料体験レッスンを受けてみる</a>'
        '<img src="//i.moshimo.com/af/i/impression?a_id=5640982&p_id=6652&pc_id=18969&pl_id=84962"'
        ' width="1" height="1" style="border:none;" alt="" loading="lazy">'
    ),
    "nativecamp_ryugaku": (
        "a8_s00000014758002",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+27S3UA+35VG+BWVTE" rel="nofollow">→ ネイティブキャンプ留学で留学費用の無料見積もりを取る</a><img border="0" width="1" height="1" src="https://www15.a8.net/0.gif?a8mat=4B9W9D+27S3UA+35VG+BWVTE" alt="" loading="lazy">'
    ),
}

# ── Topic → max 2 programs, priority order ────────────────────────────────────
TOPIC_MAP = {
    "philippines":    ["phil_navi", "cebridge"],
    "workingholiday": ["nativecamp_ryugaku", "johokan"],
    "study_abroad":   ["nativecamp_ryugaku", "johokan"],
    "agent":          ["nativecamp_ryugaku", "johokan"],
    "coaching":       ["speek", "sptr"],
    "toeic":          ["speek", "sptr"],
    "pronunciation":  ["speek", "sptr"],
    "training":       ["sptr", "speek"],
    "eikaiwa":        ["dmm", "speek"],   # オンライン英会話系は DMM 主力
    "domestic":       ["ugaku"],
    "default":        ["speek", "dmm"],   # 汎用にも DMM を露出（sptrはtoeic/training等で担保）
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
    if any(k in t for k in ["スパトレ", "トレーニング", "第二言語習得", "独学", "続かない", "アプリ"]):
        return "training"
    if any(k in t for k in ["国内", "短期集中"]):
        return "domestic"
    return "default"

# 既存CTAボックス（先頭の<hr>含む）を丸ごと除去する正規表現
_BOX_RE = re.compile(
    r'(?:\s*<hr\s*/?>)?\s*'
    r'<div style="background:#f9f9f9;border-left:4px solid #27ae60;[^"]*">.*?</div>',
    re.DOTALL,
)

def strip_box(content):
    """既存の『さくらが確かめた・次の一手』ボックスを除去（あれば）。"""
    return _BOX_RE.sub('', content).rstrip()

def build_cta(topic):
    """そのトピックの全案件（最大2件）を1つの箱にまとめて返す。"""
    programs = TOPIC_MAP.get(topic, ["speek"])[:2]
    items = '\n'.join(f'<p>{LINKS[p][1]}</p>' for p in programs)
    block = (
        '\n<hr>\n'
        '<div style="background:#f9f9f9;border-left:4px solid #27ae60;padding:16px 20px;margin:32px 0">\n'
        '<p style="margin-top:0;font-weight:bold">▶ さくらが確かめた・次の一手（すべて無料）</p>\n'
        + items +
        '\n<p style="margin-bottom:0;font-size:0.8em;color:#999">※本記事にはアフィリエイトリンクが含まれます（PR）</p>\n'
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
        topic   = classify(title)

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
