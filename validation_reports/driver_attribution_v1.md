# Driver Attribution Validation — Gate 2

**Run at:** 2026-05-20T15:44:19.144855+00:00
**DB:** production (junction.proxy.rlwy.net)

---

## Summary

**Testable cases:** 2
**Accuracy (testable only):** 2/2 = 100.0%

### Per-driver breakdown (testable cases only)

| Expected Driver | Pass | Total | Accuracy |
|---|---|---|---|
| EVENT_DRIVEN | 2 | 2 | 100.0% |

### Excluded cases

| Category | Count | Reason |
|---|---|---|
| Source Missing | 9 | source_url not set — excluded per Evidence Discipline 2026-05-19 |
| MACRO Retrospective | 7 | historical signal breadth not reproducible |
| Universe Gap | 5 | affected assets/sets not in coverage universe |

**Accuracy threshold:** TBD by Ivan based on these numbers.

---

## Testable Cases

| Event | Type | Date | Source | Asset | Expected | Actual | Confidence | Pass | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Prismatic Evolutions launch - mainstream media coverage of nationwide sellouts,  | INFLUENCER | 2025-01-17 | [source](https://gocollect.com/blog/ready-for-the-release-of-pokemon-prismatic-evolutions) | Prismatic Evolutions Booster Bundle [Prismatic Evolutions] | EVENT_DRIVEN | EVENT_DRIVEN | 0.72 | ✓ | INFLUENCER event 'Prismatic Evolutions launch - mainstream media coverage of nationwide sellouts, '  |
| Prismatic Evolutions launch - mainstream media coverage of nationwide sellouts,  | INFLUENCER | 2025-01-17 | [source](https://gocollect.com/blog/ready-for-the-release-of-pokemon-prismatic-evolutions) | Prismatic Evolutions Elite Trainer Box [Prismatic Evolutions | EVENT_DRIVEN | EVENT_DRIVEN | 0.72 | ✓ | INFLUENCER event 'Prismatic Evolutions launch - mainstream media coverage of nationwide sellouts, '  |

---

## Excluded — Source Missing

*9 events excluded. Add authoritative source_url to `market_events` to make testable.*

| Event | Type | Date | Source | Asset | Expected | Actual | Confidence | Pass | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Destined Rivals (sv10) release | RELEASE | 2026-05-30 | — | — | MACRO | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |
| Chaos Rising release  -  Mega Greninja ex SIR, Mega Floette ex SIR debut | RELEASE | 2026-05-22 | — | — | MACRO | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |
| Spring 2026 Regionals  -  first major with Journey Together legal | TOURNAMENT | 2026-04-19 | — | — | EVENT_DRIVEN | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |
| PSA April 2026 population report  -  Pikachu ex SIR Surging Sparks pop shock | SUPPLY | 2026-04-15 | — | — | SUPPLY_SHOCK | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |
| Evolving Skies reprint announcement  -  Rayquaza VMAX, Umbreon VMAX price drop | SUPPLY | 2026-03-15 | — | — | SUPPLY_SHOCK | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |
| Prismatic Evolutions restock announcement  -  Eevee SIR price correction from $2 | SUPPLY | 2026-02-01 | — | — | SUPPLY_SHOCK | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |
| Destined Rivals reprint announcement  -  vintage card prices suppress on reprint | SUPPLY | 2025-11-15 | — | — | SUPPLY_SHOCK | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |
| PSA grading population milestone  -  Charizard base shadowless PSA 10 pop exceed | SUPPLY | 2025-10-01 | — | — | SUPPLY_SHOCK | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |
| North American International Championships 2025  -  meta rotation impact | TOURNAMENT | 2025-09-28 | — | — | EVENT_DRIVEN | — | — | — | source_url not set — excluded per Evidence Discipline 2026-05-19; add authoritative URL to market_ev |

---

## Excluded — MACRO Retrospective

*7 cases excluded. MACRO attribution checks set-wide signal breadth at the moment of attribution. The `asset_signals` table reflects the current state — it does not store snapshots of historical signal states. Retrospective MACRO validation requires time-travel queries; validate forward-only via production observation after Gate 4 enables the scheduler.*

| Event | Type | Date | Source | Asset | Expected | Actual | Confidence | Pass | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Chaos Rising worldwide release - 4th Mega Evolution set, chase cards: Mega Greni | RELEASE | 2026-05-22 | [source](https://www.pokemon.com/us/pokemon-news/the-pokemon-tcg-mega-evolution-chaos-rising-expansion-arrives-on-may-22-2026) | Origin Forme Dialga VSTAR [Astral Radiance] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Journey Together (sv9) release  -  Mew ex SIR, Mewtwo ex SIR debut | RELEASE | 2026-03-28 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv9/) | Blaziken ex [Journey Together] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Prismatic Evolutions (sv8pt5) release  -  Eevee SIR hits $200+, massive market e | RELEASE | 2026-01-17 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv8pt5/) | Prismatic Evolutions Booster Bundle [Prismatic Evolutions] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Surging Sparks (sv8) release  -  Pikachu ex SIR, Raichu ex SIR demand surge | RELEASE | 2025-11-08 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv8/) | Surging Sparks Booster Box [Surging Sparks] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Stellar Crown (sv7) release  -  Terapagos ex SIR debut | RELEASE | 2025-09-12 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv7/) | Stellar Crown Booster Box [Stellar Crown] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Shrouded Fable (sv6.5) release  -  Pecharunt ex SIR, Darkrai ex SIR debut | RELEASE | 2025-08-02 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv6pt5/) | Origin Forme Dialga VSTAR [Astral Radiance] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |
| Twilight Masquerade (sv6) release  -  Bloodmoon Ursaluna ex SIR peak demand | RELEASE | 2025-06-13 | [source](https://www.pokemon.com/us/pokemon-tcg/product-line/sv6/) | Twilight Masquerade Booster Box [Twilight Masquerade] | MACRO | — | — | — | MACRO attribution requires set-wide signal breadth at moment of event; asset_signals reflects curren |

---

## Excluded — Universe Gap

*5 cases excluded. Affected assets/sets not tracked in the asset coverage universe (vintage cards, untracked sets, or broad events with no set affiliation). Engine returning UNKNOWN is correct behavior — it honestly reports uncertainty when the card is outside its data universe.*

| Event | Type | Date | Source | Asset | Expected | Actual | Confidence | Pass | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Chaos Rising (Mega Evolution-Chaos Rising) set officially announced by Pokemon C | INFLUENCER | 2026-03-12 | [source](https://www.pokemon.com/us/pokemon-news/the-pokemon-tcg-mega-evolution-chaos-rising-expansion-arrives-on-may-22-2026) | Origin Forme Dialga VSTAR [Astral Radiance] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |
| Logan Paul + Goldin 1st Edition Base Set box break ($1.38M pack sales) - vintage | INFLUENCER | 2026-02-15 | [source](https://www.cllct.com/sports-collectibles/sports-cards/packs-in-logan-paul-1st-edition-pokemon-break-sell-for-combined-1-38-million) | Origin Forme Dialga VSTAR [Astral Radiance] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |
| MrBeast x Whatnot Big Game livestream - $1M+ giveaway including Base Set Booster | INFLUENCER | 2026-02-08 | [source](https://www.actionfigureinsider.com/mrbeast-x-whatnot-super-bowl-livestream-giving-away-rare-pokemon-cards-49ers-sb-ring-and-more/) | Origin Forme Dialga VSTAR [Astral Radiance] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |
| Logan Paul Pikachu Illustrator PSA 10 relisted at Goldin (record $5.275M purchas | INFLUENCER | 2026-01-26 | [source](https://www.cllct.com/sports-collectibles/sports-cards/packs-in-logan-paul-1st-edition-pokemon-break-sell-for-combined-1-38-million) | Origin Forme Dialga VSTAR [Astral Radiance] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |
| 2025 Pokemon World Championships  -  Anaheim CA, drives meta-relevant card deman | TOURNAMENT | 2025-08-14 | [source](https://worlds.pokemon.com/en-us/) | Origin Forme Dialga VSTAR [Astral Radiance] | EVENT_DRIVEN | — | — | — | affected_asset_ids resolved to 0 DB rows and affected_set_ids had no matching assets — harness fell  |

---

## Evidence discipline

- All event data sourced from `market_events` table.
- `reference_time = event_date + 1d` simulates attribution firing one day after event.
- `signal_move_pct = +10%` (synthetic positive move).
- Cases excluded by SOURCE_MISSING remain excluded regardless of engine result.
- Source URLs for all testable cases are embedded in the Source column above.

*Generated by `scripts/validate_driver_attribution.py` at 2026-05-20T15:44:19.144855+00:00*