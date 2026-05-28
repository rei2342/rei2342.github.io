import json
import uuid
from datetime import datetime

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはSNSアフィリエイトの訴求設計専門家です。JSONのみで回答してください。"


def generate(
    case: CaseInput,
    buying_triggers: dict,
    emotion_analysis: dict,
    sns_fit: dict,
    risk_analysis: dict,
    llm: LLMClient,
) -> list:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"報酬: {case.reward}円\n"
        f"SNS投稿可否: {case.sns_allowed}"
    )

    template = load_prompt("appeal_generation_prompt.md")
    prompt = (
        template
        .replace("{case_summary}", case_summary)
        .replace("{buying_triggers}", json.dumps(buying_triggers, ensure_ascii=False))
        .replace("{emotion_analysis}", json.dumps(emotion_analysis, ensure_ascii=False))
        .replace("{sns_fit}", json.dumps(sns_fit, ensure_ascii=False))
        .replace("{risk_analysis}", json.dumps(risk_analysis, ensure_ascii=False))
    )

    result = llm.call_json(prompt, SYSTEM)
    raw_appeals = result.get("appeals", [])

    enriched = []
    for a in raw_appeals:
        enriched.append({
            "appeal_id": str(uuid.uuid4()),
            "appeal_type": a.get("appeal_type", ""),
            "hook": a.get("hook", ""),
            "target_emotion": a.get("target_emotion", ""),
            "platform": a.get("platform", []),
            "expected_strength": a.get("expected_strength", "medium"),
            "risk": a.get("risk", "medium"),
            "note": a.get("note", ""),
            "human_feedback": {
                "status": "pending",
                "comment": None,
                "reviewed_at": None,
            },
        })

    return enriched
