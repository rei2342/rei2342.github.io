import json
import uuid
from datetime import datetime, timezone

from core.llm_client import LLMClient
from core.storage import load_prompt
from core.input_loader import CaseInput
import config


SYSTEM = "あなたはアフィリエイト案件評価の専門家です。JSONのみで回答してください。"


def _empty_validation() -> dict:
    return {
        "tested": False,
        "status": "pending",
        "posts_created": 0,
        "impressions": 0,
        "engagements": 0,
        "profile_visits": 0,
        "link_clicks": 0,
        "conversions": 0,
        "revenue": 0,
        "memo": "",
    }


def _compute_creator_priority_score(
    case_score_obj: dict,
    startup_fit: dict,
    cef: dict,
    account_fit: dict | None = None,
    creator_fit: dict | None = None,
) -> int | None:
    case_score = int(case_score_obj.get("total") or 0)
    automation_fit = int(case_score_obj.get("automation_fit") or 0)
    sf_score = startup_fit.get("score") if startup_fit else None
    zcv = (startup_fit.get("zero_cost_validation_score") or {}) if startup_fit else {}
    zero_cost_total = zcv.get("total")
    cef_score = cef.get("score") if cef else None

    if sf_score is None or zero_cost_total is None or cef_score is None:
        return None

    zero_cost_norm = round(zero_cost_total / 1.2)
    has_af = account_fit and account_fit.get("score") is not None
    has_cf = creator_fit and creator_fit.get("score") is not None

    if has_af and has_cf:
        af_score = int(account_fit.get("score") or 0)
        cf_score = int(creator_fit.get("score") or 0)
        return round(
            (case_score + automation_fit + sf_score + zero_cost_norm + cef_score + af_score + cf_score) / 7
        )
    elif has_af:
        af_score = int(account_fit.get("score") or 0)
        return round(
            (case_score + automation_fit + sf_score + zero_cost_norm + cef_score + af_score) / 6
        )
    elif has_cf:
        cf_score = int(creator_fit.get("score") or 0)
        return round(
            (case_score + automation_fit + sf_score + zero_cost_norm + cef_score + cf_score) / 6
        )
    else:
        return round(
            case_score * 0.2
            + automation_fit * 0.2
            + sf_score * 0.2
            + zero_cost_norm * 0.2
            + cef_score * 0.2
        )


def _compute_scores(
    case: CaseInput,
    lp_analysis: dict,
    market_analysis: dict,
    buying_triggers: dict,
    sns_fit: dict,
    risk_analysis: dict,
    llm: LLMClient,
) -> dict:
    case_summary = (
        f"案件名: {case.case_name}\n"
        f"ジャンル: {case.category}\n"
        f"報酬: {case.reward}円"
    )

    template = load_prompt("scoring_prompt.md")
    prompt = (
        template
        .replace("{case_summary}", case_summary)
        .replace("{lp_analysis}", json.dumps(lp_analysis, ensure_ascii=False))
        .replace("{market_analysis}", json.dumps(market_analysis, ensure_ascii=False))
        .replace("{buying_triggers}", json.dumps(buying_triggers, ensure_ascii=False))
        .replace("{sns_fit}", json.dumps(sns_fit, ensure_ascii=False))
        .replace("{risk_analysis}", json.dumps(risk_analysis, ensure_ascii=False))
    )

    return llm.call_json(prompt, SYSTEM)


def build(
    case: CaseInput,
    information_quality: dict,
    lp_analysis: dict,
    market_analysis: dict,
    buying_triggers_result: dict,
    sns_fit_result: dict,
    risk_result: dict,
    scored_appeals: list,
    top_appeals: list,
    winning_data: dict,
    startup_fit: dict,
    cef: dict,
    llm: LLMClient,
    account_fit: dict | None = None,
    creator_fit: dict | None = None,
) -> dict:
    scores = _compute_scores(
        case, lp_analysis, market_analysis,
        buying_triggers_result, sns_fit_result, risk_result, llm,
    )

    inferred = lp_analysis.get("inferred_notes", [])
    information_quality["inferred"] = inferred

    now = datetime.now(timezone.utc).isoformat()

    return {
        "meta": {
            "case_id": str(uuid.uuid4()),
            "case_name": case.case_name,
            "analyzed_at": now,
            "schema_version": config.SCHEMA_VERSION,
        },
        "information_quality": information_quality,
        "basic_info": {
            "case_name": case.case_name,
            "affiliate_url": case.affiliate_url,
            "asp_name": case.asp_name,
            "category": case.category,
            "reward": case.reward,
            "reward_rate": case.reward_rate,
            "epc": case.epc,
            "approval_rate": case.approval_rate,
            "conversion_condition": case.conversion_condition,
            "restrictions": case.restrictions,
            "sns_allowed": case.sns_allowed,
            "listing_allowed": case.listing_allowed,
            "pr_required": case.pr_required,
        },
        "lp_analysis": {
            "target_audience": lp_analysis.get("target_audience", ""),
            "pain_points": lp_analysis.get("pain_points", []),
            "desires": lp_analysis.get("desires", []),
            "fears": lp_analysis.get("fears", []),
            "benefits": lp_analysis.get("benefits", []),
            "price_justification": lp_analysis.get("price_justification", ""),
            "cta_strength": lp_analysis.get("cta_strength", "medium"),
            "trust_signals": lp_analysis.get("trust_signals", []),
            "exit_factors": lp_analysis.get("exit_factors", []),
        },
        "market_analysis": {
            "demand_strength": market_analysis.get("demand_strength", "medium"),
            "sns_compatibility": market_analysis.get("sns_compatibility", "medium"),
            "search_demand": market_analysis.get("search_demand", "medium"),
            "trend": market_analysis.get("trend", "stable"),
            "seasonality": market_analysis.get("seasonality"),
            "competition_level": market_analysis.get("competition_level", "medium"),
            "beginner_friendly": market_analysis.get("beginner_friendly", True),
            "testimonial_convertible": market_analysis.get("testimonial_convertible", True),
            "reasoning": market_analysis.get("reasoning", ""),
        },
        "buying_triggers": buying_triggers_result.get("buying_triggers", []),
        "emotion_analysis": sns_fit_result.get("emotion_analysis", {"primary": [], "secondary": []}),
        "sns_fit": sns_fit_result.get("sns_fit", {}),
        "algorithm_fit_reason": sns_fit_result.get("algorithm_fit_reason", {}),
        "scores": {
            "affiliate_score": scores.get("affiliate_score", 0),
            "platform_fit_scores": scores.get("platform_fit_scores", {}),
            "score_breakdown": scores.get("score_breakdown", {}),
            "score_reasoning": scores.get("score_reasoning", ""),
        },
        "case_score": winning_data.get("case_score", {}),
        "startup_fit": startup_fit,
        "cef": cef,
        "account_fit": account_fit or {},
        "creator_fit": creator_fit or {},
        "creator_priority_score": _compute_creator_priority_score(
            winning_data.get("case_score", {}), startup_fit, cef, account_fit, creator_fit
        ),
        "winning_summary": winning_data.get("winning_summary", {}),
        "risk_score": risk_result.get("risk_score", 0),
        "risk_factors": risk_result.get("risk_factors", []),
        "ai_content_risk": risk_result.get("ai_content_risk", {}),
        "top_appeals": top_appeals,
        "appeals": scored_appeals,
        "generated_posts": [],
        "human_feedback": {
            "selected_appeals": [],
            "rejected_appeals": [],
            "notes": "",
        },
        "performance": {
            "posted": False,
            "platform": None,
            "impressions": None,
            "likes": None,
            "bookmarks": None,
            "ctr": None,
            "cv": None,
            "comments": None,
            "posted_at": None,
        },
        "validation": _empty_validation(),
    }
