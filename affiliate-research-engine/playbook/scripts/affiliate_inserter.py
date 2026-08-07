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
        '<a href="//af.moshimo.com/af/c/click?a_id=5640986&p_id=6385&pc_id=18040&pl_id=81992"'
        ' rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>'
        '→ フィリピン留学ナビの無料相談会に申し込む</a>'
        '<img src="//i.moshimo.com/af/i/impression?a_id=5640986&p_id=6385&pc_id=18040&pl_id=81992"'
        ' width="1" height="1" style="border:none;" alt="" loading="lazy">'
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
    "qq_english": (
        "a8_s00000020929001",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+2IHWQA+4HHM+669JM" rel="nofollow">→ QQ English（セブ島発・教師は全員正社員）の無料体験レッスンを予約する</a><img border="0" width="1" height="1" src="https://www18.a8.net/0.gif?a8mat=4B9W9D+2IHWQA+4HHM+669JM" alt="" loading="lazy">'
    ),
    "nativecamp": (
        "a8_s00000014758001",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+28DJG2+35VG+64JTE" rel="nofollow">→ ネイティブキャンプ（予約不要・レッスン回数無制限）の無料トライアルを試す</a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B9W9D+28DJG2+35VG+64JTE" alt="" loading="lazy">'
    ),
    "rarejob": (
        "a8_s00000008409001",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+1LR2GI+1SVU+686ZM" rel="nofollow">→ レアジョブ英会話（マンツーマン・早朝6時から深夜1時まで）の無料体験レッスンを受ける</a><img border="0" width="1" height="1" src="https://www19.a8.net/0.gif?a8mat=4B9W9D+1LR2GI+1SVU+686ZM" alt="" loading="lazy">'
    ),
    "sapuri_nichijo": (
        "a8_s00000015388006",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+2OG8S2+3AQG+ZS5GI" rel="nofollow">→ スタディサプリENGLISH 新日常英会話コースを無料体験する</a><img border="0" width="1" height="1" src="https://www12.a8.net/0.gif?a8mat=4B9W9D+2OG8S2+3AQG+ZS5GI" alt="" loading="lazy">'
    ),
    "sapuri_setplan": (
        "a8_s00000015388008",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9W9D+28YZ1U+3AQG+1BTJB6" rel="nofollow">→ スタディサプリENGLISH 新日常英会話セットプラン（アプリ＋英会話）を無料で体験する</a><img border="0" width="1" height="1" src="https://www12.a8.net/0.gif?a8mat=4B9W9D+28YZ1U+3AQG+1BTJB6" alt="" loading="lazy">'
    ),
    # Notta（A8）: EPC50以上・CTR5%以上。英語学習そのものではないが、
    # さくらは営業事務で英語の会議・電話に詰まる、という既存の軸がある。
    # 「聞き取れなかったところを後から文字起こしで確認する」用途でだけ出す。
    # 学習法・留学の記事に混ぜない（後付けの紹介になるため）。
    "notta": (
        "5ZEMQ",
        '<a href="https://px.a8.net/svt/ejp?a8mat=4B9YLD+EAFAQ+5988+5ZEMQ" rel="nofollow">'
        '→ 英語の会議を文字起こしして後から確認する（Notta・無料プランあり）</a>'
        '<img border="0" width="1" height="1" style="border:none" alt="" loading="lazy"'
        ' src="https://www19.a8.net/0.gif?a8mat=4B9YLD+EAFAQ+5988+5ZEMQ">'
    ),
}

# ── Topic → max 2 programs, priority order ────────────────────────────────────
TOPIC_MAP = {
    # NC留学はセブのスクールを取り扱う（公式リリースで確認済み）ため主力に
    "philippines":    ["nativecamp_ryugaku", "phil_navi"],
    "workingholiday": ["nativecamp_ryugaku", "johokan"],
    "study_abroad":   ["nativecamp_ryugaku", "johokan"],
    "agent":          ["nativecamp_ryugaku", "johokan"],
    "coaching":       ["speek", "sptr"],
    "toeic":          ["speek", "sptr"],
    "pronunciation":  ["speek", "sptr"],
    "training":       ["sptr", "sapuri_nichijo"],    # スパトレ(第二言語習得論)＋スタサプ(アプリ学習)
    "eikaiwa":        ["qq_english", "nativecamp"],  # QQ(確定率97.45%)＋NC(初成果ボーナス対象)
    "domestic":       ["ugaku"],
    # 職場で英語に詰まる場面。Nottaは学習サービスではないので、
    # 学習法・留学のトピックには入れない（後付けの紹介になる）
    "work_english":   ["notta", "qq_english"],
    "default":        ["speek", "dmm"],              # 汎用は高単価speek＋DMMを露出
    # 控え（LINKSには登録済み。実績を見て入れ替える）:
    #   rarejob        … 確定率39%と低いため主力から外す。本人OK/セルフバック可なので原体験づくり用
    #   sapuri_setplan … sapuri_nichijo と役割が重複するため控え
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
