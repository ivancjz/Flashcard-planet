"""
Step 3 — Dry-run IQR validation for ebay_web_sold.

Scrapes 20 known YGO production assets (POTE + TOCH), computes IQR per asset
from filtered EN singles. No DB connection required. No writes to price_history.

Acceptance gate (from ADR-001):
  - Median IQR across scored assets < 100%
  - >= 50% of scored assets PASS (IQR < 100%)
"""
from __future__ import annotations

import sys
import time
from decimal import Decimal

sys.path.insert(0, r"C:\Flashcard-planet")

from backend.app.ingestion.ebay_web_scrape import (  # noqa: E402
    _build_search_url,
    _extract_sold_items,
    _filter_valid_singles,
)
import httpx  # noqa: E402

# 20 representative production YGO assets (POTE + TOCH — both seeded sets)
# (name, card_number, variant)  — mirrors Asset rows in production
ASSETS: list[tuple[str, str, str]] = [
    # POTE — Power of the Elements (2022, high-value singles)
    ("Spright Elf",                  "POTE-EN049", "Ultra Rare"),
    ("Tearlaments Kitkallos",        "POTE-EN042", "Ultra Rare"),
    ("Tearlaments Scheiren",         "POTE-EN014", "Super Rare"),
    ("Kurikara Divincarnate",        "POTE-EN031", "Secret Rare"),
    ("Exosister Martha",             "POTE-EN025", "Secret Rare"),
    ("Tearlaments Kaleido-Heart",    "POTE-EN043", "Secret Rare"),
    ("Instant Contact",              "POTE-EN052", "Secret Rare"),
    ("Favorite Contact",             "POTE-EN069", "Ultra Rare"),
    ("Garura, Wings of Resonant Life","POTE-EN082","Ultra Rare"),
    ("Elemental HERO Shining Neos Wingman","POTE-EN041","Ultra Rare"),
    # TOCH — Toon Chaos (2020, staples)
    ("Toon Harpie Lady",             "TOCH-EN001", "Super Rare"),
    ("Toon Dark Magician",           "TOCH-EN002", "Super Rare"),
    ("Toon Bookmark",                "TOCH-EN004", "Super Rare"),
    ("Red-Eyes Toon Dragon",         "TOCH-EN003", "Super Rare"),
    ("Toon Terror",                  "TOCH-EN005", "Super Rare"),
    ("Infinite Impermanence",        "TOCH-EN054", "Ultra Rare"),
    ("Called by the Grave",          "TOCH-EN055", "Ultra Rare"),
    ("Dark Ruler No More",           "TOCH-EN056", "Ultra Rare"),
    ("Nibiru, the Primal Being",     "TOCH-EN057", "Ultra Rare"),
    ("Lightning Storm",              "TOCH-EN058", "Ultra Rare"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.ebay.com/",
}
DELAY = 2.0
MIN_SALES = 5
IQR_PASS_THRESHOLD = 100.0


def _quartile(prices: list[Decimal], q: float) -> Decimal:
    sp = sorted(prices)
    n = len(sp)
    idx = (n - 1) * q / 100
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    return sp[lo] + (sp[hi] - sp[lo]) * Decimal(str(idx - lo))


print(f"Step 3 — IQR dry-run on {len(ASSETS)} assets (no DB writes)\n")

results = []
with httpx.Client() as client:
    for i, (name, card_num, rarity) in enumerate(ASSETS, 1):
        print(f"  [{i:02}/{len(ASSETS)}] {card_num} {rarity:<18} {name[:35]}", end=" ", flush=True)
        url = _build_search_url(name, card_num, rarity)
        try:
            resp = client.get(url, headers=HEADERS, follow_redirects=True, timeout=20.0)
            resp.raise_for_status()
            page_text = resp.text
        except Exception as e:
            print(f"→ HTTP_ERR: {e}")
            results.append({"card": card_num, "name": name[:35], "rarity": rarity,
                             "n_raw": 0, "n_valid": 0, "verdict": "HTTP_ERR"})
            time.sleep(DELAY)
            continue

        raw = _extract_sold_items(page_text)
        valid = _filter_valid_singles(raw)
        prices = sorted(i["price_usd"] for i in valid)

        if len(prices) < MIN_SALES:
            print(f"→ SKIP (only {len(prices)} valid sales)")
            results.append({"card": card_num, "name": name[:35], "rarity": rarity,
                             "n_raw": len(raw), "n_valid": len(prices), "verdict": "SKIP_FEW"})
            time.sleep(DELAY)
            continue

        q1 = _quartile(prices, 25)
        med = _quartile(prices, 50)
        q3 = _quartile(prices, 75)
        iqr_pct = float((q3 - q1) / med * 100) if med > 0 else 999.0
        verdict = "PASS" if iqr_pct < IQR_PASS_THRESHOLD else "FAIL"

        print(f"→ n={len(prices)} med=${float(med):.2f} IQR={iqr_pct:.0f}% {verdict}")

        results.append({
            "card": card_num, "name": name[:35], "rarity": rarity,
            "n_raw": len(raw), "n_valid": len(prices),
            "min": float(prices[0]), "q1": float(q1), "med": float(med),
            "q3": float(q3), "max": float(prices[-1]),
            "iqr_pct": round(iqr_pct, 1), "verdict": verdict,
        })
        time.sleep(DELAY)

# ── Full table ────────────────────────────────────────────────────────────────
print(f"\n{'Card':<15} {'Rarity':<20} {'Name':<38} {'n':>3} {'Min':>7} {'Q1':>7} {'Med':>7} {'Q3':>7} {'Max':>8} {'IQR%':>6}  Result")
print("─" * 130)
for r in results:
    if "med" not in r:
        print(f"{r['card']:<15} {r['rarity']:<20} {r['name']:<38} {r['n_valid']:>3}  {'—':>7}  {'—':>7}  {'—':>7}  {'—':>7}  {'—':>8}  {'—':>6}  {r['verdict']}")
    else:
        print(f"{r['card']:<15} {r['rarity']:<20} {r['name']:<38} {r['n_valid']:>3} "
              f"${r['min']:>6.2f} ${r['q1']:>6.2f} ${r['med']:>6.2f} ${r['q3']:>6.2f} ${r['max']:>7.2f} "
              f"{r['iqr_pct']:>5.1f}%  {r['verdict']}")

# ── Gate ──────────────────────────────────────────────────────────────────────
scored = [r for r in results if "iqr_pct" in r]
passed = [r for r in scored if r["verdict"] == "PASS"]
skipped = [r for r in results if "iqr_pct" not in r]
pass_rate = len(passed) / len(scored) * 100 if scored else 0
sorted_iqrs = sorted(r["iqr_pct"] for r in scored)
median_iqr = sorted_iqrs[len(sorted_iqrs) // 2] if sorted_iqrs else 999.0

print(f"\n{'═'*130}")
print(f"Scored: {len(scored)}  PASS: {len(passed)}  FAIL: {len(scored)-len(passed)}  SKIP/ERR: {len(skipped)}")
print(f"Pass rate: {pass_rate:.0f}%  |  Median IQR across scored assets: {median_iqr:.1f}%")
gate_ok = pass_rate >= 50 and median_iqr < 100
print(f"\nADR-001 gate: pass_rate >= 50% AND median_IQR < 100%")
print(f"  pass_rate  {pass_rate:.0f}% {'✓' if pass_rate >= 50 else '✗'}")
print(f"  median_IQR {median_iqr:.1f}% {'✓' if median_iqr < 100 else '✗'}")
print(f"\nGATE {'✓ PASSED' if gate_ok else '✗ FAILED'}")
print(f"EBAY_WEB_SOLD_ENABLED → {'true  (safe to activate)' if gate_ok else 'false (keep disabled)'}")
