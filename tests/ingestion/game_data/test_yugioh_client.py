"""
tests/ingestion/game_data/test_yugioh_client.py

Covers:
  a. YugiohClient structurally satisfies GameDataClient Protocol
  b. game property returns Game.YUGIOH
  c. rate_limit_per_second is positive
  d. fetch_card_by_external_id returns CardMetadata on valid API response
  e. fetch_card_by_external_id returns None on 400 (card not found)
  f. fetch_card_by_external_id raises on 500
  g. raw_payload fully preserved in CardMetadata
  h. set_code/set_name/rarity mapped from card_sets[0]
  i. card_sets empty → set_code/set_name fallback to UNKNOWN/Unknown
  j. image_url mapped from card_images[0]; get_image_url size variants
  k. fetch_cards_by_set returns list of CardMetadata
  l. list_sets returns list of SetMetadata
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import httpx

from backend.app.ingestion.game_data.base import CardMetadata, SetMetadata
from backend.app.models.game import Game


FAKE_CARD_RAW = {
    "id": 89631139,
    "name": "Blue-Eyes White Dragon",
    "type": "Normal Monster",
    "card_sets": [
        {
            "set_name": "Legend of Blue Eyes White Dragon",
            "set_code": "LOB-001",
            "set_rarity": "Ultra Rare",
            "set_rarity_code": "(UR)",
            "set_price": "62.15",
        }
    ],
    "card_images": [
        {
            "id": 89631139,
            "image_url": "https://images.ygoprodeck.com/images/cards/89631139.jpg",
            "image_url_small": "https://images.ygoprodeck.com/images/cards_small/89631139.jpg",
            "image_url_cropped": "https://images.ygoprodeck.com/images/cards_cropped/89631139.jpg",
        }
    ],
    "card_prices": [{"tcgplayer_price": "0.11", "ebay_price": "5.95"}],
    "banlist_info": None,
}

FAKE_API_RESPONSE = {"data": [FAKE_CARD_RAW]}

FAKE_SETS_RESPONSE = [
    {
        "set_name": "Legend of Blue Eyes White Dragon",
        "set_code": "LOB",
        "num_of_cards": 126,
        "tcg_date": "2002-03-08",
        "set_image": "https://images.ygoprodeck.com/images/sets/LOB.jpg",
    },
    {
        "set_name": "Metal Raiders",
        "set_code": "MRD",
        "num_of_cards": 144,
        "tcg_date": "2002-06-26",
    },
]


def _make_client():
    from backend.app.ingestion.game_data.yugioh_client import YugiohClient
    return YugiohClient()


# ---------------------------------------------------------------------------
# a/b/c. Protocol conformance, game property, rate limit
# ---------------------------------------------------------------------------

class TestYugiohClientProtocol:
    def test_isinstance_game_data_client_protocol(self):
        from backend.app.ingestion.game_data.base import GameDataClient
        client = _make_client()
        assert isinstance(client, GameDataClient)

    def test_game_property_is_yugioh(self):
        client = _make_client()
        assert client.game == Game.YUGIOH

    def test_rate_limit_per_second_is_positive(self):
        client = _make_client()
        assert client.rate_limit_per_second > 0


# ---------------------------------------------------------------------------
# d. fetch_card_by_external_id — success
# ---------------------------------------------------------------------------

class TestYugiohClientFetchCard:
    def _mock_get(self, response_data):
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_returns_card_metadata_on_success(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert isinstance(result, CardMetadata)

    def test_external_id_mapped_as_string(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert result.external_id == "89631139"

    def test_name_mapped_correctly(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert result.name == "Blue-Eyes White Dragon"

    def test_game_field_is_yugioh(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert result.game == Game.YUGIOH

    def test_image_url_from_card_images(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert result.image_url == "https://images.ygoprodeck.com/images/cards/89631139.jpg"


# ---------------------------------------------------------------------------
# e. 400 response → None
# ---------------------------------------------------------------------------

    def test_returns_none_when_card_not_found_400(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad request",
            request=MagicMock(),
            response=MagicMock(status_code=400),
        )
        with patch.object(client.client, "get", return_value=mock_resp):
            result = client.fetch_card_by_external_id("99999999999")
        assert result is None


# ---------------------------------------------------------------------------
# f. 500 response → raises
# ---------------------------------------------------------------------------

    def test_raises_on_500_error(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "server error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        with patch.object(client.client, "get", return_value=mock_resp):
            with pytest.raises(httpx.HTTPStatusError):
                client.fetch_card_by_external_id("89631139")


# ---------------------------------------------------------------------------
# g. raw_payload preserved
# ---------------------------------------------------------------------------

    def test_raw_payload_fully_preserved(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert result.raw_payload == FAKE_CARD_RAW


# ---------------------------------------------------------------------------
# h. set_code / set_name / rarity from card_sets[0]
# ---------------------------------------------------------------------------

    def test_set_code_from_card_sets_0(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert result.set_code == "LOB-001"

    def test_set_name_from_card_sets_0(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert result.set_name == "Legend of Blue Eyes White Dragon"

    def test_rarity_from_card_sets_0(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_API_RESPONSE)):
            result = client.fetch_card_by_external_id("89631139")
        assert result.rarity == "Ultra Rare"


# ---------------------------------------------------------------------------
# i. card_sets empty → UNKNOWN fallback
# ---------------------------------------------------------------------------

    def test_set_code_falls_back_to_unknown_when_no_sets(self):
        raw = {**FAKE_CARD_RAW, "card_sets": []}
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get({"data": [raw]})):
            result = client.fetch_card_by_external_id("89631139")
        assert result.set_code == "UNKNOWN"

    def test_set_name_falls_back_to_unknown_when_no_sets(self):
        raw = {**FAKE_CARD_RAW, "card_sets": []}
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get({"data": [raw]})):
            result = client.fetch_card_by_external_id("89631139")
        assert result.set_name == "Unknown"

    def test_rarity_is_none_when_no_sets(self):
        raw = {**FAKE_CARD_RAW, "card_sets": []}
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get({"data": [raw]})):
            result = client.fetch_card_by_external_id("89631139")
        assert result.rarity is None


# ---------------------------------------------------------------------------
# j. get_image_url size variants
# ---------------------------------------------------------------------------

class TestYugiohClientGetImageUrl:
    def _make_metadata(self, image_url=None, image_url_small=None, image_url_cropped=None):
        raw = {
            **FAKE_CARD_RAW,
            "card_images": [{"id": 89631139, "image_url": image_url, "image_url_small": image_url_small, "image_url_cropped": image_url_cropped}],
        }
        return CardMetadata(
            external_id="89631139",
            name="Blue-Eyes White Dragon",
            set_code="LOB-001",
            set_name="Legend of Blue Eyes White Dragon",
            collector_number="",
            rarity="Ultra Rare",
            image_url=image_url,
            game=Game.YUGIOH,
            raw_payload=raw,
        )

    def test_get_image_url_normal_returns_full_url(self):
        client = _make_client()
        card = self._make_metadata(image_url="full.jpg", image_url_small="small.jpg")
        assert client.get_image_url(card, size="normal") == "full.jpg"

    def test_get_image_url_small_returns_small_url(self):
        client = _make_client()
        card = self._make_metadata(image_url="full.jpg", image_url_small="small.jpg")
        assert client.get_image_url(card, size="small") == "small.jpg"

    def test_get_image_url_returns_none_when_missing(self):
        client = _make_client()
        card = self._make_metadata()
        assert client.get_image_url(card) is None


# ---------------------------------------------------------------------------
# k. fetch_cards_by_set
# ---------------------------------------------------------------------------

class TestYugiohClientFetchCardsBySet:
    def _mock_get(self, response_data):
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def _make_side_effect(self, sets_data, cards_data):
        sets_mock = self._mock_get(sets_data)
        cards_mock = self._mock_get(cards_data)
        def _side_effect(url, **kwargs):
            return sets_mock if "cardsets" in url else cards_mock
        return _side_effect

    def test_returns_list_of_card_metadata(self):
        client = _make_client()
        side_effect = self._make_side_effect(FAKE_SETS_RESPONSE, FAKE_API_RESPONSE)
        with patch.object(client.client, "get", side_effect=side_effect):
            result = client.fetch_cards_by_set("LOB")
        assert isinstance(result, list)
        assert all(isinstance(c, CardMetadata) for c in result)

    def test_returns_correct_count(self):
        client = _make_client()
        side_effect = self._make_side_effect(FAKE_SETS_RESPONSE, FAKE_API_RESPONSE)
        with patch.object(client.client, "get", side_effect=side_effect):
            result = client.fetch_cards_by_set("LOB")
        assert len(result) == 1

    def test_sends_set_name_not_code_to_cardset_param(self):
        client = _make_client()
        mock_get = MagicMock(side_effect=self._make_side_effect(FAKE_SETS_RESPONSE, FAKE_API_RESPONSE))
        with patch.object(client.client, "get", mock_get):
            client.fetch_cards_by_set("LOB")
        cardinfo_call = next(
            c for c in mock_get.call_args_list if "cardinfo" in c.args[0]
        )
        assert cardinfo_call.kwargs["params"]["cardset"] == "Legend of Blue Eyes White Dragon"

    def test_unknown_set_code_raises_value_error(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_SETS_RESPONSE)):
            with pytest.raises(ValueError, match="BOGUS"):
                client.fetch_cards_by_set("BOGUS")

    def test_set_name_cache_avoids_repeated_cardsets_calls(self):
        client = _make_client()
        mock_get = MagicMock(side_effect=self._make_side_effect(FAKE_SETS_RESPONSE, FAKE_API_RESPONSE))
        with patch.object(client.client, "get", mock_get):
            client.fetch_cards_by_set("LOB")
            client.fetch_cards_by_set("MRD")
        cardsets_calls = [c for c in mock_get.call_args_list if "cardsets.php" in c.args[0]]
        assert len(cardsets_calls) == 1


# ---------------------------------------------------------------------------
# l. list_sets
# ---------------------------------------------------------------------------

class TestYugiohClientListSets:
    def _mock_get(self, response_data):
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_returns_list_of_set_metadata(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_SETS_RESPONSE)):
            result = client.list_sets()
        assert isinstance(result, list)
        assert all(isinstance(s, SetMetadata) for s in result)

    def test_set_code_mapped_correctly(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_SETS_RESPONSE)):
            result = client.list_sets()
        assert result[0].set_code == "LOB"

    def test_set_name_mapped_correctly(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_SETS_RESPONSE)):
            result = client.list_sets()
        assert result[0].set_name == "Legend of Blue Eyes White Dragon"

    def test_release_date_mapped_correctly(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_SETS_RESPONSE)):
            result = client.list_sets()
        assert result[0].release_date == "2002-03-08"

    def test_total_cards_mapped_correctly(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_SETS_RESPONSE)):
            result = client.list_sets()
        assert result[0].total_cards == 126

    def test_game_field_is_yugioh(self):
        client = _make_client()
        with patch.object(client.client, "get", return_value=self._mock_get(FAKE_SETS_RESPONSE)):
            result = client.list_sets()
        assert all(s.game == Game.YUGIOH for s in result)
