"""reject future-dated captured_at on price_history via trigger

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-27

Problem: eBay API returns listing end_time values that can be in the future
(auctions not yet closed).  ebay_sold.py did not filter these at ingest time,
so rows with captured_at > NOW() accumulated silently.  749 such rows were
discovered on 2026-04-27 and deleted, but any new ingest path (MTG, OPTCG,
future eBay variants) could reintroduce the pattern without application-layer
protection.

Fix: a BEFORE INSERT OR UPDATE trigger that raises immediately if
captured_at > CURRENT_TIMESTAMP + 5 minutes.  The 5-minute buffer absorbs
clock skew between app server and Postgres host.

Postgres CHECK constraints cannot use CURRENT_TIMESTAMP (STABLE, not
IMMUTABLE), so a trigger is the correct vehicle.  The trigger uses
clock_timestamp() (wall clock, advances during the transaction) rather than
CURRENT_TIMESTAMP (pinned to transaction start) — ingest transactions can run
several minutes, and CURRENT_TIMESTAMP would false-reject valid rows captured
near the end of a long transaction.

Downgrade: drops the trigger and function.  No data change on either path.
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION reject_future_captured_at()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.captured_at > clock_timestamp() + INTERVAL '5 minutes' THEN
                RAISE EXCEPTION
                    'price_history.captured_at % is more than 5 minutes in the future',
                    NEW.captured_at;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER price_history_no_future_captured_at
        BEFORE INSERT OR UPDATE ON price_history
        FOR EACH ROW EXECUTE FUNCTION reject_future_captured_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS price_history_no_future_captured_at ON price_history;")
    op.execute("DROP FUNCTION IF EXISTS reject_future_captured_at();")
