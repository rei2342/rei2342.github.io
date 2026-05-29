import json

from core.llm_client import LLMClient
from core.storage import load_prompt


SYSTEM = "あなたはSNSアフィリエイトの訴求評価専門家です。JSONのみで回答してください。"

BATCH_SIZE = 50


def _score_batch(
    appeals_batch: list,
    buying_triggers: dict,
    emotion_analysis: dict,
    sns_fit: dict,
    risk_analysis: dict,
    llm: LLMClient,
) -> dict:
    appeals_list = [
        {
            "appeal_id": a["appeal_id"],
            "appeal_type": a["appeal_type"],
            "hook": a["hook"],
            "platform": a["platform"],
            "risk": a["risk"],
        }
        for a in appeals_batch
    ]

    template = load_prompt("appeal_scoring_prompt.md")
    prompt = (
        template
        .replace("{buying_triggers}", json.dumps(buying_triggers, ensure_ascii=False))
        .replace("{emotion_analysis}", json.dumps(emotion_analysis, ensure_ascii=False))
        .replace("{sns_fit}", json.dumps(sns_fit, ensure_ascii=False))
        .replace("{risk_analysis}", json.dumps(risk_analysis, ensure_ascii=False))
        .replace("{appeals_list}", json.dumps(appeals_list, ensure_ascii=False, indent=2))
        # Clarify batch size in prompt
        .replace(
            "100件の中での**相対評価**で採点すること",
            f"このバッチ{len(appeals_batch)}件の中での**相対評価**で採点すること",
        )
        .replace(
            "上位10件はスコア80以上になることが望ましい",
            f"上位{max(1, len(appeals_batch)//10)}件はスコア80以上になることが望ましい",
        )
    )

    result = llm.call_json(prompt, SYSTEM)
    return {s["appeal_id"]: s for s in result.get("scores", [])}


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
        scored_appeals: all appeals with score/reason/repeatability merged in
        top_appeals: top 10 by score, with enriched fields
    """
    # Split into batches to stay within token limits
    scores_map = {}
    for i in range(0, len(appeals), BATCH_SIZE):
        batch = appeals[i: i + BATCH_SIZE]
        batch_scores = _score_batch(
            batch, buying_triggers, emotion_analysis, sns_fit, risk_analysis, llm
        )
        scores_map.update(batch_scores)

    # Merge scores back into full appeals
    scored_appeals = []
    for appeal in appeals:
        aid = appeal["appeal_id"]
        s = scores_map.get(aid, {})
        merged = dict(appeal)
        merged["appeal_score"] = int(s.get("score") or 0)
        merged["appeal_score_reason"] = s.get("reason", "")
        merged["content_repeatability"] = s.get("content_repeatability", "medium")
        merged["repeatability_reason"] = s.get("repeatability_reason", "")
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
