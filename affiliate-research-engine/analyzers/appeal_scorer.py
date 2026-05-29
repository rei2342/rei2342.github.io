import json

from core.llm_client import LLMClient
from core.storage import load_prompt


SYSTEM = "あなたはSNSアフィリエイトの訴求評価専門家です。JSONのみで回答してください。"


def score_and_rank(
    appeals: list,
    buying_triggers: dict,
    emotion_analysis: dict,
    sns_fit: dict,
    risk_analysis: dict,
    llm: LLMClient,
) -> tuple[list, list]:
    """
    Returns:
        scored_appeals: all 100 appeals with score/reason/repeatability merged in
        top_appeals: top 10 by score, with enriched fields
    """
    # Minimal payload per appeal to save tokens
    appeals_list = [
        {
            "appeal_id": a["appeal_id"],
            "appeal_type": a["appeal_type"],
            "hook": a["hook"],
            "platform": a["platform"],
            "risk": a["risk"],
        }
        for a in appeals
    ]

    template = load_prompt("appeal_scoring_prompt.md")
    prompt = (
        template
        .replace("{buying_triggers}", json.dumps(buying_triggers, ensure_ascii=False))
        .replace("{emotion_analysis}", json.dumps(emotion_analysis, ensure_ascii=False))
        .replace("{sns_fit}", json.dumps(sns_fit, ensure_ascii=False))
        .replace("{risk_analysis}", json.dumps(risk_analysis, ensure_ascii=False))
        .replace("{appeals_list}", json.dumps(appeals_list, ensure_ascii=False, indent=2))
    )

    result = llm.call_json(prompt, SYSTEM)
    scores_map = {s["appeal_id"]: s for s in result.get("scores", [])}

    # Merge scores back into full appeals
    scored_appeals = []
    for appeal in appeals:
        aid = appeal["appeal_id"]
        score_data = scores_map.get(aid, {})
        merged = dict(appeal)
        merged["appeal_score"] = score_data.get("score", 0)
        merged["appeal_score_reason"] = score_data.get("reason", "")
        merged["content_repeatability"] = score_data.get("content_repeatability", "medium")
        merged["repeatability_reason"] = score_data.get("repeatability_reason", "")
        scored_appeals.append(merged)

    # Sort by score descending
    scored_appeals.sort(key=lambda x: x["appeal_score"], reverse=True)

    # Build top 10
    top_appeals = []
    for rank, appeal in enumerate(scored_appeals[:10], start=1):
        top_appeals.append({
            "rank": rank,
            "appeal_id": appeal["appeal_id"],
            "appeal_type": appeal["appeal_type"],
            "hook": appeal["hook"],
            "appeal_score": appeal["appeal_score"],
            "appeal_score_reason": appeal["appeal_score_reason"],
            "content_repeatability": appeal["content_repeatability"],
            "repeatability_reason": appeal["repeatability_reason"],
            "platform": appeal["platform"],
            "target_emotion": appeal["target_emotion"],
            "risk": appeal["risk"],
        })

    return scored_appeals, top_appeals
