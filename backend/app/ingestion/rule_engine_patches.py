"""
backend/app/ingestion/rule_engine_patches.py  — B2

Patches for rule_engine.py — mapping quality improvements.

Four additions:
  1. GRADED_CARD_FILTER   — PSA/BGS/CGC/SGC listings never match raw assets
  2. VARIANT_EXTRACTOR    — Holo/RH/1st Ed extracted before scoring
  3. LANGUAGE_DETECTOR    — JP/KR/FR/DE/ES/IT/PT/ZH listings flagged
  4. NOISE_EXPANSION      — additional noise tokens + confidence penalty

Integration: call preflight_observation(title) before stage_observation_match().
Use result.normalised_title as input to the rule engine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# 1. GRADED CARD FILTER
# ─────────────────────────────────────────────────────────────────────────────

_GRADER_PATTERN = re.compile(
    r"\b(PSA|BGS|CGC|SGC|CSG|HGA|GAI|BECKETT)(?:\b|\d)",
    re.IGNORECASE,
)
_GRADE_VALUE_PATTERN = re.compile(
    r"\b(PSA|BGS|CGC|SGC|CSG|HGA|GAI|BECKETT)\s*(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


def is_graded_listing(title: str) -> bool:
    """Return True if the title indicates a graded (slabbed) card."""
    return bool(_GRADER_PATTERN.search(title))


def extract_grade_info(title: str) -> dict | None:
    """Extract grader and grade value if present."""
    m = _GRADE_VALUE_PATTERN.search(title)
    if m:
        return {"grader": m.group(1).upper(), "grade": float(m.group(2))}
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. VARIANT EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

class CardVariant(str, Enum):
    BASE          = "base"
    HOLO          = "holo"
    REVERSE_HOLO  = "reverse_holo"
    FIRST_EDITION = "first_edition"
    SHADOWLESS    = "shadowless"
    UNLIMITED     = "unlimited"
    PROMO         = "promo"
    FULL_ART      = "full_art"
    SECRET_RARE   = "secret_rare"


_VARIANT_PATTERNS: list[tuple[CardVariant, re.Pattern]] = [
    (CardVariant.FIRST_EDITION, re.compile(r"\b(1st\s*ed(?:ition)?|first\s*edition)\b", re.I)),
    (CardVariant.SHADOWLESS,    re.compile(r"\bshadowless\b", re.I)),
    (CardVariant.REVERSE_HOLO,  re.compile(r"\b(reverse\s*holo(?:graphic)?|rev\.?\s*holo|rh\b)", re.I)),
    (CardVariant.FULL_ART,      re.compile(r"\b(full\s*art|alternate\s*art|alt\s*art|aa\b)\b", re.I)),
    (CardVariant.SECRET_RARE,   re.compile(r"\b(secret\s*rare|rainbow\s*rare|hyper\s*rare)\b", re.I)),
    (CardVariant.PROMO,         re.compile(r"\bpromo\b", re.I)),
    (CardVariant.HOLO,          re.compile(r"\bholo(?:graphic)?\b", re.I)),
    (CardVariant.UNLIMITED,     re.compile(r"\bunlimited\b", re.I)),
]


@dataclass
class VariantExtractionResult:
    variant: CardVariant
    matched_pattern: str
    title_without_variant: str


def extract_variant(title: str) -> VariantExtractionResult:
    """Identify the card variant from a listing title; strip the matched token."""
    for variant, pattern in _VARIANT_PATTERNS:
        m = pattern.search(title)
        if m:
            cleaned = pattern.sub("", title).strip()
            cleaned = re.sub(r"\s{2,}", " ", cleaned)
            return VariantExtractionResult(
                variant=variant,
                matched_pattern=m.group(0),
                title_without_variant=cleaned,
            )
    return VariantExtractionResult(
        variant=CardVariant.BASE,
        matched_pattern="",
        title_without_variant=title,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. LANGUAGE DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

class CardLanguage(str, Enum):
    EN = "en"
    JP = "jp"
    KR = "kr"
    FR = "fr"
    DE = "de"
    ES = "es"
    IT = "it"
    PT = "pt"
    ZH = "zh"


_LANGUAGE_PATTERNS: list[tuple[CardLanguage, re.Pattern]] = [
    (CardLanguage.JP, re.compile(
        r"\b(japanese|japan|japanese\s*ver(?:sion)?|jp\s*ver(?:sion)?|"
        r"japanese\s*card|japanese\s*pokemon)\b", re.I
    )),
    (CardLanguage.KR, re.compile(r"\b(korean|korea|kr\s*ver(?:sion)?|korean\s*card)\b", re.I)),
    (CardLanguage.FR, re.compile(r"\b(french|fran[çc]ais|fr\s*ver(?:sion)?|french\s*card)\b", re.I)),
    (CardLanguage.DE, re.compile(r"\b(german|deutsch|de\s*ver(?:sion)?|german\s*card)\b", re.I)),
    (CardLanguage.ES, re.compile(r"\b(spanish|espa[ñn]ol|es\s*ver(?:sion)?|spanish\s*card)\b", re.I)),
    (CardLanguage.IT, re.compile(r"\b(italian|italiano|it\s*ver(?:sion)?|italian\s*card)\b", re.I)),
    (CardLanguage.PT, re.compile(r"\b(portuguese|portugu[eê]s|pt\s*ver(?:sion)?)\b", re.I)),
    (CardLanguage.ZH, re.compile(
        r"\b(chinese|mandarin|zh\s*ver(?:sion)?|traditional\s*chinese|simplified\s*chinese)\b", re.I
    )),
]

_NON_ASCII_RATIO_THRESHOLD = 0.15


def detect_language(title: str) -> CardLanguage:
    """Detect the language of a listing title. Returns EN if no marker found."""
    for lang, pattern in _LANGUAGE_PATTERNS:
        if pattern.search(title):
            return lang
    if len(title) > 0:
        non_ascii = sum(1 for c in title if ord(c) > 127)
        if non_ascii / len(title) > _NON_ASCII_RATIO_THRESHOLD:
            return CardLanguage.JP
    return CardLanguage.EN


# ─────────────────────────────────────────────────────────────────────────────
# 4. NOISE EXPANSION + CONFIDENCE PENALTY
# ─────────────────────────────────────────────────────────────────────────────

ADDITIONAL_NOISE_TOKENS: frozenset[str] = frozenset({
    "nm", "nm/mt", "near", "mint", "lp", "lightly", "played",
    "mp", "moderately", "hp", "heavily", "damaged", "poor",
    "excellent", "vg", "very", "good", "fair",
    "lot", "bundle", "bulk", "collection", "set", "pack",
    "sealed", "booster", "tin", "box",
    "free", "shipping", "fast", "combined", "tracked",
    "authentic", "genuine", "official", "oem",
    "scan", "actual", "photo", "shown", "pictured",
    "ungraded", "raw", "unslabbed",
    "pokemon", "card", "cards", "tcg", "trading",
    "expansion", "base", "edition",
})


@dataclass
class ConfidencePenalty:
    amount: float
    reason: str


def confidence_penalty(title: str, raw_confidence: float) -> ConfidencePenalty:
    """
    Apply downward confidence adjustment for ambiguous titles.
    Called after main scoring, before the 0.750 threshold check.
    """
    penalties: list[ConfidencePenalty] = []

    if re.search(r"\b(lot|bundle|bulk|collection)\b", title, re.I):
        penalties.append(ConfidencePenalty(0.15, "lot/bundle listing"))

    if len(title.split()) <= 3:
        penalties.append(ConfidencePenalty(0.10, "very short title"))

    if not re.search(r"\b\d+/\d+\b|\b[a-z]{2,4}\d+-\d+\b", title, re.I):
        penalties.append(ConfidencePenalty(0.05, "no collector number in title"))

    if not penalties:
        return ConfidencePenalty(0.0, "no penalty")

    total = min(sum(p.amount for p in penalties), raw_confidence)
    reasons = "; ".join(p.reason for p in penalties)
    return ConfidencePenalty(total, reasons)


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION SHIM
# ─────────────────────────────────────────────────────────────────────────────

class ObservationSkipReason(str, Enum):
    GRADED_CARD      = "graded_card"
    NON_ENGLISH      = "non_english"
    VARIANT_NO_POOL  = "variant_no_pool"


@dataclass
class PreflightResult:
    should_skip: bool = False
    skip_reason: ObservationSkipReason | None = None
    language: CardLanguage = CardLanguage.EN
    variant: CardVariant = CardVariant.BASE
    grade_info: dict | None = None
    normalised_title: str = ""


def preflight_observation(title: str) -> PreflightResult:
    """
    Run all pre-flight checks on a raw eBay listing title.

    Call before stage_observation_match(). Pass normalised_title to the rule engine.
    Graded cards and non-English listings are skipped immediately.
    Variant detection annotates but does not skip.
    """
    result = PreflightResult(normalised_title=title)

    if is_graded_listing(title):
        result.should_skip = True
        result.skip_reason = ObservationSkipReason.GRADED_CARD
        result.grade_info = extract_grade_info(title)
        return result

    lang = detect_language(title)
    result.language = lang
    if lang != CardLanguage.EN:
        result.should_skip = True
        result.skip_reason = ObservationSkipReason.NON_ENGLISH
        return result

    variant_result = extract_variant(title)
    result.variant = variant_result.variant
    result.normalised_title = variant_result.title_without_variant

    return result
