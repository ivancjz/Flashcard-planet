import unittest

from backend.app.core.config import Settings


class TestNewAuthFields(unittest.TestCase):
    def test_new_auth_fields_have_defaults(self):
        s = Settings(
            database_url="postgresql+psycopg://x:x@localhost/x",
        )
        self.assertEqual(s.google_client_id, "")
        self.assertEqual(s.google_client_secret, "")
        self.assertEqual(s.resend_api_key, "")
        self.assertEqual(s.magic_link_secret, "change-me-magic-link-secret")
        self.assertEqual(s.admin_emails, "")
        self.assertEqual(s.app_url, "http://localhost:8000")
