"""
Guard test: ensures no code reverts to hardcoded category == 'Pokemon' query patterns.
Use game == Game.POKEMON instead.
"""
import unittest
from pathlib import Path


FORBIDDEN_PATTERNS = [
    'category == "Pokemon"',
    "category == 'Pokemon'",
    'Asset.category == "Pokemon"',
    "Asset.category == 'Pokemon'",
]

EXEMPT_PREFIXES = (
    "backend/app/schemas/",
    "backend/app/bot/",
    "tests/",
    "migrations/",
    ".worktrees/",
)


def test_no_hardcoded_pokemon_category_query():
    repo_root = Path(__file__).resolve().parent.parent
    offenders = []
    for py_file in repo_root.rglob("*.py"):
        rel = py_file.relative_to(repo_root).as_posix()
        if any(rel.startswith(p) for p in EXEMPT_PREFIXES):
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in content:
                offenders.append((rel, pattern))
    assert not offenders, (
        f"Found forbidden category == 'Pokemon' query patterns: {offenders}. "
        "Use game == Game.POKEMON instead."
    )


class TestAssetDualFieldCoexistence(unittest.TestCase):
    """Verify category and game columns coexist correctly on the Asset ORM model."""

    def test_asset_orm_has_both_category_and_game_columns(self):
        from backend.app.models.asset import Asset
        cols = Asset.__mapper__.columns.keys()
        self.assertIn("category", cols)
        self.assertIn("game", cols)

    def test_game_column_default_is_pokemon(self):
        from backend.app.models.asset import Asset
        col = Asset.__mapper__.columns["game"]
        self.assertEqual(col.default.arg, "pokemon")

    def test_game_enum_matches_column_default(self):
        from backend.app.models.game import Game
        from backend.app.models.asset import Asset
        col = Asset.__mapper__.columns["game"]
        self.assertEqual(col.default.arg, Game.POKEMON.value)

    def test_game_where_clause_is_valid_sqlalchemy_expression(self):
        from backend.app.models.asset import Asset
        from backend.app.models.game import Game
        from sqlalchemy import select
        # Verify the expression compiles without error
        stmt = select(Asset).where(Asset.game == Game.POKEMON.value)
        compiled = stmt.compile()
        self.assertIn("game", str(compiled))
