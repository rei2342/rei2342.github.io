import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from core.llm_client import LLMClient
from core.input_loader import load_case, generate_information_quality
from core.storage import save_case_output, load_case_output, update_case_output
import config

import analyzers.lp_analyzer as lp_analyzer
import analyzers.market_analyzer as market_analyzer
import analyzers.buying_trigger_analyzer as buying_trigger_analyzer
import analyzers.sns_fit_analyzer as sns_fit_analyzer
import analyzers.risk_analyzer as risk_analyzer
import analyzers.appeal_scorer as appeal_scorer
import analyzers.startup_fit_analyzer as startup_fit_analyzer
import analyzers.account_fit_analyzer as account_fit_analyzer
import analyzers.creator_fit_analyzer as creator_fit_analyzer
import generators.appeal_generator as appeal_generator
import generators.winning_summary_generator as winning_summary_generator
import generators.report_generator as report_generator
import generators.post_generator as post_generator


def _step(label: str) -> None:
    click.echo(f"\n  [{label}]", nl=False)


def _ok() -> None:
    click.echo(" ✓")


def _priority_label(priority: str) -> str:
    return {"High": "HIGH ★★★", "Medium": "MEDIUM ★★", "Low": "LOW ★"}.get(priority, priority)


def _print_summary(report: dict) -> None:
    meta = report["meta"]
    scores = report["scores"]
    case_score = report.get("case_score", {})
    winning = report.get("winning_summary", {})
    risk = report.get("risk_score", 0)
    ai_risk = report.get("ai_content_risk", {})
    triggers = report.get("buying_triggers", [])
    top_appeals = report.get("top_appeals", [])
    iq = report.get("information_quality", {})

    click.echo("\n" + "=" * 65)
    click.echo(f"  案件名   : {meta['case_name']}")
    click.echo(f"  分析日時 : {meta['analyzed_at'][:19]}")
    click.echo("=" * 65)

    # 開始優先度（最重要項目を先頭に）
    priority = winning.get("start_priority", "-")
    priority_reason = winning.get("start_priority_reason", "")
    click.echo(f"\n▶ 開始優先度     : {_priority_label(priority)}")
    if priority_reason:
        click.echo(f"  理由             : {priority_reason}")

    # case_score
    ct = case_score.get("total", "-")
    af = case_score.get("automation_fit", "-")
    click.echo(f"\n▶ case_score     : {ct}")
    click.echo(f"  automation_fit   : {af}  ← Claude Codeでの量産適性")
    click.echo(f"  profitability    : {case_score.get('profitability', '-')}")
    click.echo(f"  sns_scalability  : {case_score.get('sns_scalability', '-')}")
    click.echo(f"  content_repeat   : {case_score.get('content_repeatability', '-')}")
    click.echo(f"  conv_closeness   : {case_score.get('conversion_closeness', '-')}")
    click.echo(f"  risk_safety      : {case_score.get('risk_safety', '-')}")

    # 勝ち筋
    wa = winning.get("winning_angle", "")
    best_p = ", ".join(winning.get("best_platforms", []))
    best_a = ", ".join(winning.get("best_appeal_types", []))
    diff = winning.get("difficulty", "-")
    if wa:
        click.echo(f"\n▶ 勝ち筋         : {wa}")
    if best_p:
        click.echo(f"  最強媒体         : {best_p}")
    if best_a:
        click.echo(f"  最強訴求タイプ   : {best_a}")
    click.echo(f"  難易度           : {diff}")

    # TOP10訴求
    if top_appeals:
        click.echo(f"\n▶ TOP10訴求（スコア順）")
        for a in top_appeals[:10]:
            rep = a.get("content_repeatability", "?").upper()
            click.echo(
                f"  #{a['rank']:02d} [{a['appeal_score']:3d}] "
                f"[量産:{rep}] "
                f"[{a['appeal_type']}] {a['hook']}"
            )

    # 購買トリガー
    if triggers:
        click.echo(f"\n▶ 購買トリガー TOP3")
        for t in triggers[:3]:
            click.echo(f"  [{t.get('strength','?').upper()}] {t.get('trigger','')} — {t.get('reason','')}")

    # startup_fit
    sf = report.get("startup_fit", {})
    if sf:
        sf_score = sf.get("score", "-")
        sf_level = sf.get("level", "-")
        sf_bottleneck = sf.get("bottleneck", "")
        sf_action = sf.get("recommended_first_action", "")
        sf_breakdown = sf.get("breakdown", {})
        zcv = sf.get("zero_cost_validation_score", {}) or {}
        zcv_total = zcv.get("total", "-")
        zcv_bd = zcv.get("breakdown", {})
        click.echo(f"\n▶ startup_fit    : {sf_score} [{sf_level}]")
        if sf_breakdown:
            click.echo(f"  zero_follower    : {sf_breakdown.get('zero_follower_viable', '-')}")
            click.echo(f"  no_track_record  : {sf_breakdown.get('no_track_record_needed', '-')}")
            click.echo(f"  no_face          : {sf_breakdown.get('no_face_required', '-')}")
            click.echo(f"  no_physical      : {sf_breakdown.get('no_physical_product_needed', '-')}")
            click.echo(f"  free_trial       : {sf_breakdown.get('free_trial_available', '-')}")
            click.echo(f"  trust_free_conv  : {sf_breakdown.get('trust_free_conversion', '-')}")
        if zcv_bd:
            click.echo(f"\n▶ zero_cost_validation : {zcv_total}/120  ← 費用ゼロ検証スコア（新規参入最重要指標）")
            click.echo(f"  free_signup      : {zcv_bd.get('free_signup', '-')}/20")
            click.echo(f"  free_trial       : {zcv_bd.get('free_trial', '-')}/20")
            click.echo(f"  self_apply_ok    : {zcv_bd.get('self_application_ok', '-')}/20")
            click.echo(f"  no_purchase      : {zcv_bd.get('no_purchase_needed', '-')}/20")
            click.echo(f"  no_face          : {zcv_bd.get('no_face_needed', '-')}/20")
            click.echo(f"  no_track_record  : {zcv_bd.get('no_track_record_needed', '-')}/20")
        if sf_bottleneck:
            click.echo(f"\n  ボトルネック     : {sf_bottleneck}")
        if sf_action:
            click.echo(f"  最初のアクション : {sf_action}")

    # リスク
    click.echo(f"\n▶ リスク")
    click.echo(f"  risk_score      : {risk}")
    click.echo(f"  ai_content_risk : {ai_risk.get('score', '-')} ({ai_risk.get('risk_level', '-')})")

    # 情報不足
    if iq.get("missing"):
        click.echo(f"\n▶ 情報不足 (missing)")
        for m in iq["missing"]:
            click.echo(f"  ⚠ {m}")

    total_appeals = len(report.get("appeals", []))
    click.echo(f"\n  全訴求フック: {total_appeals}件（スコア順でJSONに保存済み）")
    click.echo("=" * 65)


@click.group()
def cli():
    """Affiliate Research Engine v1"""


def _run_single_analysis(input_path: str, llm: LLMClient, verbose: bool = True) -> tuple[dict, str]:
    """
    Run full analysis pipeline on one case JSON.
    Returns (report, output_path). Raises on error.
    verbose=False suppresses per-step output (batch mode).
    """
    def step(label: str):
        if verbose:
            _step(label)

    def ok():
        if verbose:
            _ok()

    case = load_case(input_path)
    iq = generate_information_quality(case)

    step("LP分析"); lp = lp_analyzer.analyze(case, llm); ok()
    step("市場分析"); market = market_analyzer.analyze(case, lp, llm); ok()
    step("購買トリガー分析"); triggers = buying_trigger_analyzer.analyze(case, lp, market, llm); ok()
    step("SNS適性・アルゴリズム分析"); sns_fit = sns_fit_analyzer.analyze(case, lp, market, triggers, llm); ok()
    step("リスク分析"); risk = risk_analyzer.analyze(case, lp, market, llm); ok()

    step("訴求フック生成（100件）")
    emotion = sns_fit.get("emotion_analysis", {"primary": [], "secondary": []})
    raw_appeals = appeal_generator.generate(case, triggers, emotion, sns_fit, risk, llm)
    ok()

    step("訴求スコアリング・TOP10抽出")
    scored_appeals, top_appeals = appeal_scorer.score_and_rank(
        raw_appeals, triggers, emotion, sns_fit, risk, llm
    )
    ok()

    step("勝ち筋サマリー・case_score生成")
    winning_data = winning_summary_generator.generate(
        case, lp, market, triggers, sns_fit, risk, top_appeals, llm
    )
    ok()

    step("startup_fit / CEF分析")
    sf_result = startup_fit_analyzer.analyze(case, lp, market, risk, triggers, llm)
    sf = sf_result.get("startup_fit", {})
    cef = sf_result.get("cef", {})
    ok()

    step("レポート統合・スコアリング")
    report = report_generator.build(
        case, iq, lp, market, triggers, sns_fit, risk,
        scored_appeals, top_appeals, winning_data, sf, cef, llm
    )
    ok()

    step("JSON保存")
    output_path = save_case_output(report, case.case_name)
    ok()

    return report, output_path


@cli.command("analyze-case")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True), help="入力JSONファイルのパス")
def analyze_case(input_path: str):
    """案件を分析してJSONレポートを生成します"""
    click.echo(f"\nAffiliate Research Engine — 案件分析開始")
    click.echo(f"入力ファイル: {input_path}")

    llm = LLMClient()
    try:
        _step("入力データ読み込み"); _ok()
        report, output_path = _run_single_analysis(input_path, llm, verbose=True)
        _print_summary(report)
        click.echo(f"\n出力ファイル: {output_path}\n")
    except ValueError as e:
        click.echo(f"\n[エラー] {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n[予期せぬエラー] {e}", err=True)
        raise


@cli.command("generate-posts")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True), help="分析済みJSONファイルのパス")
@click.option("--appeal-ids", required=True, help="カンマ区切りのappal_id一覧（top_appealsのappeal_idを使用）")
@click.option(
    "--platform",
    required=True,
    type=click.Choice(["x", "threads", "tiktok", "instagram", "note"]),
    help="投稿媒体",
)
def generate_posts(input_path: str, appeal_ids: str, platform: str):
    """選択済みの訴求から投稿案を生成します"""
    click.echo(f"\nAffiliate Research Engine — 投稿案生成")
    click.echo(f"ファイル: {input_path}")
    click.echo(f"媒体: {platform}")

    llm = LLMClient()

    ids = [aid.strip() for aid in appeal_ids.split(",") if aid.strip()]
    if not ids:
        click.echo("[エラー] appeal-ids が空です", err=True)
        sys.exit(1)

    click.echo(f"対象 appeal_id: {len(ids)}件")

    try:
        _step("ファイル読み込み")
        case_data = load_case_output(input_path)
        _ok()

        _step("投稿文生成")
        new_posts = post_generator.generate(case_data, ids, platform, llm)
        _ok()

        _step("ファイル更新")
        case_data.setdefault("generated_posts", []).extend(new_posts)
        update_case_output(input_path, case_data)
        _ok()

        click.echo(f"\n▶ 生成された投稿案 ({len(new_posts)}件)")
        for post in new_posts:
            click.echo(f"\n  [post_id] {post['post_id']}")
            click.echo(f"  [appeal_id] {post['appeal_id']}")
            preview = post["content"][:80].replace("\n", " ")
            click.echo(f"  [内容] {preview}...")

        click.echo(f"\n保存先: {input_path}\n")

    except ValueError as e:
        click.echo(f"\n[エラー] {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n[予期せぬエラー] {e}", err=True)
        raise


_SCREENSHOT_TO_CASE_SYSTEM = (
    "あなたはASPアフィリエイトプログラムのデータ抽出専門家です。"
    "スクリーンショットから読み取れる情報のみを抽出し、JSONのみを返してください。推測禁止。"
)


@cli.command("screenshot-to-case")
@click.argument("images", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--output-dir", default=None, type=click.Path(), help="保存先ディレクトリ（デフォルト: data/cases/）")
@click.option("--name", default=None, help="case_name を上書き指定")
def screenshot_to_case(images: tuple, output_dir: str | None, name: str | None):
    """スクリーンショットから CaseInput JSON を生成します"""
    base = Path(__file__).parent
    out_dir = Path(output_dir) if output_dir else base / "data" / "cases"
    out_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"\nscreenshot-to-case — 画像読み込み: {len(images)}枚")
    llm = LLMClient()

    from core.storage import load_prompt
    prompt = load_prompt("screenshot_to_case_prompt.md")

    try:
        result = llm.call_vision_json(prompt, list(images), _SCREENSHOT_TO_CASE_SYSTEM)
    except Exception as e:
        click.echo(f"[エラー] LLM呼び出し失敗: {e}", err=True)
        sys.exit(1)

    if name:
        result["case_name"] = name

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    case_name = result.get("case_name", "unknown_case")
    out_file = out_dir / f"{case_name}_{today}.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # バリデーション
    try:
        from core.input_loader import CaseInput
        CaseInput(**result)
        click.echo("  バリデーション: OK")
    except Exception as e:
        click.echo(f"  バリデーション: 警告 — {e}")

    # 不足・null レポート
    null_fields = [k for k, v in result.items() if v is None]
    empty_fields = [k for k, v in result.items() if v == [] or v == ""]
    click.echo(f"\n✓ 保存: {out_file}")
    click.echo(f"\n▶ 不足・null項目:")
    if null_fields:
        for f in null_fields:
            click.echo(f"  ⚠ {f}: null")
    else:
        click.echo("  なし")
    if empty_fields:
        click.echo(f"\n▶ 空配列・空文字項目:")
        for f in empty_fields:
            click.echo(f"  △ {f}: 空")
    click.echo()


@cli.command("case-check")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
def case_check(paths: tuple):
    """分析前に案件JSONの不足項目を確認します"""
    from core.input_loader import generate_information_quality

    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            click.echo(f"[エラー] {path}: {e}", err=True)
            continue

        from core.input_loader import CaseInput
        try:
            case = CaseInput(**data)
        except Exception as e:
            click.echo(f"[バリデーションエラー] {path}: {e}")
            continue

        iq = generate_information_quality(case)
        missing = iq.get("missing", [])
        confirmed = iq.get("confirmed", [])

        # 分析可否判定
        blockers = [m for m in missing if m in ("LP本文またはアフィリエイトURL",)]
        ready = "✓ 分析可能" if not blockers else "✗ 分析不可（LP情報が必要）"

        sep = "─" * 50
        click.echo(f"\n{sep}")
        click.echo(f"  {Path(path).name}")
        click.echo(f"  case_name : {case.case_name}")
        click.echo(f"  判定      : {ready}")
        click.echo(sep)
        click.echo(f"  確認済み ({len(confirmed)}件):")
        for c in confirmed:
            click.echo(f"    ✓ {c}")
        if missing:
            click.echo(f"  不足 ({len(missing)}件):")
            for m in missing:
                marker = "✗" if m in ("LP本文またはアフィリエイトURL",) else "⚠"
                click.echo(f"    {marker} {m}")
        click.echo()


@cli.command("set-account")
@click.option("--type", "account_type", required=True, help="アカウント種別（例: 20代女性）")
@click.option("--interests", required=True, help="興味関心（カンマ区切り）")
@click.option("--platform", "platform_focus", required=True, help="主要媒体（カンマ区切り）")
@click.option("--style", "content_style", default="体験談・比較・ライフハック系", help="コンテンツスタイル")
@click.option("--persona", default="", help="ペルソナ説明（任意）")
def set_account(account_type: str, interests: str, platform_focus: str, content_style: str, persona: str):
    """アカウントプロフィールを設定します（account_fit算出に使用）"""
    base = Path(__file__).parent
    profile = {
        "account_type": account_type,
        "interests": [i.strip() for i in interests.split(",")],
        "platform_focus": [p.strip() for p in platform_focus.split(",")],
        "content_style": content_style,
        "follower_stage": "ゼロフォロワー新規",
        "persona": persona,
    }
    out = base / "data" / "account_profile.json"
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"\n✓ アカウントプロフィール保存: {out}")
    click.echo(f"  account_type : {account_type}")
    click.echo(f"  interests    : {', '.join(profile['interests'])}")
    click.echo(f"  platforms    : {', '.join(profile['platform_focus'])}")
    click.echo(f"  style        : {content_style}")
    if persona:
        click.echo(f"  persona      : {persona}")
    click.echo(f"\n  次: python main.py account-fit-score  でスコアを算出してください\n")


@cli.command("account-fit-score")
@click.option("--cases-dir", default=None, type=click.Path(), help="分析済みJSONディレクトリ（デフォルト: outputs/cases/）")
@click.option("--force", is_flag=True, default=False, help="既存スコアを上書き")
def account_fit_score(cases_dir: str | None, force: bool):
    """分析済み案件にaccount_fitスコアを追加します"""
    base = Path(__file__).parent
    cases_path = Path(cases_dir) if cases_dir else base / "outputs" / "cases"
    profile_path = base / "data" / "account_profile.json"

    if not profile_path.exists():
        click.echo("[エラー] data/account_profile.json が見つかりません", err=True)
        click.echo("  先に: python main.py set-account --type ... --interests ... --platform ...", err=True)
        sys.exit(1)

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    click.echo(f"\naccount-fit-score  アカウント: {profile.get('account_type','不明')} / {', '.join(profile.get('interests',[]))}")

    json_files = sorted(cases_path.glob("*.json"))
    if not json_files:
        click.echo(f"[エラー] {cases_path} にJSONファイルが見つかりません", err=True)
        sys.exit(1)

    # 同一case_nameは最新のみ（compare-topと同じ重複排除）
    seen: dict[str, Path] = {}
    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("meta", {}).get("case_name") or data.get("basic_info", {}).get("case_name", f.stem)
            seen[name] = f
        except Exception:
            pass

    llm = LLMClient()
    sep = "=" * 65
    click.echo(sep)
    total, skipped, errors = 0, 0, []

    for name, f in seen.items():
        data = json.loads(f.read_text(encoding="utf-8"))
        existing = data.get("account_fit", {})
        if existing and not force:
            click.echo(f"  {name:<40} → スキップ（スコア済み: {existing.get('score','-')}）")
            skipped += 1
            continue

        click.echo(f"  {name:<40} → 採点中...", nl=False)
        try:
            af = account_fit_analyzer.analyze(data, llm)
            if af:
                data["account_fit"] = af
                # creator_priority_scoreを再計算
                cs_obj = data.get("case_score", {})
                sf = data.get("startup_fit", {}) or {}
                cef = data.get("cef", {}) or {}
                cf_existing = data.get("creator_fit", {}) or {}
                from generators.report_generator import _compute_creator_priority_score
                data["creator_priority_score"] = _compute_creator_priority_score(cs_obj, sf, cef, af, cf_existing)
                f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                click.echo(f"  ✓  account_fit:{af.get('score','-')}  creator_ps:{data['creator_priority_score']}")
                total += 1
            else:
                click.echo(f"  ✗  空レスポンス")
                errors.append(name)
        except Exception as e:
            click.echo(f"  ✗  エラー: {e}")
            errors.append(name)

    click.echo(sep)
    click.echo(f"  完了: {total}件  スキップ: {skipped}件  エラー: {len(errors)}件")
    if errors:
        for e in errors:
            click.echo(f"    エラー: {e}")
    click.echo(sep + "\n")
    if total > 0:
        click.echo("  → rank-cases または compare-top でaccount_fit込みランキングを確認できます\n")


@cli.command("set-creator-profile")
@click.option("--name", default="", help="発信者名")
@click.option("--expertise", required=True, help="専門分野・スキル（カンマ区切り）")
@click.option("--domains", required=True, help="一次情報保有領域（カンマ区切り）")
@click.option("--style", "content_style", default="実験ログ・データ公開・一次情報共有", help="コンテンツスタイル")
@click.option("--projects", default="", help="現在進行中のプロジェクト（カンマ区切り）")
@click.option("--topics", default="", help="継続発信可能なテーマ（カンマ区切り）")
@click.option("--weak", default="", help="一次情報が薄い領域（カンマ区切り）")
def set_creator_profile(
    name: str, expertise: str, domains: str, content_style: str,
    projects: str, topics: str, weak: str
):
    """発信者プロフィールを設定します（creator_fit算出に使用）"""
    base = Path(__file__).parent
    profile = {
        "name": name,
        "expertise": [e.strip() for e in expertise.split(",") if e.strip()],
        "first_hand_domains": [d.strip() for d in domains.split(",") if d.strip()],
        "proven_content_style": content_style,
        "current_projects": [p.strip() for p in projects.split(",") if p.strip()],
        "sustainable_topics": [t.strip() for t in topics.split(",") if t.strip()],
        "weak_domains": [w.strip() for w in weak.split(",") if w.strip()],
    }
    out = base / "data" / "creator_profile.json"
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"\n✓ 発信者プロフィール保存: {out}")
    click.echo(f"  name       : {name or '（未設定）'}")
    click.echo(f"  expertise  : {', '.join(profile['expertise'])}")
    click.echo(f"  domains    : {', '.join(profile['first_hand_domains'])}")
    click.echo(f"  style      : {content_style}")
    click.echo(f"\n  次: python main.py creator-fit-score  でスコアを算出してください\n")


@cli.command("creator-fit-score")
@click.option("--cases-dir", default=None, type=click.Path(), help="分析済みJSONディレクトリ（デフォルト: outputs/cases/）")
@click.option("--force", is_flag=True, default=False, help="既存スコアを上書き")
def creator_fit_score_cmd(cases_dir: str | None, force: bool):
    """分析済み案件にcreator_fitスコアを追加します"""
    base = Path(__file__).parent
    cases_path = Path(cases_dir) if cases_dir else base / "outputs" / "cases"
    profile_path = base / "data" / "creator_profile.json"

    if not profile_path.exists():
        click.echo("[エラー] data/creator_profile.json が見つかりません", err=True)
        click.echo("  先に: python main.py set-creator-profile --expertise ... --domains ...", err=True)
        sys.exit(1)

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    name = profile.get("name") or "発信者"
    click.echo(f"\ncreator-fit-score  発信者: {name} / {', '.join(profile.get('expertise', [])[:3])}")

    json_files = sorted(cases_path.glob("*.json"))
    if not json_files:
        click.echo(f"[エラー] {cases_path} にJSONファイルが見つかりません", err=True)
        sys.exit(1)

    # 同一case_nameは最新のみ
    seen: dict[str, Path] = {}
    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cname = data.get("meta", {}).get("case_name") or data.get("basic_info", {}).get("case_name", f.stem)
            seen[cname] = f
        except Exception:
            pass

    llm = LLMClient()
    sep = "=" * 65
    click.echo(sep)
    total, skipped, errors = 0, 0, []

    for cname, f in seen.items():
        data = json.loads(f.read_text(encoding="utf-8"))
        existing = data.get("creator_fit", {})
        if existing and not force:
            click.echo(f"  {cname:<40} → スキップ（スコア済み: {existing.get('score','-')}）")
            skipped += 1
            continue

        click.echo(f"  {cname:<40} → 採点中...", nl=False)
        try:
            cf = creator_fit_analyzer.analyze(data, llm)
            if cf:
                data["creator_fit"] = cf
                cs_obj = data.get("case_score", {})
                sf = data.get("startup_fit", {}) or {}
                cef = data.get("cef", {}) or {}
                af = data.get("account_fit", {}) or {}
                from generators.report_generator import _compute_creator_priority_score
                data["creator_priority_score"] = _compute_creator_priority_score(cs_obj, sf, cef, af, cf)
                f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                click.echo(f"  ✓  creator_fit:{cf.get('score','-')}  creator_ps:{data['creator_priority_score']}")
                total += 1
            else:
                click.echo(f"  ✗  空レスポンス")
                errors.append(cname)
        except Exception as e:
            click.echo(f"  ✗  エラー: {e}")
            errors.append(cname)

    click.echo(sep)
    click.echo(f"  完了: {total}件  スキップ: {skipped}件  エラー: {len(errors)}件")
    if errors:
        for e in errors:
            click.echo(f"    エラー: {e}")
    click.echo(sep + "\n")
    if total > 0:
        click.echo("  → rank-cases または compare-top でcreator_fit込みランキングを確認できます\n")


@cli.command("set-phase")
@click.argument("phase", type=click.Choice(["1", "2", "3", "4"]))
def set_phase(phase: str):
    """現在の成長フェーズを設定します（phase_score算出に使用）

    \b
    Phase 1: ゼロ〜初CV       （case 50% + account 40% + curiosity 10%）
    Phase 2: 初CV〜月1万円    （+authority解放）
    Phase 3: 月1万〜月10万円  （+moat解放）
    Phase 4: 月10万〜1人メディア（+leverage解放）
    """
    base = Path(__file__).parent
    phase_path = base / "data" / "growth_phase.json"
    data = json.loads(phase_path.read_text(encoding="utf-8")) if phase_path.exists() else {}
    data["current_phase"] = int(phase)
    phase_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    descriptions = {
        "1": "ゼロ〜初CV：case 50% + account 40% + curiosity 10%",
        "2": "初CV〜月1万円：+authority_fit 解放（30%）",
        "3": "月1万〜月10万円：+moat_fit 解放（25%）",
        "4": "月10万〜1人メディア：+leverage_fit 解放（35%）",
    }
    click.echo(f"\n✓ Phase {phase} に設定: {descriptions[phase]}")
    click.echo(f"  → rank-cases --phase {phase}  または  compare-top --phase {phase}  で確認できます\n")


@cli.command("cluster-themes")
@click.option("--cases-dir", default=None, type=click.Path(), help="分析済みJSONディレクトリ（デフォルト: outputs/cases/）")
@click.option("--phase", "phase_num", default="1", type=click.Choice(["1", "2", "3", "4"]), show_default=True, help="phase_scoreの計算フェーズ")
@click.option("--force", is_flag=True, default=False, help="既存クラスタを上書き")
def cluster_themes(cases_dir: str | None, phase_num: str, force: bool):
    """案件をテーマ別に自動クラスタリングします"""
    base = Path(__file__).parent
    cases_path = Path(cases_dir) if cases_dir else base / "outputs" / "cases"
    out_path = base / "outputs" / "theme_clusters.json"

    if out_path.exists() and not force:
        click.echo(f"\n  既存クラスタを読み込み: {out_path}")
        click.echo(f"  上書きする場合は --force を追加してください")
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        _display_theme_clusters(existing, int(phase_num))
        return

    # 全案件ロード（重複排除）
    json_files = sorted(cases_path.glob("*.json"))
    if not json_files:
        click.echo(f"[エラー] {cases_path} にJSONファイルが見つかりません", err=True)
        sys.exit(1)

    seen: dict[str, dict] = {}
    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cname = data.get("meta", {}).get("case_name") or data.get("basic_info", {}).get("case_name", f.stem)
            seen[cname] = data
        except Exception:
            pass

    entries = {cname: _extract_ranking_entry(data, "") for cname, data in seen.items()}
    phase_int = int(phase_num)
    for e in entries.values():
        e["phase_score"] = _compute_phase_score(e, phase_int)

    # クラスタリング用サマリー生成
    cases_summary_lines = []
    for cname, data in seen.items():
        e = entries[cname]
        bi = data.get("basic_info", {})
        ws = data.get("winning_summary", {})
        cf_bd = (data.get("creator_fit") or {}).get("breakdown", {}) if isinstance(data.get("creator_fit"), dict) else {}
        cases_summary_lines.append(
            f"- {cname}\n"
            f"  カテゴリ: {bi.get('category','')}\n"
            f"  勝ち筋: {ws.get('winning_angle','')[:60]}\n"
            f"  creator_fit: {e.get('creator_fit','-')}  curiosity:{cf_bd.get('curiosity_fit','-')}  leverage:{cf_bd.get('leverage_fit','-')}"
        )

    creator_profile = {}
    cp_path = base / "data" / "creator_profile.json"
    if cp_path.exists():
        creator_profile = json.loads(cp_path.read_text(encoding="utf-8"))

    template = (base / "prompts" / "theme_cluster_prompt.md").read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{creator_profile}", json.dumps(creator_profile, ensure_ascii=False, indent=2))
        .replace("{cases_summary}", "\n".join(cases_summary_lines))
    )

    click.echo(f"\ncluster-themes  {len(seen)}案件を分析中...")
    llm = LLMClient()
    result = llm.call_json(prompt, "あなたはコンテンツマーケティングの専門家です。JSONのみで回答してください。")
    raw_themes = result.get("themes", {})

    if not raw_themes:
        click.echo("[エラー] テーマクラスタが取得できませんでした", err=True)
        sys.exit(1)

    # 各テーマにスコア統計を付与
    themes_with_stats = {}
    for theme_name, theme_data in raw_themes.items():
        case_names = theme_data.get("cases", [])
        theme_entries = [entries[c] for c in case_names if c in entries]

        ph1_scores = [_compute_phase_score(e, 1) for e in theme_entries]
        ph4_scores = [_compute_phase_score(e, 4) for e in theme_entries]
        cf_scores  = [e.get("creator_fit") or 0 for e in theme_entries]
        af_scores  = [e.get("account_fit") or 0 for e in theme_entries]

        def avg(lst):
            valid = [x for x in lst if x is not None]
            return round(sum(valid) / len(valid)) if valid else None

        avg_ph4 = avg(ph4_scores)
        avg_cf  = avg(cf_scores)
        theme_size   = theme_data.get("theme_size", 50)
        asset_score  = round(avg_ph4 * avg_cf / 100) if (avg_ph4 is not None and avg_cf is not None) else None
        theme_value  = round(asset_score * theme_size / 100) if asset_score is not None else None

        themes_with_stats[theme_name] = {
            **theme_data,
            "stats": {
                "case_count": len(case_names),
                "avg_phase1": avg(ph1_scores),
                "avg_phase4": avg_ph4,
                "compound_score": (avg_ph4 - avg(ph1_scores)) if avg_ph4 is not None and avg(ph1_scores) is not None else None,
                "avg_creator_fit": avg_cf,
                "avg_account_fit": avg(af_scores),
                "theme_size": theme_size,
                "asset_score": asset_score,
                "theme_value": theme_value,
            }
        }

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(seen),
        "theme_count": len(themes_with_stats),
        "themes": themes_with_stats,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    _display_theme_clusters(output, phase_int)
    click.echo(f"\n  クラスタJSON: {out_path}\n")


def _display_theme_clusters(data: dict, phase_num: int = 1) -> None:
    themes = data.get("themes", {})
    sep = "=" * 65

    click.echo(f"\n{sep}")
    click.echo(f"  Theme Cluster  {data.get('total_cases','-')}案件 → {data.get('theme_count','-')}テーマ")
    click.echo(f"  theme_value  = asset_score × theme_size / 100")
    click.echo(f"  asset_score  = Phase4 × creator_fit / 100  （今の自分が積める資産量）")
    click.echo(f"  compound     = Phase4 - Phase1  （資産の成長方向）")
    click.echo(sep)

    # theme_value降順でソート（最終価値が高いテーマを優先）
    sorted_themes = sorted(
        themes.items(),
        key=lambda x: x[1].get("stats", {}).get("theme_value") or -999,
        reverse=True
    )

    for rank, (theme_name, theme_data) in enumerate(sorted_themes, start=1):
        stats = theme_data.get("stats", {})
        ph1          = stats.get("avg_phase1")
        ph4          = stats.get("avg_phase4")
        compound     = stats.get("compound_score")
        cf           = stats.get("avg_creator_fit")
        af           = stats.get("avg_account_fit")
        theme_size   = stats.get("theme_size")
        asset_score  = stats.get("asset_score")
        theme_value  = stats.get("theme_value")
        n            = stats.get("case_count", 0)

        # compound の矢印
        if compound is not None:
            if compound > 0:
                cmp_disp = f"+{compound} ↑"
            elif compound == 0:
                cmp_disp = f" {compound} →"
            else:
                cmp_disp = f"{compound} ↓"
        else:
            cmp_disp = "-"

        # theme_value バー
        if theme_value is not None:
            bar_len = min(theme_value // 5, 20)
            bar = "█" * bar_len
        else:
            bar = ""

        tv_label = "◎ 最重点" if (theme_value or 0) >= 50 else ("○ 注目" if (theme_value or 0) >= 25 else "△ 補助")
        cf_stars = "★★★" if (cf or 0) >= 70 else ("★★" if (cf or 0) >= 40 else "★")

        click.echo(f"\n  #{rank} {theme_name}  [{cf_stars}]  {n}案件  [{tv_label}]")

        # theme_value メイン表示
        tv_str   = f"{theme_value:>3}" if theme_value is not None else "  -"
        as_str   = f"{asset_score:>3}" if asset_score is not None else "  -"
        ts_str   = f"{theme_size:>3}" if theme_size is not None else "  -"
        click.echo(f"       theme_value  : {tv_str}  {bar}")
        click.echo(f"       asset_score  : {as_str}  ( Phase4={ph4 if ph4 is not None else '-':>3} × creator_fit={cf if cf is not None else '-':>3} )")
        click.echo(f"       theme_size   : {ts_str}  compound={cmp_disp}  ( Phase1={ph1 if ph1 is not None else '-':>3} → Phase4={ph4 if ph4 is not None else '-':>3} )")
        click.echo(f"       account_fit  : {af if af is not None else '-':>3}")

        desc = theme_data.get("description", "")
        if desc:
            click.echo(f"       {desc}")
        axis = theme_data.get("content_axis", "")
        if axis:
            click.echo(f"       コンテンツ軸: {axis[:55]}")
        note = theme_data.get("creator_fit_note", "")
        if note:
            click.echo(f"       発信者適合: {note[:50]}")

        click.echo(f"       ─────────────────────────────────────────────")
        for cname in theme_data.get("cases", []):
            click.echo(f"         {cname}")

    click.echo(f"\n{sep}")


@cli.command("batch-analyze")
@click.option("--cases-dir", default=None, type=click.Path(), help="入力JSONディレクトリ（デフォルト: data/cases/）")
@click.option("--force", is_flag=True, default=False, help="分析済みでも再分析する")
@click.option("--limit", "max_cases", default=None, type=int, help="最大分析件数")
def batch_analyze(cases_dir: str | None, force: bool, max_cases: int | None):
    """data/cases/*.json を一括分析します（分析済みはスキップ）"""
    base = Path(__file__).parent
    cases_path = Path(cases_dir) if cases_dir else base / "data" / "cases"
    outputs_path = base / "outputs" / "cases"

    input_files = sorted(cases_path.glob("*.json"))
    if not input_files:
        click.echo(f"[エラー] {cases_path} にJSONファイルが見つかりません", err=True)
        sys.exit(1)

    if max_cases:
        input_files = input_files[:max_cases]

    # 分析済みケースを判定（outputs/cases/{case_name}_*.json が存在するか）
    def _is_analyzed(case_name: str) -> bool:
        return bool(list(outputs_path.glob(f"{case_name}_*.json")))

    llm = LLMClient()
    results = []
    skipped = []
    errors = []

    sep = "=" * 65
    click.echo(f"\n{sep}")
    click.echo(f"  batch-analyze  対象: {len(input_files)}件  force={force}")
    click.echo(sep)

    for i, f in enumerate(input_files, start=1):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            case_name = raw.get("case_name", f.stem)
        except Exception:
            case_name = f.stem

        if not force and _is_analyzed(case_name):
            click.echo(f"  [{i:02d}/{len(input_files)}] {case_name}  → スキップ（分析済み）")
            skipped.append(case_name)
            continue

        click.echo(f"  [{i:02d}/{len(input_files)}] {case_name}  → 分析中...", nl=False)
        try:
            report, out_path = _run_single_analysis(str(f), llm, verbose=False)
            cs_obj = report.get("case_score", {})
            sf_obj = report.get("startup_fit", {}) or {}
            zcv = (sf_obj.get("zero_cost_validation_score") or {}).get("total", "-")
            cef_obj = report.get("cef", {}) or {}
            cef_score = cef_obj.get("score", "-")
            creator_ps = report.get("creator_priority_score")
            click.echo(
                f"  ✓  "
                f"case_score:{cs_obj.get('total','-')}  "
                f"automation:{cs_obj.get('automation_fit','-')}  "
                f"startup_fit:{sf_obj.get('score','-')}  "
                f"zero_cost:{zcv}/120  "
                f"cef:{cef_score}  "
                f"creator_ps:{creator_ps if creator_ps is not None else '-'}"
            )
            results.append({"name": case_name, "path": str(out_path), "report": report})
        except Exception as e:
            click.echo(f"  ✗  エラー: {e}")
            errors.append((case_name, str(e)))

    click.echo(f"\n{sep}")
    click.echo(f"  完了: {len(results)}件  スキップ: {len(skipped)}件  エラー: {len(errors)}件")
    if errors:
        click.echo("  エラー詳細:")
        for name, msg in errors:
            click.echo(f"    {name}: {msg}")
    click.echo(sep + "\n")

    if results:
        click.echo("  → rank-cases で横並び比較できます: python main.py rank-cases")


@cli.command("compare-top")
@click.option("--cases-dir", default=None, type=click.Path(), help="分析済みJSONディレクトリ（デフォルト: outputs/cases/）")
@click.option("--top", "top_n", default=10, show_default=True, help="表示件数")
@click.option("--phase", "phase_num", default=None, type=click.Choice(["1", "2", "3", "4"]), help="フェーズ別スコアで表示（未指定=creator_ps）")
def compare_top(cases_dir: str | None, top_n: int, phase_num: str | None):
    """TOP N 案件をスコア比較表で表示します"""
    base = Path(__file__).parent
    cases_path = Path(cases_dir) if cases_dir else base / "outputs" / "cases"

    json_files = sorted(cases_path.glob("*.json"))
    if not json_files:
        click.echo(f"[エラー] {cases_path} にJSONファイルが見つかりません", err=True)
        sys.exit(1)

    entries = []
    seen_names: set[str] = set()
    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            e = _extract_ranking_entry(data, str(f))
            # 同一case_nameは最新ファイルのみ（ファイル名ソートで後優先）
            if e["product_name"] in seen_names:
                entries = [x for x in entries if x["product_name"] != e["product_name"]]
            seen_names.add(e["product_name"])
            entries.append(e)
        except Exception:
            pass

    # Phase score computation
    if phase_num:
        phase_int = int(phase_num)
        for e in entries:
            e["phase_score"] = _compute_phase_score(e, phase_int)
        sort_key = lambda x: x.get("phase_score") or 0
        sort_label = f"phase_score（Phase {phase_num}）"
    else:
        sort_key = lambda x: x["priority_score"]
        sort_label = "priority_score"

    entries.sort(key=sort_key, reverse=True)
    top = entries[:top_n]

    W = 22  # column width
    sep = "=" * (W * min(len(top), 5) + 20)

    click.echo(f"\n{sep}")
    click.echo(f"  compare-top  TOP{top_n}案件比較（{sort_label}順）  ※creator_psは7軸総合スコア")
    click.echo(sep)

    ROWS = [
        ("priority_score",  lambda e: str(e["priority_score"]) + ("※" if e["priority_score_note"] else "")),
        ("zero_cost/120",   lambda e: f"{e['zero_cost_total']}/120" if e["zero_cost_total"] is not None else "-"),
        ("startup_fit",     lambda e: f"{e['startup_fit']} [{e['startup_fit_level'] or '?'}]" if e["startup_fit"] is not None else "未分析"),
        ("case_score",      lambda e: str(e["case_score"])),
        ("automation_fit",  lambda e: str(e["automation_fit"])),
        ("start_priority",  lambda e: e["start_priority"] or "-"),
        ("EPC",             lambda e: str(e["epc"]) if e["epc"] is not None else "-"),
        ("approval_rate",   lambda e: f"{e['approval_rate']}%" if e["approval_rate"] is not None else "-"),
        ("CEF/100",          lambda e: f"{e['cef_score']}/100" if e.get("cef_score") is not None else "未分析"),
        ("account_fit",      lambda e: f"{e['account_fit']}/100" if e.get("account_fit") is not None else "未設定"),
        ("creator_fit",      lambda e: f"{e['creator_fit']}/100" if e.get("creator_fit") is not None else "未設定"),
        ("creator_ps",       lambda e: str(e["creator_priority_score"]) if e.get("creator_priority_score") is not None else "未分析"),
        ("phase_score",      lambda e: str(e["phase_score"]) if e.get("phase_score") is not None else "-"),
        ("category",        lambda e: (e["category"] or "-")[:18]),
    ]

    # Print in groups of 5 columns
    chunk = 5
    for col_start in range(0, len(top), chunk):
        cols = top[col_start:col_start + chunk]

        # Header
        header = f"  {'指標':<18}" + "".join(f"  {c['product_name'][:W-2]:<{W-2}}" for c in cols)
        click.echo(f"\n{header}")
        click.echo("  " + "─" * (18 + (W) * len(cols)))

        # Rows
        for label, fn in ROWS:
            row = f"  {label:<18}" + "".join(f"  {fn(c):<{W-2}}" for c in cols)
            click.echo(row)

        click.echo()

    # zcv breakdown table
    has_zcv = [e for e in top if e.get("zero_cost_breakdown")]
    if has_zcv:
        click.echo(f"{'─' * 60}")
        click.echo("  【zero_cost 内訳】\n")
        ZCV_ROWS = [
            ("free_signup /20",   "free_signup"),
            ("free_trial /20",    "free_trial"),
            ("self_apply /20",    "self_application_ok"),
            ("no_purchase /20",   "no_purchase_needed"),
            ("no_face /20",       "no_face_needed"),
            ("no_record /20",     "no_track_record_needed"),
        ]
        for col_start in range(0, len(has_zcv), chunk):
            cols = has_zcv[col_start:col_start + chunk]
            header = f"  {'軸':<18}" + "".join(f"  {c['product_name'][:W-2]:<{W-2}}" for c in cols)
            click.echo(header)
            click.echo("  " + "─" * (18 + W * len(cols)))
            for label, key in ZCV_ROWS:
                row = f"  {label:<18}" + "".join(
                    f"  {c['zero_cost_breakdown'].get(key, '-'):<{W-2}}" for c in cols
                )
                click.echo(row)
            click.echo()

    # cef breakdown table
    has_cef = [e for e in top if e.get("cef_breakdown")]
    if has_cef:
        click.echo(f"{'─' * 60}")
        click.echo("  【CEF 内訳】\n")
        CEF_ROWS = [
            ("量産性 /20",      "content_producibility"),
            ("市場規模 /20",    "market_size"),
            ("継続性 /20",      "continuity"),
            ("横展開性 /20",    "cross_expansion"),
            ("動画適性 /20",    "short_video_fit"),
            ("資産化 /20",      "account_asset_potential"),
        ]
        for col_start in range(0, len(has_cef), chunk):
            cols = has_cef[col_start:col_start + chunk]
            header = f"  {'軸':<18}" + "".join(f"  {c['product_name'][:W-2]:<{W-2}}" for c in cols)
            click.echo(header)
            click.echo("  " + "─" * (18 + W * len(cols)))
            for label, key in CEF_ROWS:
                row = f"  {label:<18}" + "".join(
                    f"  {c['cef_breakdown'].get(key, '-'):<{W-2}}" for c in cols
                )
                click.echo(row)
            click.echo()

    # account_fit breakdown table
    has_af = [e for e in top if e.get("account_fit_breakdown")]
    if has_af:
        click.echo(f"{'─' * 60}")
        click.echo("  【account_fit 内訳】\n")
        AF_ROWS = [
            ("視聴者一致 /100",    "audience_match"),
            ("テーマ親和 /100",    "interest_alignment"),
            ("スタイル適合 /100",  "content_style_fit"),
            ("信頼性適合 /100",    "credibility_fit"),
            ("フォロワー相乗 /100", "follower_growth_synergy"),
            ("購買心理一致 /100",  "purchase_psychology_match"),
        ]
        for col_start in range(0, len(has_af), chunk):
            cols = has_af[col_start:col_start + chunk]
            header = f"  {'軸':<20}" + "".join(f"  {c['product_name'][:W-2]:<{W-2}}" for c in cols)
            click.echo(header)
            click.echo("  " + "─" * (20 + W * len(cols)))
            for label, key in AF_ROWS:
                row = f"  {label:<20}" + "".join(
                    f"  {c['account_fit_breakdown'].get(key, '-'):<{W-2}}" for c in cols
                )
                click.echo(row)
            click.echo()

    # creator_fit breakdown table
    has_cf = [e for e in top if e.get("creator_fit_breakdown")]
    if has_cf:
        click.echo(f"{'─' * 60}")
        click.echo("  【creator_fit 内訳】\n")
        CF_ROWS = [
            ("一次情報 /100",    "first_hand_info"),
            ("専門性 /100",      "expertise_alignment"),
            ("継続ネタ量 /100",   "content_sustainability"),
            ("差別化力 /100",    "differentiation_potential"),
            ("体験語り /100",    "authentic_voice"),
            ("継続性 /100",      "longevity"),
            ("好奇心 /100",      "curiosity_fit"),
            ("権威積上 /100",    "authority_fit"),
            ("参入障壁 /100",    "moat_fit"),
            ("複利率 /100",      "leverage_fit"),
        ]
        for col_start in range(0, len(has_cf), chunk):
            cols = has_cf[col_start:col_start + chunk]
            header = f"  {'軸':<20}" + "".join(f"  {c['product_name'][:W-2]:<{W-2}}" for c in cols)
            click.echo(header)
            click.echo("  " + "─" * (20 + W * len(cols)))
            for label, key in CF_ROWS:
                row = f"  {label:<20}" + "".join(
                    f"  {c['creator_fit_breakdown'].get(key, '-'):<{W-2}}" for c in cols
                )
                click.echo(row)
            click.echo()

    click.echo(sep + "\n")


def _load_growth_phase() -> dict:
    p = Path(__file__).parent / "data" / "growth_phase.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _compute_phase_score(entry: dict, phase: int) -> int | None:
    phase_data = _load_growth_phase()
    weights = phase_data.get("phase_weights", {}).get(str(phase))
    if not weights:
        return None

    cf_bd = entry.get("creator_fit_breakdown") or {}
    scores = {
        "case_score":    entry.get("case_score") or 0,
        "account_fit":   entry.get("account_fit") or 0,
        "curiosity_fit": cf_bd.get("curiosity_fit") or 0,
        "authority_fit": cf_bd.get("authority_fit") or 0,
        "moat_fit":      cf_bd.get("moat_fit") or 0,
        "leverage_fit":  cf_bd.get("leverage_fit") or 0,
    }

    total = sum(scores.get(k, 0) * w for k, w in weights.items())
    return round(total)


def _extract_ranking_entry(data: dict, path: str) -> dict:
    meta = data.get("meta", {})
    basic = data.get("basic_info", {})
    case_score_obj = data.get("case_score", {})
    winning = data.get("winning_summary", {})
    sf = data.get("startup_fit", {})

    case_score = int(case_score_obj.get("total") or 0)
    automation_fit = int(case_score_obj.get("automation_fit") or 0)
    startup_fit_score = int(sf.get("score") or 0) if sf else None
    startup_fit_level = sf.get("level") if sf else None

    zcv = (sf.get("zero_cost_validation_score") or {}) if sf else {}
    zero_cost_total = int(zcv.get("total") or 0) if zcv else None
    zero_cost_breakdown = zcv.get("breakdown", {}) if zcv else {}

    cef = data.get("cef", {}) or {}
    cef_score = int(cef.get("score") or 0) if cef else None
    cef_total = int(cef.get("total") or 0) if cef else None
    cef_breakdown = cef.get("breakdown", {}) if cef else {}

    af = data.get("account_fit", {}) or {}
    account_fit_score = int(af.get("score") or 0) if af else None
    account_fit_breakdown = af.get("breakdown", {}) if af else {}
    account_fit_verdict = af.get("verdict", "") if af else ""
    account_fit_angle = af.get("recommended_angle", "") if af else ""

    cf = data.get("creator_fit", {}) or {}
    creator_fit_score = int(cf.get("score") or 0) if cf else None
    creator_fit_breakdown = cf.get("breakdown", {}) if cf else {}
    creator_fit_verdict = cf.get("verdict", "") if cf else ""
    creator_fit_angle = cf.get("content_angle", "") if cf else ""
    creator_fit_risk = cf.get("risk_note", "") if cf else ""

    creator_ps = data.get("creator_priority_score")
    if creator_ps is None and startup_fit_score is not None and zero_cost_total is not None and cef_score is not None:
        zero_cost_norm = round(zero_cost_total / 1.2)
        creator_ps = round(
            case_score * 0.2
            + automation_fit * 0.2
            + startup_fit_score * 0.2
            + zero_cost_norm * 0.2
            + cef_score * 0.2
        )

    if startup_fit_score is not None:
        priority_score = round(
            case_score * 0.3 + automation_fit * 0.3 + startup_fit_score * 0.4
        )
    else:
        # startup_fit未分析の場合は case_score + automation_fit の平均で代替
        priority_score = round((case_score + automation_fit) / 2)

    return {
        "file": Path(path).name,
        "case_id": meta.get("case_id"),
        "analyzed_at": meta.get("analyzed_at", "")[:19],
        "product_name": basic.get("case_name", meta.get("case_name", "unknown")),
        "category": basic.get("category", ""),
        "case_score": case_score,
        "automation_fit": automation_fit,
        "startup_fit": startup_fit_score,
        "startup_fit_level": startup_fit_level,
        "zero_cost_total": zero_cost_total,
        "zero_cost_breakdown": zero_cost_breakdown,
        "cef_score": cef_score,
        "cef_total": cef_total,
        "cef_breakdown": cef_breakdown,
        "account_fit": account_fit_score,
        "account_fit_breakdown": account_fit_breakdown,
        "account_fit_verdict": account_fit_verdict,
        "account_fit_angle": account_fit_angle,
        "creator_fit": creator_fit_score,
        "creator_fit_breakdown": creator_fit_breakdown,
        "creator_fit_verdict": creator_fit_verdict,
        "creator_fit_angle": creator_fit_angle,
        "creator_fit_risk": creator_fit_risk,
        "creator_priority_score": creator_ps,
        "start_priority": winning.get("start_priority"),
        "winning_angle": winning.get("winning_angle", ""),
        "epc": basic.get("epc"),
        "approval_rate": basic.get("approval_rate"),
        "priority_score": priority_score,
        "priority_score_note": None if startup_fit_score is not None else "startup_fit未分析のため概算",
    }


def _level_label(level: str | None) -> str:
    return {"High": "High ★★★", "Medium": "Medium ★★", "Low": "Low ★"}.get(level or "", level or "-")


@cli.command("rank-cases")
@click.option(
    "--cases-dir",
    default=None,
    type=click.Path(),
    help="分析済みJSONが入ったディレクトリ（デフォルト: outputs/cases/）",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="ランキングJSONの保存先（デフォルト: outputs/rankings/）",
)
@click.option("--phase", "phase_num", default=None, type=click.Choice(["1", "2", "3", "4"]), help="フェーズ別スコアで表示")
def rank_cases(cases_dir: str | None, output_dir: str | None, phase_num: str | None):
    """分析済みJSON一覧からpriority_score順にランキングを表示・保存します"""
    base = Path(__file__).parent
    cases_path = Path(cases_dir) if cases_dir else base / "outputs" / "cases"
    rankings_path = Path(output_dir) if output_dir else base / "outputs" / "rankings"
    rankings_path.mkdir(parents=True, exist_ok=True)

    json_files = sorted(cases_path.glob("*.json"))
    if not json_files:
        click.echo(f"[エラー] {cases_path} にJSONファイルが見つかりません", err=True)
        sys.exit(1)

    entries = []
    errors = []
    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            entries.append(_extract_ranking_entry(data, str(f)))
        except Exception as e:
            errors.append((f.name, str(e)))

    if phase_num:
        phase_int = int(phase_num)
        for e in entries:
            e["phase_score"] = _compute_phase_score(e, phase_int)
        entries.sort(key=lambda x: x.get("phase_score") or 0, reverse=True)
    else:
        entries.sort(key=lambda x: x["priority_score"], reverse=True)

    # ターミナル表示
    phase_data = _load_growth_phase()
    phase_descs = phase_data.get("phase_descriptions", {})
    click.echo(f"\n{'=' * 65}")
    click.echo(f"  案件ランキング  ({len(entries)}件)")
    if phase_num:
        click.echo(f"  ソート: phase_score（Phase {phase_num}）")
        click.echo(f"  {phase_descs.get(phase_num, '')}")
    else:
        click.echo(f"  priority_score     = case_score×0.3 + automation_fit×0.3 + startup_fit×0.4")
        click.echo(f"  creator_priority   = (case_score + automation_fit + startup_fit + zero_cost_norm + CEF + account_fit + creator_fit) / 7")
    click.echo(f"{'=' * 65}")

    for rank, e in enumerate(entries, start=1):
        sf_disp = str(e["startup_fit"]) if e["startup_fit"] is not None else "未分析"
        note = f"  ※{e['priority_score_note']}" if e["priority_score_note"] else ""
        zcv = e.get("zero_cost_total")
        zcv_bd = e.get("zero_cost_breakdown") or {}

        click.echo(f"\n  #{rank:02d} {e['product_name']}")
        if phase_num and e.get("phase_score") is not None:
            click.echo(f"       phase_score    : {e['phase_score']}  （Phase {phase_num}）")
        click.echo(f"       priority_score : {e['priority_score']}{note}")

        # zero_cost_validation_score を最重要指標として最上部に表示
        if zcv is not None:
            bar_filled = round(zcv / 120 * 20)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            click.echo(f"       zero_cost      : {zcv:>3}/120  [{bar}]  ← 費用ゼロ検証スコア")
            if zcv_bd:
                parts = []
                for k, label in [
                    ("free_signup", "登録"),
                    ("free_trial", "体験"),
                    ("self_application_ok", "本人申込"),
                    ("no_purchase_needed", "購入不要"),
                    ("no_face_needed", "顔出し不要"),
                    ("no_track_record_needed", "実績不要"),
                ]:
                    v = zcv_bd.get(k, "-")
                    parts.append(f"{label}:{v}")
                click.echo(f"                     {' / '.join(parts)}")
        else:
            click.echo(f"       zero_cost      : 未分析")

        click.echo(f"       startup_fit    : {sf_disp}", nl=False)
        if e["startup_fit_level"]:
            click.echo(f"  [{_level_label(e['startup_fit_level'])}]")
        else:
            click.echo()
        click.echo(f"       case_score     : {e['case_score']}  automation_fit: {e['automation_fit']}")
        cef_s = e.get("cef_score")
        cef_bd = e.get("cef_breakdown") or {}
        if cef_s is not None:
            cef_total = e.get("cef_total", 0)
            bar_filled = round(cef_s / 100 * 20)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            click.echo(f"       CEF            : {cef_s:>3}/100  [{bar}]  ← コンテンツエンジン適性")
            if cef_bd:
                parts = []
                for k, label in [
                    ("content_producibility", "量産"),
                    ("market_size", "市場"),
                    ("continuity", "継続"),
                    ("cross_expansion", "横展開"),
                    ("short_video_fit", "動画"),
                    ("account_asset_potential", "資産化"),
                ]:
                    parts.append(f"{label}:{cef_bd.get(k, '-')}")
                click.echo(f"                     {' / '.join(parts)}")
        else:
            click.echo(f"       CEF            : 未分析")

        af_s = e.get("account_fit")
        af_bd = e.get("account_fit_breakdown") or {}
        if af_s is not None:
            bar_filled = round(af_s / 100 * 20)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            click.echo(f"       account_fit    : {af_s:>3}/100  [{bar}]  ← アカウント適合スコア")
            af_verdict = e.get("account_fit_verdict", "")
            if af_verdict:
                click.echo(f"                     {af_verdict[:60]}")
        else:
            click.echo(f"       account_fit    : 未設定（set-account → account-fit-score で算出）")

        cf_s = e.get("creator_fit")
        if cf_s is not None:
            bar_filled = round(cf_s / 100 * 20)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            click.echo(f"       creator_fit    : {cf_s:>3}/100  [{bar}]  ← 発信者適合スコア")
            cf_verdict = e.get("creator_fit_verdict", "")
            if cf_verdict:
                click.echo(f"                     {cf_verdict[:60]}")
            cf_risk = e.get("creator_fit_risk", "")
            if cf_risk:
                click.echo(f"                     ⚠ {cf_risk[:55]}")
        else:
            click.echo(f"       creator_fit    : 未設定（set-creator-profile → creator-fit-score で算出）")

        creator_ps = e.get("creator_priority_score")
        if creator_ps is not None:
            click.echo(f"       creator_ps     : {creator_ps}  ← 7軸総合スコア")
        if e["start_priority"]:
            click.echo(f"       start_priority : {_priority_label(e['start_priority'])}")
        if e["epc"] is not None:
            click.echo(f"       EPC            : {e['epc']}", nl=False)
        if e["approval_rate"] is not None:
            click.echo(f"  approval_rate: {e['approval_rate']}%")
        elif e["epc"] is not None:
            click.echo()
        if e["winning_angle"]:
            wa = e["winning_angle"][:60] + ("…" if len(e["winning_angle"]) > 60 else "")
            click.echo(f"       winning_angle  : {wa}")
        if e["category"]:
            click.echo(f"       category       : {e['category']}")

    if errors:
        click.echo(f"\n⚠ 読み込みエラー ({len(errors)}件):")
        for fname, msg in errors:
            click.echo(f"  {fname}: {msg}")

    click.echo(f"\n{'=' * 65}")

    # JSON保存
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_file = rankings_path / f"ranking_{today}.json"
    ranking_doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": config.SCHEMA_VERSION,
        "total": len(entries),
        "formula": "priority_score = case_score × 0.3 + automation_fit × 0.3 + startup_fit × 0.4",
        "rankings": [{"rank": i + 1, **e} for i, e in enumerate(entries)],
    }
    out_file.write_text(
        json.dumps(ranking_doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    click.echo(f"  ランキングJSON: {out_file}\n")


_EMPTY_VALIDATION = {
    "tested": False,
    "status": "pending",
    "posts_created": 0,
    "impressions": 0,
    "engagements": 0,
    "profile_visits": 0,
    "link_clicks": 0,
    "conversions": 0,
    "revenue": 0,
    "memo": "",
}

_VALID_STATUSES = ("pending", "testing", "done", "paused")


def _fill_validation(v: dict) -> dict:
    """既存JSONの旧フォーマット互換 + 欠損フィールド補完。"""
    filled = dict(_EMPTY_VALIDATION)
    filled.update(v)
    # 旧フィールド clicks → link_clicks に移行
    if "clicks" in filled and "link_clicks" not in v:
        filled["link_clicks"] = filled.pop("clicks")
    filled.pop("clicks", None)
    return filled


def _safe_rate(numerator: int, denominator: int, pct: bool = True) -> str:
    if not denominator:
        return "-%"
    val = numerator / denominator
    return f"{val * 100:.2f}%" if pct else f"{val:.4f}"


@cli.command("set-validation")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="更新対象の案件JSONファイル")
@click.option("--tested/--not-tested", default=None, help="検証済みフラグ")
@click.option("--status", type=click.Choice(_VALID_STATUSES), default=None, help="ステータス")
@click.option("--posts", "posts_created", type=int, default=None, help="投稿作成数")
@click.option("--impressions", type=int, default=None, help="インプレッション数")
@click.option("--engagements", type=int, default=None, help="エンゲージメント数（いいね+RT+返信等）")
@click.option("--profile-visits", type=int, default=None, help="プロフィール遷移数")
@click.option("--link-clicks", type=int, default=None, help="リンククリック数")
@click.option("--conversions", type=int, default=None, help="CV数")
@click.option("--revenue", type=int, default=None, help="売上（円）")
@click.option("--memo", default=None, help="メモ")
def set_validation(
    file_path: str,
    tested: bool | None,
    status: str | None,
    posts_created: int | None,
    impressions: int | None,
    engagements: int | None,
    profile_visits: int | None,
    link_clicks: int | None,
    conversions: int | None,
    revenue: int | None,
    memo: str | None,
):
    """案件JSONのvalidationフィールドを更新します"""
    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    v = _fill_validation(data.get("validation") or {})

    if tested is not None:
        v["tested"] = tested
    if status is not None:
        v["status"] = status
    if posts_created is not None:
        v["posts_created"] = posts_created
    if impressions is not None:
        v["impressions"] = impressions
    if engagements is not None:
        v["engagements"] = engagements
    if profile_visits is not None:
        v["profile_visits"] = profile_visits
    if link_clicks is not None:
        v["link_clicks"] = link_clicks
    if conversions is not None:
        v["conversions"] = conversions
    if revenue is not None:
        v["revenue"] = revenue
    if memo is not None:
        v["memo"] = memo

    data["validation"] = v
    Path(file_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    name = data.get("meta", {}).get("case_name", Path(file_path).stem)
    ctr = _safe_rate(v["link_clicks"], v["impressions"])
    eng_rate = _safe_rate(v["engagements"], v["impressions"])
    prof_rate = _safe_rate(v["profile_visits"], v["impressions"])
    cvr = _safe_rate(v["conversions"], v["link_clicks"])

    click.echo(f"\n✓ {name} — validation 更新済み")
    click.echo(f"  tested         : {v['tested']}  status: {v['status']}")
    click.echo(f"  posts_created  : {v['posts_created']}")
    click.echo(f"  impressions    : {v['impressions']:,}")
    click.echo(f"  engagements    : {v['engagements']:,}  ({eng_rate})")
    click.echo(f"  profile_visits : {v['profile_visits']:,}  ({prof_rate})")
    click.echo(f"  link_clicks    : {v['link_clicks']:,}  CTR: {ctr}")
    click.echo(f"  conversions    : {v['conversions']}  CVR: {cvr}")
    click.echo(f"  revenue        : ¥{v['revenue']:,}")
    if v["memo"]:
        click.echo(f"  memo           : {v['memo']}")
    click.echo()


def _load_cases_for_validation(cases_path: Path) -> tuple[list, list]:
    """Returns (entries_with_validation, errors)."""
    entries = []
    errors = []
    for f in sorted(cases_path.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            entry = _extract_ranking_entry(data, str(f))
            entry["validation"] = _fill_validation(data.get("validation") or {})
            entries.append(entry)
        except Exception as e:
            errors.append((f.name, str(e)))
    return entries, errors


def _print_sub_ranking(title: str, entries: list, key_fn, label_fn, min_count: int = 1) -> None:
    ranked = [e for e in entries if e["validation"].get("tested") and key_fn(e["validation"]) > 0]
    ranked.sort(key=lambda x: key_fn(x["validation"]), reverse=True)
    click.echo(f"\n{'─' * 65}")
    click.echo(f"\n{title}\n")
    if len(ranked) < min_count:
        click.echo(f"  データなし（tested=true かつ値 > 0 の案件が {min_count} 件以上必要）")
        return
    for rank, e in enumerate(ranked, start=1):
        click.echo(f"  #{rank:02d} {e['product_name']}")
        click.echo(f"       {label_fn(e['validation'])}")
        if e["validation"]["memo"]:
            click.echo(f"       memo: {e['validation']['memo']}")


@cli.command("validate-ranking")
@click.option("--cases-dir", default=None, type=click.Path(), help="分析済みJSONディレクトリ（デフォルト: outputs/cases/）")
@click.option("--output-dir", default=None, type=click.Path(), help="保存先（デフォルト: outputs/rankings/）")
def validate_ranking(cases_dir: str | None, output_dir: str | None):
    """予測ランキングと実績ランキングを比較し、予測精度を検証します"""
    base = Path(__file__).parent
    cases_path = Path(cases_dir) if cases_dir else base / "outputs" / "cases"
    rankings_path = Path(output_dir) if output_dir else base / "outputs" / "rankings"
    rankings_path.mkdir(parents=True, exist_ok=True)

    entries, errors = _load_cases_for_validation(cases_path)
    if not entries:
        click.echo(f"[エラー] {cases_path} にJSONファイルが見つかりません", err=True)
        sys.exit(1)

    tested_entries = [e for e in entries if e["validation"].get("tested")]
    predicted = sorted(entries, key=lambda x: x["priority_score"], reverse=True)

    sep = "=" * 65
    click.echo(f"\n{sep}")
    click.echo(f"  検証レポート  全件: {len(entries)}  検証済み: {len(tested_entries)}")
    click.echo(sep)

    # ── 予測ランキング ──
    click.echo("\n【予測ランキング】  priority_score = case_score×0.3 + automation_fit×0.3 + startup_fit×0.4\n")
    for rank, e in enumerate(predicted, start=1):
        note = " ※概算" if e["priority_score_note"] else ""
        tested_mark = " ✓" if e["validation"].get("tested") else ""
        v = e["validation"]
        ctr = _safe_rate(v["link_clicks"], v["impressions"])
        zcv = e.get("zero_cost_total")
        zcv_disp = f"{zcv}/120" if zcv is not None else "未分析"
        click.echo(f"  #{rank:02d} {e['product_name']}{tested_mark}")
        click.echo(f"       priority_score : {e['priority_score']}{note}  "
                   f"zero_cost: {zcv_disp}  "
                   f"startup_fit: {e['startup_fit'] if e['startup_fit'] is not None else '未分析'}  "
                   f"automation_fit: {e['automation_fit']}")
        click.echo(f"       status: {v['status']}  posts: {v['posts_created']}  "
                   f"imp: {v['impressions']:,}  clicks: {v['link_clicks']:,}  CTR: {ctr}  "
                   f"cv: {v['conversions']}  rev: ¥{v['revenue']:,}")
        if v["memo"]:
            click.echo(f"       memo: {v['memo']}")

    # ── ①売上ランキング ──
    _print_sub_ranking(
        "【①売上ランキング】  revenue順",
        entries,
        key_fn=lambda v: v["revenue"],
        label_fn=lambda v: (
            f"revenue: ¥{v['revenue']:,}  "
            f"conversions: {v['conversions']}  "
            f"CVR: {_safe_rate(v['conversions'], v['link_clicks'])}"
        ),
    )

    # ── ②CVランキング ──
    _print_sub_ranking(
        "【②CVランキング】  conversions順",
        entries,
        key_fn=lambda v: v["conversions"],
        label_fn=lambda v: (
            f"conversions: {v['conversions']}  "
            f"link_clicks: {v['link_clicks']:,}  "
            f"CVR: {_safe_rate(v['conversions'], v['link_clicks'])}"
        ),
    )

    # ── ③クリックランキング ──
    _print_sub_ranking(
        "【③クリックランキング】  link_clicks順  ← 売れてないが反応強い案件を発見",
        entries,
        key_fn=lambda v: v["link_clicks"],
        label_fn=lambda v: (
            f"link_clicks: {v['link_clicks']:,}  "
            f"impressions: {v['impressions']:,}  "
            f"CTR: {_safe_rate(v['link_clicks'], v['impressions'])}  "
            f"revenue: ¥{v['revenue']:,}"
        ),
    )

    # ── ④CTRランキング ──
    def _ctr_val(v: dict) -> float:
        return v["link_clicks"] / v["impressions"] if v["impressions"] else 0.0

    _print_sub_ranking(
        "【④CTRランキング】  link_clicks/impressions順  ← 訴求の鋭さ",
        entries,
        key_fn=_ctr_val,
        label_fn=lambda v: (
            f"CTR: {_safe_rate(v['link_clicks'], v['impressions'])}  "
            f"link_clicks: {v['link_clicks']:,}  "
            f"impressions: {v['impressions']:,}  "
            f"eng_rate: {_safe_rate(v['engagements'], v['impressions'])}  "
            f"prof_rate: {_safe_rate(v['profile_visits'], v['impressions'])}"
        ),
    )

    # ── 予測誤差（revenue順と比較） ──
    click.echo(f"\n{'─' * 65}")
    click.echo("\n【予測誤差】  予測順位(priority_score) vs 実績順位(revenue)\n")
    revenue_ranked = sorted(tested_entries, key=lambda x: x["validation"]["revenue"], reverse=True)
    if len(revenue_ranked) < 2:
        click.echo("  比較には検証済み案件（revenue > 0）が2件以上必要です。")
    else:
        pred_rank_map = {e["product_name"]: r for r, e in enumerate(predicted, start=1)}
        rev_rank_map = {e["product_name"]: r for r, e in enumerate(revenue_ranked, start=1)}

        deltas = []
        for name, act_r in rev_rank_map.items():
            pred_r = pred_rank_map.get(name)
            delta = (pred_r - act_r) if pred_r is not None else None
            deltas.append((name, pred_r, act_r, delta))
        deltas.sort(key=lambda x: (x[3] is None, abs(x[3]) if x[3] is not None else 0), reverse=True)

        for name, pred_r, act_r, delta in deltas:
            if delta is None:
                click.echo(f"  {name:30s}  予測: -    実績: #{act_r:02d}  差: 不明")
            else:
                sign = f"+{delta}" if delta > 0 else str(delta)
                direction = "予測より上" if delta > 0 else ("予測より下" if delta < 0 else "一致")
                click.echo(f"  {name:30s}  予測: #{pred_r:02d}  実績: #{act_r:02d}  差: {sign:>4s}  ({direction})")

        numeric = [abs(d) for *_, d in deltas if d is not None]
        if numeric:
            mae = sum(numeric) / len(numeric)
            click.echo(f"\n  平均絶対誤差 (MAE): {mae:.2f}  ← 0に近いほど予測精度が高い")

    click.echo(f"\n{sep}")

    # JSON保存
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_file = rankings_path / f"validation_{today}.json"
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": config.SCHEMA_VERSION,
        "total_cases": len(entries),
        "tested_cases": len(tested_entries),
        "predicted_ranking": [
            {"rank": i + 1, "product_name": e["product_name"],
             "priority_score": e["priority_score"],
             "case_score": e["case_score"],
             "automation_fit": e["automation_fit"],
             "startup_fit": e["startup_fit"],
             "validation": e["validation"]}
            for i, e in enumerate(predicted)
        ],
        "revenue_ranking": [
            {"rank": i + 1, "product_name": e["product_name"],
             **{k: e["validation"][k] for k in
                ("revenue", "conversions", "link_clicks", "impressions", "posts_created")}}
            for i, e in enumerate(revenue_ranked)
        ],
    }
    if len(revenue_ranked) >= 2:
        doc["rank_deltas"] = [
            {"product_name": name, "predicted_rank": pred_r, "actual_rank": act_r, "delta": delta}
            for name, pred_r, act_r, delta in deltas
        ]
    out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"  検証JSONを保存しました: {out_file}\n")

    if errors:
        click.echo(f"⚠ 読み込みエラー ({len(errors)}件):")
        for fname, msg in errors:
            click.echo(f"  {fname}: {msg}")


def _display_asset_type_matrix(data: dict) -> None:
    matrix = data.get("matrix", {})
    sep = "=" * 65
    click.echo(f"\n{sep}")
    click.echo(f"  Asset Type Matrix")
    click.echo(f"  breakdown: durability / stackability / differentiation / seed_rate")
    click.echo(sep)

    for theme_name, types in matrix.items():
        click.echo(f"\n  【{theme_name}】")
        sorted_types = sorted(types.items(), key=lambda x: x[1].get("score", 0), reverse=True)
        for asset_type, td in sorted_types:
            score = td.get("score", 0)
            bd    = td.get("breakdown", {})
            reason = td.get("reason", "")
            bar   = "█" * min(score // 5, 20)
            dur   = bd.get("durability", "-")
            stk   = bd.get("stackability", "-")
            dif   = bd.get("differentiation", "-")
            seed  = bd.get("seed_rate", "-")
            label = "◎" if score >= 80 else ("○" if score >= 60 else "△")
            click.echo(f"    {label} {asset_type:<16} {bar:<20}  {score:>3}")
            click.echo(f"         dur:{dur}  stack:{stk}  diff:{dif}  seed:{seed}  {reason[:30]}")

    click.echo(f"\n{sep}")


def _display_asset_candidates(data: dict, top_n: int = 15) -> None:
    candidates = data.get("candidates", [])
    sep = "=" * 65
    click.echo(f"\n{sep}")
    click.echo(f"  Asset Candidates  {len(candidates)}件  （Theme × Asset Type × First Hand Experience）")
    click.echo(sep)

    for i, c in enumerate(candidates[:top_n], start=1):
        title      = c.get("title", "")
        theme      = c.get("theme", "")
        asset_type = c.get("asset_type", "")
        score      = c.get("predicted_score", 0)
        bd         = c.get("breakdown", {})
        rationale  = c.get("rationale", "")
        source     = c.get("source_experience", "")
        bar        = "█" * min(score // 5, 20)

        u = bd.get("uniqueness", "-")
        d = bd.get("durability", "-")
        s = bd.get("seed_rate", "-")

        label = "◎ 最重点" if score >= 90 else ("○ 注目" if score >= 75 else "△ 補助")
        click.echo(f"\n  #{i:>2}  [{label}]  {title}")
        click.echo(f"        {theme}  ×  {asset_type}")
        click.echo(f"        予測: {score:>3}  {bar}")
        click.echo(f"        unique:{u}  dur:{d}  seed:{s}")
        if source:
            click.echo(f"        根拠: {source[:65]}")
        if rationale:
            click.echo(f"        {rationale[:65]}")

    click.echo(f"\n{sep}")


@cli.command("asset-type-matrix")
@click.option("--force", is_flag=True, default=False, help="既存を上書き")
def asset_type_matrix_cmd(force: bool):
    """テーマ × 資産タイプの資産生成率マトリクスを生成します（戦略層・週1確認）"""
    base = Path(__file__).parent
    out_path      = base / "outputs" / "asset_type_matrix.json"
    clusters_path = base / "outputs" / "theme_clusters.json"

    if out_path.exists() and not force:
        click.echo(f"\n  既存マトリクスを読み込み: {out_path}")
        click.echo(f"  上書きする場合は --force を追加してください")
        _display_asset_type_matrix(json.loads(out_path.read_text(encoding="utf-8")))
        return

    if not clusters_path.exists():
        click.echo("[エラー] theme_clusters.json が見つかりません。先に cluster-themes を実行してください。", err=True)
        sys.exit(1)

    clusters = json.loads(clusters_path.read_text(encoding="utf-8"))

    creator_profile = {}
    cp_path = base / "data" / "creator_profile.json"
    if cp_path.exists():
        creator_profile = json.loads(cp_path.read_text(encoding="utf-8"))

    themes_summary_lines = []
    for theme_name, theme_data in clusters.get("themes", {}).items():
        stats = theme_data.get("stats", {})
        themes_summary_lines.append(
            f"- {theme_name}\n"
            f"  説明: {theme_data.get('description', '')}\n"
            f"  creator_fit平均: {stats.get('avg_creator_fit', '-')}  theme_value: {stats.get('theme_value', '-')}"
        )

    template = (base / "prompts" / "asset_type_matrix_prompt.md").read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{creator_profile}", json.dumps(creator_profile, ensure_ascii=False, indent=2))
        .replace("{themes_summary}", "\n".join(themes_summary_lines))
    )

    click.echo(f"\nasset-type-matrix  生成中...")
    llm = LLMClient()
    result = llm.call_json(prompt, "あなたはコンテンツ戦略の専門家です。JSONのみで回答してください。")

    if not result.get("matrix"):
        click.echo("[エラー] マトリクスが取得できませんでした", err=True)
        sys.exit(1)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matrix": result["matrix"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    _display_asset_type_matrix(output)
    click.echo(f"\n  JSON: {out_path}\n")


@cli.command("asset-candidates")
@click.option("--force", is_flag=True, default=False, help="既存を上書き")
@click.option("--top", default=15, type=int, show_default=True, help="表示件数")
@click.option("--min-type-score", default=70, type=int, show_default=True, help="候補生成対象のタイプ最低スコア")
def asset_candidates_cmd(force: bool, top: int, min_type_score: int):
    """一次情報ベースの具体的なコンテンツ資産候補を生成します（実行層・毎日確認）"""
    base = Path(__file__).parent
    out_path    = base / "outputs" / "asset_candidates.json"
    matrix_path = base / "outputs" / "asset_type_matrix.json"

    if out_path.exists() and not force:
        click.echo(f"\n  既存候補を読み込み: {out_path}")
        click.echo(f"  上書きする場合は --force を追加してください")
        _display_asset_candidates(json.loads(out_path.read_text(encoding="utf-8")), top)
        return

    if not matrix_path.exists():
        click.echo("[エラー] asset_type_matrix.json が見つかりません。先に asset-type-matrix を実行してください。", err=True)
        sys.exit(1)

    matrix_data = json.loads(matrix_path.read_text(encoding="utf-8"))

    creator_profile = {}
    cp_path = base / "data" / "creator_profile.json"
    if cp_path.exists():
        creator_profile = json.loads(cp_path.read_text(encoding="utf-8"))

    # テーマごとに高スコアタイプ（閾値以上、最大4種）を絞り込む
    top_types: dict[str, list] = {}
    for theme_name, types in matrix_data.get("matrix", {}).items():
        filtered = [
            (t, d) for t, d in types.items()
            if d.get("score", 0) >= min_type_score
        ]
        top_types[theme_name] = sorted(filtered, key=lambda x: x[1].get("score", 0), reverse=True)[:4]

    template = (base / "prompts" / "asset_candidate_prompt.md").read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{creator_profile}", json.dumps(creator_profile, ensure_ascii=False, indent=2))
        .replace("{top_types}", json.dumps(top_types, ensure_ascii=False, indent=2))
    )

    click.echo(f"\nasset-candidates  生成中...")
    llm = LLMClient()
    result = llm.call_json(prompt, "あなたはコンテンツ戦略の専門家です。JSONのみで回答してください。")

    raw = result.get("candidates", [])
    if not raw:
        click.echo("[エラー] 候補が取得できませんでした", err=True)
        sys.exit(1)

    import uuid as uuid_lib
    for c in raw:
        c["id"] = str(uuid_lib.uuid4())
        c.setdefault("status", "draft")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": sorted(raw, key=lambda x: x.get("predicted_score", 0), reverse=True),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    _display_asset_candidates(output, top)
    click.echo(f"\n  JSON: {out_path}\n")


def _display_candidate_selection(data: dict) -> None:
    sep = "=" * 65
    selected = data.get("selected", [])
    total_seeds = data.get("total_seed_count", 0)
    logic = data.get("selection_logic", "")

    click.echo(f"\n{sep}")
    click.echo(f"  Candidate Selection  {len(selected)}件選択")
    click.echo(f"  最適化: seed_rate → theme_balance → asset_type_balance → score")
    click.echo(sep)

    for i, s in enumerate(selected, start=1):
        title   = s.get("title", "")
        theme   = s.get("theme", "")
        atype   = s.get("asset_type", "")
        score   = s.get("predicted_score", 0)
        sr      = s.get("seed_rate", 0)
        reason  = s.get("selection_reason", "")
        seeds   = s.get("expected_next_seeds", [])

        bar = "█" * min(score // 5, 20)
        click.echo(f"\n  #{i}  {title}")
        click.echo(f"       {theme}  ×  {atype}")
        click.echo(f"       score:{score}  {bar}  seed_rate:{sr}")
        if reason:
            click.echo(f"       理由: {reason[:65]}")
        if seeds:
            click.echo(f"       ↓ 予測種 ({len(seeds)}件):")
            for sd in seeds[:5]:
                conf   = sd.get("confidence", "-") if isinstance(sd, dict) else "-"
                stitle = sd.get("title", str(sd)) if isinstance(sd, dict) else str(sd)
                stype  = sd.get("asset_type", "") if isinstance(sd, dict) else ""
                click.echo(f"         [{conf:>3}%]  {stitle[:48]}  ({stype})")

    click.echo(f"\n  合計予測seed数 : {total_seeds}件")
    if logic:
        click.echo(f"  選択方針       : {logic[:70]}")
    click.echo(f"\n{sep}")


def _display_asset_performance(assets: list, expected_seeds_map: dict) -> None:
    sep = "=" * 65
    click.echo(f"\n{sep}")
    click.echo(f"  Asset Performance  {len(assets)}件  予測 vs 実測")
    click.echo(sep)

    has_perf = [a for a in assets if a.get("performance")]
    pending  = [a for a in assets if not a.get("performance")]

    for a in has_perf:
        title   = a.get("title", "")
        theme   = a.get("theme", "")
        atype   = a.get("asset_type", "")
        p_score = a.get("predicted_score")
        perf    = a.get("performance", {})
        cid     = a.get("candidate_id", "")
        pv      = perf.get("pv")
        sr      = perf.get("save_rate")
        cit     = perf.get("citations")
        fup     = perf.get("followup_count")

        click.echo(f"\n  {title}")
        click.echo(f"  {theme}  ×  {atype}  （predicted: {p_score}）")
        click.echo(f"  ─ Performance ─────────────────────────────")
        if pv      is not None: click.echo(f"    PV        : {pv:,}")
        if sr      is not None: click.echo(f"    保存率    : {sr}%")
        if cit     is not None: click.echo(f"    引用数    : {cit}件")
        if fup     is not None: click.echo(f"    派生数    : {fup}件")

        expected = expected_seeds_map.get(cid, [])
        actual   = a.get("actual_seeds", [])
        if expected:
            actual_lower = {s.lower() for s in actual}
            hit_count = 0
            click.echo(f"  ─ Seed 予測 vs 実測 ───────────────────────")
            for es in expected:
                es_title = es.get("title", str(es)) if isinstance(es, dict) else str(es)
                conf     = es.get("confidence", "-") if isinstance(es, dict) else "-"
                hit = any(es_title[:12].lower() in at for at in actual_lower)
                mark = "✓" if hit else "✗"
                if hit:
                    hit_count += 1
                click.echo(f"    {mark} [{conf:>3}%]  {es_title[:50]}")
            click.echo(f"    適中率: {hit_count}/{len(expected)}")
        if actual:
            click.echo(f"  ─ 実際に生まれた種 ─────────────────────────")
            for s in actual:
                click.echo(f"    → {s}")

    if pending:
        click.echo(f"\n  ─ 計測待ち {len(pending)}件 ─────────────────────────")
        for a in pending:
            click.echo(f"    [{a.get('platform',''):8}]  {a.get('title','')}  id:{a.get('id','')[:8]}")

    click.echo(f"\n{sep}")


@cli.command("candidate-selection")
@click.option("--n", default=3, type=int, show_default=True, help="選択件数")
@click.option("--force", is_flag=True, default=False, help="既存を上書き")
def candidate_selection_cmd(n: int, force: bool):
    """資産候補からIdea Graph最大化の観点でN件を選択します"""
    base = Path(__file__).parent
    out_path   = base / "outputs" / "candidate_selection.json"
    cands_path = base / "outputs" / "asset_candidates.json"

    if out_path.exists() and not force:
        click.echo(f"\n  既存選択を読み込み: {out_path}")
        click.echo(f"  上書きする場合は --force を追加してください")
        _display_candidate_selection(json.loads(out_path.read_text(encoding="utf-8")))
        return

    if not cands_path.exists():
        click.echo("[エラー] asset_candidates.json が見つかりません。先に asset-candidates を実行してください。", err=True)
        sys.exit(1)

    cands_data = json.loads(cands_path.read_text(encoding="utf-8"))
    draft = [c for c in cands_data.get("candidates", []) if c.get("status") == "draft"]
    if not draft:
        click.echo("[エラー] status=draft の候補が0件です。", err=True)
        sys.exit(1)

    creator_profile = {}
    cp_path = base / "data" / "creator_profile.json"
    if cp_path.exists():
        creator_profile = json.loads(cp_path.read_text(encoding="utf-8"))

    template = (base / "prompts" / "candidate_selection_prompt.md").read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{creator_profile}", json.dumps(creator_profile, ensure_ascii=False, indent=2))
        .replace("{candidates_json}", json.dumps(draft, ensure_ascii=False, indent=2))
        .replace("{n}", str(n))
    )

    click.echo(f"\ncandidate-selection  {len(draft)}候補から{n}件を選択中...")
    llm = LLMClient()
    result = llm.call_json(prompt, "あなたはコンテンツ戦略の専門家です。JSONのみで回答してください。")

    output = {
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "n_requested": n,
        "draft_count": len(draft),
        **result,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    _display_candidate_selection(output)
    click.echo(f"\n  JSON: {out_path}\n")


@cli.command("publish-asset")
@click.option("--candidate-id", required=True, help="asset_candidates.json の id")
@click.option("--url", required=True, help="公開URL")
@click.option("--platform", required=True,
              type=click.Choice(["note", "x", "youtube", "zenn", "threads", "instagram", "other"]))
def publish_asset_cmd(candidate_id: str, url: str, platform: str):
    """候補を公開済みとしてマークします"""
    import uuid as uuid_lib
    base = Path(__file__).parent
    cands_path = base / "outputs" / "asset_candidates.json"
    pub_path   = base / "outputs" / "published_assets.json"

    if not cands_path.exists():
        click.echo("[エラー] asset_candidates.json が見つかりません。", err=True)
        sys.exit(1)

    cands_data = json.loads(cands_path.read_text(encoding="utf-8"))
    target = None
    for c in cands_data.get("candidates", []):
        if c.get("id") == candidate_id:
            c["status"] = "published"
            target = c
            break

    if not target:
        click.echo(f"[エラー] candidate_id={candidate_id} が見つかりません。", err=True)
        sys.exit(1)

    cands_path.write_text(json.dumps(cands_data, ensure_ascii=False, indent=2), encoding="utf-8")

    pub_data = {"assets": []}
    if pub_path.exists():
        pub_data = json.loads(pub_path.read_text(encoding="utf-8"))

    pub_data["assets"].append({
        "id": str(uuid_lib.uuid4()),
        "candidate_id": candidate_id,
        "title": target.get("title", ""),
        "theme": target.get("theme", ""),
        "asset_type": target.get("asset_type", ""),
        "predicted_score": target.get("predicted_score"),
        "predicted_breakdown": target.get("breakdown", {}),
        "url": url,
        "platform": platform,
        "published_at": datetime.now(timezone.utc).date().isoformat(),
        "performance": None,
        "actual_seeds": [],
        "actual_score": None,
    })

    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_text(json.dumps(pub_data, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"\n  ✓ 公開済み登録: {target.get('title', '')}")
    click.echo(f"    platform: {platform}")
    click.echo(f"    url     : {url}\n")


@cli.command("record-performance")
@click.option("--asset-id", required=True, help="published_assets.json の id")
@click.option("--pv", default=None, type=int, help="ページビュー数")
@click.option("--save-rate", default=None, type=float, help="保存率（%）")
@click.option("--comments", default=None, type=int, help="コメント数")
@click.option("--citations", default=None, type=int, help="引用・被リンク数")
@click.option("--followup-count", default=None, type=int, help="派生コンテンツ数")
@click.option("--actual-seeds", multiple=True, help="実際に生まれた後続ネタのタイトル（複数可）")
def record_performance_cmd(asset_id, pv, save_rate, comments, citations, followup_count, actual_seeds):
    """公開済み資産のパフォーマンスと実測種を記録します"""
    base = Path(__file__).parent
    pub_path = base / "outputs" / "published_assets.json"

    if not pub_path.exists():
        click.echo("[エラー] published_assets.json が見つかりません。先に publish-asset を実行してください。", err=True)
        sys.exit(1)

    pub_data = json.loads(pub_path.read_text(encoding="utf-8"))
    target = None
    for asset in pub_data.get("assets", []):
        if asset.get("id") == asset_id:
            target = asset
            break

    if not target:
        click.echo(f"[エラー] asset_id={asset_id} が見つかりません。", err=True)
        sys.exit(1)

    target["performance"] = {
        "pv":             pv,
        "save_rate":      save_rate,
        "comments":       comments,
        "citations":      citations,
        "followup_count": followup_count,
        "measured_at":    datetime.now(timezone.utc).date().isoformat(),
    }
    target["actual_seeds"] = list(actual_seeds)

    pub_path.write_text(json.dumps(pub_data, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"\n  ✓ パフォーマンス記録: {target.get('title', '')}")
    if pv            is not None: click.echo(f"    PV        : {pv:,}")
    if save_rate     is not None: click.echo(f"    保存率    : {save_rate}%")
    if citations     is not None: click.echo(f"    引用数    : {citations}件")
    if followup_count is not None: click.echo(f"    派生数    : {followup_count}件")
    if actual_seeds:               click.echo(f"    実測種    : {', '.join(actual_seeds)}")
    click.echo()


@cli.command("asset-performance")
def asset_performance_cmd():
    """予測 vs 実測の比較レポートを表示します"""
    base = Path(__file__).parent
    pub_path = base / "outputs" / "published_assets.json"
    sel_path = base / "outputs" / "candidate_selection.json"

    if not pub_path.exists():
        click.echo("[エラー] published_assets.json が見つかりません。先に publish-asset を実行してください。", err=True)
        sys.exit(1)

    pub_data = json.loads(pub_path.read_text(encoding="utf-8"))

    expected_seeds_map: dict[str, list] = {}
    if sel_path.exists():
        sel_data = json.loads(sel_path.read_text(encoding="utf-8"))
        for s in sel_data.get("selected", []):
            cid = s.get("candidate_id")
            if cid:
                expected_seeds_map[cid] = s.get("expected_next_seeds", [])

    _display_asset_performance(pub_data.get("assets", []), expected_seeds_map)


if __name__ == "__main__":
    cli()
