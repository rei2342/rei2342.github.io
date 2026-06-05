import json
import uuid
from datetime import datetime, timezone

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput


SYSTEM = "あなたはSNSアフィリエイトの投稿文生成専門家です。JSONのみで回答してください。"

VALID_PLATFORMS = {"x", "threads", "tiktok", "instagram", "note"}


def generate(
    case_data: dict,
    appeal_ids: list,
    platform: str,
    llm: LLMClient,
) -> list:
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Invalid platform: {platform}. Choose from {VALID_PLATFORMS}")

    appeals_map = {a["appeal_id"]: a for a in case_data.get("appeals", [])}

    missing_ids = [aid for aid in appeal_ids if aid not in appeals_map]
    if missing_ids:
        raise ValueError(f"Appeal IDs not found: {missing_ids}")

    case_summary = (
        f"案件名: {case_data['basic_info']['case_name']}\n"
        f"ジャンル: {case_data['basic_info']['category']}\n"
        f"報酬: {case_data['basic_info'].get('reward', '不明')}円\n"
        f"PR表記要否: {case_data['basic_info'].get('pr_required', '不明')}\n"
        f"成果条件: {case_data['basic_info'].get('conversion_condition', '不明')}"
    )

    template = load_prompt("post_generation_prompt.md")
    posts = []
    case_id = case_data["meta"]["case_id"]

    for appeal_id in appeal_ids:
        appeal = appeals_map[appeal_id]

        prompt = (
            template
            .replace("{case_summary}", case_summary)
            .replace("{appeal}", json.dumps(appeal, ensure_ascii=False))
            .replace("{platform}", platform)
        )

        result = llm.call_json(prompt, SYSTEM)
        now = datetime.now(timezone.utc).isoformat()

        posts.append({
            "post_id": str(uuid.uuid4()),
            "case_id": case_id,
            "appeal_id": appeal_id,
            "platform": platform,
            "content": result.get("content", ""),
            "generation_notes": result.get("notes", ""),
            "generated_at": now,
            "posted_at": None,
            "performance": {
                "impressions": None,
                "likes": None,
                "bookmarks": None,
                "comments": None,
                "ctr": None,
                "cv": None,
            },
        })

    return posts
