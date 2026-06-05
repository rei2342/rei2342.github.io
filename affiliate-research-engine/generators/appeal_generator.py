import json
import uuid

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはSNSアフィリエイトの訴求設計専門家です。JSONのみで回答してください。"

# Split into 2 batches to stay within token limits
BATCHES = [
    ["不安訴求", "共感訴求", "優越訴求", "損失回避訴求", "時短訴求"],
    ["初心者訴求", "実験訴求", "比較訴求", "体験談訴求", "知らないと損訴求"],
]


def _build_prompt(
    case: CaseInput,
    buying_triggers: dict,
    emotion_analysis: dict,
    sns_fit: dict,
    risk_analysis: dict,
    target_categories: list,
) -> str:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"報酬: {case.reward}円\n"
        f"SNS投稿可否: {case.sns_allowed}"
    )

    template = load_prompt("appeal_generation_prompt.md")
    categories_str = " / ".join(target_categories)

    return (
        template
        .replace("{case_summary}", case_summary)
        .replace("{buying_triggers}", json.dumps(buying_triggers, ensure_ascii=False))
        .replace("{emotion_analysis}", json.dumps(emotion_analysis, ensure_ascii=False))
        .replace("{sns_fit}", json.dumps(sns_fit, ensure_ascii=False))
        .replace("{risk_analysis}", json.dumps(risk_analysis, ensure_ascii=False))
        .replace(
            "以下の10カテゴリについて、それぞれ10件ずつ訴求フックを生成してください。\n合計100件です。",
            f"以下の{len(target_categories)}カテゴリについて、それぞれ10件ずつ訴求フックを生成してください。\n合計{len(target_categories) * 10}件です。\n\n対象カテゴリ: {categories_str}",
        )
        .replace(
            "注意: 必ず全10カテゴリ×10件 = 100件を生成すること。",
            f"注意: 必ず指定された{len(target_categories)}カテゴリ×10件 = {len(target_categories) * 10}件を生成すること。",
        )
    )


def generate(
    case: CaseInput,
    buying_triggers: dict,
    emotion_analysis: dict,
    sns_fit: dict,
    risk_analysis: dict,
    llm: LLMClient,
) -> list:
    all_appeals = []

    for batch_categories in BATCHES:
        prompt = _build_prompt(
            case, buying_triggers, emotion_analysis,
            sns_fit, risk_analysis, batch_categories,
        )
        result = llm.call_json(prompt, SYSTEM)
        raw_appeals = result.get("appeals", [])

        for a in raw_appeals:
            all_appeals.append({
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

    return all_appeals
