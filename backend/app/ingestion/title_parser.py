import re
from dataclasses import dataclass, field
from typing import Optional

from .market_segment import build_market_segment


@dataclass
class TitleParseResult:
    market_segment: str
    grade_company: Optional[str]
    grade_score: Optional[str]
    confidence: str                          # 'high', 'medium', 'low'
    parser_notes: list[str] = field(default_factory=list)
    excluded: bool = False                   # True = do not write to price_history


# Hard exclusions — these listings are not single-card sales
_EXCLUSION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bsealed\b', re.IGNORECASE), 'sealed'),
    (re.compile(r'\bbooster\s*pack\b', re.IGNORECASE), 'booster_pack'),
    (re.compile(r'\bbooster\s*box\b', re.IGNORECASE), 'booster_box'),
    (re.compile(r'\bbundle\b', re.IGNORECASE), 'bundle'),
    (re.compile(r'\bcard\s+lot\b', re.IGNORECASE), 'card_lot'),
    (re.compile(r'\bcards\s+lot\b', re.IGNORECASE), 'cards_lot'),
    (re.compile(r'\b\d+\s+cards\b', re.IGNORECASE), 'multi_card'),
    (re.compile(r'\bcustom\b', re.IGNORECASE), 'custom'),
    (re.compile(r'\bproxy\b', re.IGNORECASE), 'proxy'),
    (re.compile(r'\bsigned\b', re.IGNORECASE), 'signed'),
    (re.compile(r'\bautograph\b', re.IGNORECASE), 'autograph'),
]

# Grade detection — (pattern, company_name)
_GRADE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bpsa\s*[-]?\s*(\d+(?:\.\d+)?)\b', re.IGNORECASE), 'PSA'),
    (re.compile(r'\bbgs\s*[-]?\s*(\d+(?:\.\d+)?)\b', re.IGNORECASE), 'BGS'),
    (re.compile(r'\bcgc\s*[-]?\s*(\d+(?:\.\d+)?)\b', re.IGNORECASE), 'CGC'),
    (re.compile(r'\bsgc\s*[-]?\s*(\d+(?:\.\d+)?)\b', re.IGNORECASE), 'SGC'),
]

# Raw-card markers — boost confidence when no grade present
_RAW_MARKERS: list[re.Pattern] = [
    re.compile(r'\bnear\s*mint\b', re.IGNORECASE),
    re.compile(r'\bnm\b', re.IGNORECASE),
    re.compile(r'\bungraded\b', re.IGNORECASE),
    re.compile(r'\braw\b', re.IGNORECASE),
    re.compile(r'\blp\b', re.IGNORECASE),
    re.compile(r'\bmint\b', re.IGNORECASE),
]


def parse_listing_title(title: str) -> TitleParseResult:
    """
    Classify an eBay listing title into a market segment.

    Returns a TitleParseResult with:
      - market_segment and optional grade fields
      - confidence ('high', 'medium', 'low')
      - parser_notes for audit trail
      - excluded=True when the listing should not be written at all
    """
    if not title or not isinstance(title, str):
        return TitleParseResult(
            market_segment='unknown',
            grade_company=None,
            grade_score=None,
            confidence='low',
            parser_notes=['empty or invalid title'],
            excluded=True,
        )

    notes: list[str] = []

    # Step 1: Hard exclusions
    for pattern, exclusion_type in _EXCLUSION_PATTERNS:
        if pattern.search(title):
            notes.append(f'excluded: {exclusion_type}')
            return TitleParseResult(
                market_segment='unknown',
                grade_company=None,
                grade_score=None,
                confidence='high',
                parser_notes=notes,
                excluded=True,
            )

    # Step 2: Grade detection
    grade_matches: list[tuple[str, str]] = []
    for pattern, company in _GRADE_PATTERNS:
        for match in pattern.finditer(title):
            grade_matches.append((company, match.group(1)))

    if len(grade_matches) > 1:
        unique_grades = set(grade_matches)
        if len(unique_grades) > 1:
            notes.append(f'multiple distinct grades: {grade_matches}')
            return TitleParseResult(
                market_segment='unknown',
                grade_company=None,
                grade_score=None,
                confidence='low',
                parser_notes=notes,
            )
        # Same grade mentioned twice — accept
        notes.append(f'grade mentioned multiple times: {grade_matches[0]}')

    if grade_matches:
        company, score = grade_matches[0]
        if not notes:
            notes.append(f'graded: {company} {score}')
        return TitleParseResult(
            market_segment=build_market_segment(company, score),
            grade_company=company,
            grade_score=score,
            confidence='high',
            parser_notes=notes,
        )

    # Step 3: Raw markers
    raw_signal_count = sum(1 for p in _RAW_MARKERS if p.search(title))
    if raw_signal_count >= 1:
        notes.append(f'raw with {raw_signal_count} explicit marker(s)')
        return TitleParseResult(
            market_segment='raw',
            grade_company=None,
            grade_score=None,
            confidence='high',
            parser_notes=notes,
        )

    # Step 4: Default — assume raw, medium confidence
    notes.append('no grade signal, defaulting to raw')
    return TitleParseResult(
        market_segment='raw',
        grade_company=None,
        grade_score=None,
        confidence='medium',
        parser_notes=notes,
    )
