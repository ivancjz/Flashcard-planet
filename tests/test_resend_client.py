import unittest
from unittest.mock import patch, MagicMock


class ResendClientTests(unittest.TestCase):

    def test_send_magic_link_email_calls_resend_with_correct_fields(self):
        mock_send = MagicMock()
        with patch("resend.Emails.send", mock_send):
            with patch("backend.app.email.resend_client.get_settings") as mock_settings:
                mock_settings.return_value.resend_api_key = "test-key"
                from backend.app.email.resend_client import send_magic_link_email
                send_magic_link_email("user@example.com", "https://example.com/verify?token=abc")

        mock_send.assert_called_once()
        call_args = mock_send.call_args[0][0]
        self.assertEqual(call_args["to"], ["user@example.com"])
        self.assertIn("https://example.com/verify?token=abc", call_args["html"])
        self.assertEqual(call_args["subject"], "Your Flashcard Planet login link")

    def test_send_magic_link_email_uses_from_address(self):
        mock_send = MagicMock()
        with patch("resend.Emails.send", mock_send):
            with patch("backend.app.email.resend_client.get_settings") as mock_settings:
                mock_settings.return_value.resend_api_key = "test-key"
                from backend.app.email.resend_client import send_magic_link_email
                send_magic_link_email("x@y.com", "http://localhost/verify?token=t")

        call_args = mock_send.call_args[0][0]
        self.assertIn("flashcardplanet.com", call_args["from"])
