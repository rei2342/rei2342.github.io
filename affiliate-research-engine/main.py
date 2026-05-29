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
        click.echo(f"\n▶ startup_fit    : {sf_score} [{sf_level}]")
        if sf_breakdown:
            click.echo(f"  zero_follower    : {sf_breakdown.get('zero_follower_viable', '-')}")
            click.echo(f"  no_track_record  : {sf_breakdown.get('no_track_record_needed', '-')}")
            click.echo(f"  no_face          : {sf_breakdown.get('no_face_required', '-')}")
            click.echo(f"  no_physical      : {sf_breakdown.get('no_physical_product_needed', '-')}")
            click.echo(f"  free_trial       : {sf_breakdown.get('free_trial_available', '-')}")
            click.echo(f"  trust_free_conv  : {sf_breakdown.get('trust_free_conversion', '-')}")
        if sf_bottleneck:
            click.echo(f"  ボトルネック     : {sf_bottleneck}")
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


@cli.command("analyze-case")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True), help="入力JSONファイルのパス")
def analyze_case(input_path: str):
    """案件を分析してJSONレポートを生成します"""
    click.echo(f"\nAffiliate Research Engine — 案件分析開始")
    click.echo(f"入力ファイル: {input_path}")

    llm = LLMClient()

    try:
        _step("入力データ読み込み")
        case = load_case(input_path)
        iq = generate_information_quality(case)
        _ok()

        _step("LP分析")
        lp = lp_analyzer.analyze(case, llm)
        _ok()

        _step("市場分析")
        market = market_analyzer.analyze(case, lp, llm)
        _ok()

        _step("購買トリガー分析")
        triggers = buying_trigger_analyzer.analyze(case, lp, market, llm)
        _ok()

        _step("SNS適性・アルゴリズム分析")
        sns_fit = sns_fit_analyzer.analyze(case, lp, market, triggers, llm)
        _ok()

        _step("リスク分析")
        risk = risk_analyzer.analyze(case, lp, market, llm)
        _ok()

        _step("訴求フック生成（100件）")
        emotion = sns_fit.get("emotion_analysis", {"primary": [], "secondary": []})
        raw_appeals = appeal_generator.generate(case, triggers, emotion, sns_fit, risk, llm)
        _ok()

        _step("訴求スコアリング・TOP10抽出")
        scored_appeals, top_appeals = appeal_scorer.score_and_rank(
            raw_appeals, triggers, emotion, sns_fit, risk, llm
        )
        _ok()

        _step("勝ち筋サマリー・case_score生成")
        winning_data = winning_summary_generator.generate(
            case, lp, market, triggers, sns_fit, risk, top_appeals, llm
        )
        _ok()

        _step("startup_fit分析")
        sf = startup_fit_analyzer.analyze(case, lp, market, risk, triggers, llm)
        _ok()

        _step("レポート統合・スコアリング")
        report = report_generator.build(
            case, iq, lp, market, triggers, sns_fit, risk,
            scored_appeals, top_appeals, winning_data, sf, llm
        )
        _ok()

        _step("JSON保存")
        output_path = save_case_output(report, case.case_name)
        _ok()

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
def rank_cases(cases_dir: str | None, output_dir: str | None):
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

    entries.sort(key=lambda x: x["priority_score"], reverse=True)

    # ターミナル表示
    click.echo(f"\n{'=' * 65}")
    click.echo(f"  案件ランキング  ({len(entries)}件)  priority_score = case_score×0.3 + automation_fit×0.3 + startup_fit×0.4")
    click.echo(f"{'=' * 65}")

    for rank, e in enumerate(entries, start=1):
        sf_disp = str(e["startup_fit"]) if e["startup_fit"] is not None else "未分析"
        note = f"  ※{e['priority_score_note']}" if e["priority_score_note"] else ""
        click.echo(f"\n  #{rank:02d} {e['product_name']}")
        click.echo(f"       priority_score : {e['priority_score']}{note}")
        click.echo(f"       case_score     : {e['case_score']}")
        click.echo(f"       automation_fit : {e['automation_fit']}")
        click.echo(f"       startup_fit    : {sf_disp}", nl=False)
        if e["startup_fit_level"]:
            click.echo(f"  [{_level_label(e['startup_fit_level'])}]")
        else:
            click.echo()
        if e["start_priority"]:
            click.echo(f"       start_priority : {_priority_label(e['start_priority'])}")
        if e["epc"] is not None:
            click.echo(f"       EPC            : {e['epc']}")
        if e["approval_rate"] is not None:
            click.echo(f"       approval_rate  : {e['approval_rate']}%")
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


if __name__ == "__main__":
    cli()
