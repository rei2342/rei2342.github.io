#!/usr/bin/env python3
"""
article_rewriter.py
Rewrites WordPress articles with unique structures per topic,
adds affiliate links, fixes 漢数字, and generates a change report.
"""
import os, sys, time, re, json
from pathlib import Path
import requests, anthropic
import urllib3
urllib3.disable_warnings()

WP_BASE  = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER  = "rei.00pt2342@gmail.com"
WP_PASS  = os.environ.get("WP_APP_PASSWORD", "")
CLAUDE   = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
DRY_RUN  = os.environ.get("DRY_RUN", "true").lower() == "true"
OUT_DIR  = Path("affiliate-research-engine/playbook/workspace/rewrites")

TARGET_IDS = [27, 67, 64, 61, 19, 18, 32, 42, 40, 41, 37, 33, 28, 23]

# ── Affiliate links ───────────────────────────────────────────────────────────
LINKS = {
    "speek": '<a href="//af.moshimo.com/af/c/click?a_id=5640991&p_id=4940&pc_id=13178&pl_id=65056" rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>→ スピークの無料トライアルを試す（完全無料・AI英会話）</a><img src="//i.moshimo.com/af/i/impression?a_id=5640991&p_id=4940&pc_id=13178&pl_id=65056" width="1" height="1" style="border:none;" loading="lazy">',
    "phil_navi": '<a href="//af.moshimo.com/af/c/click?a_id=5640986&p_id=6385&pc_id=18040&pl_id=81992" rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>フィリピン留学ナビで無料相談を予約する（完全無料）</a><img src="//i.moshimo.com/af/i/impression?a_id=5640986&p_id=6385&pc_id=18040&pl_id=81992" width="1" height="1" style="border:none;" loading="lazy">',
    "ugaku":    '<a href="//af.moshimo.com/af/c/click?a_id=5640988&p_id=4449&pc_id=11553&pl_id=59973&url=https%3A%2F%2Fu-gaku.jp%2F%3Futm_source%3Dmoshimo%26utm_medium%3Daffiliate%26utm_campaign%3Dimg01" rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>→ U-GAKUで無料オンライン個別相談を予約する（完全無料）</a><img src="//i.moshimo.com/af/i/impression?a_id=5640988&p_id=4449&pc_id=11553&pl_id=59973" width="1" height="1" style="border:none;" loading="lazy">',
    "johokan":  '<a href="//af.moshimo.com/af/c/click?a_id=5640990&p_id=4347&pc_id=11168&pl_id=58884&url=https%3A%2F%2Fwww.ryugaku-johokan.com%2Findex_mr.php%3Futm_source%3Dmoshimo%26utm_medium%3Daffiliate%26utm_campaign%3Dcounseling" rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>→ 留学情報館で無料カウンセリングを申し込む（完全無料）</a><img src="//i.moshimo.com/af/i/impression?a_id=5640990&p_id=4347&pc_id=11168&pl_id=58884" width="1" height="1" style="border:none;" loading="lazy">',
    "cebridge":  '<a href="//af.moshimo.com/af/c/click?a_id=5640987&p_id=4201&pc_id=10658&pl_id=57293&url=https%3A%2F%2Fcebridge.jp%2F" rel="nofollow" referrerpolicy="no-referrer-when-downgrade" attributionsrc>→ CEBRIDGEでフィリピン留学の無料カウンセリングを予約する</a><img src="//i.moshimo.com/af/i/impression?a_id=5640987&p_id=4201&pc_id=10658&pl_id=57293" width="1" height="1" style="border:none;" loading="lazy">',
    "liberty":  "<!-- LIBERTY_LINK_HERE -->",
    "yumekana": "<!-- YUMEKANA_LINK_HERE -->",
}

LINK_NAMES = {
    "speek":    "スピーク（AI英会話）",
    "phil_navi":"フィリピン留学ナビ",
    "ugaku":    "U-GAKU（留学無料相談）",
    "johokan":  "留学情報館（無料カウンセリング）",
    "cebridge":  "CEBRIDGE（フィリピン留学）",
    "liberty":  "LIBERTYコーチング",
    "yumekana": "夢カナ留学",
}

# ── Topic → programs ──────────────────────────────────────────────────────────
TOPIC_PROGRAMS = {
    "toeic":        ["speek", "liberty"],
    "coaching":     ["speek", "liberty"],
    "hours_2000":   ["speek", "liberty"],
    "work_english": ["speek", "liberty"],
    "habit":        ["speek", "liberty"],
    "philippines":  ["phil_navi", "cebridge", "ugaku"],
    "agent_general":["ugaku", "johokan", "yumekana"],
    "agent_free":   ["ugaku", "johokan", "yumekana"],
    "cost":         ["ugaku", "johokan", "yumekana"],
    "default":      ["speek"],
}

# ── Structure types ───────────────────────────────────────────────────────────
STRUCTURES = {
    "toeic": """**スコア実験記録型**
「27歳・TOEIC3回分のスコア変化を記録して見えたこと」一次記録形式。
月別スコア・具体的な失敗シーン・気づきを軸に展開。上位記事批判は最小限に。""",

    "coaching": """**診断分岐型**
「英語コーチングが向いている人・向いていない人」診断的入口で始める。
「向いていない人」を先に出す逆説で引きつけ、向いている人の条件を絞り込む。""",

    "hours_2000": """**時間配分解剖型**
「2000時間の使い方で到達点が3倍変わる話」数字軸で展開。
時間の量より質（何に使うか）を可視化する形式。""",

    "work_english": """**職務文設計型**
「営業事務が実際に詰まる10場面と、そこで使う英文の作り方」シナリオ分岐形式。
抽象的英語力論より具体的な職務文の反復設計を軸に。""",

    "habit": """**摩擦設計型**
「続かない理由を摩擦コストの収支表で解剖する」形式。
心理論ではなく設計問題として扱い、摩擦の種類別に削り方を提示する。""",

    "philippines": """**比較検証型**
「フィリピン留学を真剣に検討した2ヶ月で比較した5校の記録」形式。
費用・授業・英語効果を具体的な数字で比較して展開する。""",

    "agent_general": """**決断強制型**
「この3タイプの人はエージェント比較を続けるべきではない」逆説的入口で始める。
比較行為のコスト（時間・年齢消費）をワーホリ年齢制限と掛け合わせて可視化する。""",

    "agent_free": """**インセンティブ解剖型**
「エージェントのKPIを分解すると見えること」財務的切り口で始める。
報酬発生点・スコープ外・成果側の空白を数字で可視化する形式で展開。""",

    "cost": """**機会費用試算型**
「行かなかった5年の費用を計算すると怖い話」逆算的入口で始める。
機会費用（失う給与）を具体的な数字で可視化し、先送りのコストを表に出す。""",

    "default": """**問題解体型**
よくある解決策を一つずつ「なぜ効かないか」で解体し、
本当に機能する一手を最後に提示する形式で書く。""",
}

# ── 漢数字 fix ─────────────────────────────────────────────────────────────────
KANJI_MAP = [
    (r'三十歳', '30歳'), (r'二十七歳', '27歳'), (r'二十五歳', '25歳'),
    (r'二十歳', '20歳'), (r'二十代', '20代'), (r'三十代', '30代'),
    (r'三十万', '30万'), (r'二十五万', '25万'), (r'二十万', '20万'),
    (r'百二十万', '120万'), (r'百八十万', '180万'), (r'三百万', '300万'),
    (r'百万', '100万'), (r'四万五千円', '4万5千円'),
    (r'三ヶ月', '3ヶ月'), (r'六ヶ月', '6ヶ月'), (r'三か月', '3か月'),
    (r'六か月', '6か月'), (r'一ヶ月', '1ヶ月'), (r'二ヶ月', '2ヶ月'),
    (r'五年間', '5年間'), (r'三年間', '3年間'), (r'二年間', '2年間'),
    (r'一年間', '1年間'), (r'五年', '5年'), (r'三年', '3年'),
    (r'二年', '2年'), (r'一年', '1年'), (r'半年間', '6ヶ月間'),
    (r'二千時間', '2000時間'), (r'一千時間', '1000時間'),
    (r'二百時間', '200時間'), (r'三百時間', '300時間'),
]

def fix_kanji(text):
    for pat, rep in KANJI_MAP:
        text = re.sub(pat, rep, text)
    return text

def strip_html(html):
    return re.sub(r'<[^>]+>', '', html)

def classify(title, content_snippet):
    # Use title only to avoid content keywords polluting classification
    t = title.lower()
    if "toeic" in t: return "toeic"
    if "フィリピン" in t: return "philippines"
    if "2000" in t: return "hours_2000"
    if "エージェント" in t and "無料" in t: return "agent_free"
    if "エージェント" in t: return "agent_general"
    if "コーチング" in t: return "coaching"
    if "仕事" in t and "英語" in t: return "work_english"
    if "続かない" in t: return "habit"
    if "費用" in t or "現実" in t: return "cost"
    if "独学" in t: return "default"
    if "上達" in t or "伸びない" in t: return "habit"
    if "ワーホリ" in t or "貯金" in t: return "cost"
    if "ビジネス英語" in t: return "work_english"
    return "default"

def existing_links(content):
    found = set()
    if "5640991" in content: found.add("speek")
    if "5640986" in content: found.add("phil_navi")
    return found

def build_link_block(programs, already_present):
    lines = []
    for prog in programs[:3]:
        name = LINK_NAMES[prog]
        html = LINKS[prog]
        if prog in already_present:
            lines.append(f"- {name}: すでに挿入済み。テキストのみ言及（リンク重複不要）")
        else:
            lines.append(f"- {name}: 本文で言及した直後にこのHTMLをそのまま挿入:\n  {html}")
    return "\n".join(lines)

def rewrite(title, content_html, topic):
    structure  = STRUCTURES.get(topic, STRUCTURES["default"])
    programs   = TOPIC_PROGRAMS.get(topic, ["speek"])
    already    = existing_links(content_html)
    link_block = build_link_block(programs, already)
    snippet    = strip_html(content_html)[:2000]

    prompt = f"""以下の記事を完全にリライトしてください。

タイトル（変更禁止）: {title}
構成タイプ: {structure}

現在の記事の要旨（参考のみ・構成をそのままコピーしないこと）:
{snippet}

## 要件
1. 4000字以上のHTML（<h2>/<h3>/<p>/<hr>タグのみ）
2. H2×6、H3×各2〜3（**現在の記事と異なるH2テーマ**を使う）
3. さくらのエピソードは現在の記事と**別のシーン・別の失敗**を使う
4. 数字はすべてアラビア数字（27歳・3ヶ月・25万円）
5. アフィリエイトリンク:
{link_block}

HTMLのみ出力。前置き・説明・```マーカー不要。"""

    msg = CLAUDE.messages.create(
        model="claude-opus-4-8",
        max_tokens=8000,
        system="アフィリエイトブログ「sakura-eigo.com」ライター。ペルソナ: 田中さくら/27歳/営業事務/東京/英語5年後回し/スクール失敗4.5万/30歳タイムリミット。NG: 「〜について」禁止/箇条書き逃げ禁止/同語尾3連続禁止/冒頭挨拶禁止/漢数字禁止/誇大虚偽禁止。",
        messages=[{"role": "user", "content": prompt}]
    )
    result = msg.content[0].text.strip()
    result = re.sub(r'^```html?\n?', '', result)
    result = re.sub(r'\n?```$', '', result)
    return fix_kanji(result)

def get_post(post_id):
    r = requests.get(f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        headers={"User-Agent": "Mozilla/5.0"}, verify=False)
    return r.json() if r.status_code == 200 else None

def update_post(post_id, content):
    r = requests.post(f"{WP_BASE}/posts/{post_id}",
        auth=(WP_USER, WP_PASS),
        json={"content": content},
        headers={"User-Agent": "Mozilla/5.0"}, verify=False)
    return r.status_code in (200, 201)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = [f"# Article Rewrite Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n\n"]

    for post_id in TARGET_IDS:
        print(f"\n[{post_id}] Fetching...")
        post = get_post(post_id)
        if not post:
            print(f"  ✗ Fetch failed"); report.append(f"- [{post_id}] FETCH FAILED\n"); continue

        title   = post["title"]["rendered"]
        content = post["content"]["rendered"]
        topic   = classify(title, strip_html(content))

        print(f"  {title}  →  topic={topic}")
        try:
            new_content = rewrite(title, content, topic)
        except Exception as e:
            print(f"  ✗ Rewrite error: {e}"); report.append(f"- [{post_id}] {title} — ERROR: {e}\n"); continue

        out = OUT_DIR / f"{post_id}_{topic}.html"
        out.write_text(f"<!-- {post_id} | {title} | {topic} -->\n" + new_content)
        print(f"  ✓ Saved {out.name}")

        if not DRY_RUN:
            ok = update_post(post_id, new_content)
            status = "✓ UPDATED" if ok else "✗ WP FAILED"
        else:
            status = "DRY RUN"

        report.append(f"- [{post_id}] {title} ({topic}) — {status}\n")
        print(f"  {status}")
        time.sleep(8)

    # Note impact (Track A = 転職, Track B = 英語/留学 → no overlap expected)
    report.append("\n## noteへの影響\nsakura-eigo.com は Track B（英語/留学）専用。Track A（転職/キャリア）のnote資産との内容重複なし。影響なし。\n")
    # アイキャッチ: titles are not changed, so no アイキャッチ update needed
    report.append("\n## アイキャッチ更新\nタイトル（WP title フィールド）は変更しないため、アイキャッチ更新は不要。\n")

    (OUT_DIR / "REPORT.md").write_text("".join(report))
    print("\n✓ Done. Report saved.")

if __name__ == "__main__":
    main()
