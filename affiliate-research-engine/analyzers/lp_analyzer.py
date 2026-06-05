import json
import requests
from bs4 import BeautifulSoup

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはアフィリエイトマーケティングの専門家です。指示に従い、JSONのみで回答してください。"


def _fetch_lp_text(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:8000]
    except Exception as e:
        return f"[LP取得失敗: {e}]"


def analyze(case: CaseInput, llm: LLMClient) -> dict:
    if case.lp_text:
        lp_content = case.lp_text[:8000]
    elif case.affiliate_url:
        lp_content = _fetch_lp_text(case.affiliate_url)
    else:
        lp_content = "LP情報なし"

    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"報酬: {case.reward}円\n"
        f"成果条件: {case.conversion_condition or '不明'}\n"
        f"禁止事項: {case.restrictions or '不明'}"
    )

    template = load_prompt("lp_analysis_prompt.md")
    prompt = template.replace("{case_summary}", case_summary).replace("{lp_content}", lp_content)

    return llm.call_json(prompt, SYSTEM)
