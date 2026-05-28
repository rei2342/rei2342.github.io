import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from core.llm_client import LLMClient
from core.input_loader import load_case, generate_information_quality
from core.storage import save_case_output, load_case_output, update_case_output

import analyzers.lp_analyzer as lp_analyzer
import analyzers.market_analyzer as market_analyzer
import analyzers.buying_trigger_analyzer as buying_trigger_analyzer
import analyzers.sns_fit_analyzer as sns_fit_analyzer
import analyzers.risk_analyzer as risk_analyzer
import generators.appeal_generator as appeal_generator
import generators.report_generator as report_generator
import generators.post_generator as post_generator


def _step(label: str) -> None:
    click.echo(f"\n  [{label}]", nl=False)


def _ok() -> None:
    click.echo(" ✓")


def _print_summary(report: dict) -> None:
    meta = report["meta"]
    scores = report["scores"]
    risk = report.get("risk_score", 0)
    ai_risk = report.get("ai_content_risk", {})
    triggers = report.get("buying_triggers", [])
    iq = report.get("information_quality", {})

    click.echo("\n" + "=" * 60)
    click.echo(f"  案件名   : {meta['case_name']}")
    click.echo(f"  分析日時 : {meta['analyzed_at'][:19]}")
    click.echo("=" * 60)

    click.echo("\n▶ スコア")
    click.echo(f"  affiliate_score : {scores.get('affiliate_score', '-')}")
    click.echo(f"  risk_score      : {risk}")
    click.echo(f"  ai_content_risk : {ai_risk.get('score', '-')} ({ai_risk.get('risk_level', '-')})")

    pf = scores.get("platform_fit_scores", {})
    if pf:
        click.echo("\n▶ 媒体別スコア")
        for platform, score in pf.items():
            click.echo(f"  {platform:<12}: {score}")

    if triggers:
        click.echo("\n▶ 購買トリガー TOP3")
        for t in triggers[:3]:
            click.echo(f"  [{t.get('strength','?').upper()}] {t.get('trigger','')} — {t.get('reason','')}")

    appeals = report.get("appeals", [])
    click.echo(f"\n▶ 生成された訴求フック : {len(appeals)}件")

    high_appeals = [a for a in appeals if a.get("expected_strength") == "high"]
    if high_appeals:
        click.echo(f"\n▶ 期待値 HIGH の訴求 (上位5件)")
        for a in high_appeals[:5]:
            click.echo(f"  [{a.get('appeal_type','')}] {a.get('hook','')}")

    if iq.get("missing"):
        click.echo(f"\n▶ 情報不足 (missing)")
        for m in iq["missing"]:
            click.echo(f"  ⚠ {m}")

    click.echo("=" * 60)


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
        appeals = appeal_generator.generate(case, triggers, emotion, sns_fit, risk, llm)
        _ok()

        _step("スコアリング・レポート統合")
        report = report_generator.build(
            case, iq, lp, market, triggers, sns_fit, risk, appeals, llm
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
@click.option("--appeal-ids", required=True, help="カンマ区切りのappal_id一覧")
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


if __name__ == "__main__":
    cli()
