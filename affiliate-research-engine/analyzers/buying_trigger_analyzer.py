import json

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたは消費者心理と購買行動の専門家です。JSONのみで回答してください。"


def analyze(case: CaseInput, lp_analysis: dict, market_analysis: dict, llm: LLMClient) -> dict:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"報酬: {case.reward}円"
    )

    template = load_prompt("buying_trigger_prompt.md")
    prompt = (
        template
        .replace("{case_summary}", case_summary)
        .replace("{lp_analysis}", json.dumps(lp_analysis, ensure_ascii=False))
        .replace("{market_analysis}", json.dumps(market_analysis, ensure_ascii=False))
    )

    return llm.call_json(prompt, SYSTEM)
