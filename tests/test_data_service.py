from unittest.mock import MagicMock, patch
import uuid
from decimal import Decimal

from backend.app.core.data_service import DataService
from backend.app.core.response_types import CardDetailResponse, SignalsResponse


def _mock_card_detail_vm():
    vm = MagicMock()
    vm.name = "Charizard Base Set"
    vm.latest_price = Decimal("150.00")    # CardDetailViewModel uses latest_price
    vm.price_history = []
    vm.sample_size = 47
    vm.match_confidence_avg = Decimal("0.85")
    vm.data_age = None
    vm.source_breakdown = {"eBay": 33, "TCG": 14}
    return vm


def _mock_signals_feed_result():
    result = MagicMock()
    result.rows = []
    result.hidden_count = 12    # SignalsFeedResult uses hidden_count, not total_eligible
    return result


class TestDataServiceGetCardDetail:
    @patch("backend.app.core.data_service.build_card_detail")
    def test_returns_card_detail_response_for_known_asset(self, mock_build):
        mock_build.return_value = _mock_card_detail_vm()
        db = MagicMock()
        asset_id = uuid.uuid4()

        result = DataService.get_card_detail(db, asset_id, access_tier="free")

        assert isinstance(result, CardDetailResponse)
        assert result.card_name == "Charizard Base Set"
        assert result.sample_size == 47
        assert result.access_tier == "free"

    @patch("backend.app.core.data_service.build_card_detail")
    def test_returns_none_for_unknown_asset(self, mock_build):
        mock_build.return_value = None
        db = MagicMock()
        result = DataService.get_card_detail(db, uuid.uuid4(), access_tier="free")
        assert result is None

    @patch("backend.app.core.data_service.build_card_detail")
    def test_free_user_gets_pro_gate_config_for_price_history(self, mock_build):
        mock_build.return_value = _mock_card_detail_vm()
        db = MagicMock()
        result = DataService.get_card_detail(db, uuid.uuid4(), access_tier="free")
        assert result.pro_gate_config is not None
        assert result.pro_gate_config.is_locked is True

    @patch("backend.app.core.data_service.build_card_detail")
    def test_pro_user_gets_no_pro_gate(self, mock_build):
        mock_build.return_value = _mock_card_detail_vm()
        db = MagicMock()
        result = DataService.get_card_detail(db, uuid.uuid4(), access_tier="pro")
        assert result.pro_gate_config is None


class TestDataServiceGetSignals:
    @patch("backend.app.core.data_service.build_signals_feed")
    def test_returns_signals_response(self, mock_feed):
        mock_feed.return_value = _mock_signals_feed_result()
        db = MagicMock()
        result = DataService.get_signals(db, access_tier="free")
        assert isinstance(result, SignalsResponse)
        assert result.total_eligible == 12
        assert result.access_tier == "free"

    @patch("backend.app.core.data_service.build_signals_feed")
    def test_free_user_gets_signals_pro_gate(self, mock_feed):
        mock_feed.return_value = _mock_signals_feed_result()
        db = MagicMock()
        result = DataService.get_signals(db, access_tier="free")
        assert result.pro_gate_config is not None
        assert result.pro_gate_config.urgency == "high"

    @patch("backend.app.core.data_service.build_signals_feed")
    def test_pro_user_gets_no_signals_gate(self, mock_feed):
        mock_feed.return_value = _mock_signals_feed_result()
        db = MagicMock()
        result = DataService.get_signals(db, access_tier="pro")
        assert result.pro_gate_config is None
