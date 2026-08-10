#!/usr/bin/env python3
"""
social_gate.py
X・Threadsの投稿文を、出す前に見る。**落ちたら投稿しない。**

記事側の `quality_rules.unverified_self_facts()` をそのまま使う。
SNSだけ別基準にすると、記事で止めたものがSNSから漏れる。

  from social_gate import run_gates
  results = run_gates(spec, platform, parts, article, history)

戻り値は [(gate_id, ok, detail), ...]。1つでも ok=False なら出さない。
"""
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_rules as qr
import social_claims as sc

EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿←-⇿"
                   r"⬀-⯿️]")
URL = re.compile(r"https?://\S+")


def _plain(t):
    """URLと絵文字を除いた本文の長さを数えるための素の文字列。"""
    return EMOJI.sub("", URL.sub("", t)).strip()


def _ngrams(t, n=3):
    t = re.sub(r"\s+", "", URL.sub("", t))
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def jaccard(a, b):
    x, y = _ngrams(a), _ngrams(b)
    return len(x & y) / len(x | y) if x | y else 0.0


# ── 個別のゲート ────────────────────────────────────
def fact_gate(spec, text):
    """未確認の一人称の事実。**記事側と同じ関数を使う。**

    記事側は一人称の印（私・自分）を手がかりにしている。SNSは主語を落とすので、
    印が無くても落とすものを仕様の leak_patterns から足す。
    """
    hits = [str(h) for h in qr.unverified_self_facts(text)]
    pers = spec["persona"]
    marks = pers.get("self_markers", [])
    exempt = pers.get("exempt", [])
    for sent in sc.sentences(text):
        # 出典つきの公式情報・一般的な条件・仮定の試算・fact ID つきは通す
        why = next((e["name"] for e in exempt if re.search(e["re"], sent)),
                   None)
        if why:
            continue
        has_self = any(m in sent for m in marks)
        for pat in pers.get("leak_patterns", []):
            if pat.get("needs_self") and not has_self:
                continue        # 数字があるだけでは落とさない
            m = re.search(pat["re"], sent)
            if m:
                hits.append(f"{pat['name']}: {m.group(0)}")
    return (not hits, "; ".join(hits[:3]))


def broken_gate(spec, text):
    bad = [x for x in spec["forbidden"]["patterns"]["broken_output"]
           if x in text]
    return (not bad, " ".join(bad))


def shape_gate(spec, platform, parts):
    """URLだけの投稿、空投稿、行数、空行、絵文字、ハッシュタグ。"""
    bad = []
    s = spec["style"]
    for i, p in enumerate(parts, 1):
        body = _plain(p)
        if not body:
            bad.append(f"{i}投稿目がURLだけ、または空")
            continue
        n_emoji = len(EMOJI.findall(p))
        lim = s["emoji"]["x" if platform == "x" else "threads"]
        if not lim["min"] <= n_emoji <= lim["max"]:
            bad.append(f"{i}投稿目の絵文字が{n_emoji}個"
                       f"（{lim['min']}〜{lim['max']}）")
        if re.search(r"#\S", p):
            bad.append(f"{i}投稿目にハッシュタグがある")
        if re.search(r"[↓→]\s*$", p.strip()) and platform == "threads":
            bad.append(f"{i}投稿目が矢印で終わっている（強制の『↓』は廃止）")
    if platform == "x":
        p = parts[0]
        lines = [l for l in p.split("\n") if l.strip()]
        x = spec["x"]
        if not x["lines"]["min"] <= len(lines) <= x["lines"]["max"]:
            bad.append(f"{len(lines)}行（{x['lines']['min']}〜"
                       f"{x['lines']['max']}行）")
        blanks = len(re.findall(r"\n\s*\n", p.strip()))
        if blanks > x["blank_lines_max"]:
            bad.append(f"空行が{blanks}つ（{x['blank_lines_max']}つまで）")
    return (not bad, " / ".join(bad))


def length_gate(spec, platform, parts):
    bad = []
    if platform == "x":
        n = len(_plain(parts[0]))
        lo, hi = spec["x"]["length"]["min"], spec["x"]["length"]["max"]
        if not lo <= n <= hi:
            bad.append(f"{n}字（{lo}〜{hi}）")
        w = weighted_len(spec, parts[0])
        lim = spec["x"]["weighted"]["hard_limit"]
        if w > lim:
            bad.append(f"加重{w}（上限{lim}）")
    elif len(parts) == 1 and spec["threads"].get("single"):
        # 1投稿で完結する形。part1 の上限で測ると必ず落ちる
        lo = spec["threads"]["single"]["length"]["min"]
        hi = spec["threads"]["single"]["length"]["max"]
        n = len(_plain(parts[0]))
        if not lo <= n <= hi:
            bad.append(f"1投稿完結で{n}字（{lo}〜{hi}）")
    else:
        t = spec["threads"]
        keys = ["part1", "part2"]
        for i, p in enumerate(parts):
            if i >= len(keys):
                bad.append(f"{i + 1}投稿目が多い（最大{t['parts']['max']}）")
                break
            lo = t[keys[i]]["length"]["min"]
            hi = t[keys[i]]["length"]["max"]
            n = len(_plain(p))
            if not lo <= n <= hi:
                bad.append(f"{i + 1}投稿目が{n}字（{lo}〜{hi}）")
    return (not bad, " / ".join(bad))


def link_gate(spec, platform, parts, article):
    """URLの位置・utm・記事URLとの一致。"""
    bad = []
    want = article["url"]
    utm = spec[platform]["url"]["utm"]
    last = parts[-1]
    urls = URL.findall("\n".join(parts))
    if not urls:
        bad.append("URLが無い")
    else:
        if not URL.search(last) or not last.rstrip().endswith(urls[-1]):
            bad.append("URLが最終投稿の末尾に無い")
        for u in urls:
            if utm not in u:
                bad.append(f"utmが無い: {u}")
            base = u.split("?")[0]
            if base.rstrip("/") != want.split("?")[0].rstrip("/"):
                bad.append(f"記事URLと違う: {u}")
            if "example.com" in u or "?p=" in u:
                bad.append(f"公開URLでない: {u}")
    if len(urls) > 1:
        bad.append(f"URLが{len(urls)}個ある")
    return (not bad, " / ".join(bad))


def article_gate(spec, article):
    bad = []
    if article.get("status") != "publish":
        bad.append(f"記事が {article.get('status')}")
    if not article.get("modified_gmt"):
        bad.append("modified_gmt が無い（あとで stale を判定できない）")
    return (not bad, " / ".join(bad))


def unchanged_gate(spec, article, stock_modified):
    ok = stock_modified and article.get("modified_gmt") == stock_modified
    return (bool(ok), "" if ok else
            f"生成時 {stock_modified} → 今 {article.get('modified_gmt')}")


def duplicate_gate(spec, text, history):
    """過去180日の投稿と、完全一致・近似重複が無いか。"""
    th = spec["duplicate"]["near_threshold"]
    for h in history:
        if jaccard(text, h["text"]) >= 1.0:
            return (False, f"完全一致: {h.get('stock_id', h.get('posted_id'))}")
        j = jaccard(text, h["text"])
        if j >= th:
            return (False, f"近似 {j:.2f}: "
                           f"{h.get('stock_id', h.get('posted_id'))}")
    return (True, "")


def cross_platform_gate(spec, text, other_text):
    """XとThreadsが同じ文になっていないか。"""
    if not other_text:
        return (True, "もう片方がまだ無い")
    j = jaccard(text, other_text)
    th = spec["duplicate"]["near_threshold"]
    return (j < th, f"XとThreadsの近さ {j:.2f}（{th}未満にする）")


def weighted_len(spec, text):
    """Xの数え方に合わせる。**Pythonの文字数では通さない。**

    URLは長さによらず 23。CJKと全角記号は2、半角は1。
    """
    w = spec["x"]["weighted"]
    n = len(URL.findall(text)) * w["url_weight"]
    for ch in URL.sub("", text):
        if ch == "\n":
            n += w["narrow_weight"]
        elif ord(ch) < 0x1100 or 0xFF61 <= ord(ch) <= 0xFF9F:
            n += w["narrow_weight"]
        else:
            n += w["wide_weight"]
    return n


def subset_gate(spec, parts, article, inferences=()):
    """記事に無い**命題**を足していないか。数字だけでは足りない。

    因果・診断・効果は、記事に無ければ勝手な断定になる。
    記事が「確認項目」として書いているものを言い切っていたら、それも落とす。
    """
    bad = []
    body = article.get("body", "")
    for p in parts:
        for n in re.findall(r"[0-9]+(?:\.[0-9]+)?", _plain(p)):
            if len(n) >= 2 and n not in body:
                bad.append(f"記事に無い数字: {n}")
    for r in sc.failures(sc.check(spec, parts, article, inferences)):
        bad.append(f"{r['verdict']}: {r['text'][:26]}（{r['why']}）")
    return (not bad, " / ".join(dict.fromkeys(bad)))


def template_gate(spec, parts, recent=()):
    """定型句と文型の重なり。**落とさずに警告する。**

    直近の投稿と、冒頭・締め・定型句が3件以上重なったら知らせる。
    """
    t = spec["template_variety"]
    text = "\n".join(parts)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # **冒頭の型は冒頭の行だけで見る。** 全行で見ると
    # 「今日ためせるのは、この順番です」のような本文中の一文まで
    # 「冒頭の型」として数えてしまう（2026-08-10に誤検知した）
    where = {"phrases": lines, "openers": lines[:1], "closers": lines[-1:]}
    mine = set()
    for group in ("phrases", "openers", "closers"):
        for pat in t[group]:
            for line in where[group]:
                if re.search(pat["re"], line):
                    mine.add(pat["id"])
                    break
    warn = []
    for pid in sorted(mine):
        same = sum(1 for r in list(recent)[-t["window"]:]
                   if pid in (r.get("template_ids") or []))
        if same >= t["max_same"]:
            warn.append(f"「{pid}」がこれで{same + 1}件目"
                        f"（直近{t['window']}本・{t['max_same']}件まで）")
    return sorted(mine), warn


# ── 温度と会話（2026-08-09 追加）──────────────────────
# 事実として安全でも、説明調だと読まれない。
# **落とすのは架空の共感だけ。** 残りは警告にして人が見る。
def empathy_without_evidence(spec, text):
    """「私も」「わかります」「経験した」。**fact ID が無ければ落とす。**

    温度を上げようとして真っ先に出るのがこれで、
    そのまま出すと台帳に無い体験を書いたことになる。
    """
    t = spec["tone"]["empathy_without_evidence"]
    if t.get("allow_with_fact_id"):
        for e in spec["persona"].get("exempt", []):
            if e["name"] == "fact IDつき" and re.search(e["re"], text):
                return (True, "fact ID がある")
    hit = [p for p in t["patterns"] if p in text]
    # 「わかります」は語として拾うと「〜が分かります」まで落ちる。
    # **一節まるごとがそれだけ**のときに、はじめて相づちだと分かる
    bare = {i + b for b in t.get("bare_patterns", [])
            for i in t.get("bare_intensifiers", [""])}
    for chunk in re.split(r"[、。！？\n]", EMOJI.sub("", text)):
        if chunk.strip() in bare:
            hit.append(chunk.strip())
    return (not hit, "台帳に無い共感: " + " ".join(hit) if hit else "")


def cold_tone_warning(spec, text):
    """「してください」「ではありません」が**合計**で多いと説明調になる。"""
    t = spec["tone"]["cold_tone"]
    n = sum(text.count(p) for p in t["patterns"])
    if n > t["max_total"]:
        return [f"命令・否定の言い切りが合計{n}回（{t['max_total']}回まで）"]
    return []


def emoji_role(spec, parts):
    """絵文字は飾りではなく役割。**役割の無いものを知らせる。**"""
    roles = spec["style"]["emoji"]["roles"]
    warn = []
    for i, p in enumerate(parts, 1):
        found = EMOJI.findall(p)
        unknown = [e for e in found if e not in roles]
        if unknown:
            warn.append(f"{i}投稿目に役割の無い絵文字 {' '.join(unknown)}")
        for a, b in zip(found, found[1:]):
            if p.find(a + b) >= 0:
                warn.append(f"{i}投稿目で絵文字が連続している（{a}{b}）")
        for line in p.split("\n"):
            line = line.strip()
            if line and line[0] in roles:
                warn.append(f"{i}投稿目の行頭に絵文字がある（{line[0]}）")
    return warn


def emoji_repetition(spec, parts, recent=()):
    """同じ絵文字が直近3投稿続いたら知らせる。"""
    roles = spec["style"]["emoji"]["roles"]
    mine = {e for e in EMOJI.findall("\n".join(parts)) if e in roles}
    warn = []
    prev = list(recent)[-2:]
    for e in sorted(mine):
        if prev and len(prev) == 2 and all(e in r.get("text", "")
                                           for r in prev):
            warn.append(f"{e} が3投稿続いている")
    return warn


def sentence_height(spec, parts):
    """同じ語尾が3文続くと、全部が同じ高さになって平坦に読める。"""
    t = spec["tone"]["sentence_height"]
    warn = []
    for i, p in enumerate(parts, 1):
        run, last = 0, None
        # **内容語で絞らずに割る。** sc.sentences() は内容語の無い文を
        # 落とすので、「朝に開きます。昼に開きます。」の連続が消える
        for s in re.split(r"(?<=[。！？])|\n", URL.sub("", p)):
            # 絵文字を落としてから語尾を見る。「〜です🌿」を数え落とさない
            s = EMOJI.sub("", s or "").strip()
            if not s:
                continue
            end = next((e for e in t["endings"]
                        if re.search(e + r"[。！？]?$", s)), None)
            if end and end == last:
                run += 1
            else:
                run, last = 1, end
            if end and run > t["max_run"]:
                warn.append(f"{i}投稿目で「{end}」止めが{run}文続いている")
                run = 0
    return warn


def conversation_mix(spec, platform, parts, recent=()):
    """Threadsに問いかけが無いと、読むだけで終わって会話にならない。

    逆に**全部が問いかけでも**警告する。毎回聞かれると答える気が失せる。
    """
    t = spec["tone"]["conversation_mix"]
    if platform != t["platform"]:
        return []

    def has_q(x):
        # **URLを外してから見る。** `?utm_source=threads` の `?` を
        # 問いかけと数えて、全投稿が問いかけ扱いになっていた
        return any(m in URL.sub("", x) for m in t["question_marks"])

    window = [r.get("text", "") for r in list(recent)[-(t["window"] - 1):]]
    window.append("\n".join(parts))
    n = sum(1 for x in window if has_q(x))
    if len(window) < t["window"]:
        return []
    if n < t["min_questions"]:
        return [f"直近{t['window']}本に問いかけが{n}件"
                f"（{t['min_questions']}件以上）"]
    if n > t["max_questions"]:
        return [f"直近{t['window']}本のうち{n}件が問いかけ"
                f"（{t['max_questions']}件まで）"]
    return []


def _paras(text):
    return [x.strip() for x in URL.sub("", text).split("\n") if x.strip()]


def opener_type(spec, text, declared=None):
    """導入がどの型か。

    **書き手が宣言した型を優先する。** 正規表現の推測だけに頼ると、
    「型を使い分ける」という判断そのものが機械任せになる。
    宣言が無いときだけ推測する。
    """
    if declared:
        return declared
    first = (_paras(text) or [""])[0]
    if re.search(r"でしょうか|ますか$|ますか。", first):
        return "direct_answer"
    if re.search(r"と(?:聞く|言われ|いう言い方)|と考えがち|と思いがち", first):
        return "misreading"
    if re.search(r"^(?:結論|先に言うと)|だけです。$|それだけです", first):
        return "conclusion_first"
    if re.search(r"大丈夫です|安心|しなくていい|責めなくて", first):
        return "short_reassurance"
    return "reader_scene"


def variety_check(spec, rows):
    """**5件の窓で偏りを見る。** 1件ずつでは分からない。

    温かさの作り方が1つに寄ると、5件並べたときに同じ顔になる。
    落とさずに警告で出す。
    """
    v = spec.get("variety")
    if not v:
        return [], {}
    win = [r for r in rows][-v["window"]:]
    conf = {c["id"]: c for c in v["checks"]}
    counts, warn = {}, []

    n = 0
    for r in win:
        first = (_paras(r["text"]) or [""])[0]
        if re.search(conf["emotion_guess_open"]["re"], first):
            n += 1
    counts["emotion_guess_open"] = n
    if n > conf["emotion_guess_open"]["max"]:
        warn.append(f"感情を推測する導入が{n}件"
                    f"（{conf['emotion_guess_open']['max']}件まで）")

    n = 0
    for r in win:
        ps = _paras(r["text"])
        if len(ps) >= 2 and ps[1].startswith("でも"):
            n += 1
    counts["demo_second_para"] = n
    if n > conf["demo_second_para"]["max"]:
        warn.append(f"2段落目を「でも」で始めるのが{n}件"
                    f"（{conf['demo_second_para']['max']}件まで）")

    n = 0
    for r in win:
        ps = _paras(r["text"])
        if ps and re.search(conf["kochira_before_cta"]["re"], ps[-1]):
            n += 1
    counts["kochira_before_cta"] = n
    if n > conf["kochira_before_cta"]["max"]:
        warn.append(f"CTA直前の「こちら」が{n}件"
                    f"（{conf['kochira_before_cta']['max']}件まで）")

    types = [opener_type(spec, r["text"], r.get("opener_type")) for r in win]
    counts["opener_types"] = types
    run = mx = 1
    for a, b in zip(types, types[1:]):
        run = run + 1 if a == b else 1
        mx = max(mx, run)
    counts["same_opener_run"] = mx
    if mx > conf["same_opener_run"]["max_run"]:
        warn.append(f"同じ導入構造が{mx}件続いている"
                    f"（{conf['same_opener_run']['max_run']}件まで）")

    counts["closers"] = closer_counts(spec, win)
    for k, c in counts["closers"].items():
        if c > conf["same_closer"]["max"]:
            warn.append(f"同じ締め方「{k}」が{c}件"
                        f"（{conf['same_closer']['max']}件まで）")
    return warn, counts


def closer_class(spec, text):
    """締めの**意味の型**を返す。

    語尾の完全一致だけで見ると、「まとめました」を「整理しました」へ
    言い換えただけで別物になる。**同じ意味・同じ構文を1つに数える。**
    どの型にも当たらないものは、語尾の見た目でまとめる。
    """
    conf = next((c for c in spec["variety"]["checks"]
                 if c["id"] == "same_closer"), {})
    ps = _paras(text)
    if not ps:
        return "（空）"
    last = ps[-1]
    for cl in conf.get("classes", []):
        if re.search(cl["re"], last):
            return cl["id"]
    return "尾:" + re.sub(r"[^ぁ-んァ-ヶ一-龥？?]", "", last)[-6:]


def closer_counts(spec, rows):
    from collections import Counter
    return dict(Counter(closer_class(spec, r["text"]) for r in rows))


def same_closer_gate(spec, rows):
    """**承認ゲート。** 同じ意味・同じ構文の締めが上限を超えたら止める。

    記事への導線そのものは禁止しない。型ごとに数えて、
    5件のうち上限を超えた型だけを落とす。
    """
    conf = next((c for c in spec["variety"]["checks"]
                 if c["id"] == "same_closer"), {})
    if not conf.get("blocking"):
        return True, ""
    win = list(rows)[-spec["variety"]["window"]:]
    bad = [f"{k}が{n}件" for k, n in closer_counts(spec, win).items()
           if n > conf["max"]]
    return (not bad, f"同じ締めの型: {' / '.join(bad)}"
                     f"（{conf['max']}件まで）" if bad else "")


def market_reference_gate(spec):
    """参考にした投稿を記録しているか。**文章は採らない。構造だけ採る。**

    記録が無いまま「ベンチマークを見た」と言えてしまうと、
    次の月にどこを見直せばよいか追えなくない。落とさずに知らせる。
    """
    mr = spec["market_reference"]
    f = Path(__file__).resolve().parents[1] / mr["file"]
    if not f.exists():
        return [f"{mr['file']} が無い"]
    import yaml
    d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    rows = d.get("references") or []
    if not rows:
        return [f"{mr['file']} に記録が無い"]
    warn = []
    for r in rows:
        miss = [k for k in mr["required_fields"] if not r.get(k)]
        if miss:
            warn.append(f"{r.get('url', '(URL無し)')} に "
                        f"{'・'.join(miss)} が無い")
    return warn


def format_mix_gate(spec, stock_rows):
    """Threadsの1投稿型と2投稿型が、決めた本数と役割で並んでいるか。

    **同じ記事を割っただけのA/B案を作らない。** 形を比べるのであって、
    同じ文の見え方を比べるのではない。だから
    1投稿型と2投稿型で、使う固有の成果物が重ならないことも見る。
    """
    fm = spec["threads"].get("format_mix")
    if not fm:
        return []
    # **退役した在庫は形の勘定に入れない**（stale/rejected/archived）
    th = [s for s in stock_rows if s["platform"] == "threads"
          and s.get("state") not in ("stale", "rejected", "archived")]
    if not th:
        return []
    bad = []
    got = {"single": 0, "two_part": 0}
    arts = {"single": set(), "two_part": set()}
    for s in th:
        f = s.get("threads_format") or (
            "single" if len(s["thread_parts"]) == 1 else "two_part")
        got[f] = got.get(f, 0) + 1
        if s.get("artifact_used"):
            arts.setdefault(f, set()).add(s["artifact_used"])
    for f in ("single", "two_part"):
        if fm.get(f) is not None and got.get(f, 0) != fm[f]:
            bad.append(f"{f} が{got.get(f, 0)}本（{fm[f]}本にする）")
    if fm.get("artifact_must_differ"):
        both = arts["single"] & arts["two_part"]
        if both:
            bad.append("1投稿型と2投稿型が同じ成果物を使っている: "
                       + "・".join(sorted(both)))
    # 形が違うだけで中身が同じものが無いか
    for a in th:
        for b in th:
            if a["stock_id"] >= b["stock_id"]:
                continue
            if a["article_id"] == b["article_id"]:
                bad.append(f"同じ記事で2案ある: {a['stock_id']} と "
                           f"{b['stock_id']}（割っただけのA/Bにしない）")
    return bad


def tone_warnings(spec, platform, parts, recent=()):
    """温度の警告をまとめる。**落とさない。** 人が見て判断する。"""
    same = [r for r in recent if r.get("platform") == platform]
    return (cold_tone_warning(spec, "\n".join(parts))
            + emoji_role(spec, parts)
            + emoji_repetition(spec, parts, same)
            + sentence_height(spec, parts)
            + conversation_mix(spec, platform, parts, same)
            + market_reference_gate(spec))


def style_warnings(spec, parts):
    """落とさないが知らせるもの。短行の連打・不自然な改行。"""
    warn = []
    for i, p in enumerate(parts, 1):
        lines = [l for l in p.split("\n") if l.strip()]
        short = [l for l in lines if len(l) <= 12]
        if len(lines) >= 5 and len(short) / len(lines) > 0.7:
            warn.append(f"{i}投稿目が短い行の連打（{len(short)}/{len(lines)}行）")
        for w in spec["style"]["avoid"]:
            pass
        if re.search(r"実は|意志が弱いんじゃない|な人だけ見て", p):
            warn.append(f"{i}投稿目に定型フックがある")
    return warn


# ── まとめて走らせる ────────────────────────────────
def run_gates(spec, platform, parts, article, history=(), other_text="",
              stock_modified=None, inferences=()):
    text = "\n\n".join(parts)
    res = [
        ("article_published", *article_gate(spec, article)),
        ("fact_gate", *fact_gate(spec, text)),
        ("empathy_without_evidence", *empathy_without_evidence(spec, text)),
        ("broken_output", *broken_gate(spec, text)),
        ("style_gate", *shape_gate(spec, platform, parts)),
        ("length_gate", *length_gate(spec, platform, parts)),
        ("link_gate", *link_gate(spec, platform, parts, article)),
        ("subset_gate", *subset_gate(spec, parts, article,
                                     inferences)),
        ("duplicate_gate", *duplicate_gate(spec, text, history)),
        ("cross_platform_gate", *cross_platform_gate(spec, text, other_text)),
    ]
    if stock_modified is not None:
        res.append(("article_unchanged",
                    *unchanged_gate(spec, article, stock_modified)))
    return res


def passed(results):
    return all(ok for _, ok, _ in results)


def fmt(results):
    return "\n".join(("OK  " if ok else "NG  ") + gid
                     + (f" … {d}" if d else "")
                     for gid, ok, d in results)
