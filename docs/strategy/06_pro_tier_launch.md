# Pro Tier Launch — Payment Integration Design Doc

**Status:** Draft — awaiting operator decision on provider and pricing
**Task:** TASK-203
**Date:** 2026-05-02
**Author:** Claude Code
**Operator decision required:** §1 (provider), §3 (trial model), §6 (pricing final)

---

## 1. Payment provider comparison

### Candidates

| | Stripe | LemonSqueezy | Paddle |
|---|---|---|---|
| **Merchant of record** | No (you are) | **Yes** | **Yes** |
| **AU GST compliance** | You handle | They handle | They handle |
| **EU VAT / US sales tax** | You handle | They handle | They handle |
| **Per-transaction fee** | ~2.5–3.5% + 30¢ | **5% + 50¢** | 5% + 50¢ |
| **Subscription billing** | Stripe Billing (add-on) | Built-in | Built-in |
| **Solo-dev friendliness** | Moderate | **High** | Moderate |
| **AU availability** | Yes | Yes | Yes |
| **Webhook reliability** | Excellent | Good | Good |
| **SDK maturity** | Excellent | Good | Good |
| **Ownership risk** | Public co. | Acquired by Stripe 2023 | Independent |

### Recommendation: LemonSqueezy

**Why not Stripe:**
As a solo Australian developer, you are the merchant of record. You must register for GST (if revenue > $75k/yr), collect and remit EU VAT for every EU customer, handle US state sales tax in states where you have "economic nexus." This is 20–40 hours of annual compliance work that has nothing to do with your product. At <100 subscribers, Stripe's lower transaction fee (~2.5% vs 5%) saves at most AUD $15/month — not worth the compliance overhead.

**Why LemonSqueezy:**
- They are the merchant of record — all tax registration, collection, remittance is their problem
- Built for indie SaaS developers exactly at this scale
- Acquired by Stripe in 2023: financial stability, not a startup risk
- Clean REST API + webhooks, Python-friendly
- Setup time: ~2 hours vs ~1 day for Stripe Billing + Stripe Tax

**Revisit Stripe when:**
- Monthly recurring revenue > AUD $5,000 (5% fee becomes meaningful)
- You have a dedicated ops person for tax compliance
- You need Stripe-only integrations (Stripe Radar, Stripe Identity, etc.)

**Decision required:** Confirm LemonSqueezy, or choose alternative.

---

## 2. Schema changes

New columns on `users` table (migration 0030):

```sql
subscription_status      VARCHAR(20)   DEFAULT 'free'
  -- values: 'free' | 'trialing' | 'active' | 'past_due' | 'cancelled' | 'expired'
subscription_provider    VARCHAR(20)   NULLABLE
  -- 'lemonsqueezy' (extensible for future provider migration)
subscription_provider_id VARCHAR(128)  NULLABLE
  -- LemonSqueezy subscription ID (for webhook correlation)
subscription_variant_id  VARCHAR(128)  NULLABLE
  -- LemonSqueezy variant ID (maps to the $12/mo product)
current_period_start     TIMESTAMP     NULLABLE
current_period_end       TIMESTAMP     NULLABLE
  -- when current billing period ends; Pro access valid until this date
trial_ends_at            TIMESTAMP     NULLABLE
  -- null if user never started a trial
cancelled_at             TIMESTAMP     NULLABLE
  -- set when user cancels; access continues until current_period_end
```

**`access_tier` relationship:**
`access_tier` remains the authoritative field for permission checks (it's what `Feature` enum reads). The new subscription columns are the source of truth for billing state. A background job (or webhook handler) syncs `subscription_status → access_tier`:

| subscription_status | access_tier |
|---|---|
| free | free |
| trialing | pro |
| active | pro |
| past_due | pro (grace period: 7 days, then free) |
| cancelled | pro (until period_end, then free) |
| expired | free |

---

## 3. Free trial strategy

**Decision required — three options:**

**Option A — Card-required 7-day trial (standard SaaS)**
User enters credit card → 7-day trial → auto-charges on day 8.
- Pros: Higher conversion rate (friction filters tire-kickers), immediate revenue pipeline
- Cons: Friction barrier for new users with zero brand trust; may lose 60–70% of potential trialists

**Option B — Card-not-required 7-day trial (recommended for launch)**
User registers with email → gets Pro access for 7 days automatically → conversion email on day 5 → "Enter payment to keep Pro" on day 7.
- Pros: Maximum trial top-of-funnel; removes "I don't know if this is worth it" objection
- Cons: Some users will trial and leave; conversion rate lower per trialist but higher in absolute terms

**Option C — Waitlist-to-trial**
Waitlist subscribers (TASK-302) get a "Pro is live — your 7-day trial starts now" email on launch day. No card required for trial; card required after.
- Pros: Launch day has immediate engaged users; waitlist becomes trial pipeline
- Cons: Requires TASK-302 list to be non-trivial size at launch time

**Recommendation:** Option B for general users + Option C for waitlist on launch day. These compose naturally — waitlist gets an email, regular visitors get Option B.

**Implementation note:** Trial start is recorded in `trial_ends_at = NOW() + 7 days`. Access check: `can(user, Feature.X)` already reads `access_tier`. No new permission logic needed — just set `access_tier = 'pro'` and `subscription_status = 'trialing'` on trial start.

---

## 4. Webhook handling (LemonSqueezy)

All webhooks POST to `POST /api/v1/webhooks/lemonsqueezy`. Verified via HMAC signature (`X-Signature` header, secret stored as `LEMONSQUEEZY_WEBHOOK_SECRET` env var).

| Event | Action |
|---|---|
| `subscription_created` | Create/update subscription fields, set `trialing` or `active`, sync `access_tier = 'pro'` |
| `subscription_updated` | Update `current_period_end`, status, variant |
| `subscription_cancelled` | Set `cancelled_at`; keep `access_tier = 'pro'` until `current_period_end` |
| `subscription_expired` | Set `subscription_status = 'expired'`, `access_tier = 'free'` |
| `subscription_payment_failed` | Set `subscription_status = 'past_due'`; send alert email; grace period 7 days |
| `subscription_payment_success` | Set `subscription_status = 'active'`, update `current_period_end` |
| `subscription_resumed` | Re-activate if previously cancelled within same period |

**Idempotency:** Each webhook handler checks `subscription_provider_id` before writing. Re-delivered webhooks must be safe to process twice.

**Failure handling:** If webhook processing fails (DB error, etc.), return HTTP 500 so LemonSqueezy retries. Log all webhook events to a `webhook_log` table (future migration) for audit.

---

## 5. `/pricing` page implementation

**Route:** `/pricing`
**File:** `frontend/src/pages/PricingPage.tsx`
**Router:** Add to `frontend/src/main.tsx` (or wherever React Router routes are defined)

**Page structure:**
1. Hero: "Simple pricing. Cancel anytime."
2. Free / Pro comparison table (from `docs/strategy/03_pricing_page_copy.md`)
3. FAQ: "Is there a free trial?", "What happens if I cancel?", "What currencies do you accept?"
4. CTA: "Start 7-day free trial →" → registration flow
5. For logged-in users already on free: "Upgrade to Pro →" → LemonSqueezy checkout overlay

**Checkout flow:**
- LemonSqueezy provides a hosted checkout page or an embeddable overlay
- Recommended: overlay (keeps users in-app, better conversion)
- Pass `checkout[custom][user_id]` so the webhook can correlate the subscription to the correct user

**i18n:** English first. Chinese in TASK-305.

---

## 6. CTA placement (5 points from `03_pricing_page_copy.md`)

| Location | Trigger | CTA text |
|---|---|---|
| Card Detail — AI Analysis panel | User is Free | "Unlock AI Analysis — Pro" (already exists as ProGate) |
| Signals feed | Beyond top-5 results | "See all signals — upgrade to Pro" |
| Watchlist | At FREE_WATCHLIST_LIMIT | "Add more cards — upgrade to Pro" |
| Alert setup | At FREE_ALERT_LIMIT | "Set unlimited alerts — upgrade to Pro" |
| Navigation bar | Always (subtle) | "Pro" badge → `/pricing` |

All 5 use existing `ProGate` macro and `Feature` enum. No new permission logic needed.

---

## 7. Refund and cancellation

**Policy:** 14-day money-back guarantee, no questions asked.

**Process (manual initially):**
1. User emails hello@flashcardplanet.com
2. Operator issues refund via LemonSqueezy dashboard (< 5 min)
3. Webhook `subscription_cancelled` fires → `access_tier` downgraded immediately for refunds (vs end-of-period for regular cancellations)

**When to automate:** When monthly refund requests > 5/month (i.e., meaningful support load). Until then, manual is faster to ship.

**Cancellation (non-refund):**
- User cancels → `cancelled_at` set → access continues until `current_period_end` → downgraded to free
- "Resume" before period_end is possible (LemonSqueezy supports this)

---

## 8. "What if I stop paying?"

| Timeframe | State |
|---|---|
| Cancellation to period_end | Pro access continues (paid for it) |
| At period_end | `access_tier = 'free'` immediately |
| Days 1–90 after downgrade | Watchlist, alerts, history data retained |
| Day 91+ | Non-essential data (alert history > free tier limit) pruned |
| Price history | Never deleted — it's asset-level, not user-specific |
| Resubscription | Full Pro access restored instantly; retained data re-accessible |

**User-facing copy:** "Your data is safe. If you resubscribe within 90 days, everything is exactly where you left it."

---

## 9. Implementation sequence (once operator approves)

TASK-301 should follow this order to reduce risk:

1. **Migration 0030** — add subscription columns to users (backward-compatible, all nullable)
2. **LemonSqueezy account setup** — create product/variant, configure webhook endpoint
3. **Webhook handler** — `POST /api/v1/webhooks/lemonsqueezy` + HMAC verification
4. **Trial activation endpoint** — `POST /api/v1/trial/start` (sets trialing status, no payment)
5. **`/pricing` page** — static page linking to LemonSqueezy checkout
6. **5 CTA placements** — wire ProGate components to `/pricing`
7. **Email flows** — trial welcome (day 0), conversion nudge (day 5), expiry warning (day 7)
8. **End-to-end test** — operator's own card, full subscribe → cancel → refund cycle
9. **Waitlist blast** — email TASK-302 list with "Pro is live + your free trial link"

**Estimated total:** 2–3 weeks part-time (M effort per BACKLOG). XL was likely an overestimate given the existing `permissions.py` and `access_tier` infrastructure already in place.

---

## 10. Open questions for operator

1. **Provider:** LemonSqueezy confirmed, or reconsider?
2. **Pricing:** $12/mo AUD or USD? Launch promo $9/mo for first 100 — confirm?
3. **Trial model:** Card-not-required (Option B) confirmed?
4. **Refund window:** 14 days confirmed?
5. **Data retention:** 90-day grace period confirmed?
6. **Launch sequence:** Waitlist blast on same day as launch, or soft-launch waitlist first?

**Once all 6 are answered, TASK-301 can start.**
