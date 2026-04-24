"""Unit tests for _card_number_matches set-identity filter.

Tests cover the 5 edge cases from the spec:
  1. Same card number + same set total → True
  2. Same card number + different set total → False  (cross-set rejection)
  3. Different card number → False
  4. No X/Y pattern in title → True
  5. Asset metadata missing set.total → fall back to card number only
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.ingestion.ebay_sold import _card_number_matches


def _asset(external_id: str, metadata: dict | None = None) -> SimpleNamespace:
    """Minimal Asset-like object with only the fields _card_number_matches needs."""
    return SimpleNamespace(
        external_id=external_id,
        metadata_json=metadata,
    )


# ── 1. Same card number + same set total ─────────────────────────────────────

def test_same_card_num_same_set_total_returns_true() -> None:
    # Pokemon 151 Dragonite (149/165) matching a correct listing
    asset = _asset("sv3pt5-149", {"set": {"total": 165}})
    assert _card_number_matches(asset, "Pokémon Dragonite 149/165 SV3pt5 Holo Rare") is True


# ── 2. Same card number + different set total → rejected ─────────────────────

def test_same_card_num_different_set_total_returns_false() -> None:
    # sv3pt5-149 (set total 165) vs a hypothetical listing that says 149/200
    asset = _asset("sv3pt5-149", {"set": {"total": 165}})
    assert _card_number_matches(asset, "Pokemon Card 149/200 Dragonite SomeOtherSet") is False


# ── 3. Different card number → rejected ──────────────────────────────────────

def test_different_card_num_returns_false() -> None:
    # Base Set Dragonite is 19/102; sv3pt5-149 is card 149
    asset = _asset("sv3pt5-149", {"set": {"total": 165}})
    assert _card_number_matches(asset, "Pokémon Dragonite Holo Rare 19/102 Base Set 1999 WOTC") is False


# ── 4. No X/Y pattern in title → cannot validate, pass through ───────────────

def test_no_card_number_in_title_returns_true() -> None:
    asset = _asset("sv3pt5-149", {"set": {"total": 165}})
    assert _card_number_matches(asset, "Pokemon Dragonite Holo Rare NM Pokemon 151 Reprint") is True


# ── 5. Missing set total in metadata → fall back to card number match ─────────

def test_missing_set_total_falls_back_to_card_num_match() -> None:
    # No set.total → use card number only; same number passes
    asset = _asset("sv3pt5-149", {})
    assert _card_number_matches(asset, "Pokemon Dragonite 149/200 SomeOtherSet") is True


def test_missing_set_total_falls_back_to_card_num_reject() -> None:
    # No set.total → use card number only; different number still fails
    asset = _asset("sv3pt5-149", {})
    assert _card_number_matches(asset, "Pokemon Dragonite 19/102 Base Set") is False


# ── Extra: malformed external_id doesn't crash ────────────────────────────────

def test_malformed_external_id_returns_true() -> None:
    asset = _asset("non-numeric-id", {"set": {"total": 165}})
    assert _card_number_matches(asset, "Pokemon Dragonite 149/165 Holo") is True


# ── printedTotal preferred over total (sv3pt5 case) ──────────────────────────
# sv3pt5 (Pokemon 151): printedTotal=165 (on card backs), total=207 (full set).
# eBay titles use the printed number ("149/165"), so printedTotal must win.

def test_printed_total_used_when_listing_uses_printed_numbering() -> None:
    # Asset has both: printedTotal=165, total=207. Title says 149/165.
    asset = _asset("sv3pt5-149", {"set": {"printedTotal": 165, "total": 207}})
    assert _card_number_matches(asset, "Pokemon Dragonite 149/165 sv3pt5 Holo") is True


def test_total_207_does_not_reject_valid_165_listing() -> None:
    # If only total=207 is checked, a valid 149/165 listing would be wrongly rejected.
    asset = _asset("sv3pt5-149", {"set": {"printedTotal": 165, "total": 207}})
    assert _card_number_matches(asset, "Pokemon Dragonite 149/165 Pokemon 151") is not False


def test_printed_total_fallback_to_total_when_only_total_present() -> None:
    # No printedTotal → fall back to total (Base Set behaviour)
    asset = _asset("base1-2", {"set": {"total": 102}})
    assert _card_number_matches(asset, "Blastoise 2/102 Base Set Holo Rare") is True
