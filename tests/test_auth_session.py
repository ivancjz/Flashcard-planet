import unittest
from unittest.mock import MagicMock


class SessionHelpersTests(unittest.TestCase):

    def _make_request(self, session_data: dict):
        req = MagicMock()
        req.session = session_data
        return req

    def test_login_user_sets_user_id_in_session(self):
        from backend.app.auth.session import login_user
        user = MagicMock()
        user.id = "test-uuid-1234"
        user.last_login_at = None
        req = self._make_request({})
        login_user(req, user)
        self.assertEqual(req.session["user_id"], "test-uuid-1234")

    def test_logout_user_clears_session(self):
        from backend.app.auth.session import logout_user
        req = self._make_request({"user_id": "test-uuid", "other": "data"})
        logout_user(req)
        self.assertEqual(req.session, {})

    def test_get_session_user_id_returns_value(self):
        from backend.app.auth.session import get_session_user_id
        req = self._make_request({"user_id": "abc-123"})
        self.assertEqual(get_session_user_id(req), "abc-123")

    def test_get_session_user_id_returns_none_when_missing(self):
        from backend.app.auth.session import get_session_user_id
        req = self._make_request({})
        self.assertIsNone(get_session_user_id(req))
