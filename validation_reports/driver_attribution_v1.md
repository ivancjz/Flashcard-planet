# Driver Attribution Validation — Gate 2

**Run at:** 2026-05-20T16:28:54.888887+00:00
**DB:** production (junction.proxy.rlwy.net)

---

## Summary

**Testable cases:** 3
**Accuracy (testable only):** 3/3 = 100.0%

### Per-driver breakdown (testable cases only)

| Expected Driver | Pass | Total | Accuracy |
|---|---|---|---|
| EVENT_DRIVEN | 3 | 3 | 100.0% |

### Excluded cases

| Category | Count | Reason |
|---|---|---|
| Source Missing | 0 | source_url not set — excluded per Evidence Discipline 2026-05-19 |
| MACRO Retrospective | 5 | historical signal breadth not reproducible |
| Universe Gap | 5 | affected assets/sets not in coverage universe |

**Accuracy threshold:** TBD by Ivan based on these numbers.

---

## Testable Cases

| Event | Type | Date | Source | Asset | Expected | Actual | Confidence | Pass | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Surging Sparks (sv8) release  -  Pikachu ex SIR, Raichu ex SIR demand surge | RELEASE | 2025-11-08 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv8/) | Pikachu ex [Surging Sparks] | EVENT_DRIVEN | EVENT_DRIVEN | 0.714 | ✓ | RELEASE event 'Surging Sparks (sv8) release  -  Pikachu ex SIR, Raichu ex SIR demand surge' explicit |
| Journey Together (sv9) release  -  Mew ex SIR, Mewtwo ex SIR debut | RELEASE | 2025-03-28 | [source](https://bulbapedia.bulbagarden.net/wiki/Journey_Together_(TCG)) | Lillie's Clefairy ex [Journey Together] | EVENT_DRIVEN | EVENT_DRIVEN | 0.714 | ✓ | RELEASE event 'Journey Together (sv9) release  -  Mew ex SIR, Mewtwo ex SIR debut' explicitly target |
| Prismatic Evolutions (sv8.5) release - mainstream media coverage of nationwide s | RELEASE | 2025-01-17 | [source](https://gocollect.com/blog/ready-for-the-release-of-pokemon-prismatic-evolutions) | Umbreon ex [Prismatic Evolutions] | EVENT_DRIVEN | EVENT_DRIVEN | 0.6 | ✓ | RELEASE event 'Prismatic Evolutions (sv8.5) release - mainstream media coverage of nationwide s' exp |

---

## Excluded — Source Missing

*0 events excluded. Add authoritative source_url to `market_events` to make testable.*

| Event | Type | Date | Source | Asset | Expected | Actual | Confidence | Pass | Reason |
|---|---|---|---|---|---|---|---|---|---|

---

## Excluded — MACRO Retrospective

*5 cases excluded. MACRO attribution checks set-wide signal breadth at the moment of attribution. The `asset_signals` table reflects the current state — it does not store snapshots of historical signal states. Retrospective MACRO validation requires time-travel queries; validate forward-only via production observation after Gate 4 enables the scheduler.*

| Event | Type | Date | Source | Asset | Expected | Actual | Confidence | Pass | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Chaos Rising worldwide release - 4th Mega Evolution set, chase cards: Mega Greni | RELEASE | 2026-05-22 | [source](https://www.pokemon.com/us/pokemon-news/the-pokemon-tcg-mega-evolution-chaos-rising-expansion-arrives-on-may-22-2026) | Seel [Phantasmal Flames] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Chaos Rising set officially announced by The Pokemon Company - pre-release hype  | RELEASE | 2026-03-12 | [source](https://www.pokemon.com/us/pokemon-news/the-pokemon-tcg-mega-evolution-chaos-rising-expansion-arrives-on-may-22-2026) | Seel [Phantasmal Flames] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Stellar Crown (sv7) release  -  Terapagos ex SIR debut | RELEASE | 2025-09-12 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv7/) | Stellar Crown Booster Box [Stellar Crown] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Shrouded Fable (sv6.5) release  -  Pecharunt ex SIR, Darkrai ex SIR debut | RELEASE | 2025-08-02 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv6pt5/) | Seel [Phantasmal Flames] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Twilight Masquerade (sv6) release  -  Bloodmoon Ursaluna ex SIR peak demand | RELEASE | 2025-06-13 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv6/) | Twilight Masquerade Booster Box [Twilight Masquerade] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |

---

## Excluded — Universe Gap

*5 cases excluded. Affected assets/sets not tracked in the asset coverage universe (vintage cards, untracked sets, or broad events with no set affiliation). Engine returning UNKNOWN is correct behavior — it honestly reports uncertainty when the card is outside its data universe.*

| Event | Type | Date | Source | Asset | Expected | Actual | Confidence | Pass | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Logan Paul Pikachu Illustrator PSA 10 final sale at Goldin auction - $16.492M re | INFLUENCER | 2026-02-15 | [source](https://inasianspaces.com/2026/02/17/logan-paul-pikachu-illustrator-16-million-goldin-auction-record/) | Seel [Phantasmal Flames] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |
| Logan Paul + Goldin 1st Edition Base Set box break ($1.38M pack sales) - vintage | INFLUENCER | 2026-02-15 | [source](https://www.cllct.com/sports-collectibles/sports-cards/packs-in-logan-paul-1st-edition-pokemon-break-sell-for-combined-1-38-million) | Seel [Phantasmal Flames] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |
| MrBeast x Whatnot Big Game livestream - $1M+ giveaway including Base Set Booster | INFLUENCER | 2026-02-08 | [source](https://www.actionfigureinsider.com/mrbeast-x-whatnot-super-bowl-livestream-giving-away-rare-pokemon-cards-49ers-sb-ring-and-more/) | Seel [Phantasmal Flames] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |
| Logan Paul Pikachu Illustrator PSA 10 Goldin auction opens Jan 5 2026 - original | INFLUENCER | 2026-01-26 | [source](https://www.comicsbeat.com/logan-paul-pikachu-card-to-go-up-for-auction-january-5/) | Seel [Phantasmal Flames] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |
| 2025 Pokemon World Championships Anaheim CA (Aug 15-17) - TCG Masters won by Ril | TOURNAMENT | 2025-08-17 | [source](https://bulbapedia.bulbagarden.net/wiki/2025_Pok%C3%A9mon_World_Championships) | Seel [Phantasmal Flames] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |

---

## Evidence discipline

- All event data sourced from `market_events` table.
- `reference_time = event_date + 1d` simulates attribution firing one day after event.
- `signal_move_pct = +10%` (synthetic positive move).
- Cases excluded by SOURCE_MISSING remain excluded regardless of engine result.
- Source URLs for all testable cases are embedded in the Source column above.

*Generated by `scripts/validate_driver_attribution.py` at 2026-05-20T16:28:54.888887+00:00*