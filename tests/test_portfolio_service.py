from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles

from backend.app.models.asset import Asset
from backend.app.models.portfolio_lot import PortfolioLot
from backend.app.models.price_history import PriceHistory
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
    get_portfolio,
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


def test_stale_plus_user_uses_refreshed_free_tier_for_position_limit(sqlite_db):
    user = make_user(
        sqlite_db,
        tier="free",
        subscription_tier="plus",
        subscription_status="active",
    )
    seed_distinct_positions(sqlite_db, user)
    eleventh_asset = make_asset(sqlite_db, 11)

    sqlite_db.execute(
        update(User)
        .where(User.id == user.id)
        .values(subscription_tier="free", subscription_status="inactive")
        .execution_options(synchronize_session=False)
    )

    database_tier = sqlite_db.execute(
        select(User.subscription_tier, User.subscription_status).where(
            User.id == user.id
        )
    ).one()
    assert database_tier == ("free", "inactive")
    assert (user.subscription_tier, user.subscription_status) == ("plus", "active")

    with pytest.raises(PortfolioPositionLimitError):
        create_portfolio_lot(sqlite_db, user, make_request(eleventh_asset))

    assert distinct_position_count(sqlite_db, user) == 10


def test_stale_free_user_uses_refreshed_plus_tier_for_position_limit(sqlite_db):
    user = make_user(
        sqlite_db,
        tier="free",
        subscription_tier="free",
        subscription_status="inactive",
    )
    seed_distinct_positions(sqlite_db, user)
    eleventh_asset = make_asset(sqlite_db, 11)

    sqlite_db.execute(
        update(User)
        .where(User.id == user.id)
        .values(subscription_tier="plus", subscription_status="active")
        .execution_options(synchronize_session=False)
    )

    database_tier = sqlite_db.execute(
        select(User.subscription_tier, User.subscription_status).where(
            User.id == user.id
        )
    ).one()
    assert database_tier == ("plus", "active")
    assert (user.subscription_tier, user.subscription_status) == ("free", "inactive")

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

PRIMARY_PRICE_SOURCE = "pokemon_tcg_api"
INACTIVE_PRICE_SOURCE = "ebay_sold"


@pytest.fixture
def active_price_source(monkeypatch):
    settings = SimpleNamespace(primary_price_source=PRIMARY_PRICE_SOURCE)
    monkeypatch.setattr(
        "backend.app.core.price_sources.get_settings",
        lambda: settings,
    )
    return PRIMARY_PRICE_SOURCE


def make_valuation_asset(
    db,
    *,
    name: str,
    game: str = "pokemon",
    set_name: str = "Portfolio Set",
    card_number: str | None = None,
) -> Asset:
    asset = Asset(
        name=name,
        set_name=set_name,
        card_number=card_number or str(uuid4()),
        game=game,
        external_id=f"portfolio-valuation-{uuid4()}",
    )
    db.add(asset)
    db.flush()
    return asset


def add_valuation_lot(
    db,
    user: User,
    asset: Asset,
    *,
    quantity: int = 1,
    unit_cost_usd: str = "10.00",
    purchased_on: date = date(2026, 7, 1),
) -> PortfolioLot:
    lot = PortfolioLot(
        user_id=user.id,
        asset_id=asset.id,
        quantity=quantity,
        unit_cost_usd=Decimal(unit_cost_usd),
        purchased_on=purchased_on,
    )
    db.add(lot)
    db.flush()
    return lot


def add_price_observation(
    db,
    asset: Asset,
    *,
    price: str,
    captured_at: datetime,
    source: str = PRIMARY_PRICE_SOURCE,
    market_segment: str = "raw",
    currency: str = "USD",
    observation_id: UUID | None = None,
) -> PriceHistory:
    observation = PriceHistory(
        id=observation_id or uuid4(),
        asset_id=asset.id,
        source=source,
        currency=currency,
        price=Decimal(price),
        captured_at=captured_at,
        market_segment=market_segment,
    )
    db.add(observation)
    db.flush()
    return observation


@pytest.mark.parametrize(
    ("tier", "expected_limit"),
    [("free", 10), ("plus", None)],
)
def test_empty_portfolio_returns_stable_zero_summary(
    sqlite_db,
    tier,
    expected_limit,
):
    user = make_user(sqlite_db, tier=tier)

    portfolio = get_portfolio(sqlite_db, user)

    assert portfolio.summary.total_cost_basis == Decimal("0.00")
    assert portfolio.summary.priced_cost_basis == Decimal("0.00")
    assert portfolio.summary.total_market_value == Decimal("0.00")
    assert portfolio.summary.unrealized_pnl == Decimal("0.00")
    assert portfolio.summary.unrealized_pnl_percent is None
    assert portfolio.summary.position_count == 0
    assert portfolio.summary.priced_position_count == 0
    assert portfolio.summary.unpriced_position_count == 0
    assert portfolio.summary.valuation_coverage_percent == Decimal("0.00")
    assert portfolio.summary.position_limit == expected_limit
    assert portfolio.allocations == []
    assert portfolio.positions == []


def test_multi_lot_aggregation_and_missing_price_summary(
    sqlite_db,
    active_price_source,
):
    user = make_user(sqlite_db)
    priced_asset = make_valuation_asset(
        sqlite_db,
        name="Moonbreon",
        card_number="215/203",
    )
    unpriced_asset = make_valuation_asset(sqlite_db, name="Unpriced Card")
    other_user = make_user(sqlite_db)
    other_asset = make_valuation_asset(sqlite_db, name="Private Card")

    add_valuation_lot(
        sqlite_db,
        user,
        priced_asset,
        quantity=2,
        unit_cost_usd="100.00",
        purchased_on=date(2026, 7, 1),
    )
    add_valuation_lot(
        sqlite_db,
        user,
        priced_asset,
        quantity=1,
        unit_cost_usd="160.00",
        purchased_on=date(2026, 7, 10),
    )
    add_valuation_lot(
        sqlite_db,
        user,
        unpriced_asset,
        quantity=2,
        unit_cost_usd="25.00",
    )
    add_valuation_lot(sqlite_db, other_user, other_asset)

    add_price_observation(
        sqlite_db,
        priced_asset,
        price="170.00",
        captured_at=datetime(2026, 7, 1, 12, 0),
    )
    add_price_observation(
        sqlite_db,
        priced_asset,
        price="200.00",
        captured_at=datetime(2026, 7, 2, 12, 0),
    )
    add_price_observation(
        sqlite_db,
        priced_asset,
        price="500.00",
        captured_at=datetime(2026, 7, 3, 12, 0),
        market_segment="graded",
    )

    portfolio = get_portfolio(sqlite_db, user)

    assert [position.name for position in portfolio.positions] == [
        "Moonbreon",
        "Unpriced Card",
    ]
    priced = portfolio.positions[0]
    assert priced.quantity == 3
    assert priced.cost_basis_usd == Decimal("360.00")
    assert priced.average_unit_cost_usd == Decimal("120.00")
    assert priced.latest_raw_price_usd == Decimal("200.00")
    assert priced.market_value_usd == Decimal("600.00")
    assert priced.unrealized_pnl_usd == Decimal("240.00")
    assert priced.unrealized_pnl_percent == Decimal("66.67")
    assert [lot.purchased_on for lot in priced.lots] == [
        date(2026, 7, 10),
        date(2026, 7, 1),
    ]

    unpriced = portfolio.positions[1]
    assert unpriced.valuation_status == "unpriced"
    assert unpriced.latest_raw_price_usd is None
    assert unpriced.latest_price_at is None
    assert unpriced.market_value_usd is None
    assert unpriced.unrealized_pnl_usd is None
    assert unpriced.unrealized_pnl_percent is None

    summary = portfolio.summary
    assert summary.total_cost_basis == Decimal("410.00")
    assert summary.priced_cost_basis == Decimal("360.00")
    assert summary.total_market_value == Decimal("600.00")
    assert summary.unrealized_pnl == Decimal("240.00")
    assert summary.unrealized_pnl_percent == Decimal("66.67")
    assert summary.position_count == 2
    assert summary.priced_position_count == 1
    assert summary.unpriced_position_count == 1
    assert summary.valuation_coverage_percent == Decimal("50.00")
    assert all(position.asset_id != other_asset.id for position in portfolio.positions)


def test_latest_raw_price_breaks_timestamp_ties_by_id(
    sqlite_db,
    active_price_source,
):
    user = make_user(sqlite_db)
    asset = make_valuation_asset(sqlite_db, name="Tie Break Card")
    add_valuation_lot(sqlite_db, user, asset)
    captured_at = datetime(2026, 7, 4, 12, 0)
    add_price_observation(
        sqlite_db,
        asset,
        price="111.00",
        captured_at=captured_at,
        observation_id=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    )
    add_price_observation(
        sqlite_db,
        asset,
        price="222.00",
        captured_at=captured_at,
        observation_id=UUID("bbbbbbbb-0000-0000-0000-000000000002"),
    )

    portfolio = get_portfolio(sqlite_db, user)

    assert portfolio.positions[0].latest_raw_price_usd == Decimal("222.00")
    assert portfolio.positions[0].latest_price_at == captured_at


def test_wrong_currency_non_raw_and_inactive_source_are_unpriced(
    sqlite_db,
    active_price_source,
):
    user = make_user(sqlite_db)
    anchor = make_valuation_asset(sqlite_db, name="Active Raw")
    wrong_currency = make_valuation_asset(sqlite_db, name="Euro Raw")
    non_raw = make_valuation_asset(sqlite_db, name="Graded Only")
    inactive = make_valuation_asset(sqlite_db, name="Inactive Source")
    for asset in (anchor, wrong_currency, non_raw, inactive):
        add_valuation_lot(sqlite_db, user, asset)

    observed_at = datetime(2026, 7, 5, 12, 0)
    add_price_observation(
        sqlite_db,
        anchor,
        price="10.00",
        captured_at=observed_at,
    )
    add_price_observation(
        sqlite_db,
        wrong_currency,
        price="20.00",
        captured_at=observed_at,
        currency="EUR",
    )
    add_price_observation(
        sqlite_db,
        non_raw,
        price="30.00",
        captured_at=observed_at,
        market_segment="graded",
    )
    add_price_observation(
        sqlite_db,
        inactive,
        price="40.00",
        captured_at=observed_at,
        source=INACTIVE_PRICE_SOURCE,
    )

    portfolio = get_portfolio(sqlite_db, user)
    by_name = {position.name: position for position in portfolio.positions}

    assert by_name["Active Raw"].valuation_status == "priced"
    for name in ("Euro Raw", "Graded Only", "Inactive Source"):
        assert by_name[name].valuation_status == "unpriced"
        assert by_name[name].market_value_usd is None


def test_zero_cost_and_zero_price_are_handled_without_false_missing_state(
    sqlite_db,
    active_price_source,
):
    user = make_user(sqlite_db)
    zero_cost = make_valuation_asset(sqlite_db, name="Zero Cost")
    zero_price = make_valuation_asset(sqlite_db, name="Zero Price")
    add_valuation_lot(
        sqlite_db,
        user,
        zero_cost,
        quantity=2,
        unit_cost_usd="0.00",
    )
    add_valuation_lot(
        sqlite_db,
        user,
        zero_price,
        quantity=1,
        unit_cost_usd="5.00",
    )
    captured_at = datetime(2026, 7, 6, 12, 0)
    add_price_observation(
        sqlite_db,
        zero_cost,
        price="10.00",
        captured_at=captured_at,
    )
    add_price_observation(
        sqlite_db,
        zero_price,
        price="0.00",
        captured_at=captured_at,
    )

    portfolio = get_portfolio(sqlite_db, user)
    by_name = {position.name: position for position in portfolio.positions}

    assert by_name["Zero Cost"].market_value_usd == Decimal("20.00")
    assert by_name["Zero Cost"].unrealized_pnl_usd == Decimal("20.00")
    assert by_name["Zero Cost"].unrealized_pnl_percent is None
    assert by_name["Zero Price"].valuation_status == "priced"
    assert by_name["Zero Price"].latest_raw_price_usd == Decimal("0.00")
    assert by_name["Zero Price"].market_value_usd == Decimal("0.00")
    assert by_name["Zero Price"].unrealized_pnl_percent == Decimal("-100.00")


def test_all_zero_market_value_has_no_undefined_allocation(
    sqlite_db,
    active_price_source,
):
    user = make_user(sqlite_db)
    asset = make_valuation_asset(sqlite_db, name="Zero Allocation")
    add_valuation_lot(sqlite_db, user, asset)
    add_price_observation(
        sqlite_db,
        asset,
        price="0.00",
        captured_at=datetime(2026, 7, 7, 12, 0),
    )

    portfolio = get_portfolio(sqlite_db, user)

    assert portfolio.summary.priced_position_count == 1
    assert portfolio.summary.total_market_value == Decimal("0.00")
    assert portfolio.allocations == []


def test_game_allocation_is_deterministic_and_totals_exactly_one_hundred(
    sqlite_db,
    active_price_source,
):
    user = make_user(sqlite_db)
    specs = [
        ("One Piece Card", "one_piece", "10.00"),
        ("Pokemon A", "pokemon", "4.00"),
        ("Pokemon B", "pokemon", "6.00"),
        ("Yugioh Card", "yugioh", "10.00"),
    ]
    captured_at = datetime(2026, 7, 8, 12, 0)
    for name, game, price in specs:
        asset = make_valuation_asset(sqlite_db, name=name, game=game)
        add_valuation_lot(sqlite_db, user, asset, unit_cost_usd="1.00")
        add_price_observation(
            sqlite_db,
            asset,
            price=price,
            captured_at=captured_at,
        )

    portfolio = get_portfolio(sqlite_db, user)

    assert [allocation.game for allocation in portfolio.allocations] == [
        "one_piece",
        "pokemon",
        "yugioh",
    ]
    assert [allocation.market_value_usd for allocation in portfolio.allocations] == [
        Decimal("10.00"),
        Decimal("10.00"),
        Decimal("10.00"),
    ]
    assert [allocation.percentage for allocation in portfolio.allocations] == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]
    assert sum(
        allocation.percentage for allocation in portfolio.allocations
    ) == Decimal("100.00")
    assert [
        allocation.priced_position_count for allocation in portfolio.allocations
    ] == [1, 2, 1]


def test_position_order_uses_name_then_set_then_asset_id(
    sqlite_db,
    active_price_source,
):
    user = make_user(sqlite_db)
    assets = [
        make_valuation_asset(sqlite_db, name="beta", set_name="A"),
        make_valuation_asset(sqlite_db, name="Alpha", set_name="B"),
        make_valuation_asset(sqlite_db, name="alpha", set_name="A"),
    ]
    for asset in assets:
        add_valuation_lot(sqlite_db, user, asset)

    portfolio = get_portfolio(sqlite_db, user)

    assert [(position.name, position.set_name) for position in portfolio.positions] == [
        ("alpha", "A"),
        ("Alpha", "B"),
        ("beta", "A"),
    ]


def test_portfolio_read_query_count_is_bounded_and_has_no_transaction_control(
    sqlite_db,
    active_price_source,
):
    user = make_user(sqlite_db)
    captured_at = datetime(2026, 7, 9, 12, 0)
    for index in range(12):
        asset = make_valuation_asset(sqlite_db, name=f"Query Card {index:02d}")
        add_valuation_lot(sqlite_db, user, asset)
        add_price_observation(
            sqlite_db,
            asset,
            price="10.00",
            captured_at=captured_at,
        )

    statements: list[str] = []

    def record_statement(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    engine = sqlite_db.get_bind()
    event.listen(engine, "before_cursor_execute", record_statement)
    db = TransactionSpy(sqlite_db)
    try:
        portfolio = get_portfolio(db, user)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert len(portfolio.positions) == 12
    assert len(statements) <= 4
    assert db.commit_calls == 0
    assert db.rollback_calls == 0
