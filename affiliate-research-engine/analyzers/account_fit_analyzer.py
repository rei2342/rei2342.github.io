import json
from pathlib import Path

from core.llm_client import LLMClient
from core.storage import load_prompt


SYSTEM = "あなたはSNSアフィリエイトのアカウント戦略専門家です。JSONのみで回答してください。"


def _load_account_profile() -> dict:
    base = Path(__file__).parent.parent
    profile_path = base / "data" / "account_profile.json"
    if not profile_path.exists():
        return {}
    return json.loads(profile_path.read_text(encoding="utf-8"))


def analyze(case_report: dict, llm: LLMClient) -> dict:
    profile = _load_account_profile()
    if not profile:
        return {}

    basic = case_report.get("basic_info", {})
    market = case_report.get("market_analysis", {})
    winning = case_report.get("winning_summary", {})
    sf = case_report.get("startup_fit", {}) or {}
    cef = case_report.get("cef", {}) or {}

    case_summary = (
        f"案件名: {basic.get('case_name', '')}\n"
        f"ジャンル: {basic.get('category', '')}\n"
        f"EPC: {basic.get('epc', '不明')}\n"
        f"成果報酬率: {basic.get('reward_rate', '不明')}%\n"
        f"確定率: {basic.get('approval_rate', '不明')}%\n"
        f"SNS許可: {basic.get('sns_allowed', '不明')}"
    )

    analysis_summary = (
        f"勝ち筋: {winning.get('winning_angle', '')}\n"
        f"最強媒体: {', '.join(winning.get('best_platforms', []))}\n"
        f"startup_fit: {sf.get('score', '-')} [{sf.get('level', '-')}]\n"
        f"CEF: {cef.get('score', '-')}/100\n"
        f"ターゲット: {case_report.get('lp_analysis', {}).get('target_audience', '')}"
    )

    template = load_prompt("account_fit_prompt.md")
    prompt = (
        template
        .replace("{account_profile}", json.dumps(profile, ensure_ascii=False, indent=2))
        .replace("{case_summary}", case_summary)
        .replace("{analysis_summary}", analysis_summary)
    )

    result = llm.call_json(prompt, SYSTEM)
    return result.get("account_fit", {})
