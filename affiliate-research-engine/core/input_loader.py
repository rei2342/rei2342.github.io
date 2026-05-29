import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, field_validator


class CaseInput(BaseModel):
    case_name: str
    affiliate_url: Optional[str] = None
    lp_text: Optional[str] = None
    asp_name: Optional[str] = None
    reward: Optional[int] = None
    reward_type: Optional[str] = None
    reward_rate: Optional[float] = None
    reward_note: Optional[str] = None
    epc: Optional[float] = None
    approval_rate: Optional[float] = None
    cookie_period: Optional[int] = None
    category: str
    conversion_condition: Optional[str] = None
    restrictions: Optional[str] = None
    sns_allowed: Optional[bool] = None
    listing_allowed: Optional[bool] = None
    pr_required: Optional[bool] = None
    sns_examples: List[str] = []
    competitor_examples: List[str] = []

    @field_validator("case_name", "category")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


def load_case(path: str) -> CaseInput:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return CaseInput(**raw)


def generate_information_quality(case: CaseInput) -> dict:
    confirmed = []
    missing = []

    if case.reward is not None:
        confirmed.append(f"報酬単価は{case.reward}円")
    else:
        missing.append("報酬単価")

    if case.asp_name:
        confirmed.append(f"ASP名は「{case.asp_name}」")
    else:
        missing.append("ASP名")

    if case.lp_text:
        confirmed.append("LP本文あり（テキスト貼り付け）")
    elif case.affiliate_url:
        confirmed.append(f"アフィリエイトURL指定あり: {case.affiliate_url}")
    else:
        missing.append("LP本文またはアフィリエイトURL")

    if case.conversion_condition:
        confirmed.append(f"成果条件: {case.conversion_condition}")
    else:
        missing.append("成果条件")

    if case.restrictions:
        confirmed.append("禁止事項・規約情報あり")
    else:
        missing.append("禁止事項・規約情報")

    if case.sns_allowed is not None:
        confirmed.append(f"SNS投稿{'可' if case.sns_allowed else '不可'}")
    else:
        missing.append("SNS投稿可否")

    if case.listing_allowed is not None:
        confirmed.append(f"リスティング広告{'可' if case.listing_allowed else '不可'}")
    else:
        missing.append("リスティング広告可否")

    if case.pr_required is not None:
        confirmed.append(f"PR表記{'必要' if case.pr_required else '不要'}")
    else:
        missing.append("PR表記要否")

    if case.sns_examples:
        confirmed.append(f"SNS投稿例 {len(case.sns_examples)}件あり")
    else:
        missing.append("SNSで伸びている投稿例")

    if case.competitor_examples:
        confirmed.append(f"競合事例 {len(case.competitor_examples)}件あり")
    else:
        missing.append("競合記事・投稿例（任意）")

    return {
        "confirmed": confirmed,
        "inferred": [],  # LLM analysis later
        "missing": missing,
    }
