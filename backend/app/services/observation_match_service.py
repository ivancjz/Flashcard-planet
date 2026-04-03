from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.observation_match_log import ObservationMatchLog

ASSET_IDENTITY_FIELDS = (
    "asset_class",
    "category",
    "name",
    "set_name",
    "card_number",
    "year",
    "language",
    "variant",
    "grade_company",
    "grade_score",
)

MATCH_STATUS_MATCHED_EXISTING = "matched_existing"
MATCH_STATUS_MATCHED_CREATED = "matched_created"
MATCH_STATUS_MATCHED_CANONICAL = "matched_canonical"
MATCH_STATUS_UNMATCHED_NO_PRICE = "unmatched_no_price"
MATCH_STATUS_UNMATCHED_AMBIGUOUS = "unmatched_ambiguous"


@dataclass(frozen=True)
class ObservationMatchResult:
    observation_log: ObservationMatchLog
    matched_asset: Asset | None
    asset_created: bool
    can_write_price_history: bool


def _normalize_canonical_value(value: object | None) -> str:
    if value is None:
        return "<none>"

    if isinstance(value, Decimal):
        return format(value.normalize(), "f")

    text = str(value).strip()
    return " ".join(text.lower().split()) or "<none>"


def build_canonical_key(asset_payload: dict[str, object]) -> str:
    return "|".join(
        f"{field}={_normalize_canonical_value(asset_payload.get(field))}"
        for field in ASSET_IDENTITY_FIELDS
    )


def _build_identity_match_clause(asset_payload: dict[str, object]):
    filters = []
    for field in ASSET_IDENTITY_FIELDS:
        column = getattr(Asset, field)
        value = asset_payload.get(field)
        if value is None:
            filters.append(column.is_(None))
        else:
            filters.append(column == value)
    return and_(*filters)


def _apply_asset_payload(
    asset: Asset,
    asset_payload: dict[str, object],
    *,
    preserve_provider_identity: bool,
) -> None:
    for key, value in asset_payload.items():
        if preserve_provider_identity and key in {"external_id", "metadata_json", "notes"}:
            continue
        setattr(asset, key, value)


def _create_observation_log(
    session: Session,
    *,
    provider: str,
    external_item_id: str,
    raw_title: str | None,
    raw_set_name: str | None,
    raw_card_number: str | None,
    raw_language: str | None,
    matched_asset_id,
    canonical_key: str | None,
    match_status: str,
    confidence: Decimal,
    reason: str,
    requires_review: bool,
) -> ObservationMatchLog:
    log = ObservationMatchLog(
        provider=provider,
        external_item_id=external_item_id,
        raw_title=raw_title,
        raw_set_name=raw_set_name,
        raw_card_number=raw_card_number,
        raw_language=raw_language,
        matched_asset_id=matched_asset_id,
        canonical_key=canonical_key,
        match_status=match_status,
        confidence=confidence,
        reason=reason,
        requires_review=requires_review,
    )
    session.add(log)
    session.flush()
    return log


def stage_observation_match(
    session: Session,
    *,
    provider: str,
    external_item_id: str,
    raw_title: str | None,
    raw_set_name: str | None,
    raw_card_number: str | None,
    raw_language: str | None,
    asset_payload: dict[str, object] | None,
    unmatched_reason: str | None = None,
) -> ObservationMatchResult:
    if asset_payload is None:
        observation_log = _create_observation_log(
            session,
            provider=provider,
            external_item_id=external_item_id,
            raw_title=raw_title,
            raw_set_name=raw_set_name,
            raw_card_number=raw_card_number,
            raw_language=raw_language,
            matched_asset_id=None,
            canonical_key=None,
            match_status=MATCH_STATUS_UNMATCHED_NO_PRICE,
            confidence=Decimal("0.00"),
            reason=unmatched_reason or "No canonical asset payload was available for this observation.",
            requires_review=False,
        )
        return ObservationMatchResult(
            observation_log=observation_log,
            matched_asset=None,
            asset_created=False,
            can_write_price_history=False,
        )

    canonical_key = build_canonical_key(asset_payload)
    external_id = str(asset_payload["external_id"])
    existing_asset = session.scalar(select(Asset).where(Asset.external_id == external_id))
    if existing_asset is not None:
        _apply_asset_payload(existing_asset, asset_payload, preserve_provider_identity=False)
        observation_log = _create_observation_log(
            session,
            provider=provider,
            external_item_id=external_item_id,
            raw_title=raw_title,
            raw_set_name=raw_set_name,
            raw_card_number=raw_card_number,
            raw_language=raw_language,
            matched_asset_id=existing_asset.id,
            canonical_key=canonical_key,
            match_status=MATCH_STATUS_MATCHED_EXISTING,
            confidence=Decimal("1.00"),
            reason="Matched existing canonical asset by provider external id.",
            requires_review=False,
        )
        return ObservationMatchResult(
            observation_log=observation_log,
            matched_asset=existing_asset,
            asset_created=False,
            can_write_price_history=True,
        )

    canonical_matches = session.execute(
        select(Asset).where(_build_identity_match_clause(asset_payload))
    ).scalars().all()
    if len(canonical_matches) > 1:
        observation_log = _create_observation_log(
            session,
            provider=provider,
            external_item_id=external_item_id,
            raw_title=raw_title,
            raw_set_name=raw_set_name,
            raw_card_number=raw_card_number,
            raw_language=raw_language,
            matched_asset_id=None,
            canonical_key=canonical_key,
            match_status=MATCH_STATUS_UNMATCHED_AMBIGUOUS,
            confidence=Decimal("0.00"),
            reason="Multiple canonical asset candidates matched this observation; review is required.",
            requires_review=True,
        )
        return ObservationMatchResult(
            observation_log=observation_log,
            matched_asset=None,
            asset_created=False,
            can_write_price_history=False,
        )

    if len(canonical_matches) == 1:
        matched_asset = canonical_matches[0]
        _apply_asset_payload(matched_asset, asset_payload, preserve_provider_identity=True)
        observation_log = _create_observation_log(
            session,
            provider=provider,
            external_item_id=external_item_id,
            raw_title=raw_title,
            raw_set_name=raw_set_name,
            raw_card_number=raw_card_number,
            raw_language=raw_language,
            matched_asset_id=matched_asset.id,
            canonical_key=canonical_key,
            match_status=MATCH_STATUS_MATCHED_CANONICAL,
            confidence=Decimal("0.90"),
            reason=(
                "Matched existing canonical asset by identity fields while preserving the stored external id; "
                "review is recommended because the provider external id differs."
            ),
            requires_review=True,
        )
        return ObservationMatchResult(
            observation_log=observation_log,
            matched_asset=matched_asset,
            asset_created=False,
            can_write_price_history=True,
        )

    matched_asset = Asset(**asset_payload)
    session.add(matched_asset)
    session.flush()
    observation_log = _create_observation_log(
        session,
        provider=provider,
        external_item_id=external_item_id,
        raw_title=raw_title,
        raw_set_name=raw_set_name,
        raw_card_number=raw_card_number,
        raw_language=raw_language,
        matched_asset_id=matched_asset.id,
        canonical_key=canonical_key,
        match_status=MATCH_STATUS_MATCHED_CREATED,
        confidence=Decimal("1.00"),
        reason="Created a canonical asset from a deterministic provider observation before writing price history.",
        requires_review=False,
    )
    return ObservationMatchResult(
        observation_log=observation_log,
        matched_asset=matched_asset,
        asset_created=True,
        can_write_price_history=True,
    )
