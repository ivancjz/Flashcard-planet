# P0 Pre-Fix Evidence — Bug 1: Liquidity Counts TCG Polls as Sales

**Captured:** 2026-05-01 12:52 UTC (before fix applied)

## Key metric: liquidity_score vs actual eBay data

Every BREAKOUT card has liquidity_score=95-98 despite having 0-5 eBay rows in 7 days.
The score is driven entirely by 158-352 pokemon_tcg_api polling rows per card.

| Card | Set | Liquidity | Confidence | eBay 7d | TCG polls 7d | Total 7d |
|------|-----|-----------|------------|---------|-------------|----------|
| Lickitung | Jungle | 98 | 83 | 2 | 180 | 182 |
| Kangaskhan ex | 151 | 98 | 83 | 2 | 158 | 160 |
| Snorlax | Crown Zenith | 95 | 86 | 0 | 176 | 176 |
| Dark Jolteon | Team Rocket | 95 | 86 | 0 | 179 | 179 |
| Marowak | Jungle | 98 | 83 | 1 | 180 | 181 |
| Alakazam ex | 151 | 95 | 86 | 0 | 158 | 158 |
| Venomoth | Jungle | 95 | 86 | 0 | 180 | 180 |
| Snorlax | Lost Origin | 95 | 86 | 0 | 176 | 176 |
| Dark Slowbro | Team Rocket | 95 | 86 | 0 | 179 | 179 |
| Dark Gyarados | Team Rocket | 95 | 86 | 0 | 179 | 179 |

## Signal distribution — only two possible liquidity scores

BREAKOUT: 20 cards at 98, 132 cards at 95
MOVE: 47 cards at 98, 283 cards at 95
WATCH: 12 cards at 98, 144 cards at 95

All 638 actionable signals are at exactly 95 or 98 — evidence of the floor effect
caused by TCG polls maxing out the sales/history/recency components.

## Lickitung Jungle source breakdown (showing the inflation)

| Source | cnt_7d | cnt_30d | last_observed |
|--------|--------|---------|---------------|
| pokemon_tcg_api | 180 | 573 | 2026-05-01 11:46:26 |
| ebay_sold | 2 | 2 | 2026-04-27 01:02:01 |

get_liquidity_snapshots treated all 182 rows as "sales", returning sales_count_7d=182.
After fix: sales_count_7d=2 (only ebay_sold rows count).

## Pass criteria for post-deploy verification

```sql
-- After fix deployed: Lickitung should show sales_count driven by eBay, not TCG
-- liquidity_score for cards with 0 eBay rows should drop to ~5-20 (not 95-98)
-- Run after signal-sweep (15 min interval) has executed post-deploy
SELECT
    a.name, a.set_name, s.liquidity_score, s.confidence, s.label,
    COUNT(ph.id) FILTER (WHERE ph.source='ebay_sold' AND ph.captured_at>=NOW()-INTERVAL '7 days') ebay_7d,
    COUNT(ph.id) FILTER (WHERE ph.source='pokemon_tcg_api' AND ph.captured_at>=NOW()-INTERVAL '7 days') tcg_7d
FROM asset_signals s
JOIN assets a ON a.id=s.asset_id
LEFT JOIN price_history ph ON ph.asset_id=s.asset_id
WHERE s.label='BREAKOUT' AND a.game='pokemon'
GROUP BY a.id, a.name, a.set_name, s.liquidity_score, s.confidence, s.label
ORDER BY s.liquidity_score DESC
LIMIT 20;
```

Pass: cards with ebay_7d=0 have liquidity_score < 30 (not 95-98).
Fail: any card with ebay_7d=0 still shows liquidity_score >= 60.
