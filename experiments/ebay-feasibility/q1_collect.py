"""
Q1 data collection — eBay Browse API ask-price quality assessment.
Run via: railway run python experiments/ebay-feasibility/q1_collect.py

Mirrors _build_search_query() from backend/app/ingestion/ebay_sold.py.
Deviation from production: FIXED_PRICE filter removed to capture auctions
too — Q1 needs full listing distribution, not just BIN.
"""
import csv, json, math, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE   = Path("experiments/ebay-feasibility")
RAW    = HERE / "browse-raw"
RAW.mkdir(parents=True, exist_ok=True)

BROWSE_URL  = "https://api.ebay.com/buy/browse/v1/item_summary/search"
OAUTH_URL   = "https://api.ebay.com/identity/v1/oauth2/token"
POKEMON_CAT = "2536"   # eBay: Collectible Card Games > Pokémon > Individual Cards
UNGRADED_EXCL = ["-PSA", "-BGS", "-CGC", "-SGC", "-GMA", "-graded", "-slab"]


def get_token(client: httpx.Client) -> str:
    import base64
    creds = base64.b64encode(
        f"{os.environ['EBAY_APP_ID']}:{os.environ['EBAY_CERT_ID']}".encode()
    ).decode()
    r = client.post(
        OAUTH_URL,
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials",
              "scope": "https://api.ebay.com/oauth/api_scope"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def build_query(row: dict) -> str:
    """Mirror _build_search_query for ungraded Pokemon cards."""
    parts = ["Pokemon", row["name"]]
    if row.get("set_name"):
        parts.append(row["set_name"])
    # All sample cards are ungraded (grade_company == '' in CSV)
    parts.extend(UNGRADED_EXCL)
    return " ".join(parts)


def listing_age_days(creation_date: str | None) -> float | None:
    if not creation_date:
        return None
    try:
        dt = datetime.fromisoformat(creation_date.replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 86400, 1)
    except Exception:
        return None


def parse_listing(item: dict) -> dict:
    price_info = item.get("price", {})
    price_val  = price_info.get("value") if isinstance(price_info, dict) else None

    buying = item.get("buyingOptions", [])
    is_auction = "AUCTION" in buying
    is_bin     = "FIXED_PRICE" in buying

    shipping = None
    for opt in item.get("shippingOptions", []):
        sc = opt.get("shippingCost", {})
        if isinstance(sc, dict) and sc.get("value") is not None:
            shipping = sc["value"]
            break

    seller = item.get("seller", {})
    feedback = seller.get("feedbackScore") if isinstance(seller, dict) else None

    condition = item.get("condition")  # raw string, not normalized

    creation = item.get("itemCreationDate") or item.get("itemEndDate")
    age = listing_age_days(creation)

    return {
        "item_id":               item.get("itemId", ""),
        "title":                 item.get("title", ""),
        "listing_price":         float(price_val) if price_val else None,
        "condition":             condition,
        "seller_feedback_score": feedback,
        "is_auction":            is_auction,
        "is_buy_it_now":         is_bin,
        "shipping_cost":         float(shipping) if shipping is not None else None,
        "listing_age_days":      age,
    }


def fetch_card(client: httpx.Client, token: str, row: dict) -> list[dict]:
    q = build_query(row)
    params = {
        "q":            q,
        "category_ids": POKEMON_CAT,
        "sort":         "endingSoonest",
        "limit":        "200",
    }
    try:
        r = client.get(
            BROWSE_URL,
            headers={"Authorization": f"Bearer {token}",
                     "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            params=params,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ERROR fetching {row['name']}: {e}", flush=True)
        return []

    # Preserve raw
    card_id = row["asset_id"]
    with open(RAW / f"{card_id}.json", "w") as f:
        json.dump({"query": q, "params": params, "response": data}, f, indent=2)

    return data.get("itemSummaries", [])


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    frac = idx - lo
    return round(s[lo] + frac * (s[hi] - s[lo]), 2)


def card_summary(card_id: str, name: str, tier: str,
                 listings: list[dict]) -> dict:
    prices = [l["listing_price"] for l in listings if l["listing_price"] is not None]
    prices.sort()
    n = len(prices)

    med = percentile(prices, 50) if prices else None
    p25 = percentile(prices, 25) if prices else None
    p75 = percentile(prices, 75) if prices else None

    iqr_pct = None
    if med and med > 0 and p25 is not None and p75 is not None:
        iqr_pct = round((p75 - p25) / med * 100, 1)

    outliers = 0
    if med and med > 0:
        for p in prices:
            if p > 3 * med or p < 0.3 * med:
                outliers += 1

    bin_count     = sum(1 for l in listings if l["is_buy_it_now"])
    auction_count = sum(1 for l in listings if l["is_auction"])

    return {
        "card_id":        card_id,
        "name":           name,
        "tier":           tier,
        "listing_count":  len(listings),
        "price_median":   med,
        "price_p25":      p25,
        "price_p75":      p75,
        "price_min":      round(min(prices), 2) if prices else None,
        "price_max":      round(max(prices), 2) if prices else None,
        "iqr_pct":        iqr_pct,
        "outlier_count":  outliers,
        "buy_it_now_count": bin_count,
        "auction_count":  auction_count,
    }


def condition_analysis(card_id: str, name: str, tier: str,
                       listings: list[dict]) -> dict:
    buckets: dict[str, list[float]] = {}
    for l in listings:
        cond = l["condition"] or "Unknown"
        price = l["listing_price"]
        if price is not None:
            buckets.setdefault(cond, []).append(price)

    distinct = len(buckets)
    cond_strings = list(buckets.keys())

    # Median per bucket
    bucket_medians = {
        c: percentile(sorted(prices), 50)
        for c, prices in buckets.items()
        if prices
    }

    ratio = None
    if len(bucket_medians) >= 2:
        vals = list(bucket_medians.values())
        hi, lo = max(vals), min(v for v in vals if v > 0)
        ratio = round(hi / lo, 2) if lo > 0 else None

    grade_mixed = (distinct >= 3 and ratio is not None and ratio > 5.0)

    return {
        "card_id":                  card_id,
        "name":                     name,
        "tier":                     tier,
        "distinct_condition_count": distinct,
        "condition_strings":        json.dumps(cond_strings),
        "max_condition_price_ratio": ratio,
        "grade_mixed_flag":         grade_mixed,
    }


def main():
    # Read sample
    cards = []
    with open(HERE / "sample-cards.csv") as f:
        for row in csv.DictReader(f):
            cards.append(row)
    print(f"Loaded {len(cards)} cards. H={sum(1 for c in cards if c['tier']=='H')} "
          f"M={sum(1 for c in cards if c['tier']=='M')} "
          f"L={sum(1 for c in cards if c['tier']=='L')}", flush=True)

    with httpx.Client(timeout=20) as client:
        token = get_token(client)
        print("OAuth token obtained.", flush=True)

        all_listings_rows  = []
        all_summary_rows   = []
        all_condition_rows = []

        for i, card in enumerate(cards):
            card_id = card["asset_id"]
            name    = card["name"]
            tier    = card["tier"]
            print(f"[{i+1:02d}/30] [{tier}] {name} ({card['set_name']})...", flush=True)

            raw_items = fetch_card(client, token, card)
            listings  = [parse_listing(item) for item in raw_items]

            # Attach card metadata to each listing
            for l in listings:
                l["card_id"] = card_id
                l["name"]    = name
                l["tier"]    = tier

            all_listings_rows.extend(listings)

            summary   = card_summary(card_id, name, tier, listings)
            cond_anal = condition_analysis(card_id, name, tier, listings)

            all_summary_rows.append(summary)
            all_condition_rows.append(cond_anal)

            print(f"         listings={len(listings)}  "
                  f"median=${summary.get('price_median')}  "
                  f"iqr_pct={summary.get('iqr_pct')}%  "
                  f"grade_mixed={cond_anal['grade_mixed_flag']}", flush=True)

            # Polite rate limit: ~3 req/s
            time.sleep(0.35)

    # Write browse-listings.csv
    listing_fields = [
        "card_id","name","tier","item_id","title",
        "listing_price","condition","seller_feedback_score",
        "is_auction","is_buy_it_now","shipping_cost","listing_age_days",
    ]
    with open(HERE / "browse-listings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=listing_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_listings_rows)
    print(f"\nWrote browse-listings.csv ({len(all_listings_rows)} rows)", flush=True)

    # Write browse-summary.csv
    summary_fields = [
        "card_id","name","tier","listing_count",
        "price_median","price_p25","price_p75","price_min","price_max",
        "iqr_pct","outlier_count","buy_it_now_count","auction_count",
    ]
    with open(HERE / "browse-summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=summary_fields)
        w.writeheader()
        w.writerows(all_summary_rows)
    print(f"Wrote browse-summary.csv ({len(all_summary_rows)} rows)", flush=True)

    # Write condition-analysis.csv
    cond_fields = [
        "card_id","name","tier",
        "distinct_condition_count","condition_strings",
        "max_condition_price_ratio","grade_mixed_flag",
    ]
    with open(HERE / "condition-analysis.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cond_fields)
        w.writeheader()
        w.writerows(all_condition_rows)
    print(f"Wrote condition-analysis.csv ({len(all_condition_rows)} rows)", flush=True)

    print("\nDone. Artifacts in experiments/ebay-feasibility/", flush=True)


if __name__ == "__main__":
    main()
