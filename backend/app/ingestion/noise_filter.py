from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - exercised by local environment fallback
    Anthropic = None


SYSTEM_PROMPT = """You classify trading card marketplace listing titles for an ingestion pipeline.

Decide whether each title is a real individual card listing or noise.

Return true only for real individual card listings, including graded singles and raw singles.
Return false for noise, including:
- bulk lots, mystery lots, or quantity-heavy listings like "50x pokemon cards"
- accessories like sleeves, binders, deck boxes, playmats, toploaders, stands, cases
- sealed product like booster packs, booster boxes, ETBs, tins, collections, promo boxes, blisters
- non-card items like digital codes, plush, figures, posters, clothing, coins, empty boxes

Respond with strict JSON only: a single JSON array of booleans in the same order as the input titles.
true = real individual card listing
false = noise
"""


def _log_json(level: int, event: str, **fields: object) -> None:
    payload = json.dumps({"event": event, **fields}, default=str, sort_keys=True)
    if level == logging.WARNING:
        logger.warning(payload)
        return
    logger.log(level, payload)


def filter_noise(titles: list[str]) -> list[bool]:
    if not titles:
        return []
    if Anthropic is None:
        _log_json(logging.WARNING, "noise_filter_unavailable", anthropic_imported=False)
        return [True] * len(titles)

    user_payload = [{"index": index + 1, "title": title} for index, title in enumerate(titles)]
    try:
        client = Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Classify each title and return only a JSON array of booleans in the same order.\n"
                                "Titles:\n"
                                + json.dumps(user_payload, ensure_ascii=False)
                            ),
                        }
                    ],
                }
            ],
        )
        text_payload = "".join(
            block.text for block in getattr(response, "content", []) if getattr(block, "type", None) == "text"
        ).strip()
        parsed = json.loads(text_payload)
        if not isinstance(parsed, list):
            raise ValueError("Noise filter response must be a JSON array.")
        if len(parsed) != len(titles):
            raise ValueError("Noise filter response length did not match input length.")
        if any(type(item) is not bool for item in parsed):
            raise ValueError("Noise filter response must contain only booleans.")
        return parsed
    except Exception as exc:  # noqa: BLE001
        _log_json(
            logging.WARNING,
            "noise_filter_failed",
            error_type=type(exc).__name__,
            message=str(exc),
            titles=len(titles),
        )
        return [True] * len(titles)
