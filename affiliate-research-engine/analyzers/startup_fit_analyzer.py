import json

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはSNSアフィリエイトの新規参入戦略の専門家です。JSONのみで回答してください。"


def analyze(
    case: CaseInput,
    lp_analysis: dict,
    market_analysis: dict,
    risk_analysis: dict,
    buying_triggers: dict,
    llm: LLMClient,
) -> dict:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"商品種別: {case.product_type if hasattr(case, 'product_type') else '不明'}\n"
        f"報酬: {case.reward}円\n"
        f"CV条件: {case.conversion_condition}\n"
        f"SNS許可: {case.sns_allowed}\n"
        f"PR表記必須: {case.pr_required}"
    )

    template = load_prompt("startup_fit_prompt.md")
    prompt = (
        template
        .replace("{case_summary}", case_summary)
        .replace("{lp_analysis}", json.dumps(lp_analysis, ensure_ascii=False))
        .replace("{market_analysis}", json.dumps(market_analysis, ensure_ascii=False))
        .replace("{risk_analysis}", json.dumps(risk_analysis, ensure_ascii=False))
        .replace("{buying_triggers}", json.dumps(buying_triggers, ensure_ascii=False))
    )

    result = llm.call_json(prompt, SYSTEM)
    startup_fit = result.get("startup_fit", {})
    if not startup_fit and "score" in result:
        startup_fit = result
    cef = result.get("cef", {})
    return {"startup_fit": startup_fit, "cef": cef}
