from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.deps import get_database
from backend.app.api.routes.web import router as web_router


def _make_row(**kwargs):
    """Return an object that quacks like a SQLAlchemy Row with _mapping."""
    row = MagicMock()
    row._mapping = kwargs
    return row


def _db_dep(db):
    """Wrap a mock db as a FastAPI dependency override (generator function)."""
    def _gen():
        yield db
    return _gen


def _make_app(db):
    app = FastAPI()
    app.include_router(web_router)
    app.dependency_overrides[get_database] = _db_dep(db)
    return app, TestClient(app)


class WebStatsTests(TestCase):
    def _db_with(self, total, signal_rows, last_ingest):
        db = MagicMock()
        execute_results = [
            MagicMock(scalar=MagicMock(return_value=total)),
            MagicMock(fetchall=MagicMock(return_value=signal_rows)),
            MagicMock(scalar=MagicMock(return_value=last_ingest)),
        ]
        db.execute.side_effect = execute_results
        return db

    def setUp(self):
        from datetime import datetime, timezone
        self.last_ingest = datetime(2026, 4, 22, 10, 0, 0, tzinfo=timezone.utc)

        signal_rows = [
            MagicMock(label="BREAKOUT", cnt=5),
            MagicMock(label="MOVE", cnt=12),
        ]
        db = self._db_with(total=100, signal_rows=signal_rows, last_ingest=self.last_ingest)

        app, self.client = _make_app(db)

    def test_total_assets(self):
        resp = self.client.get("/api/v1/web/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total_assets"], 100)

    def test_signal_counts_present_with_defaults(self):
        resp = self.client.get("/api/v1/web/stats")
        counts = resp.json()["signal_counts"]
        self.assertEqual(counts["BREAKOUT"], 5)
        self.assertEqual(counts["MOVE"], 12)
        self.assertEqual(counts["WATCH"], 0)
        self.assertEqual(counts["IDLE"], 0)
        self.assertEqual(counts["INSUFFICIENT_DATA"], 0)

    def test_last_ingest_utc_is_iso(self):
        resp = self.client.get("/api/v1/web/stats")
        self.assertIn("2026-04-22", resp.json()["last_ingest_utc"])

    def test_sources_active_present(self):
        resp = self.client.get("/api/v1/web/stats")
        sources = resp.json()["sources_active"]
        self.assertIn("pokemon_tcg_api", sources)
        self.assertIn("ebay_sold", sources)

    def test_no_ingest_returns_null(self):
        signal_rows = []
        db = self._db_with(total=0, signal_rows=signal_rows, last_ingest=None)
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["last_ingest_utc"])


class WebTickerTests(TestCase):
    def setUp(self):
        rows = [
            _make_row(asset_id="abc", name="Charizard", signal="BREAKOUT",
                      price_delta_pct=15.2, current_price=42.50),
            _make_row(asset_id="def", name="Blastoise", signal="MOVE",
                      price_delta_pct=-8.0, current_price=18.00),
        ]
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = rows
        app, self.client = _make_app(db)

    def test_returns_list(self):
        resp = self.client.get("/api/v1/web/ticker")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

    def test_item_shape(self):
        resp = self.client.get("/api/v1/web/ticker")
        item = resp.json()[0]
        self.assertIn("asset_id", item)
        self.assertIn("name", item)
        self.assertIn("signal", item)
        self.assertIn("price_delta_pct", item)


class WebCardsTests(TestCase):
    def _make_db(self, total=5, cards=None):
        if cards is None:
            cards = [
                _make_row(asset_id="id1", name="Pikachu", set_name="Base",
                          rarity="holo", card_type="pokemon", signal="BREAKOUT",
                          price_delta_pct=10.0, liquidity_score=0.8,
                          tcg_price=25.0, ebay_price=20.0, volume_24h=3, image_url=None),
            ]
        db = MagicMock()
        db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=total)),
            MagicMock(fetchall=MagicMock(return_value=cards)),
        ]
        return db

    def test_default_params_returns_200(self):
        db = self._make_db()
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/cards")
        self.assertEqual(resp.status_code, 200)

    def test_response_shape(self):
        db = self._make_db(total=1)
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/cards")
        body = resp.json()
        self.assertIn("cards", body)
        self.assertIn("total", body)
        self.assertIn("limit", body)
        self.assertIn("offset", body)
        self.assertEqual(body["total"], 1)

    def test_card_fields(self):
        db = self._make_db()
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/cards")
        card = resp.json()["cards"][0]
        for field in ("asset_id", "name", "set_name", "rarity", "card_type",
                      "signal", "price_delta_pct", "tcg_price", "ebay_price",
                      "volume_24h", "image_url"):
            self.assertIn(field, card)

    def test_signal_filter_passes_param(self):
        db = self._make_db()
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/cards?signal=BREAKOUT")
        self.assertEqual(resp.status_code, 200)

    def test_limit_offset_params(self):
        db = self._make_db()
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/cards?limit=10&offset=20")
        body = resp.json()
        self.assertEqual(body["limit"], 10)
        self.assertEqual(body["offset"], 20)


class WebCardDetailTests(TestCase):
    def _make_db(self, card_row, history_rows=None, signal_history_rows=None):
        if history_rows is None:
            history_rows = []
        if signal_history_rows is None:
            signal_history_rows = []
        db = MagicMock()
        db.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=card_row)),
            MagicMock(fetchall=MagicMock(return_value=history_rows)),
            MagicMock(fetchall=MagicMock(return_value=signal_history_rows)),
        ]
        return db

    def test_returns_card_detail(self):
        card = _make_row(
            asset_id="abc123", name="Charizard", set_name="Base",
            rarity="ultra", card_type="pokemon", signal="BREAKOUT",
            price_delta_pct=15.0, liquidity_score=0.9,
            tcg_price=100.0, ebay_price=90.0, image_url=None, spread_pct=10.0,
        )
        from datetime import date
        h = MagicMock(date=date(2026, 4, 22), tcg_price=100.0, ebay_price=90.0)
        db = self._make_db(card, [h])
        app, client = _make_app(db)

        resp = client.get("/api/v1/web/cards/abc123")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["name"], "Charizard")
        self.assertIn("price_history", body)

    def test_card_not_found_returns_404(self):
        db = self._make_db(None)
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/cards/nonexistent-uuid")
        self.assertEqual(resp.status_code, 404)

    def test_price_history_shape(self):
        card = _make_row(
            asset_id="abc123", name="Charizard", set_name="Base",
            rarity="ultra", card_type="pokemon", signal="BREAKOUT",
            price_delta_pct=15.0, liquidity_score=0.9,
            tcg_price=100.0, ebay_price=90.0, image_url=None, spread_pct=10.0,
        )
        from datetime import date
        history = [
            MagicMock(date=date(2026, 4, 20), tcg_price=95.0, ebay_price=85.0),
            MagicMock(date=date(2026, 4, 21), tcg_price=97.5, ebay_price=None),
        ]
        db = self._make_db(card, history)
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/cards/abc123")
        ph = resp.json()["price_history"]
        self.assertEqual(len(ph), 2)
        self.assertIn("date", ph[0])
        self.assertIn("tcg_price", ph[0])
        self.assertIn("ebay_price", ph[0])
        self.assertIsNone(ph[1]["ebay_price"])

    def test_signal_history_query_excludes_pre_previous_label_rows(self):
        card = _make_row(
            asset_id="abc123", name="Charizard", set_name="Base",
            rarity="ultra", card_type="pokemon", signal="BREAKOUT",
            price_delta_pct=15.0, liquidity_score=0.9,
            tcg_price=100.0, ebay_price=90.0, image_url=None, spread_pct=10.0,
        )
        db = self._make_db(card)
        app, client = _make_app(db)

        resp = client.get("/api/v1/web/cards/abc123")

        self.assertEqual(resp.status_code, 200)
        signal_history_sql = str(db.execute.call_args_list[2].args[0])
        self.assertIn("previous_label IS NOT NULL", signal_history_sql)
        self.assertIn("label IS DISTINCT FROM previous_label", signal_history_sql)

    def test_detail_price_query_uses_game_specific_market_source(self):
        card = _make_row(
            asset_id="abc123", name="Dark Magician", set_name="LOB",
            rarity="ultra", card_type="spellcaster", signal="IDLE",
            price_delta_pct=0.0, liquidity_score=0.3,
            tcg_price=2.5, ebay_price=None, image_url=None, spread_pct=None,
        )
        db = self._make_db(card)
        app, client = _make_app(db)

        resp = client.get("/api/v1/web/cards/abc123")

        self.assertEqual(resp.status_code, 200)
        detail_sql = str(db.execute.call_args_list[0].args[0])
        self.assertIn("CASE a.game WHEN 'yugioh' THEN 'ygoprodeck_api' ELSE 'pokemon_tcg_api' END", detail_sql)

    # TEMP: tests added for testing phase — ai_analysis returned unconditionally.
    # Restore when commercial tier is finalized: update to assert tier-gated behaviour.
    def test_ai_analysis_returned_when_explanation_present(self):
        card = _make_row(
            asset_id="abc123", name="Charizard", set_name="Base",
            rarity="ultra", card_type="pokemon", signal="BREAKOUT",
            price_delta_pct=15.0, liquidity_score=0.9,
            tcg_price=100.0, ebay_price=90.0, image_url=None, spread_pct=10.0,
            ai_analysis="Price jumped 15% above baseline on high eBay volume.",
        )
        db = self._make_db(card)
        app, client = _make_app(db)

        resp = client.get("/api/v1/web/cards/abc123")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ai_analysis"], "Price jumped 15% above baseline on high eBay volume.")

    def test_ai_analysis_is_null_when_no_explanation(self):
        card = _make_row(
            asset_id="abc123", name="Charizard", set_name="Base",
            rarity="ultra", card_type="pokemon", signal="IDLE",
            price_delta_pct=0.0, liquidity_score=0.3,
            tcg_price=10.0, ebay_price=None, image_url=None, spread_pct=None,
            ai_analysis=None,
        )
        db = self._make_db(card)
        app, client = _make_app(db)

        resp = client.get("/api/v1/web/cards/abc123")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["ai_analysis"])

    def test_detail_sql_selects_explanation_as_ai_analysis(self):
        card = _make_row(
            asset_id="abc123", name="Charizard", set_name="Base",
            rarity="ultra", card_type="pokemon", signal="IDLE",
            price_delta_pct=0.0, liquidity_score=0.3,
            tcg_price=10.0, ebay_price=None, image_url=None, spread_pct=None,
            ai_analysis=None,
        )
        db = self._make_db(card)
        app, client = _make_app(db)

        client.get("/api/v1/web/cards/abc123")

        detail_sql = str(db.execute.call_args_list[0].args[0])
        self.assertIn("s.explanation", detail_sql)
        self.assertIn("ai_analysis", detail_sql)


class WebAlertsTests(TestCase):
    def _make_db(self, rows):
        from datetime import datetime, timezone
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = rows
        return db

    def _make_alert_row(self, signal="BREAKOUT", prev="WATCH"):
        from datetime import datetime, timezone
        row = MagicMock()
        row._mapping = {
            "id": "alert-1",
            "asset_id": "card-1",
            "card_name": "Charizard",
            "previous_signal": prev,
            "current_signal": signal,
            "price_delta_pct": 10.0,
            "created_at": datetime(2026, 4, 22, 9, 0, 0, tzinfo=timezone.utc),
            "severity": "high",
        }
        return row

    def test_returns_alerts_list(self):
        rows = [self._make_alert_row()]
        db = self._make_db(rows)
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/alerts")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("alerts", body)
        self.assertIn("total", body)
        self.assertEqual(body["total"], 1)

    def test_alert_shape(self):
        rows = [self._make_alert_row()]
        db = self._make_db(rows)
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/alerts")
        alert = resp.json()["alerts"][0]
        for field in ("id", "asset_id", "card_name", "previous_signal",
                      "current_signal", "severity", "created_at"):
            self.assertIn(field, alert)

    def test_created_at_is_iso_string(self):
        rows = [self._make_alert_row()]
        db = self._make_db(rows)
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/alerts")
        alert = resp.json()["alerts"][0]
        self.assertIsInstance(alert["created_at"], str)
        self.assertIn("2026-04-22", alert["created_at"])

    def test_empty_db_returns_empty_list(self):
        db = self._make_db([])
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/alerts")
        body = resp.json()
        self.assertEqual(body["alerts"], [])
        self.assertEqual(body["total"], 0)

    def test_high_filter_passes_without_error(self):
        rows = [self._make_alert_row(signal="BREAKOUT")]
        db = self._make_db(rows)
        app, client = _make_app(db)
        resp = client.get("/api/v1/web/alerts?filter=HIGH")
        self.assertEqual(resp.status_code, 200)
