"""
Single source of truth for market_segment string generation.
All write paths must use build_market_segment(); never construct
segment strings directly elsewhere in the codebase.
"""

from typing import Optional

GRADE_COMPANIES = {'PSA', 'BGS', 'CGC', 'SGC'}


def build_market_segment(
    grade_company: Optional[str] = None,
    grade_score: Optional[str] = None,
    **_future_dims,  # accept future dimensions, ignore in MVP
) -> str:
    """
    Compute canonical market_segment from structured grade fields.

    Returns:
        'raw'           — no grade supplied
        '{co}_{score}'  — validly graded (e.g. 'psa_10', 'bgs_9_5')
        'unknown'       — grade fields inconsistent or unparseable
    """
    if grade_company is None and grade_score is None:
        return 'raw'

    if grade_company is None or grade_score is None:
        return 'unknown'

    company = grade_company.strip().upper()
    if company not in GRADE_COMPANIES:
        return 'unknown'

    try:
        normalised = grade_score.strip().replace('.', '_')
        if not normalised:
            raise ValueError('empty score')
        float(normalised.replace('_', '.'))  # validate numeric
    except (ValueError, AttributeError):
        return 'unknown'

    return f"{company.lower()}_{normalised}"
