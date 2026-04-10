from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.app.ingestion.matcher.rule_engine import normalize_listing_title

logger = logging.getLogger(__name__)

try:
    from anthropic import Anthropic
    from anthropic import RateLimitError as AnthropicRateLimitError
except ImportError:  # pragma: no cover - exercised by local environment fallback
    Anthropic = None
    AnthropicRateLimitError = None


def _log_json(level: int, event: str, **fields: object) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, default=str, sort_keys=True))


SYSTEM_PROMPT = """You are an expert trading card identifier for Flashcard Planet.
Given raw eBay listing titles, extract structured card identity fields.

Rules:
- game is always "Pokemon" for this pipeline
- grade_company: PSA / BGS / CGC / SGC only, null if raw
- grade_score: numeric only, null if ungraded
- variant: SAR / IR / UR / HR / FA / Alt Art / Rainbow / Full Art, null if standard
- language: EN / JP / KR / ZH / DE / FR, default EN if unclear
- confidence: 0.0-1.0
- card_number: exact format like 199/165 or null if unknown
- Respond with strict JSON only.
"""

FEW_SHOT_EXAMPLES = """[
  {
    "title": "Pokemon Charizard ex SAR 199/165 SV151 PSA 10",
    "result": {
      "name": "Charizard ex",
      "set_name": "Scarlet & Violet 151",
      "card_number": "199/165",
      "variant": "SAR",
      "grade_company": "PSA",
      "grade_score": 10.0,
      "language": "EN",
      "confidence": 0.97
    }
  },
  {
    "title": "PIKACHU FULL ART PROMO JAPANESE MINT",
    "result": {
      "name": "Pikachu",
      "set_name": null,
      "card_number": null,
      "variant": "Full Art",
      "grade_company": null,
      "grade_score": null,
      "language": "JP",
      "confidence": 0.61
    }
  }
]"""


class AiListingPayload(BaseModel):
    title: str
    name: str | None = None
    set_name: str | None = None
    card_number: str | None = None
    variant: str | None = None
    language: str | None = None
    grade_company: str | None = None
    grade_score: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class AiBatchPayload(BaseModel):
    results: list[AiListingPayload]


@dataclass(slots=True)
class AiMatchResult:
    raw_title: str
    normalized_title: str
    name: str | None
    set_name: str | None
    card_number: str | None
    variant: str | None
    language: str | None
    grade_company: str | None
    grade_score: Decimal | None
    confidence: Decimal
    status: str
    method: str


def map_batch(titles: list[str]) -> list[AiMatchResult]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not titles:
        return []
    if not api_key or Anthropic is None:
        _log_json(
            logging.WARNING,
            "ai_mapper_unavailable",
            missing_api_key=(not bool(api_key)),
            anthropic_imported=(Anthropic is not None),
        )
        return [_pending_result(title) for title in titles]

    batch_size = max(int(os.getenv("AI_BATCH_SIZE", "20")), 1)
    client = Anthropic(api_key=api_key)
    mapped: list[AiMatchResult] = []
    for start in range(0, len(titles), batch_size):
        batch = titles[start : start + batch_size]
        mapped.extend(_map_batch_with_client(client, batch))
    return mapped


def _map_batch_with_client(client: Any, titles: list[str]) -> list[AiMatchResult]:
    user_prompt = {
        "titles": [{"index": index + 1, "title": title} for index, title in enumerate(titles)],
        "instructions": "Return JSON object {\"results\": [...]} with one result per title in the same order.",
    }
    delays = [0.5, 1.0, 2.0, 4.0]
    last_error: Exception | None = None
    for attempt, delay in enumerate([0.0, *delays], start=1):
        if delay:
            time.sleep(delay)
        try:
            response = client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                max_tokens=int(os.getenv("AI_MAX_TOKENS", "4096")),
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": FEW_SHOT_EXAMPLES,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": json.dumps(user_prompt)}],
                    }
                ],
            )
            text_payload = "".join(
                block.text for block in getattr(response, "content", []) if getattr(block, "type", None) == "text"
            )
            parsed = AiBatchPayload.model_validate(json.loads(text_payload))
            return _to_results(parsed, titles)
        except ValidationError as exc:
            _log_json(logging.WARNING, "ai_mapper_validation_failed", error=str(exc))
            return [_pending_result(title) for title in titles]
        except json.JSONDecodeError as exc:
            _log_json(logging.WARNING, "ai_mapper_json_decode_failed", error=str(exc))
            return [_pending_result(title) for title in titles]
        except Exception as exc:  # noqa: BLE001
            if AnthropicRateLimitError is not None and isinstance(exc, AnthropicRateLimitError) and attempt <= len(delays):
                last_error = exc
                continue
            _log_json(logging.WARNING, "ai_mapper_request_failed", error_type=type(exc).__name__, message=str(exc))
            return [_pending_result(title) for title in titles]
    _log_json(
        logging.WARNING,
        "ai_mapper_rate_limited",
        error_type=type(last_error).__name__ if last_error is not None else "UnknownError",
        message=str(last_error) if last_error is not None else "",
    )
    return [_pending_result(title) for title in titles]


def _to_results(payload: AiBatchPayload, titles: list[str]) -> list[AiMatchResult]:
    indexed = {item.title: item for item in payload.results}
    results: list[AiMatchResult] = []
    for title in titles:
        item = indexed.get(title)
        if item is None:
            results.append(_pending_result(title))
            continue
        grade_score: Decimal | None = None
        if item.grade_score is not None:
            try:
                grade_score = Decimal(str(item.grade_score))
            except InvalidOperation:
                grade_score = None
        confidence = Decimal(str(item.confidence)).quantize(Decimal("0.001"))
        status = "mapped" if confidence >= Decimal(os.getenv("AI_CONFIDENCE_THRESHOLD_REVIEW", "0.50")) else "review"
        results.append(
            AiMatchResult(
                raw_title=title,
                normalized_title=normalize_listing_title(title),
                name=item.name,
                set_name=item.set_name,
                card_number=item.card_number,
                variant=item.variant,
                language=item.language or "EN",
                grade_company=item.grade_company,
                grade_score=grade_score,
                confidence=confidence,
                status=status,
                method="ai",
            )
        )
    return results


def _pending_result(title: str) -> AiMatchResult:
    return AiMatchResult(
        raw_title=title,
        normalized_title=normalize_listing_title(title),
        name=None,
        set_name=None,
        card_number=None,
        variant=None,
        language="EN",
        grade_company=None,
        grade_score=None,
        confidence=Decimal("0.000"),
        status="pending",
        method="ai",
    )
