# eBay Search Queries — Manual Cross-Check (Step 4)

Built by `_build_search_query()` in `backend/app/ingestion/ebay_sold.py:276`

## Query template (ungraded Pokemon card)

```
Pokemon {name} {set_name} -PSA -BGS -CGC -SGC -GMA -graded -slab
```

## Three representative queries from the audit anchor cards

| Card | Exact eBay search query |
|------|------------------------|
| Lickitung (Jungle) | `Pokemon Lickitung Jungle -PSA -BGS -CGC -SGC -GMA -graded -slab` |
| Kangaskhan ex (151) | `Pokemon Kangaskhan ex 151 -PSA -BGS -CGC -SGC -GMA -graded -slab` |
| Charizard (Base Set) | `Pokemon Charizard Base Set -PSA -BGS -CGC -SGC -GMA -graded -slab` |

## How to run the cross-check

1. Go to eBay.com
2. Search for the exact query above (copy-paste)
3. Filter: **Sold Items** (left sidebar → Show only → Sold Items)
4. Note: do you see sold listings in the last 30 days?

## What to look for

**If eBay shows sold listings:** H1 (eBay outage) is wrong — our API is broken or the outage ended
**If eBay shows no or very few listings:** Confirms H1 (eBay API is serving empty results / outage ongoing)

## Important caveat

The eBay ingest queries the BROWSE API (active listings), not specifically sold listings
(the Finding API for sold items has historically been unreliable). The Browse API
results include `itemEndDate` which is used as the sale date. If Browse shows 0 items,
`match_status_counts: {}` is expected.

Test query in Browse mode: https://www.ebay.com/sch/i.html?_nkw=Pokemon+Lickitung+Jungle&LH_Sold=1
