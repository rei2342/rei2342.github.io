import json

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはSNSアルゴリズムとアフィリエイトマーケティングの専門家です。JSONのみで回答してください。"


def analyze(
    case: CaseInput,
    lp_analysis: dict,
    market_analysis: dict,
    buying_triggers: dict,
    llm: LLMClient,
) -> dict:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"SNS投稿可否: {case.sns_allowed}"
    )

    sns_block = "\n".join(case.sns_examples) if case.sns_examples else "SNS例なし"

    template = load_prompt("sns_fit_prompt.md")
    prompt = (
        template
        .replace("{case_summary}", case_summary)
        .replace("{lp_analysis}", json.dumps(lp_analysis, ensure_ascii=False))
        .replace("{buying_triggers}", json.dumps(buying_triggers, ensure_ascii=False))
        .replace("{market_analysis}", json.dumps(market_analysis, ensure_ascii=False))
        .replace("{sns_examples}", sns_block)
    )

    return llm.call_json(prompt, SYSTEM)
