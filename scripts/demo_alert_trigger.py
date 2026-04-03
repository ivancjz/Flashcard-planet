from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, select

from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.services.alert_service import evaluate_active_alerts

DEV_TEST_SOURCE = "dev_test"


def quantize_price(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_asset_by_name(session, asset_name: str) -> Asset:
    asset = session.scalar(select(Asset).where(Asset.name.ilike(asset_name)))
    if asset is None:
        raise ValueError(f"No asset found with name '{asset_name}'.")
    return asset


def get_latest_real_price_row(session, asset_id):
    row = session.execute(
        select(
            PriceHistory.price,
            PriceHistory.currency,
            PriceHistory.captured_at,
        )
        .where(
            PriceHistory.asset_id == asset_id,
            PriceHistory.source != "sample_seed",
            PriceHistory.source != DEV_TEST_SOURCE,
        )
        .order_by(PriceHistory.captured_at.desc())
        .limit(1)
    ).first()
    if row is None:
        raise ValueError("No baseline real price history was found for this asset.")
    return row


def cleanup_dev_rows(asset_name: str) -> int:
    init_db()
    with SessionLocal() as session:
        asset = get_asset_by_name(session, asset_name)
        delete_result = session.execute(
            delete(PriceHistory).where(
                PriceHistory.asset_id == asset.id,
                PriceHistory.source == DEV_TEST_SOURCE,
            )
        )
        session.commit()
        return int(delete_result.rowcount or 0)


def build_demo_price_point(session, asset_name: str, *, percent_change: Decimal | None, price: Decimal | None) -> tuple[str, Decimal, str, datetime]:
    asset = get_asset_by_name(session, asset_name)
    latest_row = get_latest_real_price_row(session, asset.id)
    latest_price = Decimal(latest_row.price)
    currency = latest_row.currency

    session.execute(
        delete(PriceHistory).where(
            PriceHistory.asset_id == asset.id,
            PriceHistory.source == DEV_TEST_SOURCE,
        )
    )

    if price is not None:
        demo_price = quantize_price(price)
    else:
        multiplier = Decimal("1") + (percent_change or Decimal("0")) / Decimal("100")
        demo_price = quantize_price(latest_price * multiplier)

    next_captured_at = max(
        datetime.now(UTC).replace(microsecond=0),
        latest_row.captured_at.replace(tzinfo=UTC) + timedelta(seconds=1)
        if latest_row.captured_at.tzinfo is None
        else latest_row.captured_at + timedelta(seconds=1),
    )

    session.add(
        PriceHistory(
            asset_id=asset.id,
            source=DEV_TEST_SOURCE,
            currency=currency,
            price=demo_price,
            captured_at=next_captured_at,
        )
    )
    session.flush()
    return asset.name, demo_price, currency, next_captured_at


def print_alert_preview(session, asset_name: str) -> None:
    evaluation = evaluate_active_alerts(session)
    matched = [
        notification
        for notification in evaluation.notifications
        if asset_name in notification.content
    ]
    print(
        "Alert preview: "
        f"active_alerts_checked={evaluation.active_alerts_checked}, "
        f"triggered={evaluation.triggered_alerts}, "
        f"price_movement_alerts_triggered={evaluation.price_movement_alerts_triggered}, "
        f"prediction_alerts_triggered={evaluation.prediction_alerts_triggered}, "
        f"alerts_rearmed={evaluation.alerts_rearmed}, "
        f"target_alerts_deactivated={evaluation.target_alerts_deactivated}, "
        f"matched_for_asset={len(matched)}"
    )
    if not matched:
        print("No alert notifications would fire yet for this asset.")
    for notification in matched:
        print("---")
        print(f"user={notification.discord_user_id}")
        print(notification.content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Insert a dev_test price point for one asset and preview which alerts would trigger."
    )
    parser.add_argument("--asset-name", required=True, help="Tracked asset name, for example Charizard")
    parser.add_argument("--cleanup", action="store_true", help="Delete dev_test price rows for the asset and exit.")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Keep the dev_test price point after preview so the running scheduler can act on it later.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--percent-change", type=Decimal, help="Percent change to apply to the latest real price.")
    group.add_argument("--price", type=Decimal, help="Explicit demo price to insert.")
    args = parser.parse_args()

    if args.cleanup:
        deleted = cleanup_dev_rows(args.asset_name)
        print(f"Deleted {deleted} dev_test row(s) for {args.asset_name}.")
        return

    init_db()
    with SessionLocal() as session:
        asset_name, demo_price, currency, captured_at = build_demo_price_point(
            session,
            args.asset_name,
            percent_change=args.percent_change,
            price=args.price,
        )
        print(
            f"Prepared dev_test price point for {asset_name}: "
            f"{demo_price} {currency} at {captured_at.isoformat()}"
        )
        print_alert_preview(session, asset_name)
        if args.commit:
            session.commit()
            print(
                "Committed the dev_test row. The running scheduler can now detect it. "
                f"Use `python -m scripts.demo_alert_trigger --asset-name \"{asset_name}\" --cleanup` to remove it later."
            )
            return
        session.rollback()
        print("Dry run only. No dev_test rows or alert state changes were saved.")


if __name__ == "__main__":
    main()
