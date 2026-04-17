import unittest
from unittest.mock import patch


class MagicLinkTokenTests(unittest.TestCase):

    def setUp(self):
        # Patch settings so tests don't need env vars
        self.settings_patcher = patch("backend.app.auth.magic_link.get_settings")
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.return_value.magic_link_secret = "test-magic-secret"
        self.mock_settings.return_value.app_url = "http://localhost:8000"

    def tearDown(self):
        self.settings_patcher.stop()

    def test_generate_and_verify_token_round_trip(self):
        from backend.app.auth.magic_link import generate_magic_token, verify_magic_token
        token = generate_magic_token("user@example.com")
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 10)
        email = verify_magic_token(token)
        self.assertEqual(email, "user@example.com")

    def test_verify_token_raises_on_bad_signature(self):
        from fastapi import HTTPException
        from backend.app.auth.magic_link import verify_magic_token
        with self.assertRaises(HTTPException) as ctx:
            verify_magic_token("not-a-valid-token")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_verify_token_raises_on_expired_token(self):
        from itsdangerous import URLSafeTimedSerializer
        from fastapi import HTTPException
        from backend.app.auth.magic_link import verify_magic_token
        s = URLSafeTimedSerializer("test-magic-secret", salt="magic-link")
        token = s.dumps("user@example.com")
        with self.assertRaises(HTTPException) as ctx:
            verify_magic_token(token, max_age=0)
        self.assertEqual(ctx.exception.status_code, 400)
