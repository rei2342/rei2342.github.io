import json

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはSNSアフィリエイトマーケティングの市場分析専門家です。JSONのみで回答してください。"


def analyze(case: CaseInput, lp_analysis: dict, llm: LLMClient) -> dict:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"報酬: {case.reward}円\n"
        f"ASP: {case.asp_name or '不明'}\n"
        f"成果条件: {case.conversion_condition or '不明'}"
    )

    sns_block = "\n".join(case.sns_examples) if case.sns_examples else "SNS例なし"
    competitor_block = "\n".join(case.competitor_examples) if case.competitor_examples else "競合例なし"

    template = load_prompt("market_analysis_prompt.md")
    prompt = (
        template
        .replace("{case_summary}", case_summary)
        .replace("{lp_analysis}", json.dumps(lp_analysis, ensure_ascii=False))
        .replace("{sns_examples}", sns_block)
        .replace("{competitor_examples}", competitor_block)
    )

    return llm.call_json(prompt, SYSTEM)
