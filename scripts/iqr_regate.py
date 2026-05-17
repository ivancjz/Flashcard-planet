"""Re-gate IQR validation — post PR #67 merge (2026-05-17)."""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, r"C:\Flashcard-planet")
from backend.app.ingestion.ebay_web_scrape import _extract_sold_items, _filter_valid_singles  # noqa: E402

OUTDIR = Path(r"C:\Users\ivan cheng\AppData\Local\Temp\iqr_regate")

ASSETS = [
    ("Spright Elf",                         "POTE-EN049", "Ultra Rare"),
    ("Tearlaments Kitkallos",               "POTE-EN042", "Ultra Rare"),
    ("Tearlaments Scheiren",                "POTE-EN014", "Super Rare"),
    ("Kurikara Divincarnate",               "POTE-EN031", "Secret Rare"),
    ("Exosister Martha",                    "POTE-EN025", "Secret Rare"),
    ("Tearlaments Kaleido-Heart",           "POTE-EN043", "Secret Rare"),
    ("Instant Contact",                     "POTE-EN052", "Secret Rare"),
    ("Favorite Contact",                    "POTE-EN069", "Ultra Rare"),
    ("Garura, Wings of Resonant Life",      "POTE-EN082", "Ultra Rare"),
    ("Elemental HERO Shining Neos Wingman", "POTE-EN041", "Ultra Rare"),
    ("Infinite Impermanence",               "TOCH-EN054", "Ultra Rare"),
    ("Called by the Grave",                 "TOCH-EN055", "Ultra Rare"),
    ("Dark Ruler No More",                  "TOCH-EN056", "Ultra Rare"),
    ("Nibiru, the Primal Being",            "TOCH-EN057", "Ultra Rare"),
    ("Lightning Storm",                     "TOCH-EN058", "Ultra Rare"),
    ("Toon Dark Magician",                  "TOCH-EN002", "Super Rare"),
    ("Toon Harpie Lady",                    "TOCH-EN001", "Super Rare"),
    ("Red-Eyes Toon Dragon",                "TOCH-EN003", "Super Rare"),
    ("Toon Bookmark",                       "TOCH-EN004", "Super Rare"),
    ("Toon Terror",                         "TOCH-EN005", "Super Rare"),
]

STEP3_IQR = {
    "POTE-EN049": 102.0, "POTE-EN042": 100.4, "POTE-EN014": 119.2,
    "POTE-EN031": 251.2, "POTE-EN025":  79.3, "POTE-EN043":  50.7,
    "POTE-EN052": 128.9, "POTE-EN069":  83.8, "POTE-EN082":  78.0,
    "POTE-EN041":  44.8, "TOCH-EN054": 178.6, "TOCH-EN055": 212.2,
    "TOCH-EN056":  62.4, "TOCH-EN057": 266.8, "TOCH-EN058": 104.9,
    "TOCH-EN002":  81.8, "TOCH-EN001": 400.0, "TOCH-EN003":  48.9,
    "TOCH-EN004":  88.6, "TOCH-EN005": 393.5,
}
OFFENDERS = {"POTE-EN031", "TOCH-EN057", "TOCH-EN001"}
MIN_N = 5


def quartile(prices, q):
    sp = sorted(prices)
    n = len(sp)
    idx = (n - 1) * q / 100
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    return sp[lo] + (sp[hi] - sp[lo]) * Decimal(str(idx - lo))


results = []
offender_debug = {}

for name, card_num, rarity in ASSETS:
    fpath = OUTDIR / f"{card_num}.txt"
    text = fpath.read_text(encoding="utf-8", errors="replace")
    raw_items = _extract_sold_items(text)
    valid_items = _filter_valid_singles(raw_items, rarity=rarity)
    prices = sorted(i["price_usd"] for i in valid_items)

    if card_num in OFFENDERS:
        raw_titles = {id(i): i["title"] for i in raw_items}
        valid_ids = {id(i) for i in valid_items}
        offender_debug[card_num] = {
            "n_raw": len(raw_items),
            "n_valid": len(prices),
            "kept": [i["title"] for i in valid_items][:6],
            "dropped": [i["title"] for i in raw_items if id(i) not in valid_ids][:8],
        }

    if len(prices) < MIN_N:
        results.append({
            "card": card_num, "name": name[:32], "rarity": rarity,
            "n_raw": len(raw_items), "n": len(prices),
            "iqr_pct": None, "verdict": "SKIP_LOW_N",
            "s3": STEP3_IQR.get(card_num), "flag": card_num in OFFENDERS,
        })
        continue

    q1 = quartile(prices, 25)
    med = quartile(prices, 50)
    q3 = quartile(prices, 75)
    iqr_pct = float((q3 - q1) / med * 100) if med > 0 else 999.0
    results.append({
        "card": card_num, "name": name[:32], "rarity": rarity,
        "n_raw": len(raw_items), "n": len(prices),
        "min": float(prices[0]), "q1": float(q1), "med": float(med),
        "q3": float(q3), "max": float(prices[-1]),
        "iqr_pct": round(iqr_pct, 1),
        "verdict": "PASS" if iqr_pct < 100 else "FAIL",
        "s3": STEP3_IQR.get(card_num), "flag": card_num in OFFENDERS,
    })

# ── Main table
print("Re-gate IQR Validation — post PR #67 (rarity-confirm + 1st-Ed positive filter)")
print()
print(f"{'Card':<15} {'Rarity':<14} {'Name':<33} {'nRaw':>5} {'n':>4}  {'Med':>7} {'IQR%':>6} {'Dlt S3':>7}  Result")
print("-" * 110)
for r in results:
    s3 = r["s3"]
    new = r["iqr_pct"]
    delta = f"{new-s3:+.0f}%" if (new is not None and s3) else "—"
    tag = " OFFENDER" if r["flag"] else ""
    warn = " [n<5]" if r["n"] < MIN_N else ""
    if new is None:
        print(f"{r['card']:<15} {r['rarity']:<14} {r['name']:<33} {r['n_raw']:>5} {r['n']:>4}  {'—':>7} {'—':>6} {delta:>7}  {r['verdict']}{warn}{tag}")
    else:
        print(f"{r['card']:<15} {r['rarity']:<14} {r['name']:<33} {r['n_raw']:>5} {r['n']:>4} "
              f"${r['med']:>6.2f} {new:>5.1f}% {delta:>7}  {r['verdict']}{warn}{tag}")

# ── Gate
scored = [r for r in results if r["iqr_pct"] is not None]
passed = [r for r in scored if r["verdict"] == "PASS"]
low_n  = [r for r in results if r["n"] < MIN_N]
pass_rate = len(passed) / len(scored) * 100 if scored else 0
sorted_iqrs = sorted(r["iqr_pct"] for r in scored)
med_iqr = sorted_iqrs[len(sorted_iqrs) // 2] if sorted_iqrs else 999
gate_ok = pass_rate >= 50 and med_iqr < 100

print(f"\n{'='*110}")
print(f"Scored={len(scored)}  PASS={len(passed)}  FAIL={len(scored)-len(passed)}  SKIP_LOW_N={len(low_n)}")
print(f"Pass rate: {pass_rate:.0f}%  (>= 50% required)  {'OK' if pass_rate>=50 else 'FAIL'}")
print(f"Median IQR: {med_iqr:.1f}%  (< 100% required)   {'OK' if med_iqr<100 else 'FAIL'}")
if low_n:
    print(f"\n[n<5 — medians unstable, excluded from gate]: {', '.join(r['card'] for r in low_n)}")
print(f"\nGATE {'PASSED' if gate_ok else 'FAILED'}")

# ── Offender deep-dive
print(f"\n{'─'*110}")
print("Original Step 3 offenders — filter effectiveness check")
for card_num, cname, crarity in [
    ("POTE-EN031", "Kurikara Divincarnate", "Secret Rare"),
    ("TOCH-EN057", "Nibiru, the Primal Being", "Ultra Rare"),
    ("TOCH-EN001", "Toon Harpie Lady", "Super Rare"),
]:
    r = next((x for x in results if x["card"] == card_num), None)
    d = offender_debug.get(card_num, {})
    s3 = STEP3_IQR.get(card_num, "?")
    new = r["iqr_pct"] if r and r["iqr_pct"] is not None else "SKIP_LOW_N"
    delta = f"{new-s3:+.1f}%" if isinstance(new, float) else "—"
    print(f"\n  {card_num} {cname} ({crarity})")
    print(f"  Step 3: {s3}%  ->  Re-gate: {new}%  (delta {delta})")
    print(f"  n_raw={d.get('n_raw','?')}  n_after_all_filters={d.get('n_valid','?')}")
    kept = d.get("kept", [])
    dropped = d.get("dropped", [])
    if kept:
        print("  Kept (sample):")
        for t in kept[:4]:
            print(f"    + {t[:80]}")
    if dropped:
        print(f"  Dropped (first {min(5,len(dropped))} of {len(dropped)}):")
        for t in dropped[:5]:
            print(f"    - {t[:80]}")
