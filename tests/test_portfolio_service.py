from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles

from backend.app.models.asset import Asset
from backend.app.models.portfolio_lot import PortfolioLot
from backend.app.models.user import User
from backend.app.schemas.portfolio import (
    PortfolioLotCreateRequest,
    PortfolioLotPatchRequest,
)
from backend.app.services.portfolio_service import (
    PortfolioAssetNotFoundError,
    PortfolioLotNotFoundError,
    PortfolioPositionLimitError,
    create_portfolio_lot,
    delete_portfolio_lot,
    update_portfolio_lot,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def make_user(
    db,
    *,
    tier: str = "free",
    email: str | None = None,
    subscription_tier: str = "free",
    subscription_status: str = "free",
) -> User:
    user = User(
        email=email or f"{uuid4()}@example.com",
        access_tier=tier,
        subscription_tier=subscription_tier,
        subscription_status=subscription_status,
    )
    db.add(user)
    db.flush()
    return user


def make_asset(db, index: int = 1) -> Asset:
    unique = uuid4()
    asset = Asset(
        name=f"Portfolio Card {index}",
        set_name="Test Set",
        card_number=str(index),
        game="pokemon",
        external_id=f"portfolio-card-{unique}",
    )
    db.add(asset)
    db.flush()
    return asset


def make_request(
    asset: Asset,
    *,
    quantity: int = 1,
    unit_cost_usd: str = "10.00",
    purchased_on: str = "2026-07-01",
) -> PortfolioLotCreateRequest:
    return PortfolioLotCreateRequest(
        asset_id=asset.id,
        quantity=quantity,
        unit_cost_usd=unit_cost_usd,
        purchased_on=purchased_on,
    )


def add_lot(db, user: User, asset: Asset) -> PortfolioLot:
    lot = PortfolioLot(
        user_id=user.id,
        asset_id=asset.id,
        quantity=1,
        unit_cost_usd=Decimal("10.00"),
        purchased_on=date(2026, 7, 1),
    )
    db.add(lot)
    db.flush()
    return lot


def seed_distinct_positions(db, user: User, count: int = 10) -> list[Asset]:
    assets = [make_asset(db, index) for index in range(count)]
    for asset in assets:
        add_lot(db, user, asset)
    return assets


def distinct_position_count(db, user: User) -> int:
    return int(
        db.scalar(
            select(func.count(func.distinct(PortfolioLot.asset_id))).where(
                PortfolioLot.user_id == user.id
            )
        )
        or 0
    )


def test_create_valid_lot_preserves_exact_values_and_ownership(sqlite_db):
    user = make_user(sqlite_db)
    asset = make_asset(sqlite_db)

    lot = create_portfolio_lot(
        sqlite_db,
        user,
        make_request(
            asset,
            quantity=2,
            unit_cost_usd="125.50",
            purchased_on="2026-07-02",
        ),
    )

    assert lot.user_id == user.id
    assert lot.asset_id == asset.id
    assert lot.quantity == 2
    assert lot.unit_cost_usd == Decimal("125.50")
    assert lot.purchased_on == date(2026, 7, 2)
    assert sqlite_db.get(PortfolioLot, lot.id) is lot


def test_update_each_editable_field_preserves_asset_and_user(sqlite_db):
    user = make_user(sqlite_db)
    asset = make_asset(sqlite_db)
    lot = add_lot(sqlite_db, user, asset)

    updated = update_portfolio_lot(
        sqlite_db,
        user,
        lot.id,
        PortfolioLotPatchRequest(
            quantity=3,
            unit_cost_usd="45.67",
            purchased_on="2026-07-20",
        ),
    )

    assert updated.id == lot.id
    assert updated.user_id == user.id
    assert updated.asset_id == asset.id
    assert updated.quantity == 3
    assert updated.unit_cost_usd == Decimal("45.67")
    assert updated.purchased_on == date(2026, 7, 20)


def test_delete_owned_lot_flushes_removal_and_returns_none(sqlite_db):
    user = make_user(sqlite_db)
    asset = make_asset(sqlite_db)
    lot = add_lot(sqlite_db, user, asset)
    lot_id = lot.id

    result = delete_portfolio_lot(sqlite_db, user, lot_id)

    assert result is None
    assert sqlite_db.get(PortfolioLot, lot_id) is None


def test_create_missing_asset_raises_typed_error(sqlite_db):
    user = make_user(sqlite_db)
    missing_asset = Asset(id=uuid4(), name="Missing", game="pokemon")

    with pytest.raises(PortfolioAssetNotFoundError):
        create_portfolio_lot(sqlite_db, user, make_request(missing_asset))


def test_create_missing_current_user_row_raises_typed_not_found(sqlite_db):
    asset = make_asset(sqlite_db)
    missing_user = User(
        id=uuid4(),
        email="missing@example.com",
        access_tier="free",
        subscription_tier="free",
        subscription_status="free",
    )

    with pytest.raises(PortfolioLotNotFoundError):
        create_portfolio_lot(sqlite_db, missing_user, make_request(asset))


def test_another_users_lot_is_unobservable_for_update_and_delete(sqlite_db):
    owner = make_user(sqlite_db, email="owner@example.com")
    other = make_user(sqlite_db, email="other@example.com")
    asset = make_asset(sqlite_db)
    lot = add_lot(sqlite_db, owner, asset)

    with pytest.raises(PortfolioLotNotFoundError):
        update_portfolio_lot(
            sqlite_db,
            other,
            lot.id,
            PortfolioLotPatchRequest(quantity=2),
        )
    with pytest.raises(PortfolioLotNotFoundError):
        delete_portfolio_lot(sqlite_db, other, lot.id)

    assert sqlite_db.get(PortfolioLot, lot.id) is lot
    assert lot.quantity == 1


def test_free_user_cannot_create_eleventh_distinct_position(sqlite_db):
    user = make_user(sqlite_db)
    seed_distinct_positions(sqlite_db, user)
    eleventh_asset = make_asset(sqlite_db, 11)

    with pytest.raises(PortfolioPositionLimitError) as error:
        create_portfolio_lot(sqlite_db, user, make_request(eleventh_asset))

    assert error.value.position_limit == 10
    assert error.value.position_count == 10
    assert "10" in str(error.value)
    assert distinct_position_count(sqlite_db, user) == 10
    assert (
        sqlite_db.scalar(
            select(func.count(PortfolioLot.id)).where(PortfolioLot.user_id == user.id)
        )
        == 10
    )


def test_free_user_can_add_lot_to_existing_asset_at_limit(sqlite_db):
    user = make_user(sqlite_db)
    assets = seed_distinct_positions(sqlite_db, user)

    lot = create_portfolio_lot(
        sqlite_db,
        user,
        make_request(assets[0], quantity=2),
    )

    assert lot.asset_id == assets[0].id
    assert lot.quantity == 2
    assert distinct_position_count(sqlite_db, user) == 10


@pytest.mark.parametrize("tier", ["plus", "pro"])
def test_direct_plus_and_pro_tiers_are_unlimited(sqlite_db, tier):
    user = make_user(sqlite_db, tier=tier)
    seed_distinct_positions(sqlite_db, user)
    eleventh_asset = make_asset(sqlite_db, 11)

    lot = create_portfolio_lot(sqlite_db, user, make_request(eleventh_asset))

    assert lot.asset_id == eleventh_asset.id
    assert distinct_position_count(sqlite_db, user) == 11


@pytest.mark.parametrize("subscription_status", ["active", "trialing"])
def test_current_plus_subscription_overrides_legacy_free(
    sqlite_db,
    subscription_status,
):
    user = make_user(
        sqlite_db,
        tier="free",
        subscription_tier="plus",
        subscription_status=subscription_status,
    )
    seed_distinct_positions(sqlite_db, user)
    eleventh_asset = make_asset(sqlite_db, 11)

    lot = create_portfolio_lot(sqlite_db, user, make_request(eleventh_asset))

    assert lot.asset_id == eleventh_asset.id
    assert distinct_position_count(sqlite_db, user) == 11


@pytest.mark.parametrize("subscription_status", ["inactive", "past_due"])
def test_inactive_plus_subscription_fails_closed_to_free_limit(
    sqlite_db,
    subscription_status,
):
    user = make_user(
        sqlite_db,
        tier="free",
        subscription_tier="plus",
        subscription_status=subscription_status,
    )
    seed_distinct_positions(sqlite_db, user)
    eleventh_asset = make_asset(sqlite_db, 11)

    with pytest.raises(PortfolioPositionLimitError) as error:
        create_portfolio_lot(sqlite_db, user, make_request(eleventh_asset))

    assert error.value.position_limit == 10
    assert error.value.position_count == 10
    assert distinct_position_count(sqlite_db, user) == 10


class RecordingSession:
    def __init__(self, asset: Asset, user: User) -> None:
        self._scalar_results = iter([asset.id, user, None, 0])
        self.scalar_statements = []
        self.added = []

    def scalar(self, statement):
        self.scalar_statements.append(statement)
        return next(self._scalar_results)

    def add(self, value) -> None:
        self.added.append(value)

    def flush(self) -> None:
        return None

    def refresh(self, value) -> None:
        return None


def test_create_locks_user_before_distinct_position_count():
    user = User(
        id=uuid4(),
        email="owner@example.com",
        access_tier="free",
        subscription_tier="free",
        subscription_status="free",
    )
    asset = Asset(id=uuid4(), name="Card", game="pokemon")
    db = RecordingSession(asset, user)

    create_portfolio_lot(db, user, make_request(asset))

    lock_indexes = [
        index
        for index, statement in enumerate(db.scalar_statements)
        if statement._for_update_arg is not None
    ]
    count_index = next(
        index
        for index, statement in enumerate(db.scalar_statements)
        if "count(distinct(portfolio_lots.asset_id))"
        in str(statement).lower().replace("\n", " ")
    )

    assert lock_indexes == [1]
    assert lock_indexes[0] < count_index


class TransactionSpy:
    def __init__(self, session) -> None:
        self._session = session
        self.commit_calls = 0
        self.rollback_calls = 0

    def __getattr__(self, name):
        return getattr(self._session, name)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_service_never_commits_or_rolls_back(sqlite_db):
    user = make_user(sqlite_db)
    asset = make_asset(sqlite_db)
    db = TransactionSpy(sqlite_db)

    lot = create_portfolio_lot(db, user, make_request(asset))
    update_portfolio_lot(
        db,
        user,
        lot.id,
        PortfolioLotPatchRequest(quantity=2),
    )
    delete_portfolio_lot(db, user, lot.id)

    assert db.commit_calls == 0
    assert db.rollback_calls == 0


@pytest.mark.parametrize(
    ("quantity", "unit_cost_usd"),
    [
        (0, Decimal("10.00")),
        (1, Decimal("-0.01")),
    ],
)
def test_database_constraints_reject_invalid_lot_values(
    sqlite_db,
    quantity,
    unit_cost_usd,
):
    user = make_user(sqlite_db)
    asset = make_asset(sqlite_db)
    sqlite_db.add(
        PortfolioLot(
            user_id=user.id,
            asset_id=asset.id,
            quantity=quantity,
            unit_cost_usd=unit_cost_usd,
            purchased_on=date(2026, 7, 1),
        )
    )

    with pytest.raises(IntegrityError):
        sqlite_db.flush()
