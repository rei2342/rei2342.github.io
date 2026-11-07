"""COMMAND CENTER — streamlit run dashboard/app.py"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from core import account_loader as L  # noqa: E402
from core import config as C  # noqa: E402
from core import drafts, revenue  # noqa: E402

NEON, BG, PANEL, MUTED = "#39FF14", "#070B07", "#0E150E", "#7FA37F"

st.set_page_config(page_title="COMMAND CENTER", page_icon="🟩", layout="wide")
st.markdown(f"""
<style>
.stApp {{ background: {BG}; color: #D8F5D8; }}
[data-testid="stHeader"] {{ background: transparent; }}
h1, h2, h3, h4 {{ color: {NEON} !important; font-family: 'JetBrains Mono', ui-monospace, monospace; letter-spacing: .04em; }}
[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid #1F3A1F; border-radius: 6px; padding: 12px 14px; }}
[data-testid="stMetricValue"] {{ color: {NEON}; font-family: ui-monospace, monospace; }}
[data-testid="stMetricLabel"] {{ color: {MUTED}; }}
.stTabs [data-baseweb="tab"] {{ font-family: ui-monospace, monospace; color: {MUTED}; }}
.stTabs [aria-selected="true"] {{ color: {NEON} !important; border-bottom: 2px solid {NEON}; }}
.stButton>button, .stDownloadButton>button {{ border: 1px solid {NEON}; color: {NEON}; background: transparent; }}
.stButton>button:hover {{ background: {NEON}; color: {BG}; }}
.badge {{ display:inline-block; padding:1px 8px; border-radius:10px; font-size:12px; margin-right:4px; border:1px solid; }}
.ok {{ color:{NEON}; border-color:{NEON}; }} .ng {{ color:#FF5C5C; border-color:#FF5C5C; }} .mid {{ color:#E8D44D; border-color:#E8D44D; }}
.mono {{ font-family: ui-monospace, monospace; font-size: 13px; }}
</style>""", unsafe_allow_html=True)


def badge(text, kind="ok"):
    return f'<span class="badge {kind}">{text}</span>'


@st.cache_data(ttl=5)
def _master_cached(mtime: float):
    return L.load_master()


def master():
    return _master_cached(C.MASTER_PATH.stat().st_mtime)


settings = C.load_settings()
try:
    M = master()
except Exception as e:
    st.error(f"accounts_master.json を読めない: {e}")
    up = st.file_uploader("Astra の accounts_master.json をインポート", type="json")
    if up and st.button("取り込む"):
        L.import_master(json.loads(up.read()), "replace", note="bootstrap")
        st.rerun()
    st.stop()

ACCOUNTS = L.get_accounts(M)
LABELS = {a.key: f"{a.label}（{a.key}）" for a in ACCOUNTS}

# ---------------------------------------------------------------- header
from automation import buzz_hunter  # noqa: E402

alerts = buzz_hunter._alerts()
new_alerts = [x for x in alerts.values() if x["status"] == "new"]
routes = [r for a in ACCOUNTS for r in a.route(settings)]
rev = revenue.summary()
dry = C.is_dry_run(settings)

st.markdown("# ▌COMMAND CENTER")
st.caption(f"master: schema {M.get('schema_version')} / generated {M.get('generated_at', '')[:19]} / "
           f"research {M.get('research_date')} ・ mode: {'DRY RUN（外部へ送らない）' if dry else 'LIVE'}")
c = st.columns(6)
c[0].metric("ACCOUNTS", len(ACCOUNTS))
c[1].metric("ACTIVE MEDIA", sum(r.readable for r in routes))
c[2].metric("PUBLISHABLE", sum(r.can_publish for r in routes))
c[3].metric("TODAY ¥", f"{rev['today']:,.0f}")
c[4].metric("MONTH ¥", f"{rev['month']:,.0f}")
c[5].metric("BUZZ ALERTS", len(new_alerts))

t1, t2, t3, t4, t5 = st.tabs(["01 ACCOUNTS", "02 CRAWL & SYNC", "03 REVENUE & BUZZ", "04 GENERATE & PUBLISH", "05 SYSTEM"])

# ================================================================ 01 ACCOUNTS
with t1:
    st.subheader("認識中のアカウントと媒体")
    df = pd.DataFrame(L.flatten(M, settings))
    edited = st.data_editor(
        df, hide_index=True, use_container_width=True, key="acct_table",
        disabled=["account", "internal_key", "platform", "verification", "credentials", "route"],
        column_config={
            "status": st.column_config.SelectboxColumn(options=["active", "inactive", "unverified"]),
            "url": st.column_config.LinkColumn(),
            "write_enabled": st.column_config.CheckboxColumn("書込許可"),
            "credentials": st.column_config.CheckboxColumn("認証"),
        })
    if st.button("編集をマスターと設定に保存"):
        n = L.apply_table_edits(edited.to_dict("records"), note="dashboard table")
        for (_, o), (_, e) in zip(df.iterrows(), edited.iterrows()):
            if bool(o["write_enabled"]) != bool(e["write_enabled"]):
                L.set_write_enabled(e["internal_key"], e["platform"], bool(e["write_enabled"]))
                n += 1
        st.success(f"{n} 件を反映（旧版は config/history に退避）")
        st.cache_data.clear()
        st.rerun()

    st.markdown("### Astra の調査結果をインポート")
    ic1, ic2 = st.columns([2, 1])
    up = ic1.file_uploader("accounts_master.json", type="json", key="imp")
    pasted = ic1.text_area("または JSON を貼り付け", height=100)
    mode = ic2.radio("取り込み方", ["merge（アカウント単位で上書き）", "replace（丸ごと差し替え）"])
    raw = up.read() if up else (pasted.encode() if pasted.strip() else None)
    if raw:
        try:
            new = json.loads(raw)
            L.validate_master(new)
            diff = L.diff_masters(M, new)
            ic2.write(f"差分 {len(diff)} 件")
            if diff:
                st.dataframe(pd.DataFrame(diff), hide_index=True, use_container_width=True)
            if st.button("▶ ワンクリック反映", type="primary"):
                _, w = L.import_master(new, mode.split("（")[0], note="dashboard import")
                for x in w:
                    st.warning(x)
                st.cache_data.clear()
                st.success("反映した")
                st.rerun()
        except Exception as e:
            st.error(f"取り込めない: {e}")

    st.markdown("### アカウント詳細")
    for a in ACCOUNTS:
        with st.expander(f"{a.label}　{' / '.join(a.active_platforms())}"):
            p = a.persona
            st.markdown(f"**テーマ** {p.get('core_theme') or '-'}  \n**読者** {p.get('observed_target_audience') or '-'}  \n"
                        f"**導線** {a.funnel_summary() or '-'}")
            st.markdown("**誘導先**  \n" + "  \n".join(f"- {d['type']}: {d['url']}" for d in a.own_destinations()) or "-")
            rows = []
            for pl in a.active_platforms():
                for af in L.affiliate_pool(a, a.platform(pl)["url"], settings):
                    rows.append({"媒体": pl, "案件": af["program_name"], "単価": af["unit_price"], "使用可": af["usable"], "判定": af["reason"]})
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            for x in a.conflicts:
                st.caption("⚠ " + x)

# ================================================================ 02 CRAWL
with t2:
    st.subheader("実アカウントからトーン＆マナーを同期")
    key = st.selectbox("アカウント", list(LABELS), format_func=LABELS.get, key="crawl_acct")
    acct = L.get_account(key, M)
    urls = {}
    cols = st.columns(len(L.PLATFORM_ORDER))
    for i, pl in enumerate(L.PLATFORM_ORDER):
        v = acct.platform(pl)
        urls[pl] = cols[i].text_input(f"{pl}", value=v.get("url") or "", key=f"u_{key}_{pl}",
                                      help=f"status={v.get('status')}（空欄は取得しない）")
    use_llm = st.checkbox("Claude でトーン要約も作る", value=True)
    if st.button("▶ クロールして同期", type="primary"):
        from core.account_crawler import crawl

        with st.spinner("取得中…"):
            res = crawl(key, urls={k: u for k, u in urls.items() if u.strip()}, use_llm=use_llm)
        st.success(f"保存: data/calibration/{key}.json")
    cal = acct.calibration()
    if cal:
        st.caption(f"最終同期 {cal.get('fetched_at')}")
        st.markdown(" ".join(badge(f"{p}: {'OK ' + str(len(d.get('posts', []))) + '件' if d.get('ok') else 'NG'}",
                                   "ok" if d.get("ok") else "ng") for p, d in cal.get("platforms", {}).items()),
                    unsafe_allow_html=True)
        for p, d in cal.get("platforms", {}).items():
            if not d.get("ok"):
                st.caption(f"{p}: {d.get('error')}")
        cc1, cc2 = st.columns(2)
        cc1.markdown("**実測スタイル**")
        cc1.json(cal.get("style_metrics", {}), expanded=False)
        cc2.markdown("**トーン要約**")
        cc2.json(cal.get("tone_summary") or {"note": cal.get("tone_summary_error", "未生成")}, expanded=False)
        with st.expander("取得した投稿"):
            for p, d in cal.get("platforms", {}).items():
                for post in d.get("posts", [])[:8]:
                    st.markdown(f"`{p}` {post.get('title') or ''} {post.get('text', '')[:200]}  \n{post.get('url') or ''}")
    st.markdown("**Astra の調査メモ**")
    st.write(acct.persona.get("tone_and_style"))

# ================================================================ 03 REVENUE & BUZZ
with t3:
    left, right = st.columns([3, 2])
    with left:
        st.subheader("収益")
        df = revenue.load()
        if not df.empty:
            since = date.today() - timedelta(days=29)
            d30 = df[pd.to_datetime(df["date"]) >= pd.Timestamp(since)]
            daily = d30.groupby("date")["amount_jpy"].sum().reindex(
                [since + timedelta(days=i) for i in range(30)], fill_value=0)
            fig = go.Figure(go.Bar(x=list(daily.index), y=list(daily.values), marker_color=NEON,
                                   hovertemplate="%{x}<br>¥%{y:,.0f}<extra></extra>"))
            fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor=BG, plot_bgcolor=BG,
                              font=dict(color=MUTED), yaxis=dict(gridcolor="#1A2A1A", tickprefix="¥"), xaxis=dict(gridcolor=BG))
            st.plotly_chart(fig, use_container_width=True)
            s1, s2 = st.columns(2)
            s1.markdown("**本日・ソース別**")
            s1.dataframe(pd.Series(rev["by_source_today"], name="¥"), use_container_width=True)
            s2.markdown("**今月・アカウント別**")
            s2.dataframe(pd.Series({LABELS.get(k, k): v for k, v in rev["by_account_month"].items()}, name="¥"), use_container_width=True)
        else:
            st.info("収益データ未登録。各ASP・Amazon・noteの管理画面からCSVを落として取り込む。")
        with st.expander("CSV 取り込み / 手入力"):
            r1, r2 = st.columns(2)
            rk = r1.selectbox("アカウント", list(LABELS), format_func=LABELS.get, key="rev_acct")
            rs = r2.selectbox("ソース", revenue.SOURCES)
            f = st.file_uploader("レポートCSV（A8 / もしも / Amazon / note）", type="csv")
            if f and st.button("取り込む"):
                try:
                    n, mapping = revenue.import_csv(f.read(), rk, rs)
                    st.success(f"{n} 行追加 列対応={mapping}")
                except Exception as e:
                    st.error(str(e))
            m1, m2, m3 = st.columns(3)
            md = m1.date_input("日付", value=date.today())
            ma = m2.number_input("金額（円）", min_value=0, step=100)
            mp = m3.text_input("案件・商品")
            if st.button("手入力で追加") and ma > 0:
                revenue.add_manual(md, rk, rs, ma, mp)
                st.rerun()
    with right:
        st.subheader("バズ検知")
        live_reply = st.toggle("LIVE で送信（オフ = outbox へ保存のみ）", value=False, disabled=dry,
                               help="settings.yaml の mode.dry_run=false で有効化できる")
        if st.button("▶ 今すぐスキャン"):
            with st.spinner("X / Threads の指標を取得中…"):
                found = buzz_hunter.scan(settings)
            st.success(f"新規 {len(found)} 件")
            st.rerun()
        st.caption("監視対象: " + ", ".join(f"{l}/{p}{'' if C.has_creds(p, a.key, settings) else '(認証なし)'}"
                                         for a in ACCOUNTS for p in settings.get("buzz", {}).get("platforms", [])
                                         if a.is_active(p) for l in [a.label]))
        for al in sorted(alerts.values(), key=lambda x: x["detected_at"], reverse=True)[:20]:
            if al["status"] == "dismissed":
                continue
            sig = al["signal"]
            with st.container(border=True):
                st.markdown(f"{badge(al['status'], 'mid' if al['status'] == 'new' else 'ok')} **{al['account_label']}** / {al['platform']}"
                            f"　{sig['views']:,} views・{sig['views_per_hour']:,}/h・ER {sig['engagement_rate']:.1%}",
                            unsafe_allow_html=True)
                st.caption(al["post_text"][:140])
                if al.get("post_url"):
                    st.markdown(f"[投稿を開く]({al['post_url']})")
                if al["status"] == "new":
                    txt = st.text_area("追撃リプライ", al["reply_text"], key=f"rt_{al['id']}", height=90)
                    for i in al.get("issues", []):
                        st.caption(("⛔ " if i["level"] == "error" else "⚠ ") + i["msg"])
                    b1, b2 = st.columns(2)
                    if b1.button("⚡ 追撃リプライ実行", key=f"go_{al['id']}"):
                        st.write(buzz_hunter.execute(al["id"], live=live_reply, text=txt, force=True))
                    if b2.button("却下", key=f"ds_{al['id']}"):
                        buzz_hunter.dismiss(al["id"])
                        st.rerun()

# ================================================================ 04 GENERATE
with t4:
    st.subheader("一括生成 → プレビュー → 配信")
    gk = st.selectbox("アカウント", list(LABELS), format_func=LABELS.get, key="gen_acct")
    ga = L.get_account(gk, M)
    active = ga.active_platforms()
    g1, g2 = st.columns([2, 1])
    topic = g1.text_input("テーマ（読者の迷いベースで書くと精度が上がる）", key="topic")
    notes = g1.text_area("補足（切り口・入れたい情報・避けたい話題）", height=80)
    srcs = g1.text_input("参照してよい一次情報URL（カンマ区切り）")
    plats = g2.multiselect("生成する媒体", active, default=active)
    pool = {a["program_id"]: a for pl in plats for a in L.affiliate_pool(ga, ga.platform(pl)["url"], settings) if a["usable"]}
    affs = g2.multiselect("使う案件（空欄 = テーマに合うものをAIが選ぶ）", list(pool),
                          format_func=lambda x: f"{pool[x]['program_name'][:28]}（{pool[x]['unit_price']}）")
    if not pool:
        g2.caption("この媒体構成で登録媒体が一致する案件は無い → 自分の note / WP / LINE への誘導で組む")
    if st.button("▶ 一括生成", type="primary", disabled=not topic or not plats):
        from core.content_generator import generate

        with st.spinner("Claude が生成中…（数十秒〜数分）"):
            try:
                d = generate(gk, topic, plats, affs or None, notes, [s.strip() for s in srcs.split(",") if s.strip()])
                st.session_state["draft_id"] = d["id"]
                st.success(f"draft {d['id']}")
            except Exception as e:
                st.error(str(e))

    ds = drafts.list_all(gk)
    if ds:
        ids = [d["id"] for d in ds]
        cur = st.session_state.get("draft_id")
        sel = st.selectbox("下書き", ids, index=ids.index(cur) if cur in ids else 0,
                           format_func=lambda i: f"{i}　{next(d['topic'] for d in ds if d['id'] == i)[:40]}")
        d = drafts.get(sel)
        st.markdown(f"**読者の迷い** {d.get('reader_problem')}  \n**切り口** {d.get('angle')}")
        st.markdown(" ".join(badge(f"{p}: {s}", "ok" if s in ("approved", "published") else "mid")
                             for p, s in d["platform_status"].items()), unsafe_allow_html=True)
        for i in d.get("issues", []):
            (st.error if i["level"] == "error" else st.warning)(f"{i['platform']} {i['where']}: {i['msg']}")
        ptabs = st.tabs(list(d["outputs"].keys()))
        for tab, (p, body) in zip(ptabs, d["outputs"].items()):
            with tab:
                if p == "wordpress":
                    body["title"] = st.text_input("タイトル", body["title"], key=f"{sel}{p}t")
                    body["html"] = st.text_area("HTML", body["html"], height=320, key=f"{sel}{p}h")
                    with st.expander("プレビュー"):
                        st.html(body["html"])
                elif p == "note":
                    body["title"] = st.text_input("タイトル", body["title"], key=f"{sel}{p}t")
                    body["markdown"] = st.text_area("Markdown", body["markdown"], height=320, key=f"{sel}{p}m")
                    with st.expander("プレビュー"):
                        st.markdown(body["markdown"])
                elif p in ("x", "threads"):
                    from core.guards import x_weighted_len

                    for i, post in enumerate(body["posts"]):
                        n = x_weighted_len(post) if p == "x" else len(post)
                        body["posts"][i] = st.text_area(f"{i + 1}（{n}{'/280 weighted' if p == 'x' else '/500'}）", post,
                                                        key=f"{sel}{p}{i}", height=110)
                    body["buzz_followup"] = st.text_area("バズ時の追撃リプライ", body.get("buzz_followup", ""), key=f"{sel}{p}f")
                elif p == "instagram":
                    imgs = body.get("image_paths", [])
                    if imgs:
                        st.image([i for i in imgs if Path(i).exists()], width=180)
                    body["caption"] = st.text_area("キャプション", body["caption"], height=160, key=f"{sel}{p}c")
                    st.caption("ハッシュタグ: " + " ".join(body.get("hashtags", [])))
        a1, a2, a3, a4 = st.columns(4)
        if a1.button("編集を保存して再検査"):
            drafts.save(d)
            from core.content_generator import revalidate

            revalidate(sel)
            st.rerun()
        ap_targets = a2.multiselect("承認する媒体", list(d["outputs"]), default=list(d["outputs"]), key="appr")
        if a2.button("✔ 承認"):
            try:
                drafts.save(d)
                drafts.approve(sel, ap_targets)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        live = a3.toggle("LIVE 配信", value=False, disabled=dry, key="live_pub")
        if a3.button("🚀 各媒体へ配信" if live else "📦 配信プレビュー（outbox）"):
            from publishers.base import publish_draft

            st.json(publish_draft(sel, ap_targets, live=live))
        a4.download_button("JSON 書き出し", json.dumps(d, ensure_ascii=False, indent=2), file_name=f"{sel}.json")

# ================================================================ 05 SYSTEM
with t5:
    st.subheader("動作モード")
    nd = st.toggle("DRY RUN（外部へ一切書き込まない）", value=settings.get("mode", {}).get("dry_run", True))
    if nd != settings.get("mode", {}).get("dry_run", True):
        settings.setdefault("mode", {})["dry_run"] = nd
        C.save_settings(settings)
        st.rerun()
    st.markdown("**認証情報の有無**（値は表示しない。config/.env に `KEY__INTERNAL_KEY` 形式で置く）")
    st.dataframe(pd.DataFrame([{"account": a.label, "platform": p,
                                "keys": ", ".join(f"{k}__{C.env_suffix(a.key)}" for k in C.CRED_KEYS.get(p, [])),
                                "set": C.has_creds(p, a.key, settings)} for a in ACCOUNTS for p in a.active_platforms()]),
                 hide_index=True, use_container_width=True)
    st.markdown("**ローカル探索（フェーズ1）**")
    roots = st.text_input("探索ルート（カンマ区切り）", "~")
    if st.button("▶ 探索を実行"):
        from core import discovery

        with st.spinner("スキャン中…"):
            discovery.run([r.strip() for r in roots.split(",")])
    rep = C.read_json(C.DATA_DIR / "discovery" / "report.json")
    if rep:
        st.caption(f"{rep['generated_at']} / {rep['files_scanned']} files / browser {len(rep['browser_sources'])}")
        e1, e2 = st.columns(2)
        e1.markdown("マスターと一致")
        e1.dataframe(pd.DataFrame(rep["matched_to_master"])[["platform", "value", "account", "source_count"]]
                     if rep["matched_to_master"] else pd.DataFrame(), hide_index=True)
        e2.markdown("未登録の候補（人が確認してからマスターへ）")
        e2.dataframe(pd.DataFrame(rep["unmatched_candidates"])[["platform", "value", "source_count"]]
                     if rep["unmatched_candidates"] else pd.DataFrame(), hide_index=True)
    st.markdown("**automation_contract（Astra）**")
    st.json(M.get("automation_contract", {}), expanded=False)
