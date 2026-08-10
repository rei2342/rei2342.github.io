#!/usr/bin/env python3
"""
content_audit.py
公開記事を**1〜5の分類へ並べるだけ**の監査。

  python content_audit.py

出力
  workspace/reports/CONTENT_AUDIT_<日付>.md
  workspace/reports/CONTENT_AUDIT_<日付>.csv

**書き換えない。公開しない。1本も自動改稿しない。**
出すのは一覧と、記事ごとの「なぜ直すか／直すと何が良くなるか／何を失うか」。
着手は人が承認してから。

判定に使うのは**手元にあるものだけ**。SERPと公式一次情報は
このコンテナから取りに行けないので、取れていない項目は
`未取得` と書いて出す。**推測で埋めない。**
"""
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as qr
import affiliate_inserter as ai

JST = timezone(timedelta(hours=9))
SPEC = ROOT / "config/content/sakura-content-v1.yaml"


def load_spec():
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


# ── 手元のデータを読む ──────────────────────────────
def published_ids(spec):
    """公開記事IDの正本。SCOPE.md の「公開記事（全体）」行から取る。"""
    t = (ROOT / spec["paths"]["scope"]).read_text(encoding="utf-8")
    m = re.search(r"公開記事（全体）\s*\|\s*\*\*(\d+)\*\*\s*\|\s*([0-9 ]+)\|", t)
    if not m:
        raise SystemExit("SCOPE.md から公開記事IDを読めない")
    ids = [int(x) for x in m.group(2).split()]
    if len(ids) != int(m.group(1)):
        raise SystemExit(f"件数が合わない: {m.group(1)} と {len(ids)}")
    return ids


def ledger(spec):
    """QUALITY_LEDGER.md の表。記事ごとの成果物・案件・CTA本数・一次情報。"""
    t = (ROOT / spec["paths"]["ledger"]).read_text(encoding="utf-8")
    out = {}
    for line in t.split("\n"):
        m = re.match(r"\|\s*\[(\d+)\]\((\S+?)\)\s*\|", line)
        if not m:
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        out[int(m.group(1))] = {
            "url": m.group(2), "title": c[1], "artifact": c[2],
            "main": c[3], "sub": c[4], "cta": c[5], "source": c[6],
            "blockers": c[7], "http": c[8], "canonical": c[9],
            "noindex": c[10]}
    return out


def page_check(spec):
    """PAGE_CHECK.md から、記事ごとの90日の表示・クリック・順位。"""
    t = (ROOT / spec["paths"]["gsc_page_check"]).read_text(encoding="utf-8")
    out = {}
    cur = None
    for line in t.split("\n"):
        m = re.match(r"##\s*記事\s*(\d+)｜", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.search(r"表示回数\s*(\d+)\*?\*?\s*/\s*\*?\*?クリック\s*(\d+)"
                      r"\*?\*?\s*/\s*\*?\*?平均掲載順位\s*([0-9.]+)", line)
        if m and cur is not None:
            out[cur] = {"imp": int(m.group(1)), "clicks": int(m.group(2)),
                        "pos": float(m.group(3))}
            cur = None
    return out


def site_audit(spec):
    """AUDIT.md の「要修正の記事」表。記事IDごとの指摘文。

    **これは過去の点検の控え。** 日付を一緒に返して、
    「いまの本文でも再現するか」を別に見られるようにする。
    """
    t = (ROOT / spec["paths"]["site_audit"]).read_text(encoding="utf-8")
    m = re.search(r"公開記事の点検\s*(\d{4}-\d{2}-\d{2})", t)
    out = {"_date": m.group(1) if m else "不明"}
    for line in t.split("\n"):
        m = re.match(r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|", line)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


def body(pid):
    f = ROOT / "workspace/claims/posts" / f"{pid}.txt"
    if not f.exists():
        return None
    return f.read_text(encoding="utf-8")


# ── 記事1本を見る ───────────────────────────────────
DATED = re.compile(r"20[0-9]{2}年[0-9]{1,2}月[0-9]{1,2}日時点")
CTA_LINE = re.compile(r"^\[p\]\s*→\s*(.+)$", re.M)
HEAD = re.compile(r"^\[h([23])\]\s*(.+)$", re.M)
TERM = re.compile(r"[一-龥ァ-ヴー]{2,}|[A-Za-z]{3,}")
STOP = {"こと", "もの", "とき", "ため", "ほう", "場合", "自分", "記事",
        "確認", "理由", "方法", "英語"}


def terms(t):
    return {w for w in TERM.findall(t) if w not in STOP}


def fact_risk(spec, pid, txt, led, sa, sa_date="不明"):
    """事実リスク。**手元で判定できるものだけ**を挙げる。"""
    out = []
    if led and led.get("blockers") not in ("0", "", None):
        out.append(f"生成ブロッカーが{led['blockers']}件残っている")
    if qr.price_without_basedate(txt):
        out.append("料金があるのに基準日が無い")
    if qr.personal_plan(txt):
        out.append("さくら個人の実現しない予定がある")
    hype = qr.hype_words(txt)
    if hype:
        out.append(f"根拠なしの強い語: {'・'.join(str(h) for h in hype[:3])}")
    inst = qr.institutional_without_source(txt)
    if inst:
        out.append("制度・年齢条件の話に確認日も出典も無い")
    # 「おすすめ」「最適」「一番」は、比較根拠か verified 体験が要る
    for w in ("おすすめ", "最適", "一番"):
        if w in txt and not DATED.search(txt):
            out.append(f"「{w}」があるのに、比較根拠も確認日も無い")
            break
    stale_note = None
    if sa:
        # 手元の本文で同じことが再現しないなら、**採点に使わない。**
        # 直したあとの記事を「まだ壊れている」と並べたら、
        # 直す順番がまるごと狂う（実際に22本がそうなった）
        if out:
            out.append(f"週次点検の指摘（{sa_date}時点）: {sa}")
        else:
            stale_note = (f"週次点検（{sa_date}）は「{sa}」と言っているが、"
                          "**いまの本文では再現しない**。"
                          "その後の全面再構成で直った可能性が高い。"
                          "点検を回し直して控えを更新する")
    return out, stale_note


def staleness(txt):
    """公式の確認日が古くないか。**90日を超えたら見直す。**"""
    ds = DATED.findall(txt)
    if not ds:
        return None, "確認日つきの公式情報が無い"
    def parse(s):
        m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        tzinfo=JST)
    newest = max(parse(d) for d in ds)
    age = (datetime.now(JST) - newest).days
    return age, (f"最新の確認日から{age}日" if age <= 90
                 else f"最新の確認日から{age}日（90日超）")


def cta_check(spec, pid, txt, led):
    """CTAの本数・役割・台帳照合。"""
    out = []
    anchors = CTA_LINE.findall(txt)
    n = len(anchors)
    if n >= 3:
        out.append(f"CTAが{n}本（2本まで）")
    if n == 0 and led and led.get("main"):
        out.append(f"案件（{led['main']}）を載せているのにCTAが0本")
    if n == 2 and led:
        # 役割が重なっていないか。**同じ方向の案件を並べない**
        if led.get("main") and led.get("main") == led.get("sub"):
            out.append("主案件と補助案件が同じ")
    # タイトルから決まる案件と、実際に載っている案件が合っているか
    if led:
        want = ai.classify(led["title"])
        names = _names(want) if want else []
        # `default` は「どの方向とも決まらない」という意味。
        # 決まっていない方向と案件を突き合わせても不一致にしかならない
        # **主案件だけで見ない。** 補助案件が方向を受けていることがある。
        # どちらにも方向の案件が無いときだけ「不一致」と言う
        if want and want != "default" and names and led.get("main"):
            where = f"{led.get('main', '')} {led.get('sub', '')}"
            if not any(k in where for k in names):
                out.append(f"タイトルの方向は {want}"
                           f"（{'・'.join(names)}）なのに、"
                           f"載っているのは 主{led['main']}／"
                           f"補{led.get('sub') or 'なし'}")
    return anchors, out


def _names(topic):
    """トピックIDから、**台帳に出てくる日本語の案件名**を作る。

    TOPIC_MAP が持っているのはスラッグ（nativecamp_ryugaku）で、
    品質台帳が持っているのは表示名（ネイティブキャンプ留学）。
    そのまま比べると全部が不一致になる（実際に45/49本で誤検知した）。
    表示名はCTAのアンカー文から取る。
    """
    out = []
    for slug in (getattr(ai, "TOPIC_MAP", {}) or {}).get(topic, []):
        html = (getattr(ai, "LINKS", {}) or {}).get(slug, ("", ""))[1]
        m = re.search(r">→\s*([^<]+)</a>", html)
        if not m:
            continue
        # 「ネイティブキャンプ留学で留学費用の…」→「ネイティブキャンプ留学」
        anchor = m.group(1)
        out.append(re.split(r"[（(で公式の]", anchor)[0].strip() or anchor)
    return out


# 本文から独自価値を見つける手がかり。仕様の unique_value.kinds に対応する。
# **台帳が空でも、本文にあるなら「無い」とは書かない。**
# 台帳の「（全面再構成の対象外）」は、以前の改修の対象外だったという意味で、
# 成果物が無いという意味ではない（18本をまとめて誤判定していた）
ARTIFACT_SIGNS = [
    ("condition_matrix", r"対応表|国ごと(の|に)(表|一覧)|条件の表"),
    ("fillable_table", r"(表|一覧)(に|へ)(書き出|埋め|並べ)|自分の(数字|条件)に(直す|組み替)"),
    ("swappable_estimate", r"試算|×\s*(想定|滞在|月数)|(総額|費用)を[^。]{0,12}で割"),
    ("fit_branch", r"向いている|向かない|合わない人|(この|その)場合は[^。]{0,20}別"),
    ("pre_signup_questions", r"(相談|申し込|契約)(の)?前に(聞く|確かめ|書き出)"),
    ("cancel_procedure", r"解約[^。]{0,10}(期限|手順|日を先に)"),
    ("failure_diagnosis", r"切り分け|どこで止まっている"),
    ("verified_experience", r"<!--fact:F[0-9]+-->"),
]


def artifact_ok(led, txt):
    """独自の成果物が1つ以上あるか。**文字数は価値に数えない。**

    台帳を先に見て、無ければ本文の合図で探す。
    どちらにも無いときだけ「無い」と書く。
    """
    a = (led or {}).get("artifact", "")
    if a and a not in ("—", "-", "なし") and "対象外" not in a:
        return True, f"台帳: {a}"
    found = [k for k, p in ARTIFACT_SIGNS if re.search(p, txt)]
    # 確認項目が3つ以上並んでいるのも診断の形として数える
    if txt.count("確認項目") >= 3:
        found.append("failure_diagnosis")
    if found:
        note = "台帳未記入" if a and "対象外" in a else "台帳に記入が無い"
        return True, f"本文から検出: {'・'.join(sorted(set(found)))}（{note}）"
    return False, ("固有の成果物が、台帳にも本文の合図にも見つからない"
                   + (f"（台帳は「{a}」）" if a else ""))


def siblings(pid, led, all_led, topics):
    """同じ方向の記事。**カニバリと断定しない。**

    どの記事とどの記事が食い合っているかは、本来
    「同じ検索語で2ページが出ている」ことで分かる。
    いまGSCの表示は28日で4件しかないので、その判定はできない。
    ここで出すのは**人が見るべき束**であって、結論ではない。
    """
    if not led:
        return [], None
    t = topics.get(pid)
    if not t or t == "default":
        return [], t
    mine = terms(led["title"])
    out = []
    for oid, o in all_led.items():
        if oid == pid or topics.get(oid) != t:
            continue
        ot = terms(o["title"])
        sh = mine & ot
        j = len(sh) / len(mine | ot) if (mine | ot) else 0
        out.append((oid, round(j, 2), "・".join(sorted(sh)[:4]) or "—"))
    return sorted(out, key=lambda x: -x[1]), t


def score(spec, f):
    """仕様の加重で並べる。**重みはここに書かない。仕様から読む。**"""
    w = spec["priority"]["weights"]
    s = 0
    if f["fact_risk"]:
        s += w["fact_risk"]
    if f["imp"] > 0 and (f["clicks"] == 0 or f["pos"] > 10):
        s += w["weak_ctr_despite_impressions"]
    if f["cta_issues"]:
        s += w["monetization_mismatch"]
    if not f["has_artifact"]:
        s += w["unanswered_intent"]
    # カニバリは**判定していない**（同じ検索語で2ページ出ているかを
    # 見るにはGSCの表示が要るが、28日で4件しかない）。
    # 加重は、同じ方向が3本以上あって、どれも表示0の束にだけ付ける
    if f["cluster_risk"]:
        s += w["cannibalization"]
    if f["stale_days"] is None or f["stale_days"] > 90:
        s += w["stale_price_or_rule"]
    return s


# 「本文を書き足す・書き直す」必要がある指摘。出典を足すだけでは済まない
STRUCTURAL = re.compile(r"実現しない予定|合わない人|注意点|"
                        r"CTAが0本|CTAが[3-9]本")


def bucket(f):
    """1〜5のどれか。**「なぜそこに入れたか」も一緒に返す。**

    分け方の芯は「何を触るか」。
      2 … 出典・基準日・CTA文言。**本文の骨格は触らない**
      3 … 節を足す、書き直す。骨格の一部を触る
      4 … 記事として成り立っていない
      5 … 統合か非公開。**SERPとGSCが無いと決められない**
    """
    risks = " ".join(f["fact_risk"])
    if f["blockers"]:
        return 4, f"生成ブロッカーが{f['blockers']}件残っている"
    if not f["has_artifact"] and f["fact_risk"]:
        return 4, "固有の成果物が無く、事実リスクも残っている"
    if (f["cluster_risk"] and not f["has_artifact"]
            and f["gsc_known"] and f["imp"] == 0):
        return 5, (f"同じ方向の記事が{f['cluster_n']}本あり、"
                   f"固有の成果物が無く、検索での表示も0")
    if not f["has_artifact"]:
        return 3, "固有の成果物が無い"
    if STRUCTURAL.search(risks) or STRUCTURAL.search(" ".join(f["cta_issues"])):
        return 3, "節を足すか書き直す指摘がある（出典を足すだけでは済まない）"
    if f["fact_risk"] or f["cta_issues"] or (f["stale_days"] or 999) > 90:
        return 2, "出典・基準日・CTAの直しだけで足りる"
    return 1, "手元のデータでは指摘なし"


def gains(f):
    g = []
    if f["fact_risk"]:
        g.append("公開してよい状態になる（事実リスクが消える）")
    if not f["has_artifact"]:
        g.append("上位記事を読んでも決まらない判断に、答えが1つ増える")
    if f["cta_issues"]:
        g.append("読者の条件とCTAの役割が合う")
    if f["gsc_known"] and f["imp"] > 0 and f["clicks"] == 0:
        g.append(f"表示{f['imp']}に対しクリック0の状態が動く可能性がある")
    if f["cluster_risk"]:
        g.append(f"同じ方向の{f['cluster_n']}本の役割がはっきりする"
                 "（統合するか、住み分けるか）")
    if (f["stale_days"] or 999) > 90:
        g.append("料金・制度の記述が、訂正ではなく事実のままでいられる")
    return g or ["いま直す理由が見つからない"]


def losses(f, led):
    l = []
    if not f["gsc_known"]:
        # **未取得を0と書かない。** 「捨てる評価は無い」と言い切ると、
        # 実は順位が付いていた記事を作り直してしまう
        l.append("検索での評価は**未取得**。作り直す前に GSC を取る")
    elif f["imp"] > 0:
        l.append(f"検索での評価（90日で表示{f['imp']}・"
                 f"平均順位{f['pos']}）。作り直すと失う可能性がある")
    else:
        l.append("検索での表示が0（GSCで確認済み）。**捨てる評価は無い**")
    if f["inbound"]:
        l.append(f"この記事へ入る内部リンク{f['inbound']}本の行き先")
    if f["has_artifact"]:
        l.append(f"固有の成果物「{led.get('artifact')}」")
    if f["anchors"]:
        l.append(f"すでに置いてあるCTA {len(f['anchors'])}本の文言と位置")
    return l


def main():
    spec = load_spec()
    ids = published_ids(spec)
    led_all = ledger(spec)
    pc = page_check(spec)
    sa = site_audit(spec)

    # 内部リンクは本文にタイトルが出てくるかで数える。
    # 控えはタグを外してあるので href が残っていない
    titles = {i: led_all[i]["title"] for i in ids if i in led_all}
    bodies = {i: body(i) for i in ids}
    inbound = defaultdict(int)
    for i, txt in bodies.items():
        if not txt:
            continue
        for j, t in titles.items():
            if j != i and t and t[:16] in txt:
                inbound[j] += 1

    topics = {i: ai.classify(led_all[i]["title"])
              for i in ids if i in led_all}
    by_topic = defaultdict(list)
    for i, t in topics.items():
        if t and t != "default":
            by_topic[t].append(i)

    rows = []
    missing = []
    for pid in ids:
        txt = bodies.get(pid)
        if not txt:
            missing.append(pid)
            continue
        led = led_all.get(pid)
        anchors, cta_issues = cta_check(spec, pid, txt, led)
        has_art, art_why = artifact_ok(led, txt)
        sib, topic = siblings(pid, led, led_all, topics)
        risks, stale_note = fact_risk(spec, pid, txt, led, sa.get(pid),
                                      sa.get("_date", "不明"))
        days, stale_why = staleness(txt)
        g = pc.get(pid, {})
        f = {
            "id": pid,
            "title": (led or {}).get("title", txt.split("\n")[0].lstrip("# ")),
            "url": (led or {}).get("url", ""),
            "fact_risk": risks,
            "stale_finding": stale_note,
            "cta_issues": cta_issues,
            "anchors": anchors,
            "has_artifact": has_art,
            "artifact_why": art_why,
            "stale_days": days,
            "stale_why": stale_why,
            "topic": topic or "default",
            "siblings": sib,
            "cluster_n": len(sib) + 1,
            # 同じ方向が3本以上あって、どれも表示が無い束。
            # **カニバリと断定しない。人が役割を決める対象**
            "cluster_risk": len(sib) >= 2,
            "blockers": (led or {}).get("blockers") not in ("0", "", None),
            "imp": g.get("imp", 0),
            "clicks": g.get("clicks", 0),
            "pos": g.get("pos", 0.0),
            "gsc_known": pid in pc,
            "inbound": inbound.get(pid, 0),
            "h2": len(re.findall(r"^\[h2\]", txt, re.M)),
        }
        f["score"] = score(spec, f)
        f["bucket"], f["bucket_why"] = bucket(f)
        f["gains"] = gains(f)
        f["losses"] = losses(f, led or {})
        rows.append(f)

    rows.sort(key=lambda r: (-r["score"], r["id"]))
    write(spec, rows, missing, ids, pc)


def write(spec, rows, missing, ids, pc):
    stamp = datetime.now(JST).strftime("%Y-%m-%d")
    out = ROOT / spec["paths"]["reports"] / f"CONTENT_AUDIT_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    names = {b["id"]: b["name"] for b in spec["initial_audit"]["buckets"]}
    by = defaultdict(list)
    for r in rows:
        by[r["bucket"]].append(r)

    L = [f"# 公開記事の最初の監査（{stamp}）\n\n",
         "**1本も書き換えていない。公開もしていない。**\n",
         "出しているのは分類と、記事ごとの理由だけ。"
         "着手は人が承認してから。\n\n",
         f"対象 {len(ids)}本（`{spec['paths']['scope']}` の公開記事ID）"
         f" / 判定できた {len(rows)}本",
         (f" / 本文の控えが無い {len(missing)}本（{' '.join(str(x) for x in missing)}）"
          if missing else ""), "\n\n",
         "## 分類\n\n| 分類 | 件数 | 記事ID |\n|---|---|---|\n"]
    for b in sorted(names):
        got = by.get(b, [])
        L.append(f"| {b} {names[b]} | {len(got)} | "
                 f"{' '.join(str(r['id']) for r in got)} |\n")
    L.append(f"| **合計** | **{len(rows)}** | |\n\n")

    # **この監査でいちばん大きい発見。** 先に書く
    stale = [r for r in rows if r["stale_finding"]]
    if stale:
        L.append(f"> **先に読むところ。** 週次点検の控え "
                 f"(`{spec['paths']['site_audit']}`) は"
                 f"「要修正22本」と言っているが、そのうち **{len(stale)}本は、"
                 f"いまの本文で同じことが再現しない。**\n>\n"
                 f"> 控えは2026-08-08で、そのあとに全面再構成が入っている。"
                 f"再現しない指摘を採点へ入れると、直す順番がまるごと狂うので"
                 f"**外してある**。\n>\n"
                 f"> 該当: {' '.join(str(r['id']) for r in stale)}\n>\n"
                 f"> **やること: 週次点検を1回回して控えを更新する。**"
                 f"それまで、この{len(stale)}本を「直った」と断定しない。\n\n")

    # **0本の分類は、理由を書く。** 空欄のままだと見落としに見える
    L.append("**1（改善不要）の読み方**: これは「手元のデータでは指摘が"
             "見つからない」という意味で、**完成という意味ではない**。"
             "SERPと公式一次情報を取ると、"
             "`market_gap_present` と `official_source_match` で"
             "分類が動く。ここを最終判断にしない。\n\n")
    if not by.get(3):
        L.append("**3（部分再構成）が0本の理由**: 節を足す・書き直す指摘は、"
                 "いま全部が「再現しない週次点検の控え」から来ていた。"
                 "採点から外した結果0本になった。"
                 "**週次点検を回し直すと増える可能性が高い。**\n\n")
    if not by.get(4):
        L.append("**4（全面再構成）が0本の理由**: 品質台帳では49本すべて"
                 "生成ブロッカー0件で、固有の成果物も1つ以上ある。"
                 "手元のデータで「記事として成り立っていない」と言える"
                 "ものが無い。SERPを取れば変わる可能性がある。\n\n")
    if not by.get(5):
        L.append("**5（統合／非公開候補）が0本の理由**: "
                 "カニバリは本来「同じ検索語で2ページが出ている」ことで"
                 "判定する。GSCの表示が28日で4件しかないので、"
                 "**この判定はできない**。代わりに、同じ方向の記事の束を"
                 "下に出した。ここから人が決める。\n\n")

    # 同じ方向の束。**カニバリと断定しない**
    clus = defaultdict(list)
    for r in rows:
        if r["topic"] != "default":
            clus[r["topic"]].append(r)
    L.append("## 同じ方向の記事の束（カニバリの候補・**未判定**）\n\n"
             "| 方向 | 本数 | 表示が有る本数 | 記事ID |\n|---|---|---|---|\n")
    for t, rs in sorted(clus.items(), key=lambda x: -len(x[1])):
        withimp = sum(1 for r in rs if r["gsc_known"] and r["imp"] > 0)
        L.append(f"| {t} | {len(rs)} | {withimp} "
                 f"| {' '.join(str(r['id']) for r in rs)} |\n")
    solo = [r for r in rows if r["topic"] == "default"]
    L.append(f"| （方向が決まらない） | {len(solo)} | "
             f"{sum(1 for r in solo if r['gsc_known'] and r['imp'] > 0)} "
             f"| {' '.join(str(r['id']) for r in solo)} |\n\n"
             "束が3本以上あって、どれも検索での表示が0なら、"
             "順位ではなく**役割の重複**を先に見る。\n\n")

    # 手元で取れないものは、取れないと書く。**推測で埋めない**
    L.append("## このコンテナで取れなかったデータ\n\n"
             "| データ | 状態 | 取り方 |\n|---|---|---|\n"
             "| SERP上位10件 | **未取得** | 外向き通信が要る。Actions で取る |\n"
             "| 公式一次情報の再取得 | **未取得** | 同上。"
             "いまは本文に書いてある確認日で代用している |\n"
             f"| GSC（記事別） | {len(pc)}本ぶんだけ手元にある | "
             "`workspace/gsc/PAGE_CHECK.md`。残りは0として扱っていない、"
             "`未取得` として区別している |\n"
             "| GA4（記事別のCTAクリック） | **未取得** | "
             "`link_domain` のイベントを記事別に出す集計が要る |\n\n"
             "**取れていない項目を0として扱っていない。**"
             "0件と未取得を混ぜると、直す順番を間違える。\n\n")

    L.append("## 優先度\n\n仕様 `priority.weights` の加重で並べた。\n\n"
             "| 観点 | 加重 |\n|---|---|\n")
    for k, v in spec["priority"]["weights"].items():
        L.append(f"| {k} | {v} |\n")
    L.append(f"\n> {spec['priority']['zero_impression_rule'].strip()}\n\n")
    known = [r for r in rows if r["gsc_known"]]
    zero = sum(1 for r in known if r["imp"] == 0)
    L.append(f"**GSCを確認できた{len(known)}本のうち、表示0が{zero}本。**"
             f"残り{len(rows) - len(known)}本は未取得（0ではない）。\n"
             "この状態で順位対策から入らない。\n\n")

    L.append("## 一覧（優先度順）\n\n"
             "| 優先度 | 分類 | ID | タイトル | 表示 | 内部リンク | 主な理由 |\n"
             "|---|---|---|---|---|---|---|\n")
    for r in rows:
        imp = str(r["imp"]) if r["gsc_known"] else "未取得"
        why = (r["fact_risk"] + r["cta_issues"]
               + ([] if r["has_artifact"] else [r["artifact_why"]]))
        L.append(f"| {r['score']} | {r['bucket']} | {r['id']} "
                 f"| {r['title'][:26]} | {imp} | {r['inbound']} "
                 f"| {(why[0] if why else '指摘なし')[:34]} |\n")

    L.append("\n---\n\n## 記事ごと\n\n")
    for r in rows:
        L.append(f"### {r['id']}｜{r['title']}\n\n")
        if r["url"]:
            L.append(f"{r['url']}\n\n")
        L.append(f"**分類 {r['bucket']} {names[r['bucket']]}**"
                 f"（優先度 {r['score']}）… {r['bucket_why']}\n\n")
        L.append("**なぜ直すか**\n\n")
        why = (r["fact_risk"] + r["cta_issues"]
               + ([] if r["has_artifact"] else [r["artifact_why"]])
               + ([f"同じ方向（{r['topic']}）の記事が{r['cluster_n']}本ある: "
                   + " ".join(f"{c[0]}" for c in r["siblings"])
                   + "。**カニバリかどうかは未判定**（GSCの表示が足りない）"]
                  if r["cluster_risk"] else [])
               + ([r["stale_why"]] if (r["stale_days"] or 999) > 90 else []))
        for x in why or ["手元のデータでは指摘なし"]:
            L.append(f"- {x}\n")
        if r["stale_finding"]:
            L.append(f"- （採点に入れていない）{r['stale_finding']}\n")
        L.append("\n**直すと何が良くなるか**\n\n")
        for x in r["gains"]:
            L.append(f"- {x}\n")
        L.append("\n**何を失うか**\n\n")
        for x in r["losses"]:
            L.append(f"- {x}\n")
        L.append(f"\n<details><summary>手元の数字</summary>\n\n"
                 f"| 項目 | 値 |\n|---|---|\n"
                 f"| 90日の表示 | {r['imp'] if r['gsc_known'] else '未取得'} |\n"
                 f"| 90日のクリック | "
                 f"{r['clicks'] if r['gsc_known'] else '未取得'} |\n"
                 f"| 平均順位 | {r['pos'] if r['gsc_known'] else '未取得'} |\n"
                 f"| H2の本数 | {r['h2']} |\n"
                 f"| CTA | {len(r['anchors'])}本 |\n"
                 f"| 固有の成果物 | {r['artifact_why']} |\n"
                 f"| 公式の確認日 | {r['stale_why']} |\n"
                 f"| 入る内部リンク | {r['inbound']}本 |\n"
                 f"\n</details>\n\n")

    L.append("---\n\n## 次にすること\n\n"
             "1. この一覧を人が見て、着手する記事と順番を決める\n"
             "2. 決まった記事だけ、SERPと公式一次情報を Actions で取る\n"
             "3. keep / fix / add / remove / merge / link / cta / evidence を作る\n"
             "4. 人が差分・出典・CTAを承認してから WordPress へ反映する\n\n"
             "**この監査の時点では、1本も変更していない。**\n")

    out.write_text("".join(L), encoding="utf-8")

    csv_p = out.with_suffix(".csv")
    with csv_p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "bucket", "bucket_name", "score", "title",
                    "impressions", "clicks", "position", "gsc_known",
                    "inbound_links", "cta_count", "has_artifact",
                    "artifact", "stale", "topic", "cluster_n",
                    "cluster_risk", "siblings", "fact_risk",
                    "cta_issues", "stale_finding", "url"])
        for r in rows:
            w.writerow([r["id"], r["bucket"], names[r["bucket"]], r["score"],
                        r["title"], r["imp"], r["clicks"], r["pos"],
                        r["gsc_known"], r["inbound"], len(r["anchors"]),
                        r["has_artifact"], r["artifact_why"], r["stale_why"],
                        r["topic"], r["cluster_n"], r["cluster_risk"],
                        " ".join(str(c[0]) for c in r["siblings"]),
                        " / ".join(r["fact_risk"]),
                        " / ".join(r["cta_issues"]),
                        r["stale_finding"] or "", r["url"]])

    print(f"→ {out}")
    print(f"→ {csv_p}")
    for b in sorted(names):
        print(f"  {b} {names[b]}: {len(by.get(b, []))}本")
    print("**1本も書き換えていない。**")


if __name__ == "__main__":
    main()
