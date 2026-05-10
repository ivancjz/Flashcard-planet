"""tests/test_ygo_metadata_set_shape.py

Tests for the YGO metadata.set nested-block fix.

Bug (Lesson 4 — designed, ran, written, but downstream-filtered silently):
  YGO ingest wrote metadata as flat {"set_code": "LOB-001", "set_name": "..."}.
  All web queries (filters/sets, set_id filter on /cards, index 0023) read
  metadata->'set'->>'id'. Result: every YGO asset was invisible to set-aware
  queries — the cardinality of /filters/sets?game=yugioh was permanently 0.

Fix: ygo.py writes both flat (legacy) and nested (web-compatible) shapes.
Migration 0028 backfills the nested shape for existing YGO rows.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.asset import Asset


def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _session():
    _coerce_postgres_types()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


_FAKE_RAW_CARD = {
    "id": 89631139,
    "name": "Blue-Eyes White Dragon",
    "type": "Normal Monster",
    "card_images": [{"image_url_small": "https://example.com/img.jpg"}],
    "atk": 3000, "def": 2500, "level": 8, "race": "Dragon", "attribute": "LIGHT",
}
_FAKE_ENTRY = {
    "set_code": "LOB-001",
    "set_name": "Legend of Blue Eyes White Dragon",
    "set_rarity": "Ultra Rare",
    "set_price": "62.15",
}


class TestYgoIngestWritesNestedSet:
    """ingest_ygo_sets must populate metadata.set.id and metadata.set.name
    so the web layer's `metadata->'set'->>'id'` queries find YGO assets."""

    def test_ingest_writes_nested_set_block(self):
        from backend.app.ingestion.ygo import ingest_ygo_sets
        from backend.app.ingestion.game_data.yugioh_client import YugiohClient as RealClient

        entries = [(_FAKE_RAW_CARD, _FAKE_ENTRY)]

        with _session() as db:
            with (
                patch("backend.app.ingestion.ygo.YugiohClient") as MockClient,
                patch("backend.app.ingestion.ygo.time.sleep"),
            ):
                MockClient.make_external_id.side_effect = RealClient.make_external_id
                mock_instance = MockClient.return_value
                mock_instance.fetch_set_entries.return_value = entries
                mock_instance.rate_limit_per_second = 10.0

                ingest_ygo_sets(db, set_codes=["LOB"])

            asset = db.execute(select(Asset)).scalars().first()

        assert asset is not None
        meta = asset.metadata_json
        assert "set" in meta, "metadata.set nested block missing"
        assert meta["set"]["id"] == "LOB", (
            f"metadata.set.id should be expansion code (LOB), got {meta['set'].get('id')!r}"
        )
        assert meta["set"]["name"] == "Legend of Blue Eyes White Dragon"

    def test_ingest_keeps_flat_set_code_for_legacy_compat(self):
        """Flat set_code/set_name keys must still exist — /diag/ygo-verify
        and existing operator SQL queries depend on them."""
        from backend.app.ingestion.ygo import ingest_ygo_sets
        from backend.app.ingestion.game_data.yugioh_client import YugiohClient as RealClient

        entries = [(_FAKE_RAW_CARD, _FAKE_ENTRY)]

        with _session() as db:
            with (
                patch("backend.app.ingestion.ygo.YugiohClient") as MockClient,
                patch("backend.app.ingestion.ygo.time.sleep"),
            ):
                MockClient.make_external_id.side_effect = RealClient.make_external_id
                mock_instance = MockClient.return_value
                mock_instance.fetch_set_entries.return_value = entries
                mock_instance.rate_limit_per_second = 10.0

                ingest_ygo_sets(db, set_codes=["LOB"])

            asset = db.execute(select(Asset)).scalars().first()

        meta = asset.metadata_json
        assert meta["set_code"] == "LOB-001", "flat set_code dropped — breaks /diag/ygo-verify"
        assert meta["set_name"] == "Legend of Blue Eyes White Dragon"


class TestYgoVisibleToSetFilter:
    """Replicates the SQL pattern from /api/v1/web/filters/sets:

        SELECT metadata->'set'->>'id' FROM assets
        WHERE game = 'yugioh' AND metadata->'set'->>'id' IS NOT NULL

    Before the fix this returned zero rows for YGO. After the fix it must
    return the set_code of every ingested YGO asset.
    """

    def test_filters_sets_query_finds_ygo_after_ingest(self):
        from backend.app.ingestion.ygo import ingest_ygo_sets
        from backend.app.ingestion.game_data.yugioh_client import YugiohClient as RealClient

        entries = [
            ({**_FAKE_RAW_CARD, "id": i, "name": f"Card {i}"},
             {**_FAKE_ENTRY, "set_code": f"LOB-{i:03d}"})
            for i in range(1, 4)
        ]

        with _session() as db:
            with (
                patch("backend.app.ingestion.ygo.YugiohClient") as MockClient,
                patch("backend.app.ingestion.ygo.time.sleep"),
            ):
                MockClient.make_external_id.side_effect = RealClient.make_external_id
                mock_instance = MockClient.return_value
                mock_instance.fetch_set_entries.return_value = entries
                mock_instance.rate_limit_per_second = 10.0

                ingest_ygo_sets(db, set_codes=["LOB"])

            assets = db.execute(select(Asset)).scalars().all()

        set_ids = {
            a.metadata_json.get("set", {}).get("id")
            for a in assets
            if a.metadata_json.get("set", {}).get("id")
        }

        # All 3 cards belong to the same expansion "LOB", so set_id groups them into 1 bucket.
        # This matches the web layer's /filters/sets behavior (13 expansion buckets, not 67 cards).
        assert set_ids == {"LOB"}, (
            f"YGO set filter should return expansion code, got {set_ids}"
        )


class TestMigration0028BackfillsLegacyYgoRows:
    """Pre-fix YGO assets in production have flat metadata only. Migration 0028
    must add the nested set block by reading from the existing flat fields,
    without dropping the flat fields."""

    def test_legacy_flat_only_asset_gets_nested_set_after_backfill_logic(self):
        with _session() as db:
            legacy = Asset(
                id=uuid.uuid4(),
                asset_class="TCG",
                game="yugioh",
                category="Normal Monster",
                name="Blue-Eyes White Dragon",
                set_name="Legend of Blue Eyes White Dragon",
                card_number="LOB-001",
                language="EN",
                variant="Ultra Rare",
                external_id="yugioh:89631139:LOB-001:ultra_rare",
                metadata_json={
                    "konami_id": 89631139,
                    "set_code": "LOB-001",
                    "set_name": "Legend of Blue Eyes White Dragon",
                    "rarity": "Ultra Rare",
                },
            )
            db.add(legacy)
            db.commit()

            # Apply the equivalent of migration 0028's UPDATE (in-Python form
            # because SQLite can't run jsonb_build_object / split_part).
            # The migration derives expansion code via split_part(set_code, '-', 1).
            printing_code = legacy.metadata_json["set_code"]   # e.g. LOB-001
            expansion_code = printing_code.split("-", 1)[0]    # e.g. LOB
            legacy.metadata_json = {
                **legacy.metadata_json,
                "set": {
                    "id": expansion_code,
                    "name": legacy.metadata_json["set_name"],
                    "total": None,
                },
            }
            db.commit()
            db.refresh(legacy)

        assert legacy.metadata_json["set"]["id"] == "LOB"
        assert legacy.metadata_json["set"]["name"] == "Legend of Blue Eyes White Dragon"
        assert legacy.metadata_json["set_code"] == "LOB-001"


class TestYgoSetFixVerifyDiagInvariant:
    """Validate C_regression_zero invariant: assets where set.id == card_number must be 0.

    Tests the Python-level equivalent of the diagnostic endpoint's regression check:
        SELECT COUNT(*) FROM assets
        WHERE game = 'yugioh' AND metadata->'set'->>'id' = card_number

    Cannot run the actual PostgreSQL JSON operator in SQLite; instead verifies
    the invariant in Python so that: (a) a correct asset produces count=0,
    (b) a bugged asset (set.id == card_number, the original failure mode) is detected.
    """

    @staticmethod
    def _count_printing_code_assets(assets) -> int:
        """Python equivalent of the C_regression SQL — counts assets where set.id == card_number."""
        return sum(
            1 for a in assets
            if a.metadata_json.get("set", {}).get("id") == a.card_number
        )

    def test_correct_asset_produces_zero_regression_count(self):
        """After fix: set.id = expansion code (LOB), card_number = printing code (LOB-001) → no match."""
        with _session() as db:
            asset = Asset(
                id=uuid.uuid4(),
                asset_class="TCG",
                game="yugioh",
                category="Normal Monster",
                name="Blue-Eyes White Dragon",
                set_name="Legend of Blue Eyes White Dragon",
                card_number="LOB-001",          # printing code
                language="EN",
                variant="Ultra Rare",
                external_id="yugioh:89631139:LOB-001:ultra_rare",
                metadata_json={
                    "set_code": "LOB-001",
                    "set": {"id": "LOB", "name": "Legend of Blue Eyes White Dragon", "total": None},
                },
            )
            db.add(asset)
            db.commit()
            assets = db.execute(select(Asset)).scalars().all()

        assert self._count_printing_code_assets(assets) == 0, (
            "C_regression_zero should be True for correctly-fixed assets"
        )

    def test_bugged_asset_triggers_regression_count(self):
        """Before fix (original bug): set.id = printing code = card_number → count > 0."""
        with _session() as db:
            asset = Asset(
                id=uuid.uuid4(),
                asset_class="TCG",
                game="yugioh",
                category="Normal Monster",
                name="Blue-Eyes White Dragon",
                set_name="Legend of Blue Eyes White Dragon",
                card_number="LOB-001",
                language="EN",
                variant="Ultra Rare",
                external_id="yugioh:89631139:LOB-001:ultra_rare",
                metadata_json={
                    "set_code": "LOB-001",
                    "set": {"id": "LOB-001", "name": "Legend of Blue Eyes White Dragon", "total": None},
                },
            )
            db.add(asset)
            db.commit()
            assets = db.execute(select(Asset)).scalars().all()

        assert self._count_printing_code_assets(assets) == 1, (
            "C_regression_zero should detect the original bug (set.id == card_number)"
        )
