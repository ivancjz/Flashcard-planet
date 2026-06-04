from unittest.mock import MagicMock, patch

from backend.app.services.sentiment_service import format_for_prompt, get_tweet_context


def test_format_for_prompt_empty():
    assert format_for_prompt([]) == ""


def test_format_for_prompt_nonempty():
    result = format_for_prompt(["price spike on Charizard", "new set announced"])
    assert result.startswith("Relevant recent social context")
    assert "- price spike on Charizard" in result
    assert "- new set announced" in result


def test_get_tweet_context_empty_table():
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []

    with patch("backend.app.services.sentiment_service._embed", return_value=[0.1] * 1536):
        result = get_tweet_context(mock_db, "Charizard price", days=30, limit=10)

    assert result == []
