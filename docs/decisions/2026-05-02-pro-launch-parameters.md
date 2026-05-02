# ADR: Pro Tier Launch Parameters

**Date:** 2026-05-02
**Status:** Decided
**Context:** TASK-203 design doc produced options; operator reviewed and confirmed all 6 decisions below.
**Reference:** `docs/strategy/06_pro_tier_launch.md`

---

## Decision 1 — Payment provider: LemonSqueezy

**Chosen:** LemonSqueezy

**Options considered:** Stripe, LemonSqueezy, Paddle

**Rationale:**
LemonSqueezy is merchant of record. They handle AU GST, EU VAT, and US sales tax on our behalf. For a solo Australian operator with an international buyer base, the alternative (Stripe) requires self-managed tax registration in every relevant jurisdiction — 20–40 hours/year of compliance work.

Cost trade-off at launch scale: 5% + $0.50 (LS) vs ~2.9% + $0.30 (Stripe) on a $12 transaction = ~$0.30 extra per subscriber per month. At 100 subscribers: $30/month. This is far less than the cost of DIY tax compliance.

**Re-evaluate when:** MRR exceeds $5,000 USD/month. At that scale the 5% fee represents ~$250/month in extra costs — large enough to justify the compliance overhead of switching to Stripe.

---

## Decision 2 — Pricing: USD $12/month standard, USD $9/month Founders

**Chosen:** USD pricing. Standard $12/mo. Founders $9/mo (lifetime lock-in, first 100 subscribers).

**USD not AUD because:**
- Target market is international (US / EU / Asia TCG collectors, 80%+ of addressable market)
- USD pricing is the international SaaS standard; non-AU users expect it
- AU users are already accustomed to USD pricing for SaaS tools
- AUD pricing signals "local product" and creates currency confusion for international buyers
- LemonSqueezy auto-localises display currency while billing in USD — no manual work needed

**Founders pricing mechanics:**
- $9/mo is lifetime lock-in, not a temporary discount. Early adopters keep $9 forever.
- Implemented as a separate LemonSqueezy product variant "Founders" with 100 coupon codes
- Once 100 codes are issued, variant is closed; standard $12/mo applies
- This creates genuine launch urgency without false scarcity

**Re-evaluate when:** Significant AU-specific user base emerges AND AU users report pricing confusion. Current assumption: this won't happen.

---

## Decision 3 — Free trial: card-not-required 7-day (Option B)

**Chosen:** Option B — 7-day free trial, no credit card required, auto-downgrade to Free on day 8.

**Rationale:**
At zero brand trust (new product, no reviews, no social proof), card-required trials see <2% conversion. Card-not-required trials see 8–15% conversion in comparable SaaS. The "dirty data" risk (trial users with no intent to pay) is acceptable — our marginal cost per trial user is near zero (no per-seat infrastructure costs).

**LemonSqueezy implementation note:** "Free trial without payment method" must be explicitly enabled in the LS dashboard. It is NOT the default.

**Critical retention mechanic:** Send a conversion email 24 hours before trial expiry: "Your Pro trial ends tomorrow — add a payment method to keep access." This single email drives the majority of trial-to-paid conversions. Must be implemented before launch.

**Trial flow:**
1. User registers (magic link or Google OAuth)
2. `subscription_status = 'trialing'`, `trial_ends_at = NOW() + 7 days`, `access_tier = 'pro'`
3. Day 6: conversion email sent
4. Day 7 end: auto-downgrade to `access_tier = 'free'` if no payment method added

**Re-evaluate when:** Trial-to-paid conversion rate is known after 30 days live. If <5%, reconsider requiring card. If >15%, keep as-is.

---

## Decision 4 — Refund window: 14 days, fully automated (self-service)

**Chosen:** 14-day money-back guarantee. Self-service via LemonSqueezy. No manual approval required.

**Rationale:**
- 14 days: longer than 7 (builds purchase trust), shorter than 30 (prevents month-long "trial by refund" abuse)
- Self-service: solo operator cannot afford 5–10 minutes per refund at scale. LS fraud detection handles abuse cases. Automated refunds lower perceived risk → higher conversion rate
- The revenue impact of a generous refund policy is smaller than the conversion uplift from removing purchase risk

**Re-evaluate when:** Refund rate exceeds 15% of monthly subscribers for 2+ consecutive months. At that point investigate root cause (product-market fit issue) rather than tightening the policy.

---

## Decision 5 — Data retention: 90-day grace period after downgrade

**Chosen:** 90-day grace period. Clear split between what is retained vs immediately lost.

**Retained for 90 days (user expects to recover on resubscription):**
- Watchlist card list
- Alert configurations (rules, thresholds)
- Any user-generated notes or tags

**Lost immediately on downgrade (live/computed data — no expectation of retention):**
- AI Analysis panel output (recomputed on next Pro visit)
- Cross-TCG signal feed (live data, no point storing stale version)
- Pro-only signal history beyond 7-day free window

**Hard delete at day 91:** Daily cleanup job (7th scheduler job). Must follow the same `scheduler_run_log` instrumentation pattern as all other jobs (write run log entry, Discord alert on zero-output).

**User-facing copy:** "Your data is safe. If you resubscribe within 90 days, your watchlist and alert configurations are exactly where you left it."

**Re-evaluate when:** GDPR/privacy audit flags different requirements. Current assumption: 90-day retention is compliant for the data types listed.

---

## Decision 6 — Launch sequence: waitlist-first 48 hours, then public

**Chosen:** Two-phase launch.

**Phase 1 (Day 0–2): Waitlist-exclusive access**
- Email subject: "You're in. Founders pricing locked."
- Waitlist subscribers receive Founders coupon codes ($9/mo lifetime)
- 48-hour window for waitlist to claim promo spots before public launch
- Serves as soft-launch / bug-catching buffer at low traffic volume

**Phase 2 (Day 3+): Public launch**
- Open registration + standard pricing page live
- Remaining Founders promo codes still available (creates urgency: "still some left at $9")
- Standard $12/mo pricing in effect in parallel
- Distribution: TCG community channels (r/PokemonTCG, r/yugioh, relevant Discord servers)

**Why not simultaneous:**
Waitlist users waited weeks/months. A 48-hour head start on Founders pricing is the cheapest possible loyalty investment. It also lets us catch Day 0 bugs at low traffic before Phase 2 load spike (which is typically 5–10x Phase 1 volume).

**Why not waitlist-only extended:**
If the waitlist is small at launch (possible — TASK-302 was just shipped), holding Phase 2 for a week wastes launch momentum. Public channels are the actual growth engine.

**Re-evaluate if:** Waitlist size at launch time exceeds 500 users. At that scale, Phase 1 is itself a meaningful launch and Phase 2 timing can be adjusted.

---

## Summary table

| Decision | Chosen | Re-evaluate trigger |
|---|---|---|
| Payment provider | LemonSqueezy (MoR) | MRR > $5K USD/month |
| Currency | USD | AU-specific user base emerges |
| Standard price | $12 USD/month | Market data after 60 days live |
| Founders price | $9 USD/month, lifetime, 100 slots | N/A — one-time launch mechanic |
| Free trial | 7-day, no card required | Conversion rate <5% after 30 days |
| Refund window | 14 days, self-service | Refund rate >15% for 2+ months |
| Data retention | 90-day grace period | GDPR audit |
| Launch sequence | Waitlist 48h → public | Waitlist size >500 at launch |
