import unittest

from backend.app.models.user import User


class TestUserModelAuthV2(unittest.TestCase):
    def test_user_has_email_column(self):
        col = User.__table__.c["email"]
        self.assertTrue(col.nullable)  # nullable in DB for migration safety
        self.assertTrue(col.unique)

    def test_user_has_google_id_column(self):
        col = User.__table__.c["google_id"]
        self.assertTrue(col.nullable)

    def test_user_has_last_login_at_column(self):
        col = User.__table__.c["last_login_at"]
        self.assertTrue(col.nullable)

    def test_discord_user_id_is_nullable(self):
        col = User.__table__.c["discord_user_id"]
        self.assertTrue(col.nullable)
