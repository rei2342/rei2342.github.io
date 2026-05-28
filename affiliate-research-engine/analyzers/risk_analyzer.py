import json

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはアフィリエイトコンプライアンスとSNSリスク管理の専門家です。JSONのみで回答してください。"


def analyze(
    case: CaseInput,
    lp_analysis: dict,
    market_analysis: dict,
    llm: LLMClient,
) -> dict:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"禁止事項: {case.restrictions or '不明'}\n"
        f"SNS投稿可否: {case.sns_allowed}\n"
        f"PR表記要否: {case.pr_required}"
    )

    template = load_prompt("risk_analysis_prompt.md")
    prompt = (
        template
        .replace("{case_summary}", case_summary)
        .replace("{lp_analysis}", json.dumps(lp_analysis, ensure_ascii=False))
        .replace("{market_analysis}", json.dumps(market_analysis, ensure_ascii=False))
    )

    return llm.call_json(prompt, SYSTEM)
