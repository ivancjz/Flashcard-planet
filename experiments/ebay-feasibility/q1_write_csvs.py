"""
Write CSVs from already-fetched browse-raw/ JSON files.
Run via: python experiments/ebay-feasibility/q1_write_csvs.py
(no railway run needed — reads local files, no API calls)
"""
import csv, json, os
from pathlib import Path
from datetime import datetime, timezone

HERE = Path("experiments/ebay-feasibility")
RAW  = HERE / "browse-raw"


def listing_age_days(creation_date):
    if not creation_date:
        return None
    try:
        dt = datetime.fromisoformat(creation_date.replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 86400, 1)
    except Exception:
        return None


def parse_listing(item):
    price_info = item.get("price", {})
    price_val  = price_info.get("value") if isinstance(price_info, dict) else None
    buying     = item.get("buyingOptions", [])
    is_auction = "AUCTION" in buying
    is_bin     = "FIXED_PRICE" in buying

    shipping = None
    for opt in item.get("shippingOptions", []):
        sc = opt.get("shippingCost", {})
        if isinstance(sc, dict) and sc.get("value") is not None:
            shipping = sc["value"]
            break

    seller   = item.get("seller", {})
    feedback = seller.get("feedbackScore") if isinstance(seller, dict) else None

    creation = item.get("itemCreationDate") or item.get("itemEndDate")

    return {
        "item_id":               item.get("itemId", ""),
        "title":                 item.get("title", ""),
        "listing_price":         float(price_val) if price_val else None,
        "condition":             item.get("condition"),
        "seller_feedback_score": feedback,
        "is_auction":            is_auction,
        "is_buy_it_now":         is_bin,
        "shipping_cost":         float(shipping) if shipping is not None else None,
        "listing_age_days":      listing_age_days(creation),
    }


def percentile(values, p):
    if not values:
        return None
    s = sorted(values)
    idx = (len(s) - 1) * p / 100
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (idx - lo) * (s[hi] - s[lo]), 2)


def card_summary(card_id, name, tier, listings):
    prices = sorted([l["listing_price"] for l in listings if l["listing_price"] is not None])
    med  = percentile(prices, 50)
    p25  = percentile(prices, 25)
    p75  = percentile(prices, 75)

    iqr_pct = None
    if med and med > 0 and p25 is not None and p75 is not None:
        iqr_pct = round((p75 - p25) / med * 100, 1)

    outliers = sum(1 for p in prices if med and (p > 3*med or p < 0.3*med))

    return {
        "card_id":           card_id, "name": name, "tier": tier,
        "listing_count":     len(listings),
        "price_median":      med,
        "price_p25":         p25,
        "price_p75":         p75,
        "price_min":         round(min(prices), 2) if prices else None,
        "price_max":         round(max(prices), 2) if prices else None,
        "iqr_pct":           iqr_pct,
        "outlier_count":     outliers,
        "buy_it_now_count":  sum(1 for l in listings if l["is_buy_it_now"]),
        "auction_count":     sum(1 for l in listings if l["is_auction"]),
    }


def condition_analysis(card_id, name, tier, listings):
    buckets = {}
    for l in listings:
        cond  = l["condition"] or "Unknown"
        price = l["listing_price"]
        if price is not None:
            buckets.setdefault(cond, []).append(price)

    distinct = len(buckets)
    bucket_medians = {c: percentile(sorted(ps), 50) for c, ps in buckets.items() if ps}

    ratio = None
    if len(bucket_medians) >= 2:
        vals = [v for v in bucket_medians.values() if v and v > 0]
        if len(vals) >= 2:
            ratio = round(max(vals) / min(vals), 2)

    grade_mixed = distinct >= 3 and ratio is not None and ratio > 5.0

    return {
        "card_id":                   card_id, "name": name, "tier": tier,
        "distinct_condition_count":  distinct,
        "condition_strings":         json.dumps(list(buckets.keys())),
        "max_condition_price_ratio": ratio,
        "grade_mixed_flag":          grade_mixed,
    }


# Read sample
cards = []
with open(HERE / "sample-cards.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cards.append(row)

all_listings_rows  = []
all_summary_rows   = []
all_condition_rows = []

for card in cards:
    card_id = card["asset_id"]
    name    = card["name"]
    tier    = card["tier"]

    raw_path = RAW / f"{card_id}.json"
    if not raw_path.exists():
        print(f"MISSING raw: {card_id} ({name})")
        listings = []
    else:
        with open(raw_path, encoding="utf-8") as f:
            data = json.load(f)
        raw_items = data.get("response", {}).get("itemSummaries", [])
        listings  = [parse_listing(item) for item in raw_items]

    for l in listings:
        l.update({"card_id": card_id, "name": name, "tier": tier})

    all_listings_rows.extend(listings)
    all_summary_rows.append(card_summary(card_id, name, tier, listings))
    all_condition_rows.append(condition_analysis(card_id, name, tier, listings))

# browse-listings.csv
listing_fields = [
    "card_id","name","tier","item_id","title",
    "listing_price","condition","seller_feedback_score",
    "is_auction","is_buy_it_now","shipping_cost","listing_age_days",
]
with open(HERE / "browse-listings.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=listing_fields, extrasaction="ignore")
    w.writeheader(); w.writerows(all_listings_rows)
print(f"browse-listings.csv: {len(all_listings_rows)} rows")

# browse-summary.csv
summary_fields = [
    "card_id","name","tier","listing_count",
    "price_median","price_p25","price_p75","price_min","price_max",
    "iqr_pct","outlier_count","buy_it_now_count","auction_count",
]
with open(HERE / "browse-summary.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=summary_fields)
    w.writeheader(); w.writerows(all_summary_rows)
print(f"browse-summary.csv: {len(all_summary_rows)} rows")

# condition-analysis.csv
cond_fields = [
    "card_id","name","tier",
    "distinct_condition_count","condition_strings",
    "max_condition_price_ratio","grade_mixed_flag",
]
with open(HERE / "condition-analysis.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cond_fields)
    w.writeheader(); w.writerows(all_condition_rows)
print(f"condition-analysis.csv: {len(all_condition_rows)} rows")
print("Done.")
