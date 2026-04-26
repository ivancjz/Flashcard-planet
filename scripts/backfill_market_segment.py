"""
Backfill market_segment, grade_company, grade_score on existing eBay price_history rows.

Strategy:
  1. Join price_history → observation_match_logs by (asset_id, captured_at, provider)
  2. Run title parser on raw_title to classify
  3. UPDATE price_history with segment fields
  4. Mirror UPDATE to observation_match_logs when the join succeeds

Resume-safe: only processes rows WHERE market_segment IS NULL.

Run:
    python scripts/backfill_market_segment.py [--batch-size 1000] [--dry-run]
"""

import argparse
import sys

from sqlalchemy import text

sys.path.insert(0, ".")
from backend.app.db.session import SessionLocal
from backend.app.ingestion.title_parser import parse_listing_title


def _backfill_batch(db, batch_size: int, dry_run: bool) -> dict:
    # DISTINCT ON (ph.id) prevents duplicate rows when multiple OML rows share
    # the same (asset_id, captured_at, provider) — possible when eBay listings
    # for the same card sell at the exact same timestamp.
    rows = db.execute(text("""
        SELECT DISTINCT ON (ph.id)
            ph.id            AS price_history_id,
            ph.asset_id,
            ph.captured_at,
            oml.id           AS oml_id,
            oml.raw_title
        FROM price_history ph
        LEFT JOIN observation_match_logs oml
               ON oml.matched_asset_id = ph.asset_id
              AND oml.created_at       = ph.captured_at
              AND oml.provider         = 'ebay_sold'
        WHERE ph.source          = 'ebay_sold'
          AND ph.market_segment IS NULL
        ORDER BY ph.id, oml.created_at
        LIMIT :batch_size
    """), {'batch_size': batch_size}).fetchall()

    if not rows:
        return {'processed': 0}

    counts = {'processed': len(rows), 'classified': 0, 'no_title': 0,
              'unknown': 0, 'raw': 0, 'graded': 0}

    for row in rows:
        if row.raw_title is None:
            segment, company, score = 'unknown', None, None
            counts['no_title'] += 1
            counts['unknown'] += 1
        else:
            result = parse_listing_title(row.raw_title)
            segment = result.market_segment
            company = result.grade_company
            score   = result.grade_score
            counts['classified'] += 1
            if segment == 'raw':
                counts['raw'] += 1
            elif segment == 'unknown':
                counts['unknown'] += 1
            else:
                counts['graded'] += 1

        if dry_run:
            continue  # classify without writing; loop breaks after first batch (see below)

        db.execute(text("""
            UPDATE price_history
               SET market_segment = :segment,
                   grade_company  = :company,
                   grade_score    = :score
             WHERE id = :id
        """), {'id': row.price_history_id, 'segment': segment,
               'company': company, 'score': score})

        if row.oml_id is not None:
            db.execute(text("""
                UPDATE observation_match_logs
                   SET market_segment = :segment,
                       grade_company  = :company,
                       grade_score    = :score
                 WHERE id = :oml_id
            """), {'oml_id': row.oml_id, 'segment': segment,
                   'company': company, 'score': score})

    if dry_run:
        return {**counts, '_dry_run_break': True}  # signal main loop to stop
    db.commit()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=1000)
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse and count only — no DB writes')
    args = parser.parse_args()

    db = SessionLocal()
    totals = {'processed': 0, 'classified': 0, 'no_title': 0,
              'unknown': 0, 'raw': 0, 'graded': 0}

    iteration = 0
    while True:
        iteration += 1
        counts = _backfill_batch(db, args.batch_size, args.dry_run)
        if counts['processed'] == 0 or counts.get('_dry_run_break'):
            break
        for k in totals:
            totals[k] += counts.get(k, 0)
        print(
            f"[batch {iteration:>4}] "
            f"processed={counts['processed']:>5}  "
            f"raw={counts['raw']:>5}  "
            f"graded={counts['graded']:>4}  "
            f"unknown={counts['unknown']:>4}  "
            f"no_title={counts['no_title']:>4}"
        )

    print("\n=== Backfill complete" + (" (DRY RUN)" if args.dry_run else "") + " ===")
    for k, v in totals.items():
        print(f"  {k}: {v}")

    db.close()


if __name__ == '__main__':
    main()
