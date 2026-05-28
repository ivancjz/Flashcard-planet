# Flashcard Planet — 12-Month Product Roadmap Design

**Date:** 2026-05-28  
**Approach:** Parallel tracks — Revenue + Product run simultaneously  
**Timeline:** 12 months (~mid-2027)  
**Status:** Approved by Ivan 2026-05-28

---

## Context

Flashcard Planet is a TCG investment signals SaaS with a genuine competitive moat: the BREAKOUT/MOVE/WATCH/IDLE classification system has zero direct competitors across 15+ platforms reviewed. The core market gap is that all existing tools are either portfolio trackers (show you what you have) or threshold alert tools (notify when a watched card moves). No competitor proactively classifies market momentum and surfaces unseen opportunities.

**Key research findings that shaped this roadmap:**
- PokeNotify earns ~$2.2M ARR from Pokemon restock alerts alone (no signal classification) at $7.99/mo × 23K+ subscribers — Flashcard Planet's signals are materially more valuable
- One Piece TCG investor tooling does not exist — investors currently use Instagram/YouTube manually
- Benchmark anchor for signal/alert tools: $7.99–$9.99/mo; defensible position at $12–$15/mo for multi-game classification
- Natural language signal explanation ("why did this card BREAKOUT?") is the highest-ROI AI feature gap — no competitor has it
- Japanese Pokemon prices lead English prices by 4–8 weeks — uniquely defensible Pro-tier feature

---

## Pricing Architecture (revised from single Pro tier)

| Tier | Price | What's included |
|------|-------|----------------|
| **Free** | $0 | IDLE/WATCH signals only, 24h delay, 1 game (Pokemon), 1 watchlist, no Discord DMs |
| **Signal** | $9.99/mo | Real-time BREAKOUT/MOVE alerts, Discord DMs, all 3 games, unlimited watchlist, 1-sentence AI explanation |
| **Pro** | $24.99/mo | All Signal features + full AI analysis (drivers/risks), Japanese lead signals, pre-grading ROI calc, portfolio analytics, API access |

**Trial:** 14 days, no card required. Converts to Signal tier.  
**Provider:** LemonSqueezy (merchant-of-record; handles AU GST, EU VAT, US sales tax)  
**Founders promo:** First 100 Signal subscribers lock in at $7.99/mo lifetime.

---

## Public Calls Track (Parallel, Active Now)

This is a separate workstream from the revenue/product phases above. The Public Calls system (predictions + Brier calibration + driver attribution + `/calls` page) has been in active development since 2026-05-18 and has its own quality gate sequence. It is NOT a Phase 1–4 item — it runs independently on its own gate timeline.

**Current gate status (as of 2026-05-28):**

| Gate | Status | Next action |
|------|--------|------------|
| Gate 1: Backend services | ✅ Done (PR #73) | — |
| Gate 2: Attribution validation 7/7 | ✅ Done | Ivan formal sign-off |
| Gate 3: Fundamental signal sanity | Blocked on Gate 2 sign-off | Sign off Gate 2 first |
| Gate 4: Resolution scheduler staging | Waiting on Ivan | **Set `RESOLVE_PREDICTIONS_ENABLED=true` in Railway** |
| Gate 5: Chaos Rising data baseline | Active — T+7d check 2026-05-29 | Run data completeness SQL tomorrow |
| Gate 6: Methodology page | ✅ Done (2026-05-28) | — |
| Gate 7: Smart sort calibration | Depends Gate 5 | After Gate 5 data confirms |
| Gate 8: Paper trade window | Opens ~2026-06-01 | 10 paper predictions required |
| Gate 9: Fresh public calls cohort | Depends Gates 1–8 | Post paper trading |
| Gate 10: Frontend /calls page | Depends Gates 6+7+9 | Final gate before public launch |

**What "Public Calls" is:**
- Every prediction is locked at creation, auto-resolved against market data, and aggregated into a public Brier score
- Driver attribution engine classifies *why* a signal occurred (MACRO / EVENT_DRIVEN / SUPPLY_SHOCK / UNKNOWN)
- `/calls` page is the public-facing credibility anchor and top-of-funnel acquisition page
- Methodology page at `/methodology` is already live

**Where this fits in the 12-month plan:**
Public Calls launches after Gate 10 — estimated June–July 2026 (within Phase 1 timeline). It becomes a differentiating feature of the Pro tier and feeds into Phase 4's Deep Analysis work (the prediction track provides the training corpus for calibration claims).

---

## Phase 1 — Months 1–2: Revenue Foundation + Platform Cleanup

### Revenue Track

**3-Tier Pricing Redesign**
- Restructure `permissions.py` feature flags for Free / Signal / Pro
- Define gate boundaries: Free = delayed 24h + IDLE/WATCH only; Signal = real-time all games; Pro = AI + JP signals
- Update `PricingPage.tsx` to reflect 3-tier model with feature comparison table

**LemonSqueezy Integration (TASK-301)**
- Schema: Add `subscription_tier`, `subscription_status`, `ls_subscription_id`, `ls_customer_id`, `trial_ends_at` to `users`
- Webhook handler: `POST /webhooks/lemonsqueezy` — handle `subscription_created`, `subscription_updated`, `subscription_cancelled`, `subscription_expired`
- Trial enforcement: auto-start on signup (once `TRIAL_AUTO_START=1` set in Railway)
- Upgrade flow: replace `upgrade_service.py` mock with real LemonSqueezy checkout URL generation
- 5 CTA placements wired (ProGate callsites → real checkout URL)
- First real payment processed (operator card)

**Domain (TASK-501) — operator infra steps first**
- Operator: register flashcardplanet.com, Railway custom domain, update Google OAuth redirect URI
- Code PR: update APP_URL fallback + email FROM_ADDRESS after domain is live

### Product Track (Cleanup + Quick Wins)

| Task | What | Size |
|------|------|------|
| TASK-801 check | Verify 8 seeded YGO cards graduated from INSUFFICIENT_DATA (overdue) | XS |
| TASK-T06 | Delete stale `/admin/diag/ingestion-history` (hardcoded 2026-04-23 timestamps) | XS |
| TASK-T07 | Add `health_warnings` to `/admin/stats` + JSON `/admin/diagnostics` endpoint | S |
| TASK-T08 | Add operational health-check reference to `DEV_NOTES.md` | XS |
| TASK-502/503 | Sealed product ingest job + `/sealed` page (pending eBay creds confirm) | S |

**Phase 1 gate:** First real LemonSqueezy payment processed end-to-end.

---

## Phase 2 — Months 2–4: Game Expansion + AI Signal Explanation

### One Piece TCG Integration (green-field, zero competition)

**Data source:** optcgapi.com (free) for Phase 1 seed; tcgapi.dev Pro ($49.99/mo) if optcgapi.com coverage proves insufficient.

**Seed list (Phase 1 — 20–30 cards):**
- OP13 "Carrying On His Will": Luffy OP13-118 (Manga Rare), Ace OP13-119, Shanks OP13-121
- OP01 "Romance Dawn" vintage: Monkey D. Luffy SEC OP01-120 (historical benchmark card)
- OP05 "Awakening of the New Era": high-liquidity modern staples
- OP09: recent high-velocity set

**Implementation:**
- New `backend/app/ingestion/onepiece.py` following YGO ingest pattern
- Scheduler job `onepiece-ingestion`, 6h interval, writes `price_history.source = 'optcgapi'`
- `game = 'optcg'` on Asset rows (existing enum value in `ygo.py` scaffold)
- Reuse `classify_signal()` unchanged — no signal engine modifications needed
- Card detail page: extend `CardDetailPage.tsx` for OPTCG assets
- Signal/Pro gate: BREAKOUT/MOVE real-time for Signal tier; Free gets IDLE/WATCH delayed

### AI Signal Explanation Layer (no competitor has this)

**What it does:** After each signal-sweep, an `explanation-sweep` job generates a 1–3 sentence LLM summary explaining *why* the classification occurred.

- Signal tier output: "Stardust Dragon BREAKOUT — 7-day price delta +42% driven by high sold velocity (15 transactions in 24h)"
- Pro tier output: Full analysis — drivers, historical pattern match, risks, suggested action

**Implementation:**
- `asset_signals.explanation` + `asset_signals.explained_at` (columns already exist per model review)
- `explanation-sweep` job (already exists in scheduler) — extend to use provider routing from TASK-401
- Provider: Anthropic Claude for Signal tier, full context + web search for Pro tier
- Cache: per (asset_id, label) pair, 24h TTL; invalidate on label change
- Frontend: `AIAnalysisSection.tsx` already exists — wire Signal tier to short explanation, Pro to full analysis

### YGO Expansion (conditional)

**Required first:** 7-day discovery test — poll 10 high-velocity 2024–2025 sets (LEDE, PHNI, AGOV, DUNE, INFO) via `/admin/diag/price-variance?source=cardmarket_avg7`.
- If ≥30% of sampled assets show ≥2 distinct prices in 7 days → proceed with TASK-201 (expand to ~30 sets)
- If not → YGO stays at 75 assets, CardMarket-only, deferred to H2

**Phase 2 gate:** One Piece live with ≥1 non-INSUFFICIENT_DATA signal; AI explanation rendering on ≥1 card.

---

## Phase 3 — Months 4–7: Differentiation Layer

### Discord Bot v2 — Slash Commands

**No competitor in the TCG space offers Discord slash commands for signal queries.**

Current architecture: outbound webhook only (no bot process). New: add Discord Gateway bot process alongside existing webhook.

| Command | What |
|---------|------|
| `/signal <card name>` | Returns current classification + delta + 1-sentence explanation |
| `/watchlist add <card>` | Add card to watchlist from Discord DM |
| `/watchlist remove <card>` | Remove from watchlist |
| `/top breakouts` | Returns top 5 BREAKOUT cards right now |
| `/digest` | On-demand market summary |

**Gate model:**
- Signal tier: `/signal`, `/top breakouts`, `/digest`
- Pro tier: `/signal` includes full AI analysis; `/watchlist` commands
- Free tier: no slash commands

**Implementation:**
- New `backend/app/discord_bot/` module with Discord.py or discord-interactions
- Separate Railway service (bot process cannot share the same dyno as the web server due to Gateway connection)
- All slash commands resolve via internal API calls to existing FastAPI endpoints — no duplicate business logic
- Pro-gated Discord server: `#breakout-alerts` channel is Signal-tier exclusive (social proof for free users)

### Japanese Lead-Signal Detection (Pro-only)

**Rationale:** JP Pokemon card prices historically lead EN prices by 4–8 weeks. This is a well-known pattern in the collector community but has never been automated in software.

**Research spike first (2 weeks):**
- Identify JP price source: Pokemon Card JP official API, YuyuTei.co.jp scrape, or buyee.jp sold prices
- Confirm `language='JP'` column exists on `Asset` model (yes, it does)
- Validate: pick 10 cards where JP→EN lead is well-documented (Pikachu VMAX, Umbreon VMAX), backtest the correlation

**Implementation (after spike confirms viability):**
- New ingest job: `japan-price-ingestion`, 6h interval, writes `price_history.source = 'pokemon_jp_*'`, `language='JP'`
- Correlation engine: `jp_lead_service.py` — for each EN card, check if its JP equivalent has a positive delta in the last 14 days; if JP delta ≥15% and EN delta <5% → emit `JP_LEAD` signal
- New `JP_LEAD` signal type in `AssetSignal.label` enum (with full enum-site audit per CLAUDE.md §3)
- Frontend: Pro-tier card detail shows "⚠️ JP signal detected — EN price may follow in 4–8 weeks"
- Discord alert: Pro users get `JP_LEAD` Discord DM alongside standard signal alerts

### Pre-Grading ROI Calculator (Pro feature)

No TCG competitor offers an ML-driven "should I grade this card?" tool.

- Input: card name + condition estimate (NM/LP/MP) + PSA/CGC/BGS selector
- Output: estimated PSA 10 price (from historical comps), submission cost, break-even threshold, estimated ROI %
- Data: population report from PSA API (or scrape) + existing `price_history` for raw vs. graded price comparison
- Frontend: new `GradingROICalculator.tsx` component on card detail page (Pro-gated)

### Frontend Polish

| Task | Size |
|------|------|
| TASK-509: Mobile hamburger nav (shadcn Sheet, ≤640px breakpoint) | S |
| TASK-T03: Modal accessibility — focus trap, Escape key, aria-modal (CardPickerModal, PlusUpgradeModal, FilterDrawer) | S |
| TASK-T05: tierBadge() → CSS classes (.badge-pro, .badge-plus) | S |
| TASK-T04: DESIGN.md — colour semantics, typography scale, component hierarchy | XS |
| TASK-T01: YGO image retry path in `ygo.py` | XS |

**Phase 3 gate:** Discord bot v2 live with slash commands, JP lead signals on ≥10 Pokemon cards, ≥10 paying Pro users.

---

## Phase 4 — Months 7–12: Pro Deep Analysis + Scale

### Pro Deep Analysis (TASK-701)

**The $24.99/mo justification** — capability gap that users cannot replicate manually with ChatGPT.

- New endpoint: `POST /api/v1/predict/deep` (Pro-gated, 5 calls/day per user, rate-limited via `llm_request_log` table)
- Provider: Anthropic Claude with `web_search_20250305` tool enabled
- Structured output: `{ drivers, historical_pattern, thesis, risks, guidance }` where `guidance.action` ∈ `{hold, wait, exit, accumulate}` (never "buy")
- Response time: 15–30s; stream to frontend
- Cost guardrail: alert if daily Deep Analysis spend >$15
- Cache: per (asset_id, date) 24h per user (not shared — Pro exclusivity)

### Sentiment Aggregation

No automated sentiment tool exists for TCG cards.

- Monitor Reddit (`r/pkmntcginvestors`, `r/pokemoncardcollectors`, `r/yugioh`), YouTube video titles, and X/Twitter for card name mention velocity
- Implementation: `sentiment_service.py` — scheduled scrape + NLP mention count, stored in `asset_sentiment` table
- Signal integration: high sentiment velocity boosts `alert_confidence` score on BREAKOUT/MOVE signals
- Frontend: "📈 Social mentions +340% in 24h" label on card detail page (Pro tier) — note: show absolute count alongside percentage
- Discord: "🔥 Trending on Reddit" flag in Pro tier alerts

### Portfolio Analytics

Converts casual users into long-term subscribers through investment tracking.

- Schema: `portfolio_entries` table — `user_id, asset_id, quantity, buy_price, buy_date`
- Features: P&L per card, total portfolio value, cost basis, unrealized gains
- Hold period recommendations: "Based on 3-year data, SIRs from this set typically peak at 18 months"
- Cross-game allocation view: % breakdown by Pokemon / YGO / One Piece
- Frontend: new `PortfolioPage.tsx`

### Scale Layer

| Item | What | Tier |
|------|------|------|
| REST API access | Rate-limited API for personal automation scripts | Pro |
| B2B/dealer tier ($49.99/mo) | Unlimited alerts, bulk CSV export, P&L reporting, webhook delivery | New tier |
| Unpriced card estimation | ML fair-value estimate for cards with <3 recent sales (CardHedger does this for sports) | Pro |
| One Piece tcgapi.dev upgrade | Upgrade from optcgapi.com to tcgapi.dev Pro if ARR ≥ $5K | Ops |

**Phase 4 gate:** ≥10 paying Pro users, Deep Analysis serving real usage, ARR trajectory visible.

---

## Implementation Sequence Summary

```
Month 1    │ Pro launch (3-tier) · LemonSqueezy · domain · cleanup tasks
Month 2    │ One Piece seed · AI explanation layer · YGO discovery test
Month 3    │ One Piece signals live · explanation in production · sealed signals calibration
Month 4    │ Discord bot v2 slash commands · JP lead signal research spike
Month 5    │ JP lead signals in production · pre-grading ROI calculator
Month 6    │ Frontend polish · a11y · mobile nav · DESIGN.md
Month 7    │ Pro deep analysis (TASK-701) · sentiment aggregation spike
Month 8    │ Sentiment aggregation in production · portfolio analytics MVP
Month 9    │ Portfolio analytics full · API access for Pro
Month 10   │ B2B dealer tier · unpriced card estimation
Month 11   │ Scale · optimization · churn analysis
Month 12   │ Review · v2 planning
```

---

## Signal Display Convention — Absolute + Relative Change

**Problem:** Displaying percentage-only changes (e.g., "+340%") looks fake and undermines trust when the absolute dollar move is only $1–2. A $0.50 card rising to $2.00 is a +300% signal but a $1.50 move — not investable for most users.

**Rule:** Always display both absolute dollar change AND percentage change. Absolute amount is the primary figure.

```
BREAKOUT  +$1.50  (+300%)
MOVE      +$0.80  (+18%)
WATCH     +$0.35  (+7%)
```

**Suppression rule:** If absolute delta < $0.50, suppress the percentage entirely and show only the dollar amount. Do not display a 3-digit percentage for noise-level moves.

**Signal engine alignment:** `signal_move_min_price_usd` and `signal_breakout_min_price_usd` already downgrade cheap cards — the display layer must reinforce this, not contradict it with eye-catching percentages.

**Implementation:**
- `SignalBadge.tsx` and `CardDetailPage.tsx`: update delta display to `+$X.XX (+YY%)`
- Add `format_delta_display(delta_pct, current_price, baseline_price)` helper in `frontend/src/utils/format.ts`
- Suppression: if `abs(current_price - baseline_price) < 0.50`, show `+$X.XX` only
- Backend: `AssetSignal.price_delta_pct` is already stored; add `price_delta_abs` (absolute dollar) to the signal response schema so the frontend doesn't need to recompute it from prices

**Files:**
- `frontend/src/components/SignalBadge.tsx`
- `frontend/src/pages/CardDetailPage.tsx`
- `frontend/src/utils/format.ts` (new helper)
- `backend/app/api/routes/signals.py` — add `price_delta_abs` to `SignalResponse`
- `backend/app/services/signal_service.py` — compute and pass `price_delta_abs` in sweep output

---

## Competitive Moat Summary

After this roadmap, Flashcard Planet will be the only TCG platform that offers:
1. Momentum-classified signals (BREAKOUT/MOVE/WATCH/IDLE) across 3 games
2. Natural language AI explanation of signal causes
3. Japanese lead-signal detection with 4–8 week advance warning
4. Discord slash command interface for signal queries
5. Deep AI analysis (drivers + thesis + risks + hold/wait/exit guidance)
6. Proactive opportunity discovery (surfaces cards the user didn't know to watch)

No existing competitor offers items 1–6 simultaneously. Items 2–6 are each individually absent across all 15+ platforms reviewed.

---

## Files to Modify by Phase

### Phase 1
- `backend/app/models/user.py` — subscription columns
- `backend/app/services/upgrade_service.py` — real checkout URL
- `backend/app/api/routes/webhooks.py` (new) — LemonSqueezy webhook handler
- `backend/app/core/permissions.py` — 3-tier gate definitions
- `frontend/src/pages/PricingPage.tsx` — 3-tier layout
- `frontend/src/components/ProGate.tsx` — update gate logic for 3 tiers
- `backend/app/backstage/routes.py` — delete stale ingestion-history endpoint, add health_warnings

### Phase 2
- `backend/app/ingestion/onepiece.py` (new)
- `backend/app/backstage/scheduler.py` — onepiece-ingestion job
- `backend/app/services/signal_explainer.py` — extend for Signal/Pro tier split
- `frontend/src/pages/CardDetailPage.tsx` — extend for OPTCG
- `frontend/src/components/AIAnalysisSection.tsx` — wire short vs. full explanation

### Phase 3
- `backend/app/discord_bot/` (new module)
- `backend/app/services/jp_lead_service.py` (new)
- `backend/app/ingestion/pokemon_jp.py` (new, post research spike)
- `backend/app/models/asset_signal.py` — JP_LEAD enum value + full site audit
- `frontend/src/components/GradingROICalculator.tsx` (new)
- `frontend/src/components/NavBar.tsx` — hamburger nav at ≤640px
- `docs/DESIGN.md` (new)

### Phase 4
- `backend/app/api/routes/predict.py` — `/predict/deep` endpoint
- `backend/app/services/sentiment_service.py` (new)
- `backend/app/models/portfolio_entry.py` (new)
- `frontend/src/pages/PortfolioPage.tsx` (new)
- `backend/app/api/routes/api_keys.py` (new) — Pro API access
