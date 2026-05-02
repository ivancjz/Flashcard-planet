"""IP / franchise tagger using OpenAI structured JSON output.

Tags TCG assets with franchise, character, theme, and artist metadata.
Foundation for Phase 3 Cross-TCG Franchise Move signals.

Entry points:
  tag_asset_for_ip(name, game, set_name)  -> IPTagResult | None
  run_ip_tagging_sample(db, n)            -> IPTagSampleResult (for validation)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from backend.app.services.llm_provider import _setting_value

logger = logging.getLogger(__name__)

_OPENAI_BASE_URL = "https://api.openai.com/v1"

_IP_TAG_SYSTEM = """You are a TCG card metadata expert.
Given a card name, game, and set name, output a JSON object with:
  franchise: the IP / brand franchise (e.g. "Pokemon", "Yu-Gi-Oh!")
  character:  the primary character or card name (e.g. "Charizard", "Blue-Eyes White Dragon")
  themes:     array of up to 3 thematic tags (e.g. ["fire", "dragon", "starter"])
  artist:     card illustrator name if known, else null

Respond with valid JSON only. No markdown fences."""

_IP_TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "franchise": {"type": "string"},
        "character":  {"type": "string"},
        "themes":     {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "artist":     {"type": ["string", "null"]},
    },
    "required": ["franchise", "character", "themes", "artist"],
    "additionalProperties": False,
}


@dataclass
class IPTagResult:
    franchise: str
    character: str
    themes: list[str]
    artist: str | None
    asset_name: str = ""
    game: str = ""
    set_name: str = ""


@dataclass
class IPTagSampleResult:
    total_attempted: int
    total_succeeded: int  # parsed valid JSON — NOT verified for correctness
    total_failed: int     # API error or unparseable response
    results: list[dict] = field(default_factory=list)

    @property
    def api_parse_success_rate(self) -> float:
        """Fraction of calls that returned parseable JSON. Not the same as tag accuracy."""
        if self.total_attempted == 0:
            return 0.0
        return self.total_succeeded / self.total_attempted


def tag_asset_for_ip(name: str, game: str, set_name: str) -> IPTagResult | None:
    """Call OpenAI with JSON schema enforcement to tag a single asset.

    Uses gpt-5.5 with response_format json_schema for strict output.
    Returns None on any failure — caller must handle gracefully.
    """
    api_key = _setting_value("OPENAI_API_KEY", "openai_api_key")
    if not api_key:
        logger.info("ip_tagger_skipped_no_openai_key")
        return None

    model = _setting_value("OPENAI_MODEL", "openai_model", "gpt-5.5")
    user_msg = f"Card: {name}\nGame: {game}\nSet: {set_name}"

    try:
        with httpx.Client(base_url=_OPENAI_BASE_URL, timeout=20.0) as client:
            resp = client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": _IP_TAG_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 256,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ip_tag",
                            "strict": True,
                            "schema": _IP_TAG_SCHEMA,
                        },
                    },
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(raw)
            return IPTagResult(
                franchise=data.get("franchise", ""),
                character=data.get("character", ""),
                themes=data.get("themes", []),
                artist=data.get("artist"),
                asset_name=name,
                game=game,
                set_name=set_name,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ip_tagger_failed name=%s error=%s", name, exc)
        return None


def run_ip_tagging_sample(db, n: int = 100) -> IPTagSampleResult:
    """Run the IP tagging validation experiment on N random assets.

    Samples n/2 Pokemon + n/2 YGO assets (or fewer if not available).
    Returns a structured result the admin endpoint can serve as JSON.
    """
    from sqlalchemy import func, text  # local import avoids circular dependency

    half = n // 2

    rows = db.execute(text("""
        (SELECT id, name, game,
                COALESCE(metadata->>'set_name', metadata->'set'->>'name', '') AS set_name
         FROM assets WHERE game = 'pokemon' ORDER BY random() LIMIT :half)
        UNION ALL
        (SELECT id, name, game,
                COALESCE(metadata->>'set_name', metadata->'set'->>'name', '') AS set_name
         FROM assets WHERE game = 'yugioh' ORDER BY random() LIMIT :half)
    """), {"half": half}).fetchall()

    sample = IPTagSampleResult(
        total_attempted=len(rows),
        total_succeeded=0,
        total_failed=0,
    )

    for row in rows:
        result = tag_asset_for_ip(row.name, row.game, row.set_name or "")
        entry: dict = {
            "asset_id": str(row.id),
            "name": row.name,
            "game": row.game,
            "set_name": row.set_name,
        }
        if result is not None:
            sample.total_succeeded += 1
            entry["tag"] = {
                "franchise": result.franchise,
                "character": result.character,
                "themes": result.themes,
                "artist": result.artist,
            }
        else:
            sample.total_failed += 1
            entry["tag"] = None
        sample.results.append(entry)

    return sample
