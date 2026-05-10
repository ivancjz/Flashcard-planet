# OpenAI IP Tagging Validation — TASK-401

**Date:** 2026-05-02
**Model:** gpt-4o-mini (gpt-5.5 rejected as invalid Chat Completions model — see fix commit 3907360)
**Endpoint:** POST /admin/trigger/ip-tagging-sample
**Conclusion:** Accuracy target met. OpenAI IP tagging is validated for Phase 3 use.

---

## Results summary

| Run | n | API parse succeeded | Parse rate | Notes |
|---|---|---|---|---|
| Run 1 | 10 | 10 | 1.0 | Initial post-fix run |
| Run 2 | 20 | 20 | 1.0 | Extended validation |

Both runs: 0 API failures, 0 parse errors.

---

## Manual accuracy review (30 results across both runs)

### Pokemon (15 cards reviewed)

| Card | franchise | character | themes | Correct? |
|---|---|---|---|---|
| Squirtle | Pokemon | Squirtle | water, starter, turtle | ✓ |
| Groudon | Pokemon | Groudon | ground, legendary, expansion | ✓ |
| Chi-Yu ex | Pokemon | Chi-Yu ex | fire, dark, ex | ✓ |
| Ribombee | Pokemon | Ribombee | bug, fairy, evolution | ✓ |
| Beedrill | Pokemon | Beedrill | bug, poison, evolution | ✓ |
| Infernape | Pokemon | Infernape | fire, fighting, evolution | ✓ |
| Meowstic | Pokemon | Meowstic | psychic, cat, evolution | ✓ |
| Hop's Zacian ex | Pokemon | Zacian | metal, legendary, trainer card | ✓ (extracts character from trainer card) |
| Candice | Pokemon | Candice | ice, gym leader, support | ✓ |
| Super Energy Removal | Pokemon | Super Energy Removal | energy removal, trainer, support | ✓ (trainer card handled correctly) |
| Dark Machoke | Pokemon | Dark Machoke | fighting, dark, evolution | ✓ |
| Team Rocket's Exeggcute | Pokemon | Team Rocket's Exeggcute | grass, dark, team rocket | ✓ |
| Tranquill | Pokemon | Tranquill | normal, flying, bird | ✓ |
| Cryogonal | Pokemon | Cryogonal | ice, frozen, pokemon | ✓ |
| Dark Gloom | Pokemon | Dark Gloom | dark, grass, evolution | ✓ |

**Pokemon accuracy: 15/15 (100%)**

### Yu-Gi-Oh! (15 cards reviewed)

| Card | franchise | character | themes | Correct? |
|---|---|---|---|---|
| Mimesis Elephant | Yu-Gi-Oh! | Mimesis Elephant | earth, beast, summon | ✓ |
| Ravenous Vendread | Yu-Gi-Oh! | Ravenous Vendread | zombie, ritual, dark | ✓ |
| Rikka Princess | Yu-Gi-Oh! | Rikka Princess | plant, fusion, ritual | ✓ |
| Krawler Soma | Yu-Gi-Oh! | Krawler Soma | insect, flip, control | ✓ |
| Toon Harpie Lady | Yu-Gi-Oh! | Toon Harpie Lady | toon, harpy, female | ✓ |
| Immortal Phoenix Gearfried | Yu-Gi-Oh! | Immortal Phoenix Gearfried | warrior, phoenix, Toon | ~ (Toon theme incorrect — not a Toon archetype card) |
| Infernoble Knight - Renaud | Yu-Gi-Oh! | Infernoble Knight - Renaud | warrior, fire, noble | ✓ |
| Brilliant Rose | Yu-Gi-Oh! | Brilliant Rose | plant, fusion, light | ✓ |
| Eanoc, Sentry of the Ghoti | Yu-Gi-Oh! | Eanoc, Sentry of the Ghoti | water, fish, sentry | ✓ |
| Evocator Eveque | Yu-Gi-Oh! | Evocator Eveque | toon, spellcaster, chaos | ~ (Toon theme incorrect) |
| Magician of Hope | Yu-Gi-Oh! | Magician of Hope | toon, spellcaster, light | ~ (Toon theme incorrect) |
| Gunkan Suship Shari Red | Yu-Gi-Oh! | Gunkan Suship Shari Red | food, seafood, fusion | ✓ |
| Gadget Gamer | Yu-Gi-Oh! | Gadget Gamer | gadget, machine, support | ✓ |
| Code Generator | Yu-Gi-Oh! | Code Generator | Toon, Machine, Support | ~ (Toon theme incorrect) |
| Rikka Princess | Yu-Gi-Oh! | Rikka Princess | plant, fusion, ritual | ✓ |

**YGO accuracy: 11/15 (73%) — 4 cards incorrectly tagged with "Toon" theme**

---

## Overall accuracy

- 26/30 manually verified correct = **87% accuracy — meets >85% target**
- Failure mode: model over-applies "Toon" theme to YGO cards that are not from the Toon archetype. Likely because "Toon" is a distinctive YGO keyword and the model pattern-matches on visual/card naming cues.

---

## Decision

**PASS.** 87% accuracy exceeds the 85% target defined in TASK-401 DoD.

OpenAI IP tagging is validated for use in Phase 3 Cross-TCG Franchise Move signals.

**Known failure mode to address in TASK-402 (if/when needed):**
- Add negative examples for "Toon" archetype to the system prompt
- Explicitly instruct: "Toon is a specific Yu-Gi-Oh! archetype — only tag it if the card name contains 'Toon'"

**Phase 3 readiness:** IP tagging can proceed to full-batch (10K assets) once Phase 3 is scheduled. Use OpenAI Batch API for 50% cost reduction.
