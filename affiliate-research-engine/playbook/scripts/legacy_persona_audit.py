#!/usr/bin/env python3
"""
legacy_persona_audit.py
旧ペルソナ設定（27歳・30歳まで・あと3年・5年後回し・営業事務）が
公開記事のどこに残っているかを、**1箇所ずつ**出す。

**一括置換はしない。** 同じ「30歳」でも意味が3つあるため。

  1. 個人の設定   … 「27歳の私が」。台帳に無いので消す
  2. 読者の条件   … 「20代後半から英語をやり直すのは遅いか」。残してよい
  3. 制度の条件   … 「ワーホリの年齢上限は30歳」。事実なので残せるが、
                     **国名・申請時期・一次情報URL・確認日**が揃っていることが条件

機械は分類の候補を出すだけで、決めるのは人。
判定できないものは「判定保留」に置いて、勝手に触らない。

  python legacy_persona_audit.py
出力: workspace/claims/LEGACY_PERSONA.md / .csv
"""
import csv
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as _q
import wp_audit as _wa

OUT = Path("affiliate-research-engine/playbook/workspace/claims")
JST = timezone(timedelta(hours=9))
SITE = "https://sakura-eigo.com"

# 探す旧設定。ラベルは扱いの違いで分けてある
PATTERNS = [
    ("年齢の明示", re.compile(r"2[0-9]\s*歳|三十歳|二十七歳")),
    ("期限の宣言", re.compile(r"30歳まで|30歳になる前|あと\s*[0-9]+\s*年|残り\s*[0-9]+\s*年")),
    ("未確認の経歴", re.compile(r"5年後回し|英語を[0-9]+年(?:後回し|放置|離れ)|営業事務")),
    ("旧サイト名", re.compile(r"さくらの英語挑戦記")),
    # 2026-08-09に追加。CTAボックスの旧見出しが公開記事に残っている
    ("旧CTA見出し", re.compile(r"さくらが確かめた|すべて無料")),
]

# ── 分類のための手掛かり ────────────────────────────────
# 一人称。これが近くにあると「さくら個人の設定」
FIRST_PERSON = re.compile(r"私|自分|さくら|僕")

# 読者に向けた言い方。これがあると「読者の条件」
READER = re.compile(
    r"あなた|読者|(?:人|方|場合)は|でしょうか|ですか[。？]|"
    r"だろうか|遅い(?:の)?(?:か|でしょうか)|〜?なら|という人|"
    r"を考えている(?:人|方)|に当てはまる")

# 制度の話。**話題がワーホリなだけでは足りない。**
# 「27歳の私が、いつかワーホリで海外に行きたい」は個人の設定であって制度ではない。
# 年齢が**要件として**書かれていることを条件にする。
SYSTEM_REQ = re.compile(
    r"年齢(?:上限|制限|条件|要件)|対象年齢|申請(?:時|資格|条件|要件)|"
    r"[0-9]{2}\s*歳\s*(?:以下|未満|以上)|"
    r"(?:ビザ|査証|制度|協定)[^。]{0,20}(?:条件|要件|対象|上限)|"
    r"応募(?:資格|条件)|参加(?:資格|条件)")

# 本人のカウントダウン。制度の要件が無ければ個人の設定として扱う
DEADLINE_DECL = re.compile(r"(?:あと|残り)\s*[0-9]+\s*年|30歳まで(?:に)?|30歳になる前")

# 制度として残すために揃っている必要があるもの
COUNTRY = re.compile(
    r"オーストラリア|豪州|カナダ|ニュージーランド|イギリス|英国|アイルランド|"
    r"シンガポール|韓国|台湾|ドイツ|フランス|ポーランド|ハンガリー|"
    r"フィリピン|マルタ|オランダ|デンマーク|チェコ|スペイン|ポルトガル")
APPLY_TIME = re.compile(
    r"申請(?:時|時点|日|の時点)|出発(?:時|前)|渡航(?:時|前)|"
    r"到着(?:時|日)|受付(?:期間|開始)|募集(?:期間|開始)|"
    r"[0-9]{4}年[0-9]{1,2}月")
PRIMARY_SRC = re.compile(
    r"https?://[^\s<）)」]*(?:go\.jp|gov|embassy|大使館|外務省|immi|"
    r"immigration|mofa)|外務省|大使館|移民局|総領事館")
CHECKED_ON = re.compile(r"20[0-9]{2}\s*年\s*[0-9]{1,2}\s*月\s*[0-9]{1,2}\s*日時点|"
                        r"20[0-9]{2}-[0-9]{2}-[0-9]{2}\s*時点|確認日")


def sentences(text):
    parts = re.split(r"(?<=[。！？\n])", text)
    return [p.strip() for p in parts if p.strip()]


def classify(sent, context):
    """1箇所の扱いを決める。**迷ったら「判定保留」にして触らない。**"""
    first = bool(FIRST_PERSON.search(sent))
    reader = bool(READER.search(sent))
    # **その文自身が要件を書いているか**と、**近くに制度の話があるか**を分ける。
    # 「私は27歳。」の前後にワーホリの年齢制限が書いてあっても、
    # その文は制度の説明ではなく本人の設定（2026-08-09に直した）。
    system_sent = bool(SYSTEM_REQ.search(sent))
    system_ctx = bool(SYSTEM_REQ.search(context))

    if first and not system_sent:
        return ("個人の設定", "削除する",
                "台帳に無いさくら固有の事実。読者の条件に置き換える")
    # 「あと3年しかない」は主語が省略されていても本人のカウントダウン
    if not system_sent and DEADLINE_DECL.search(sent) and not reader:
        return ("個人の設定", "削除する",
                "本人の期限の宣言。読者自身の問題に置き換える")
    if system_sent:
        need = []
        hay = sent + context
        if not COUNTRY.search(hay):
            need.append("国名")
        if not APPLY_TIME.search(hay):
            need.append("申請時期")
        if not PRIMARY_SRC.search(hay):
            need.append("一次情報URL")
        if not CHECKED_ON.search(hay):
            need.append("確認日")
        if need:
            return ("制度の条件（不足あり）", "補うか削除する",
                    f"制度として残すなら {'・'.join(need)} が要る")
        return ("制度の条件", "残してよい",
                "国名・申請時期・一次情報・確認日が揃っている")
    if reader:
        return ("読者の条件", "残してよい", "読者自身の悩みとして書かれている")
    if system_ctx:
        return ("判定保留", "人が読む",
                "近くに制度の話があるが、この文自体は要件を書いていない")
    return ("判定保留", "人が読む", "一人称でも読者向けでも制度でもない。文脈を見る")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    posts = _wa.published()
    print(f"公開記事 {len(posts)}本")

    rows = []
    for p in posts:
        pid = p["id"]
        title = re.sub(r"<[^>]+>", "", p["title"]["rendered"])
        body = _q.strip_tags(p.get("content", {}).get("rendered", ""))
        sents = sentences(body)
        for i, s in enumerate(sents):
            for label, rx in PATTERNS:
                m = rx.search(s)
                if not m:
                    continue
                ctx = " ".join(sents[max(0, i - 2):i + 3])
                kind, action, why = classify(s, ctx)
                if label in ("旧サイト名", "旧CTA見出し"):
                    kind, action = label, "削除する"
                    why = ("旧サイト名。新しいサイト名に直す"
                           if label == "旧サイト名"
                           else "CTAボックスの旧見出し。生成側は直済み")
                if label == "未確認の経歴":
                    kind, action = "個人の設定", "削除する"
                    why = "台帳に無い経歴。職種・年数は書けない"
                rows.append({
                    "post_id": pid, "title": title[:40],
                    "url": p.get("link", ""),
                    "pattern": label, "matched": m.group(0),
                    "kind": kind, "action": action, "why": why,
                    "sentence": s[:180],
                })

    by_post = {}
    for r in rows:
        by_post.setdefault(r["post_id"], []).append(r)

    KINDS = ["個人の設定", "制度の条件（不足あり）", "判定保留",
             "制度の条件", "読者の条件", "旧サイト名", "旧CTA見出し"]
    counts = {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS}

    L = [f"# 旧ペルソナ設定の残存 {stamp}\n\n",
         f"公開記事 **{len(posts)}本** / 残存 **{len(rows)}箇所** "
         f"（**{len(by_post)}本**に分布）\n\n",
         "**一括置換はしない。** 同じ「30歳」でも意味が3つあるため。\n\n",
         "| 扱い | 件数 | 何をするか |\n|---|---|---|\n"]
    HOW = {
        "個人の設定": "**削除する。** 台帳に無いさくら固有の事実",
        "制度の条件（不足あり）": "**国名・申請時期・一次情報URL・確認日を補うか、削除する**",
        "判定保留": "**人が読んで決める。** 機械では判断できない",
        "制度の条件": "残してよい。出典が揃っている",
        "読者の条件": "残してよい。読者自身の悩みとして書かれている",
        "旧サイト名": "**新しいサイト名に直す**",
        "旧CTA見出し": "**差し替える。** 生成側は修正済み",
    }
    for k in KINDS:
        L.append(f"| {k} | {counts[k]} | {HOW[k]} |\n")

    need_work = [k for k in KINDS if k in
                 ("個人の設定", "制度の条件（不足あり）", "判定保留",
                  "旧サイト名", "旧CTA見出し")]
    todo_posts = sorted({r["post_id"] for r in rows if r["kind"] in need_work})
    L.append(f"\n**手を入れる必要がある記事: {len(todo_posts)}本** "
             f"（{' '.join(str(x) for x in todo_posts)}）\n\n")

    L.append("\n---\n\n## 記事ごとの内訳\n\n")
    order = sorted(by_post.items(),
                   key=lambda kv: -sum(1 for r in kv[1] if r["kind"] in need_work))
    for pid, rs in order:
        todo = [r for r in rs if r["kind"] in need_work]
        mark = "🔴" if todo else "✅"
        L.append(f"\n### {mark} 記事{pid} … {rs[0]['title']}\n\n")
        L.append(f"{rs[0]['url']}\n\n")
        L.append(f"要対応 **{len(todo)}件** / 全 {len(rs)}件\n\n")
        L.append("| 種類 | 該当 | 扱い | 理由 | 元の文 |\n|---|---|---|---|---|\n")
        for r in rs:
            sent = r["sentence"].replace("|", "｜")
            L.append(f"| {r['pattern']} | `{r['matched']}` | **{r['action']}** "
                     f"| {r['why']} | {sent} |\n")

    if rows:
        with open(OUT / "LEGACY_PERSONA.csv", "w", encoding="utf-8",
                  newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    (OUT / "LEGACY_PERSONA.md").write_text("".join(L), encoding="utf-8")

    for k in KINDS:
        print(f"  {k}: {counts[k]}")
    print(f"\n{len(rows)}箇所 / 要対応 {len(todo_posts)}本 → LEGACY_PERSONA.md")


if __name__ == "__main__":
    main()
