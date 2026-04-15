"""Smoke test for the Groq LLM provider.

Runs two real API calls through the production code path:
  1. Noise filter — mixed titles, expects [True, False, False]
  2. Card mapper  — two card titles, prints extracted fields

Usage:
    python scripts/test_groq.py
"""
from __future__ import annotations

import os
import sys

os.environ["LLM_PROVIDER"] = "groq"

from backend.app.ingestion.noise_filter import filter_noise
from backend.app.ingestion.matcher.ai_mapper import map_batch


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# --- 1. Noise filter ---

section("1. Noise Filter")

titles = [
    "Pokemon Charizard ex SAR 199/165 SV151 PSA 10",   # real card  → True
    "50x Pokemon Cards Bulk Lot Common Uncommon",        # bulk lot   → False
    "Pokemon Scarlet Violet Elite Trainer Box Sealed",   # sealed     → False
]

print("\nInput titles:")
for i, t in enumerate(titles, 1):
    print(f"  {i}. {t}")

results = filter_noise(titles)

print("\nResults (True = real card, False = noise):")
for title, result in zip(titles, results):
    mark = "+" if result else "-"
    print(f"  [{mark}] {result}  {title}")

expected = [True, False, False]
noise_ok = results == expected
print(f"\n{'PASS' if noise_ok else 'FAIL'} expected {expected}, got {results}")


# --- 2. Card mapper ---

section("2. Card Mapper")

card_titles = [
    "Pokemon Charizard ex SAR 199/165 SV151 PSA 10",
    "Pikachu VMAX Alt Art JP BGS 9.5",
]

print("\nInput titles:")
for i, t in enumerate(card_titles, 1):
    print(f"  {i}. {t}")

mapped = map_batch(card_titles)

print("\nResults:")
for r in mapped:
    print(f"\n  Title:      {r.raw_title}")
    print(f"  Name:       {r.name}")
    print(f"  Set:        {r.set_name}")
    print(f"  Card #:     {r.card_number}")
    print(f"  Variant:    {r.variant}")
    print(f"  Language:   {r.language}")
    print(f"  Grade:      {r.grade_company} {r.grade_score}")
    print(f"  Confidence: {r.confidence}")
    print(f"  Status:     {r.status}")


# --- Summary ---

section("Summary")
print(f"\n  Noise filter: {'PASS' if noise_ok else 'FAIL'}")
print(f"  Card mapper:  {'PASS' if all(r.status in ('mapped', 'review') for r in mapped) else 'CHECK RESULTS'}")
print()

sys.exit(0 if noise_ok else 1)
