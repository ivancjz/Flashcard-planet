# Current Provider Evaluation

As of April 3, 2026, the active provider remains `pokemon_tcg_api`. This note keeps the scope diagnostic: no provider switch, no broad universe expansion, and no change to canonical asset identity.

## Current definitions

- `High-Activity Trial` is the contiguous `sv8pt5-148..180` premium slice from Prismatic Evolutions.
- `High-Activity Candidate` still means cards inside `High-Activity Trial` plus any modern `Chase / Collectible` card.
- `High-Activity v2` is a tighter 13-card diagnostic pool inside `sv8pt5` built from explicit single-card raw ids.

## Proposed High-Activity v2 cards

- `sv8pt5-149` Vaporeon ex
- `sv8pt5-150` Glaceon ex
- `sv8pt5-153` Jolteon ex
- `sv8pt5-155` Espeon ex
- `sv8pt5-156` Sylveon ex
- `sv8pt5-157` Iron Valiant ex
- `sv8pt5-161` Umbreon ex
- `sv8pt5-162` Roaring Moon ex
- `sv8pt5-165` Dragapult ex
- `sv8pt5-166` Raging Bolt ex
- `sv8pt5-167` Eevee ex
- `sv8pt5-168` Bloodmoon Ursaluna ex
- `sv8pt5-179` Pikachu ex

## Coverage audit summary

The current provider coverage on `High-Activity v2` is healthy.

- Consistent provider fetches: `13 of 13`
- History depth still increasing: `13 of 13`
- Cards with any observed real price change: `13 of 13`
- Cards with a real price change in the last 24 hours: `11 of 13`
- Weak coverage candidates: `0 of 13`
- No market movement observed despite healthy coverage: `0 of 13`

Key comparison against the current 33-card `High-Activity Trial` from the same April 3, 2026 run:

- No-movement cards: `0/13` in `High-Activity v2` vs `1/33` in `High-Activity Trial`
- Cards with a 7-day price change: `13/13` vs `32/33`
- Comparable-row change rate over 7 days: `2.42%` vs `2.70%`

Interpretation:

- The provider is not failing to fetch or deepen history on the relevant cards.
- The current 33-card pool is too blunt for a smart-pool test because it mixes stronger names with weaker relevance names inside the same contiguous slice.
- Even the tighter 13-card pool still shows modest row-change rates, so provider #1 is not yet proven to be a strong high-frequency movement source.

## Recommendation

Replace the current `High-Activity Trial` with `High-Activity v2` for the next observation window, but keep the current provider and continue observing before making any provider #2 decision.
