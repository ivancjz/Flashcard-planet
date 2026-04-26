import pytest
from backend.app.ingestion.market_segment import build_market_segment


@pytest.mark.parametrize("company,score,expected", [
    (None, None, 'raw'),
    ('PSA', '10', 'psa_10'),
    ('PSA', '9.5', 'psa_9_5'),
    ('bgs', '9', 'bgs_9'),           # lowercase company normalised
    ('CGC', '10', 'cgc_10'),
    ('SGC', '9.5', 'sgc_9_5'),
    ('XYZ', '10', 'unknown'),         # unrecognised company
    ('PSA', None, 'unknown'),         # missing score
    (None, '10', 'unknown'),          # missing company
    ('PSA', 'not-a-number', 'unknown'),
    ('PSA', '9.5.5', 'unknown'),      # invalid decimal
    ('PSA', '', 'unknown'),           # empty string score
])
def test_build_market_segment(company, score, expected):
    assert build_market_segment(company, score) == expected


def test_future_dims_ignored():
    """Future kwargs accepted but silently ignored in MVP."""
    assert build_market_segment(None, None, edition='1st', language='japanese') == 'raw'
