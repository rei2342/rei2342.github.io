#!/usr/bin/env python3
"""
fix_kanji_numerals.py
本文中の漢数字をアラビア数字に変換する（汎用アルゴリズム方式）。

旧版は固定の置換テーブルだったため、テーブルに無い漢数字は素通りしていた。
本版は任意の漢数字（百五十万・二百五十六万 等）を計算で変換するので
全記事を一度で処理できる。

安全設計:
  - 漢数字ラン単体は基本変換しない（一番・一緒・十分(=じゅうぶん) 等の誤爆防止）。
  - 変換するのは「直後に数量単位が来るラン」または「万/億 を含むラン」だけ。
  - 範囲表現（二十〜三十万 → 20〜30万）も2パスで処理。
  - 「十分」（じゅうぶん）は分の変換から除外。

DRY_RUN=true（デフォルト）では差分プレビューのみ保存、WPは更新しない。
POST_IDS にカンマ区切りID、または "ALL" で全公開記事を対象。
"""
import os, re, sys
from pathlib import Path
import requests, urllib3
urllib3.disable_warnings()

WP_BASE  = "https://sakura-eigo.com/wp-json/wp/v2"
WP_USER  = "rei.00pt2342@gmail.com"
WP_PASS  = os.environ.get("WP_APP_PASSWORD", "")
DRY_RUN  = os.environ.get("DRY_RUN", "true").lower() == "true"
_RAW_IDS = os.environ.get("POST_IDS", "117")
OUT_DIR  = Path("affiliate-research-engine/playbook/workspace/kanji_fixes")
UA       = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# ── 漢数字 → 整数 ──────────────────────────────────────────────
_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
           "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_SMALL  = {"十": 10, "百": 100, "千": 1000}
_BIG    = {"万": 10000, "億": 100000000, "兆": 1000000000000}
_NUMCHARS = "".join(list(_DIGITS) + list(_SMALL) + list(_BIG))

def kanji_to_int(s: str) -> int:
    total = 0      # 確定済み合計
    section = 0    # 現在の大単位(万/億)未満の値
    current = 0    # 直近の数字
    for ch in s:
        if ch in _DIGITS:
            current = _DIGITS[ch]
        elif ch in _SMALL:
            section += (current or 1) * _SMALL[ch]
            current = 0
        elif ch in _BIG:
            section += current
            total += section * _BIG[ch]
            section = 0
            current = 0
    return total + section + current

def render_int(v: int) -> str:
    """日本語慣習に合わせて万/億区切りで描画。"""
    if v >= 10**8:
        oku, rest = divmod(v, 10**8)
        return f"{oku:,}億" + (render_int(rest) if rest else "")
    if v >= 10000:
        man, rem = divmod(v, 10000)
        return f"{man:,}万" + (f"{rem:,}" if rem else "")
    return f"{v:,}"

# ── 数量単位の許可リスト（このどれかが直後に来たら数値確定）──────────
# 「番」「度」単体は語義変化（一番=最も / 一度=once）が大きいので除外。
# 「分」は時間/歩合の両方で使うが「十分(じゅうぶん)」だけ別途ガード。
_UNITS = [
    "ヶ月間", "ヶ月", "カ月", "か月", "週間", "年間", "日間", "時間",
    "歳", "円", "点", "人", "回", "日", "年", "月", "週", "分", "秒",
    "割", "桁", "段", "倍", "本", "冊", "件", "個", "つ", "番目",
    "ミリ", "メートル", "キロ", "km", "%", "％", "豪ドル", "ドル",
]
# 長い単位を先にマッチさせる
_UNITS.sort(key=len, reverse=True)
_UNIT_ALT = "|".join(re.escape(u) for u in _UNITS)

_RUN = f"[{_NUMCHARS}]+"

def _convert_run(run: str) -> str:
    return render_int(kanji_to_int(run))

def convert_text(text: str):
    """漢数字をアラビア数字へ。変換ログ(list[(before,after)])を返す。"""
    log = []

    def _has_digit(run):  # 一〜九 or 十百千 を含む（単独の万/億を弾く）
        return any(c in _DIGITS or c in _SMALL for c in run)

    # --- パス0: 小数（漢数字ラン ・ 数字ラン）→ 24.95 / 6.5 ---
    def repl_dec(m):
        left, right = m.group(1), m.group(2)
        if not all(c in _DIGITS for c in right):   # 小数部は純粋な数字のみ
            return m.group(0)
        out = f"{kanji_to_int(left):,}." + "".join(str(_DIGITS[c]) for c in right)
        log.append((m.group(0), out))
        return out

    text = re.sub(f"({_RUN})・({_RUN})", repl_dec, text)

    # --- パス1: ラン(+単位) を1パスで変換（再走査しないので万の二重処理が起きない）---
    # 「十分」直後が以下なら じゅうぶん(=十分) とみなして保護。それ以外は 10分 に変換。
    _JUUBUN_NEXT = re.compile(r"^(に|な|の|だ|です|でしょ|だっ|では|でない|でなく|すぎ|とは|でき|条件|時間)")

    def repl_main(m):
        run, unit = m.group(1), (m.group(2) or "")
        if unit:
            if run == "十" and unit == "分":      # 「十分」= じゅうぶん か 10分 か文脈判定
                tail = m.string[m.end():m.end()+4]
                if _JUUBUN_NEXT.match(tail):       # 十分に / 十分な / 十分すぎ → じゅうぶん保護
                    return m.group(0)
                # それ以外（十分から / 十分ずつ / 一日十分 等）は 10分
            if not _has_digit(run):                # 「万円」等の単独大単位は触らない
                return m.group(0)
            out = _convert_run(run) + unit
            log.append((m.group(0), out))
            return out
        # 単位なし: 万/億/兆 を含む数値だけ変換（百五十万 等）
        if any(c in "万億兆" for c in run) and _has_digit(run):
            out = _convert_run(run)
            log.append((run, out))
            return out
        return m.group(0)

    text = re.sub(f"({_RUN})({_UNIT_ALT})?", repl_main, text)

    # --- パス2: 範囲の左オペランド（漢数字ラン 〜/～/、/から → 既に変換済みの数字）---
    # 左ランは数字を含むこと＆直前がアラビア数字でないこと（変換済み「15万」の万を拾わない）
    def repl_range(m):
        run, sep = m.group(1), m.group(2)
        if not _has_digit(run):
            return m.group(0)
        out = _convert_run(run) + sep
        log.append((run + sep, out))
        return out

    text = re.sub(f"(?<![0-9])({_RUN})([〜～、\\-]|から)(?=[0-9])", repl_range, text)

    return text, log

# ── em ダッシュ（——）除去：AIっぽさを消す ─────────────────────────
# 1) 挿入句を囲う対 ——…—— は（…）へ。 2) 残りは読点へ。 3) 閉じ括弧/句点直前は削除。
_DASH = "—"  # —（EM DASH）
def clean_dashes(text: str):
    n = 0
    # 対で挿入句を囲うケース → （挿入句）。挿入句に文末/括弧/鉤括弧は含めない
    pat_pair = re.compile(f"{_DASH}{{2,}}([^{_DASH}。！？\\n\\r「」（）]+?){_DASH}{{2,}}")
    text, c = pat_pair.subn(lambda m: "（" + m.group(1) + "）", text); n += c
    # 閉じ記号の直前にある —— は不要 → 削除
    text, c = re.subn(f"{_DASH}{{1,}}(?=[」』。、，））])", "", text); n += c
    # 残りの長ダッシュ・単独ダッシュ → 読点
    text, c = re.subn(f"{_DASH}{{1,}}", "、", text); n += c
    return text, n

# ── WP I/O ────────────────────────────────────────────────────
def get_post(post_id):
    r = requests.get(f"{WP_BASE}/posts/{post_id}", auth=(WP_USER, WP_PASS),
                     headers=UA, verify=False, timeout=30)
    return r.json() if r.status_code == 200 else None

def update_post(post_id, content, title=None):
    payload = {"content": content}
    if title is not None:
        payload["title"] = title
    r = requests.post(f"{WP_BASE}/posts/{post_id}", auth=(WP_USER, WP_PASS),
                      json=payload, headers=UA, verify=False, timeout=30)
    return r.status_code in (200, 201)

def get_all_post_ids():
    # 公開・下書き・予約・レビュー待ち・非公開すべて（もれなく）
    ids, page = [], 1
    while True:
        r = requests.get(f"{WP_BASE}/posts", auth=(WP_USER, WP_PASS),
                         params={"per_page": 100, "page": page,
                                 "status": "publish,draft,pending,future,private",
                                 "_fields": "id"},
                         headers=UA, verify=False, timeout=30)
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

# ── main ──────────────────────────────────────────────────────
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if _RAW_IDS.strip().upper() == "ALL":
        post_ids = get_all_post_ids()
        print(f"ALL mode: {len(post_ids)} posts → {post_ids}")
    else:
        post_ids = [int(x) for x in _RAW_IDS.split(",") if x.strip()]

    report = [f"# Kanji Fix Report\nMode: {'DRY RUN' if DRY_RUN else 'LIVE'}\n"
              f"Targets: {len(post_ids)} posts\n\n"]

    for post_id in post_ids:
        print(f"\n[{post_id}] Fetching...")
        post = get_post(post_id)
        if not post:
            print("  ✗ Fetch failed")
            report.append(f"- [{post_id}] FETCH FAILED\n")
            continue

        title   = post["title"]["rendered"]
        content = post["content"]["rendered"]
        new_content, log = convert_text(content)
        new_content, dash_n = clean_dashes(new_content)   # 本文の —— 除去
        # タイトルも同様に処理（漢数字 + —— 除去）
        new_title, tlog = convert_text(title)
        new_title, tdash_n = clean_dashes(new_title)

        if not log and dash_n == 0 and not tlog and tdash_n == 0:
            print(f"  {new_title}\n  → 変更なし、スキップ")
            report.append(f"- [{post_id}] {new_title} — NO CHANGES\n")
            continue
        log += tlog  # タイトル分の漢数字置換もログへ

        # 重複ログを集約
        seen, uniq = set(), []
        for o, n in log:
            if (o, n) not in seen:
                seen.add((o, n)); uniq.append((o, n))

        dash_total = dash_n + tdash_n
        print(f"  {new_title}\n  → 漢数字{len(log)}箇所 / ——除去{dash_total}箇所:")
        for o, n in uniq[:40]:
            print(f"      {o} → {n}")

        (OUT_DIR / f"{post_id}_kanji_fixed.html").write_text(new_content, encoding="utf-8")

        if not DRY_RUN:
            status = "✓ UPDATED" if update_post(post_id, new_content, new_title) else "✗ WP FAILED"
        else:
            status = "DRY RUN — preview saved"

        report.append(
            f"- [{post_id}] {new_title} — 漢数字{len(log)} / ——除去{dash_total}\n"
            + "\n".join(f"  - `{o}` → `{n}`" for o, n in uniq)
            + f"\n  → **{status}**\n\n"
        )
        print(f"  {status}")

    (OUT_DIR / "REPORT.md").write_text("".join(report), encoding="utf-8")
    print("\n✓ Done.")

if __name__ == "__main__":
    main()
