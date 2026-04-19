import math
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.price_queries import build_ranked_price_subquery
from backend.app.core.price_sources import SAMPLE_PRICE_SOURCE, get_active_price_source_filter
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.schemas.price import (
    AssetHistoryResponse,
    AssetPriceResponse,
    PricePredictionResponse,
    PriceHistoryPointResponse,
    TopMoverResponse,
    TopValueResponse,
)
from backend.app.services.liquidity_service import (
    get_asset_signal_snapshots,
    is_top_mover_eligible,
)

PREDICTION_POINT_LIMIT = 8
PREDICTION_MIN_POINTS = 3
HISTORY_POINT_TYPE_DERIVED = "derived"


@dataclass
class PredictionComputation:
    prediction: str
    up_probability: Decimal | None
    down_probability: Decimal | None
    flat_probability: Decimal | None
    reason: str
    points_used: int


def aliased_subquery(subquery, alias_name: str, rank: int):
    return select(subquery).where(subquery.c.price_rank == rank).subquery(alias_name)


def _quantize_change(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _build_asset_price_responses(db: Session, rows) -> list[AssetPriceResponse]:
    percent_changes_by_asset: dict = {}
    for asset, latest_price, _currency, _source, _captured_at, previous_price, _external_id in rows:
        if previous_price is None or Decimal(previous_price) == 0:
            continue
        absolute_change = Decimal(latest_price) - Decimal(previous_price)
        percent_changes_by_asset[asset.id] = (absolute_change / Decimal(previous_price)) * Decimal("100")

    signal_snapshots = get_asset_signal_snapshots(
        db,
        [asset.id for asset, *_rest in rows],
        percent_changes_by_asset=percent_changes_by_asset,
    )

    responses: list[AssetPriceResponse] = []
    for asset, latest_price, currency, source, captured_at, previous_price, external_id in rows:
        latest_price_decimal = Decimal(latest_price)
        previous_price_decimal = Decimal(previous_price) if previous_price is not None else None
        absolute_change = None
        percent_change = None
        if previous_price_decimal is not None and previous_price_decimal != 0:
            absolute_change = _quantize_change(latest_price_decimal - previous_price_decimal)
            percent_change = _quantize_change(
                ((latest_price_decimal - previous_price_decimal) / previous_price_decimal) * Decimal("100")
            )

        signal_snapshot = signal_snapshots.get(asset.id)
        image_url = (asset.metadata_json or {}).get("images", {}).get("small")
        responses.append(
            AssetPriceResponse(
                asset_id=asset.id,
                asset_class=asset.asset_class,
                category=asset.category,
                game=asset.game,
                name=asset.name,
                set_name=asset.set_name,
                external_id=external_id,
                card_number=asset.card_number,
                year=asset.year,
                variant=asset.variant,
                grade_company=asset.grade_company,
                grade_score=asset.grade_score,
                latest_price=latest_price_decimal,
                currency=currency,
                source=source,
                captured_at=captured_at,
                previous_price=previous_price_decimal,
                absolute_change=absolute_change,
                percent_change=percent_change,
                image_url=image_url,
                liquidity_score=signal_snapshot.liquidity_score if signal_snapshot is not None else None,
                liquidity_label=signal_snapshot.liquidity_label if signal_snapshot is not None else None,
                last_real_sale_at=signal_snapshot.last_real_sale_at if signal_snapshot is not None else None,
                days_since_last_sale=signal_snapshot.days_since_last_sale if signal_snapshot is not None else None,
                sales_count_7d=signal_snapshot.sales_count_7d if signal_snapshot is not None else None,
                sales_count_30d=signal_snapshot.sales_count_30d if signal_snapshot is not None else None,
                history_depth=signal_snapshot.history_depth if signal_snapshot is not None else None,
                source_count=signal_snapshot.source_count if signal_snapshot is not None else None,
                alert_confidence=(
                    signal_snapshot.alert_confidence
                    if signal_snapshot is not None and percent_change is not None and percent_change != 0
                    else None
                ),
                alert_confidence_label=(
                    signal_snapshot.alert_confidence_label
                    if signal_snapshot is not None and percent_change is not None and percent_change != 0
                    else None
                ),
            )
        )
    return responses


def get_asset_prices_by_name(db: Session, asset_name: str) -> list[AssetPriceResponse]:
    source_filter = get_active_price_source_filter(db)
    ranked = build_ranked_price_subquery(source_filter)
    current = aliased_subquery(ranked, "current_price", 1)
    previous = aliased_subquery(ranked, "previous_price", 2)

    stmt = (
        select(
            Asset,
            current.c.price.label("latest_price"),
            current.c.currency,
            current.c.source,
            current.c.captured_at,
            previous.c.price.label("previous_price"),
            Asset.external_id,
        )
        .join(current, current.c.asset_id == Asset.id)
        .outerjoin(previous, previous.c.asset_id == Asset.id)
        .where(Asset.name.ilike(f"%{asset_name}%"))
        .order_by(Asset.name.asc(), current.c.captured_at.desc())
    )

    rows = db.execute(stmt).all()
    return _build_asset_price_responses(db, rows)


def get_asset_price_by_external_id(db: Session, external_id: str) -> AssetPriceResponse | None:
    source_filter = get_active_price_source_filter(db)
    ranked = build_ranked_price_subquery(source_filter)
    current = aliased_subquery(ranked, "current_price", 1)
    previous = aliased_subquery(ranked, "previous_price", 2)

    stmt = (
        select(
            Asset,
            current.c.price.label("latest_price"),
            current.c.currency,
            current.c.source,
            current.c.captured_at,
            previous.c.price.label("previous_price"),
            Asset.external_id,
        )
        .join(current, current.c.asset_id == Asset.id)
        .outerjoin(previous, previous.c.asset_id == Asset.id)
        .where(Asset.external_id == external_id)
        .order_by(current.c.captured_at.desc())
        .limit(1)
    )

    rows = db.execute(stmt).all()
    responses = _build_asset_price_responses(db, rows)
    return responses[0] if responses else None


def get_top_movers(db: Session, limit: int = 10) -> list[TopMoverResponse]:
    source_filter = get_active_price_source_filter(db)
    ranked = build_ranked_price_subquery(source_filter)

    current = aliased_subquery(ranked, "current", 1)
    previous = aliased_subquery(ranked, "previous", 2)

    stmt = (
        select(
            Asset.id,
            Asset.name,
            Asset.category,
            Asset.game,
            Asset.set_name,
            Asset.external_id,
            current.c.price.label("latest_price"),
            previous.c.price.label("previous_price"),
        )
        .join(current, current.c.asset_id == Asset.id)
        .join(previous, previous.c.asset_id == Asset.id)
    )

    rows = db.execute(stmt).all()
    percent_changes_by_asset: dict = {}
    for row in rows:
        previous_price = Decimal(row.previous_price)
        if previous_price == 0:
            continue
        latest_price = Decimal(row.latest_price)
        absolute_change = latest_price - previous_price
        if absolute_change == 0:
            continue
        percent_changes_by_asset[row.id] = (absolute_change / previous_price) * Decimal("100")

    signal_snapshots = get_asset_signal_snapshots(
        db,
        [row.id for row in rows],
        percent_changes_by_asset=percent_changes_by_asset,
    )

    movers: list[TopMoverResponse] = []
    for row in rows:
        previous_price = Decimal(row.previous_price)
        latest_price = Decimal(row.latest_price)
        if previous_price == 0:
            continue
        absolute_change = latest_price - previous_price
        if absolute_change == 0:
            continue
        percent_change = (absolute_change / previous_price) * Decimal("100")
        signal_snapshot = signal_snapshots.get(row.id)
        if signal_snapshot is None or not is_top_mover_eligible(signal_snapshot):
            continue
        movers.append(
            TopMoverResponse(
                asset_id=row.id,
                name=row.name,
                category=row.category,
                game=row.game,
                set_name=row.set_name,
                external_id=getattr(row, "external_id", None),
                latest_price=latest_price,
                previous_price=previous_price,
                absolute_change=_quantize_change(absolute_change),
                percent_change=_quantize_change(percent_change),
                liquidity_score=signal_snapshot.liquidity_score,
                liquidity_label=signal_snapshot.liquidity_label,
                last_real_sale_at=signal_snapshot.last_real_sale_at,
                days_since_last_sale=signal_snapshot.days_since_last_sale,
                sales_count_7d=signal_snapshot.sales_count_7d,
                sales_count_30d=signal_snapshot.sales_count_30d,
                history_depth=signal_snapshot.history_depth,
                source_count=signal_snapshot.source_count,
                alert_confidence=signal_snapshot.alert_confidence,
                alert_confidence_label=signal_snapshot.alert_confidence_label,
            )
        )

    movers.sort(key=lambda item: abs(item.percent_change), reverse=True)
    return movers[:limit]


def get_top_value_assets(db: Session, limit: int = 10) -> list[TopValueResponse]:
    source_filter = get_active_price_source_filter(db)
    ranked = (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.currency,
            PriceHistory.source,
            PriceHistory.captured_at,
            func.row_number()
            .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.captured_at.desc())
            .label("price_rank"),
        )
        .where(source_filter)
        .subquery()
    )

    latest = aliased_subquery(ranked, "latest", 1)
    stmt = (
        select(
            Asset.id,
            Asset.name,
            Asset.category,
            Asset.game,
            Asset.set_name,
            latest.c.price.label("latest_price"),
            latest.c.currency,
            latest.c.source,
            latest.c.captured_at,
        )
        .join(latest, latest.c.asset_id == Asset.id)
        .order_by(latest.c.price.desc(), latest.c.captured_at.desc(), Asset.name.asc())
        .limit(limit)
    )

    rows = db.execute(stmt).all()
    return [
        TopValueResponse(
            asset_id=row.id,
            name=row.name,
            category=row.category,
            game=row.game,
            set_name=row.set_name,
            latest_price=Decimal(row.latest_price),
            currency=row.currency,
            source=row.source,
            captured_at=row.captured_at,
        )
        for row in rows
    ]


def get_recent_real_price_points(
    db: Session, asset_id, *, limit: int = PREDICTION_POINT_LIMIT
) -> list[tuple[Decimal, object]]:
    source_filter = get_active_price_source_filter(db)
    rows = db.execute(
        select(PriceHistory.price, PriceHistory.captured_at)
        .where(PriceHistory.asset_id == asset_id, source_filter)
        .order_by(PriceHistory.captured_at.desc())
        .limit(limit)
    ).all()
    return [(Decimal(row.price), row.captured_at) for row in rows]


def _build_asset_history_response(
    db: Session, match: AssetPriceResponse, *, limit: int = 5
) -> AssetHistoryResponse:
    source_filter = get_active_price_source_filter(db)
    rows = db.execute(
        select(
            PriceHistory.captured_at,
            PriceHistory.price,
            PriceHistory.currency,
            PriceHistory.source,
        )
        .where(
            PriceHistory.asset_id == match.asset_id,
            source_filter,
        )
        .order_by(PriceHistory.captured_at.desc())
        .limit(limit)
    ).all()

    # The current schema stores provider snapshot points, so history rows are exposed as
    # derived observations until sold-vs-listing event types exist in the data model.
    history = [
        PriceHistoryPointResponse(
            timestamp=row.captured_at,
            captured_at=row.captured_at,
            price=Decimal(row.price),
            currency=row.currency,
            source=row.source,
            point_type=HISTORY_POINT_TYPE_DERIVED,
            event_type=HISTORY_POINT_TYPE_DERIVED,
            is_real_data=(row.source != SAMPLE_PRICE_SOURCE),
        )
        for row in rows
    ]

    return AssetHistoryResponse(
        asset_id=match.asset_id,
        name=match.name,
        category=match.category,
        game=match.game,
        set_name=match.set_name,
        current_price=Decimal(match.latest_price),
        currency=match.currency,
        points_returned=len(history),
        image_url=match.image_url,
        liquidity_score=match.liquidity_score,
        liquidity_label=match.liquidity_label,
        last_real_sale_at=match.last_real_sale_at,
        days_since_last_sale=match.days_since_last_sale,
        sales_count_7d=match.sales_count_7d,
        sales_count_30d=match.sales_count_30d,
        history_depth=match.history_depth,
        source_count=match.source_count,
        alert_confidence=match.alert_confidence,
        alert_confidence_label=match.alert_confidence_label,
        history=history,
    )


def get_asset_history_by_name(db: Session, asset_name: str, limit: int = 5) -> AssetHistoryResponse | None:
    matches = get_asset_prices_by_name(db, asset_name)
    if not matches:
        return None
    return _build_asset_history_response(db, matches[0], limit=limit)


def get_asset_history_by_external_id(
    db: Session, external_id: str, limit: int = 5
) -> AssetHistoryResponse | None:
    match = get_asset_price_by_external_id(db, external_id)
    if match is None:
        return None
    return _build_asset_history_response(db, match, limit=limit)


def build_prediction_reason_not_enough_data(points_used: int) -> str:
    return (
        f"Only {points_used} recent real price point(s) are available. "
        "At least 3 are needed before the probability model can score direction."
    )


def normalize_feature(value: float, scale: float, clamp_limit: float = 2.5) -> float:
    if scale == 0:
        return 0.0
    normalized = value / scale
    return max(-clamp_limit, min(clamp_limit, normalized))


def get_move_returns(prices: list[Decimal]) -> list[float]:
    move_returns: list[float] = []
    for previous_price, current_price in zip(prices, prices[1:]):
        if previous_price == 0:
            move_returns.append(0.0)
            continue
        move_returns.append(float((current_price - previous_price) / previous_price))
    return move_returns


def get_direction_streak(move_returns: list[float]) -> tuple[int, int]:
    streak_sign: int | None = None
    streak_length = 0

    for move_return in reversed(move_returns):
        move_sign = 1 if move_return > 0 else -1 if move_return < 0 else 0
        if streak_sign is None:
            streak_sign = move_sign
            streak_length = 1
            continue
        if move_sign != streak_sign:
            break
        streak_length += 1

    return (streak_sign or 0), streak_length


def calculate_softmax_probabilities(scores: dict[str, float]) -> dict[str, Decimal]:
    max_score = max(scores.values())
    raw_probabilities = {
        label: math.exp(score - max_score)
        for label, score in scores.items()
    }
    total = sum(raw_probabilities.values())
    percentage_probabilities = {
        label: (raw_probability / total) * 100.0
        for label, raw_probability in raw_probabilities.items()
    }

    rounded = {
        label: Decimal(str(percentage)).quantize(Decimal("0.01"))
        for label, percentage in percentage_probabilities.items()
    }
    adjustment = Decimal("100.00") - sum(rounded.values())
    top_label = max(percentage_probabilities, key=percentage_probabilities.get)
    rounded[top_label] += adjustment
    return rounded


def build_prediction_reason(
    prediction: str,
    *,
    points_used: int,
    net_return: float,
    latest_vs_average: float,
    positive_moves: int,
    negative_moves: int,
    flat_moves: int,
    streak_sign: int,
    streak_length: int,
    volatility: float,
    up_probability: Decimal,
    down_probability: Decimal,
    flat_probability: Decimal,
) -> str:
    streak_label = "flat"
    if streak_sign > 0:
        streak_label = "up"
    elif streak_sign < 0:
        streak_label = "down"

    return (
        f"Used {points_used} recent real price points. Net return over the window is {net_return * 100:+.2f}%, "
        f"and the latest price is {latest_vs_average * 100:+.2f}% versus the recent average. "
        f"Recent moves were {positive_moves} up, {negative_moves} down, and {flat_moves} flat, "
        f"with a latest {streak_label} streak of {streak_length}. "
        f"Short-term volatility was {volatility * 100:.2f}%. "
        f"Softmax converted the class scores into Up {up_probability}%, Down {down_probability}%, and Flat {flat_probability}%, "
        f"so {prediction} ranked highest."
    )


def score_prediction_probabilities(prices: list[Decimal]) -> tuple[dict[str, Decimal], dict[str, float]]:
    latest_price = prices[-1]
    first_price = prices[0]
    average_price = sum(prices, Decimal("0")) / Decimal(len(prices))
    move_returns = get_move_returns(prices)

    positive_moves = sum(move > 0 for move in move_returns)
    negative_moves = sum(move < 0 for move in move_returns)
    flat_moves = len(move_returns) - positive_moves - negative_moves

    if first_price == 0:
        net_return = 0.0
    else:
        net_return = float((latest_price - first_price) / first_price)

    if average_price == 0:
        latest_vs_average = 0.0
    else:
        latest_vs_average = float((latest_price - average_price) / average_price)

    mean_move = sum(move_returns) / len(move_returns)
    volatility = math.sqrt(sum((move - mean_move) ** 2 for move in move_returns) / len(move_returns))
    average_absolute_move = sum(abs(move) for move in move_returns) / len(move_returns)
    direction_consistency = (positive_moves - negative_moves) / len(move_returns)
    streak_sign, streak_length = get_direction_streak(move_returns)
    streak_feature = streak_sign * (streak_length / len(move_returns))

    net_feature = normalize_feature(net_return, 0.03)
    average_feature = normalize_feature(latest_vs_average, 0.02)
    volatility_penalty = min(volatility / 0.02, 2.5)
    intensity_penalty = min(average_absolute_move / 0.02, 2.5)

    score_up = (
        1.4 * net_feature
        + 1.0 * average_feature
        + 0.9 * direction_consistency
        + 0.7 * streak_feature
        - 0.35 * volatility_penalty
    )
    score_down = (
        -1.4 * net_feature
        - 1.0 * average_feature
        - 0.9 * direction_consistency
        - 0.7 * streak_feature
        - 0.35 * volatility_penalty
    )
    score_flat = (
        1.6
        - 0.9 * abs(net_feature)
        - 0.7 * abs(average_feature)
        - 0.5 * abs(direction_consistency)
        - 0.4 * abs(streak_feature)
        - 0.6 * volatility_penalty
        - 0.4 * intensity_penalty
    )

    probabilities = calculate_softmax_probabilities(
        {
            "Up": score_up,
            "Down": score_down,
            "Flat": score_flat,
        }
    )
    features = {
        "net_return": net_return,
        "latest_vs_average": latest_vs_average,
        "positive_moves": float(positive_moves),
        "negative_moves": float(negative_moves),
        "flat_moves": float(flat_moves),
        "streak_sign": float(streak_sign),
        "streak_length": float(streak_length),
        "volatility": volatility,
    }
    return probabilities, features


def compute_prediction_from_recent_points(recent_points_desc: list[tuple[Decimal, object]]) -> PredictionComputation:
    points_used = len(recent_points_desc)

    if points_used < PREDICTION_MIN_POINTS:
        return PredictionComputation(
            prediction="Not enough data",
            up_probability=None,
            down_probability=None,
            flat_probability=None,
            reason=build_prediction_reason_not_enough_data(points_used),
            points_used=points_used,
        )

    recent_points = list(reversed(recent_points_desc))
    prices = [price for price, _captured_at in recent_points]
    probabilities, features = score_prediction_probabilities(prices)
    up_probability = probabilities["Up"]
    down_probability = probabilities["Down"]
    flat_probability = probabilities["Flat"]
    prediction = max(
        ("Up", "Down", "Flat"),
        key=lambda label: probabilities[label],
    )
    reason = build_prediction_reason(
        prediction,
        points_used=points_used,
        net_return=features["net_return"],
        latest_vs_average=features["latest_vs_average"],
        positive_moves=int(features["positive_moves"]),
        negative_moves=int(features["negative_moves"]),
        flat_moves=int(features["flat_moves"]),
        streak_sign=int(features["streak_sign"]),
        streak_length=int(features["streak_length"]),
        volatility=features["volatility"],
        up_probability=up_probability,
        down_probability=down_probability,
        flat_probability=flat_probability,
    )
    return PredictionComputation(
        prediction=prediction,
        up_probability=up_probability,
        down_probability=down_probability,
        flat_probability=flat_probability,
        reason=reason,
        points_used=points_used,
    )


def get_prediction_state_for_asset(db: Session, asset_id) -> PredictionComputation:
    recent_points_desc = get_recent_real_price_points(db, asset_id)
    return compute_prediction_from_recent_points(recent_points_desc)


def predict_assets_by_name(db: Session, asset_name: str) -> list[PricePredictionResponse]:
    matches = get_asset_prices_by_name(db, asset_name)
    predictions: list[PricePredictionResponse] = []

    for match in matches:
        prediction_state = get_prediction_state_for_asset(db, match.asset_id)

        predictions.append(
            PricePredictionResponse(
                asset_id=match.asset_id,
                name=match.name,
                category=match.category,
                game=match.game,
                set_name=match.set_name,
                current_price=Decimal(match.latest_price),
                currency=match.currency,
                prediction=prediction_state.prediction,
                up_probability=prediction_state.up_probability,
                down_probability=prediction_state.down_probability,
                flat_probability=prediction_state.flat_probability,
                reason=prediction_state.reason,
                points_used=prediction_state.points_used,
                captured_at=match.captured_at,
                image_url=match.image_url,
            )
        )

    return predictions
