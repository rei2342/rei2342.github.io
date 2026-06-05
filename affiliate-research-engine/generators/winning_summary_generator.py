import json

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはアフィリエイト案件評価とSNS量産システム設計の専門家です。JSONのみで回答してください。"


def generate(
    case: CaseInput,
    lp_analysis: dict,
    market_analysis: dict,
    buying_triggers: dict,
    sns_fit: dict,
    risk_analysis: dict,
    top_appeals: list,
    llm: LLMClient,
) -> dict:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"報酬: {case.reward}円\n"
        f"ASP: {case.asp_name or '不明'}\n"
        f"成果条件: {case.conversion_condition or '不明'}\n"
        f"SNS可否: {case.sns_allowed}\n"
        f"禁止事項: {case.restrictions or '不明'}"
    )

    # Slim down top_appeals for prompt (keep essentials)
    top_slim = [
        {
            "rank": a["rank"],
            "appeal_type": a["appeal_type"],
            "hook": a["hook"],
            "appeal_score": a["appeal_score"],
            "content_repeatability": a["content_repeatability"],
        }
        for a in top_appeals
    ]

    template = load_prompt("winning_summary_prompt.md")
    prompt = (
        template
        .replace("{case_summary}", case_summary)
        .replace("{lp_analysis}", json.dumps(lp_analysis, ensure_ascii=False))
        .replace("{market_analysis}", json.dumps(market_analysis, ensure_ascii=False))
        .replace("{buying_triggers}", json.dumps(buying_triggers, ensure_ascii=False))
        .replace("{sns_fit}", json.dumps(sns_fit, ensure_ascii=False))
        .replace("{risk_analysis}", json.dumps(risk_analysis, ensure_ascii=False))
        .replace("{top_appeals}", json.dumps(top_slim, ensure_ascii=False, indent=2))
    )

    result = llm.call_json(prompt, SYSTEM)
    return {
        "winning_summary": result.get("winning_summary", {}),
        "case_score": result.get("case_score", {}),
    }
