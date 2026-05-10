import pytest
from backend.app.ingestion.title_parser import parse_listing_title


# ── Graded titles ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title,expected_segment,expected_company,expected_score", [
    ('Pokemon Charizard PSA 10 Base Set', 'psa_10', 'PSA', '10'),
    ('PSA 9 Pikachu Promo', 'psa_9', 'PSA', '9'),
    ('Charizard BGS 9.5', 'bgs_9_5', 'BGS', '9.5'),
    ('Pokemon Card CGC-10', 'cgc_10', 'CGC', '10'),
    ('SGC 9 Charizard Base Set', 'sgc_9', 'SGC', '9'),
    ('PSA10 Charizard No Space', 'psa_10', 'PSA', '10'),
])
def test_parse_graded(title, expected_segment, expected_company, expected_score):
    result = parse_listing_title(title)
    assert result.market_segment == expected_segment
    assert result.grade_company == expected_company
    assert result.grade_score == expected_score
    assert not result.excluded


# ── Raw titles ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    'Pokemon Charizard Base Set Near Mint',
    'Charizard NM Holographic',
    'Pokemon Card Ungraded Charizard',
    'Pokemon Charizard',  # no markers — default raw
])
def test_parse_raw(title):
    result = parse_listing_title(title)
    assert result.market_segment == 'raw'
    assert result.grade_company is None
    assert result.grade_score is None
    assert not result.excluded


# ── Excluded titles ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("title,reason", [
    ('Pokemon Booster Pack Base Set', 'booster_pack'),
    ('Pokemon Card Lot 50 Cards', 'card_lot'),
    ('Pokemon Booster Box Sealed', 'sealed'),
    ('Custom Pokemon Charizard Card', 'custom'),
    ('Signed Pokemon Charizard PSA 10', 'signed'),  # signed wins over graded
])
def test_parse_excluded(title, reason):
    result = parse_listing_title(title)
    assert result.excluded
    assert result.market_segment == 'unknown'


# ── Ambiguous / unknown ───────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    'Charizard PSA 9 BGS 10 Comparable',  # multiple distinct grades
    '',                                    # empty
])
def test_parse_unknown(title):
    result = parse_listing_title(title)
    assert result.market_segment == 'unknown'


# ── Confidence levels ─────────────────────────────────────────────────────────

def test_high_confidence_for_graded():
    result = parse_listing_title('Charizard PSA 10')
    assert result.confidence == 'high'


def test_high_confidence_for_explicit_raw():
    result = parse_listing_title('Charizard Near Mint')
    assert result.confidence == 'high'


def test_medium_confidence_for_default_raw():
    result = parse_listing_title('Pokemon Charizard')
    assert result.confidence == 'medium'
