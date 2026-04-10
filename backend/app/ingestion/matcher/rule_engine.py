from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from decimal import Decimal

from backend.app.ingestion.matcher.catalog import CatalogCard, get_catalog, normalize_catalog_text

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - exercised by local environment fallback
    fuzz = None

NOISE_TOKENS = {
    "wow",
    "free",
    "ship",
    "shipping",
    "look",
    "read",
    "nm",
    "mint",
    "graded",
    "card",
    "pokemon",
    "tcg",
    "rare",
    "holo",
    "gem",
    "pristine",
    "authentic",
}
LANGUAGE_TOKENS = {
    "japanese": "JP",
    "jp": "JP",
    "english": "EN",
    "eng": "EN",
    "korean": "KR",
    "kr": "KR",
    "chinese": "ZH",
    "german": "DE",
    "french": "FR",
}
GRADE_COMPANIES = {"PSA", "BGS", "CGC", "SGC"}
CARD_NUMBER_RE = re.compile(r"\b\d{1,3}/\d{1,3}\b", re.IGNORECASE)
GRADE_RE = re.compile(r"\b(PSA|BGS|CGC|SGC)\s*(10|9(?:\.5)?|8(?:\.5)?|7(?:\.5)?)\b", re.IGNORECASE)
VARIANT_RE = re.compile(r"\b(SAR|SIR|IR|UR|HR|FA|FULL ART|ALT ART|ALTERNATE ART|RAINBOW)\b", re.IGNORECASE)


@dataclass(slots=True)
class RuleMatchResult:
    raw_title: str
    normalized_title: str
    asset_external_id: str | None
    name: str | None
    set_name: str | None
    card_number: str | None
    language: str | None
    variant: str | None
    grade_company: str | None
    grade_score: Decimal | None
    year: int | None
    confidence: Decimal
    should_use_ai: bool
    matched: bool
    method: str


def normalize_listing_title(title: str) -> str:
    stripped = normalize_catalog_text(title)
    tokens = [token for token in stripped.split() if token not in NOISE_TOKENS]
    return " ".join(tokens)


def match_batch(titles: list[str]) -> list[RuleMatchResult]:
    cards = get_catalog().get_cards()
    return [_match_single(title, cards) for title in titles]


def _match_single(title: str, cards: list[CatalogCard]) -> RuleMatchResult:
    normalized_title = normalize_listing_title(title)
    language = _extract_language(title)
    variant = _extract_variant(title)
    grade_company, grade_score = _extract_grade(title)
    card_number = _extract_card_number(title)

    best_card: CatalogCard | None = None
    best_ratio = -1.0
    for card in cards:
        ratio = _ratio(normalized_title, normalize_catalog_text(card.name))
        if ratio > best_ratio:
            best_ratio = ratio
            best_card = card

    score = Decimal("0.000")
    if best_ratio >= 85.0:
        score += Decimal("0.500")
    elif best_ratio >= 70.0:
        score += Decimal("0.350")
    elif best_ratio >= 55.0:
        score += Decimal("0.200")

    if best_card is not None and best_card.set_name and normalize_catalog_text(best_card.set_name) in normalized_title:
        score += Decimal("0.200")
    if best_card is not None and card_number and best_card.card_number and card_number.casefold() == best_card.card_number.casefold():
        score += Decimal("0.200")
    if language is not None:
        score += Decimal("0.050")
    if grade_company is not None and grade_score is not None:
        score += Decimal("0.050")

    confidence = min(score, Decimal("1.000")).quantize(Decimal("0.001"))
    matched = best_card is not None and confidence >= Decimal("0.750")
    return RuleMatchResult(
        raw_title=title,
        normalized_title=normalized_title,
        asset_external_id=best_card.external_id if best_card is not None else None,
        name=best_card.name if best_card is not None else None,
        set_name=best_card.set_name if best_card is not None else None,
        card_number=best_card.card_number if best_card is not None else card_number,
        language=language or (best_card.language if best_card is not None else "EN"),
        variant=variant,
        grade_company=grade_company,
        grade_score=grade_score,
        year=best_card.year if best_card is not None else None,
        confidence=confidence,
        should_use_ai=confidence < Decimal("0.750"),
        matched=matched,
        method="rule",
    )


def _ratio(left: str, right: str) -> float:
    if fuzz is not None:
        return float(fuzz.token_sort_ratio(left, right))
    left_tokens = " ".join(sorted(left.split()))
    right_tokens = " ".join(sorted(right.split()))
    return SequenceMatcher(None, left_tokens, right_tokens).ratio() * 100.0


def _extract_language(title: str) -> str | None:
    lowered = normalize_catalog_text(title)
    for token, code in LANGUAGE_TOKENS.items():
        if token in lowered.split():
            return code
    return None


def _extract_card_number(title: str) -> str | None:
    match = CARD_NUMBER_RE.search(title)
    return match.group(0) if match else None


def _extract_grade(title: str) -> tuple[str | None, Decimal | None]:
    match = GRADE_RE.search(title)
    if not match:
        return None, None
    company = match.group(1).upper()
    if company not in GRADE_COMPANIES:
        return None, None
    return company, Decimal(match.group(2))


def _extract_variant(title: str) -> str | None:
    match = VARIANT_RE.search(title)
    if not match:
        return None
    variant = match.group(1).upper()
    if variant == "ALTERNATE ART":
        return "Alt Art"
    if variant == "FULL ART":
        return "Full Art"
    return variant.title() if " " in variant else variant
