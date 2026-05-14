# Q1 Brief — eBay Browse API Ask-Price Data Quality
**Date:** 2026-05-14  
**Stage:** 2 (Q1 only — Q2 parked)  
**Sample:** 30 cards × 200-listing cap = 5,914 listings  
**Method:** Browse API, query mirrors `_build_search_query()`, FIXED_PRICE filter removed to capture full distribution  

---

## a. Aggregate stats per tier

| Metric | Tier H (10 cards) | Tier M (10 cards) | Tier L (10 cards) |
|---|---|---|---|
| Mean listing count | 200.0 (all hit cap) | 200.0 (all hit cap) | 191.4 (1 card under cap) |
| Median IQR% | **189.4%** | **129.3%** | **63.7%** |
| % cards with outliers | **100%** | **100%** | 90% |
| % cards with <5 listings | 0% | 0% | 0% |
| % cards grade-mixed (≥3 cond, ratio >5×) | **90%** | **90%** | 70% |

IQR% = `(p75 - p25) / median × 100`. A sold-price substitute needs IQR% under ~30% to be usable as a signal input. The only tier approaching that is Tier L modern cards.

---

## b. Grade-mixed pollution analysis

**90% of Tier H and Tier M cards are grade-mixed.** The `-PSA -BGS -CGC -SGC -GMA -graded -slab` query exclusions filter graded keywords from listing *titles* but do not prevent:

1. **Raw condition categories** ("Ungraded", "Used", "Open Box/Used") which cover a huge range — from a $1.89 heavily-played to a $7,599 near-perfect. eBay's "Ungraded" condition is not a quality grade; it means "the seller did not submit this to a grading service."

2. **"Graded" as a condition string** — distinct from title keywords. eBay allows sellers to set condition = "Graded" even if "PSA" doesn't appear in the title. Seen on Gyarados (6 listings), Blastoise (6), Nidoking (4).

3. **"New/Factory Sealed"** slipping through — Blastoise returned 14 listings at median $700 in this condition. These are sealed booster packs/boxes, not individual cards. The query doesn't exclude sealed product.

4. **International condition strings** passing as distinct buckets — "Non gradée" (French), "Non gradata" (Italian), "Nicht bewertet" (German), "Sin clasificar" (Spanish), "Gebraucht" (German for "used"). Each is a separate condition string in the raw data. Together they represent ~5-15 listings per popular card. Without normalization, they inflate distinct_condition_count and fragment the distribution.

**Grade-mix severity by tier:**

| Tier | Cards grade-mixed | Max ratio seen | Notable case |
|---|---|---|---|
| H | 9/10 | 767× (Blastoise) | Sealed packs at $700 vs played raw at $0.99 |
| M | 9/10 | 219× (Haunter) | Graded vs poor condition raw |
| L | 7/10 | 60× (Growlithe) | Vintage Base commons have same contamination as holos |

The 3 cards NOT grade-mixed: Ninetales (H, ratio 4.61×), Mega Sharpedo ex (M, ratio 83× BUT only 2 distinct conditions — flag: ratio threshold definition), Murkrow (L, ratio 1.21×), Switching Cups (L, ratio 1.75×), Garbodor V (L, ratio 2.45×).

Note: Mega Sharpedo ex has ratio 83× across only 2 conditions ("Ungraded" and "Nicht bewertet") — it wasn't flagged by the grade_mixed rule (requires ≥3 distinct) but a 2-bucket 83× spread is still unusable.

---

## c. Three example cards per tier

### Tier H

**Worst: Pikachu (Base) — IQR 686.4%, 8 conditions**
> Query "Pokemon Pikachu Base -PSA..." matches every Base Set Pikachu variant: Shadowless, 1st Edition, Unlimited, Yellow Cheeks — each with different values. Card number (#58) not in query. The 200-listing cap also contains a $1,050 "Unknown" condition listing and a $1,130.83 "Ungraded" outlier next to $1.83 commons.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 167 | $11.99 | $1.83 – $1,130.83 |
| Used | 22 | $35.00 | $1.50 – $3,499.00 |
| Non gradée (FR) | 3 | $35.04 | $21.12 – $35.21 |
| Graded | 2 | $80.00 | $32.86 – $80.00 |
| Unknown | 1 | $1,050.00 | — |

**Median: Blastoise (Base) — IQR 186.8%, 11 conditions**
> "New/Factory Sealed" is the third-largest bucket at 14 listings, median $700. The "Ungraded" bucket alone spans $0.99 to $7,599.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 145 | $121.86 | $0.99 – $7,599.00 |
| Used | 24 | $200.00 | $4.99 – $3,500.00 |
| New/Factory Sealed | 14 | $700.00 | $599.99 – $3,500.00 |
| Graded | 6 | $470.60 | $55.00 – $1,700.00 |
| Open Box/Used | 3 | $1,350.00 | $51.11 – $4,495.95 |

**Best: Gyarados (Base) — IQR 122.1%, 9 conditions**
> Still 100% outlier rate, ratio 6.1×. "Best in Tier H" is still not usable.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 156 | $27.99 | $1.89 – $1,300.00 |
| Used | 29 | $43.08 | $10.95 – $2,190.42 |
| Graded | 6 | $60.04 | $14.96 – $1,999.99 |

---

### Tier M

**Worst: Eevee (Jungle) — IQR 166.3%, 8 conditions**
> Contains a $11,111.11 outlier in the "Ungraded" bucket — junk price listing that passes all current filters. Multi-language fragmentation: French, Italian, German each appear as separate conditions.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 175 | $3.00 | $0.91 – $11,111.11 |
| Used | 18 | $8.00 | $0.99 – $19.99 |
| Nicht bewertet (DE) | 2 | $29.35 | $14.66 – $29.35 |

**Median: Nidoking (Base) — IQR 125.7%, 10 conditions**
> Graded bucket at median $328.56 contaminates the distribution. "Non gradée" (French "Ungraded") has median $105.64 — 3× the main "Ungraded" bucket.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 149 | $30.00 | $1.25 – $1,000.00 |
| Used | 34 | $40.00 | $14.99 – $5,476.05 |
| Non gradée (FR) | 4 | $105.64 | $58.68 – $410.87 |
| Graded | 4 | $328.56 | $75.00 – $924.50 |

**Best: Salazzle ex (Perfect Order) — IQR 40.2%, 4 conditions**
> 197/200 listings in "Ungraded" with tight range. Modern card; condition contamination minimal. Closest thing to usable in Tier M.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 197 | $2.49 | $0.99 – $19.99 |
| Nicht bewertet (DE) | 1 | $11.67 | — |
| Non gradé (FR) | 1 | $1.83 | — |

---

### Tier L

**Worst: Dark Wartortle (Team Rocket) — IQR 154.3%, 7 conditions**
> Vintage Team Rocket card shows same contamination as Base Set holos: graded listings, international condition strings, "Used" bucket spanning $1.50 to $225.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 171 | $5.00 | $1.05 – $189.98 |
| Used | 21 | $14.60 | $1.50 – $225.00 |
| Graded | 3 | $35.00 | $14.99 – $275.00 |

**Median: Garbodor V (Evolving Skies) — IQR 63.5%, 5 conditions**
> Modern V card: 91% of listings in "Ungraded", relatively tight. Still has "Used" bucket at 2× median price, and German/Italian condition strings. Usable with condition filter.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 182 | $2.49 | $0.88 – $109.52 |
| Used | 14 | $4.74 | $1.79 – $36.51 |

**Best: Murkrow (Phantasmal Flames) — IQR 47.3%, 4 conditions**
> 197/200 "Ungraded", ratio 1.21×. Essentially clean. Modern common card with no collector premium creates no grade-mixing pressure. Best data quality in the entire sample.

| Condition | Count | Median | Range |
|---|---|---|---|
| Ungraded | 197 | $1.69 | $0.72 – $4.00 |

---

## d. Honest per-tier assessment

### Tier H — NOT USABLE

Verdict is unambiguous. 9/10 cards grade-mixed, median IQR 189.4%, 100% outlier rate. The "Ungraded" bucket alone (which would be the post-filter target) has ranges spanning 3–4 orders of magnitude. Blastoise "Ungraded": $0.99 to $7,599. This is not noise that a filter can clean; it reflects a genuine population of listings — played raw cards, near-mint raw cards, and mislabeled near-graded cards all in the same bucket. The ask-price median for a Tier H card is meaningless as a signal input.

**Even with strict condition filtering ("Ungraded" only):** Charizard "Ungraded" median ~$400 sounds plausible, but the range $4.99–$4,999 remains because "Ungraded" doesn't differentiate worn from near-mint. One heavy-play card at $5 and one near-gem at $4,999 both say "Ungraded." Ask-price cannot recover from this.

### Tier M — NOT USABLE

Same structural problems as Tier H, slightly lower magnitude. 90% grade-mixed, median IQR 129.3%. The exception (Salazzle ex at IQR 40.2%) is a modern card that happens to be in Tier M by our sample criteria — its characteristics are more Tier L than Tier M. The vintage cards in Tier M (Arcanine Base, Nidoking Base, Pinsir Jungle, Haunter Base, Magneton Base) all show the same grade-mix pattern as Tier H. The few modern cards (Mega Sharpedo ex, Spewpa) would be usable but represent the exception, not the rule.

### Tier L — USABLE WITH CONDITION FILTER (modern cards only)

**Conditional verdict.** The tier splits cleanly:

- **Modern commons/uncommons** (Murkrow Phantasmal Flames, Switching Cups, Garbodor V, Hisuian Sneasler, Bellsprout): IQR 47–65%, ratio under 5×, 90%+ "Ungraded". Filtering to "Ungraded" (and normalizing international equivalents) would produce a workable ask-price signal. These cards are $1–$5 range; absolute noise is small.
- **Vintage/older cards in Tier L** (Dragonair Base, Dark Wartortle Team Rocket, Growlithe Base, Rapidash Jungle): Same contamination as Tier H/M. IQR 96–154%, grade-mixed. Tier L status reflects low eBay *sold* activity, not low *listing* noise.

**The ask-price median for a modern Tier L common could serve as a rough signal proxy**, but it would measure "what sellers are asking" not "what buyers paid." That distinction matters for signal calibration.

---

## e. Gotchas for future eBay work

**1. Query doesn't encode card number — Pikachu is the canonical example.**
`_build_search_query` produces "Pokemon Pikachu Base -PSA..." which matches Pikachu #58 (Base), Pikachu #60 (Base Yellow Cheeks), Pikachu #58 (Shadowless), Pikachu #58 (1st Edition) — cards with 10× price differences. Any card with multiple prints in a set will return a mixed-variant pool. The `card_number` field exists on `Asset` but is not in the query. Adding it would narrow results significantly for any card with variants.

**2. International condition strings are silently fragmenting distributions.**
eBay returns conditions in the seller's locale language: "Non gradée" (FR), "Non gradata" (IT), "Nicht bewertet" (DE), "Sin clasificar" (ES), "Gebraucht" (DE for Used), "Usato" (IT for Used), "Neuf/Scellé" (FR for New/Sealed). All mean "Ungraded" or "Used" — there are at least 10+ distinct strings that a normalization step would collapse to 2. Without normalization, a condition filter on "Ungraded" misses ~8% of listings for popular cards.

**3. "New/Factory Sealed" is not a card condition.**
eBay's condition taxonomy allows "New/Factory Sealed" on individual card listings. Sellers use this for packs ripped in front of buyer, sealed booster boxes, or first-edition "new old stock." Blastoise had 14 such listings at median $700. A condition filter must explicitly exclude this.

**4. "Graded" as eBay condition vs graded keywords in title.**
The `-graded` title exclusion works when the seller writes "PSA 9 Charizard" in the title. But sellers can set eBay condition = "Graded" with a clean title like "Charizard Base Set Holo" — passes title exclusions. For ask-price ingestion, filtering by condition (exclude "Graded") is necessary in addition to title exclusions.

**5. Every popular card hit the 200-listing cap.**
29/30 cards returned exactly 200 results. The Browse API default limit is 200. These 200 listings are a snapshot of potentially thousands — for Charizard Base, there may be 10,000+ active listings. The 200 we see are sorted by "endingSoonest" (soonest-to-expire auctions and BIN). This biases toward shorter-duration listings and may undersample "Buy It Now at my ask price forever" listings. Any aggregate statistic from this data represents "the 200 cheapest-expiring listings," not "the full market."

**6. $11,111.11 and similar junk prices pass all filters.**
Eevee returned a $11,111.11 listing in the "Ungraded" condition bucket. These are common eBay placeholder prices (some sellers set prices as 11111, 99999, etc. as inventory placeholders). A price ceiling filter (e.g. >10× the p75) is needed before computing any aggregate.

**7. "Used" condition is not equivalent to "played."**
eBay's "Used" condition means different things across categories. For Pokémon cards, sellers apply "Used" for everything from light play to heavily damaged. The "Used" bucket median is consistently 2–3× higher than "Ungraded" median — suggesting "Used" is being applied to older or rarer copies, not to lower-quality ones. Counterintuitive but consistent across the sample.

**8. The query exclusion list needs "sealed" and "box" for vintage holos.**
Blastoise's "New/Factory Sealed" contamination suggests adding `-sealed -booster -box` to the ungraded exclusion list for vintage cards. These terms appear in sealed-product listings that slip through because the individual card name is in the item title.

---

*Artifacts:*
- `browse-raw/<card_id>.json` — one raw API response per card (30 files)
- `browse-listings.csv` — 5,914 individual listing records
- `browse-summary.csv` — per-card price statistics
- `condition-analysis.csv` — per-card condition distribution flags
