# Flashcard Planet — Phase 1 Enterprise Rebuild Spec

**Date:** 2026-05-13
**Author:** Strategy/architecture handoff from claude.ai → Claude Code execution
**Status:** Approved by Ivan; ready for execution
**Filename suggested in repo:** `.claude/specs/2026-05-13-phase-1-enterprise-rebuild.md`

---

## 0. North Star

### 0.1 The single sentence the entire build serves

> **Flashcard Planet is the founder-led, signal-first, multi-TCG intelligence platform that makes serious card investing legible — and feels like the cards themselves.**

Every component, every animation, every line of copy, every backend decision in this spec flows downstream from this sentence. When in doubt, return to it.

### 0.2 The four-reference visual formula

This product borrows from four distinct visual lineages, in roughly this proportion:

- **40% TradingView** — financial density, mono numbers, chart-as-protagonist, restrained palette where green/red/amber carry *meaning* not decoration
- **30% Linear.app** — craft, speed, micro-interaction polish, keyboard shortcuts, command palette, consistent radii, the feeling of a tool built by people who care
- **20% Cursor.com** — founder voice, editorial confidence, thesis-led landing page, code/data shown as the hero, no marketing-team boilerplate
- **10% MTG Arena / Hearthstone** — card reverence, 3D tilt on hover, real holo shimmer, signal-event animations, optional sound design, the joy moments

When implementing any new surface, hold these proportions in mind. Pure TradingView reads cold. Pure MTG Arena reads toy. The synthesis is what makes the product distinctive.

### 0.3 The unbreakable principle: *idle is still*

> Joy moments must be earned by user action, never pushed at idle.
>
> The user hovers a card → tilt activates. The user clicks → reveal animation. The user gets a signal → pulse and glow. The user opens the app and stares at the dashboard for ten seconds → *nothing wiggles, nothing animates, nothing demands attention.* The UI is at rest.
>
> **Idle = stillness. Action = joy. Always.**

This is what separates a premium tool from a slot machine. Slot machines wiggle at idle to keep you engaged; premium tools sit still until you choose to interact. We are the second.

### 0.4 The serious-to-fun ratio per surface

| Surface | Serious % | Fun % |
|---|---|---|
| Navigation, auth, billing | 100 | 0 |
| Data tables, filters, settings | 95 | 5 |
| Card grid (the workhorse) | 70 | 30 |
| Card detail page | 50 | 50 |
| Signal event / alert moment | 20 | 80 |
| Landing page | 60 | 40 |
| Onboarding first-time flow | 40 | 60 |

The chrome stays steady. The cards bring the energy.

### 0.5 The trust killer list — explicitly forbidden

Claude Code must reject any pattern from this list, even if asked. These are non-negotiable. If a future request appears to require one of these, surface the conflict rather than complying.

- No confetti, ever (Mailchimp-tier cliché, also uncomfortable on outcomes-with-losers)
- No custom cursors of any kind
- No mascot or cartoon character anywhere
- No "You did it!" celebratory modals for ordinary actions
- No skeumorphic card binders, wood-grain backgrounds, or fantasy-game UI chrome
- No emoji in the application chrome (nav, buttons, headers, labels)
- No more than one sound playing simultaneously
- No tilt, holo, or hover effects on data tables — cards tilt, rows don't
- No Comic Sans, no "playful" rounded display fonts, no children's-product typography
- No animated gradients on the application chrome (acceptable on landing page hero only)
- No idle animations on the dashboard — see 0.3
- No "Built for serious collectors"-tier generic SaaS copy anywhere
- No four-card emoji feature grids
- No floating Pokéball, no card-suit decorations, no Pokémon-fan-site aesthetic
- No purple-gradient-on-white anything (the universal generic-AI-template tell)

### 0.6 How Claude Code should use this spec

1. **Read sections 0, 1, and 2 in full before starting any PR.** These are the foundation everything else inherits.
2. **For each PR, read the corresponding subsection in section 3 in full.** Each PR section is self-contained.
3. **Follow the PR order.** Some PRs depend on earlier ones (Tailwind migration must precede shadcn adoption, backups must precede everything user-facing).
4. **Every PR ships with `## Codex Review` section** per the project convention. Pre-written prompts are in each PR subsection.
5. **Acceptance criteria are SQL/curl/browser-verifiable.** "Shipped" means the criteria pass in production after Railway/Cloudflare deploy, not when local tests pass. Per project convention: merge ≠ deploy ≠ verified.
6. **If a contradiction or ambiguity appears, stop and ask Ivan via claude.ai.** Do not invent an interpretation.

---

## 1. Design System — The Foundation Everything Inherits

### 1.1 Brand identity

- **Product name (English):** Flashcard Planet
- **Product name (中文):** 闪卡星球 (used as a bilingual subtitle in the logo, full bilingual UI per 1.8)
- **Wordmark:** "Flashcard Planet" in the display face, gold star glyph to the left
- **Tagline (English):** *Market intelligence for every TCG you play.*
- **Tagline (中文):** *为每一款卡牌游戏提供市场情报。*
- **Founder presence:** The landing page carries a thesis paragraph written in Ivan's voice (drafted by Ivan, polished by Claude Code; final copy approved by Ivan). His name and a one-line bio appear in the footer and on a `/about` page.

### 1.2 Color tokens

All colors live as CSS custom properties on `:root`, then exposed through the Tailwind config so both raw CSS and Tailwind utilities reference the same source. Defined in `frontend/src/styles/tokens.css` (new file, supersedes current `theme.css` color section).

```css
:root {
  /* Backgrounds — near-black, Linear-style, four-step elevation */
  --bg-base:     #0a0a0c;  /* page background */
  --bg-surface:  #111114;  /* cards, panels */
  --bg-elevated: #16161a;  /* hover, dropdowns */
  --bg-floating: #1c1c22;  /* modals, popovers */

  /* Borders */
  --border-subtle: rgba(255, 255, 255, 0.05);
  --border-default: rgba(255, 255, 255, 0.10);
  --border-strong: rgba(255, 255, 255, 0.18);

  /* Text — must pass WCAG AA on bg-base */
  --text-primary:   #f4f4f6;  /* contrast 17.5:1 */
  --text-secondary: #a1a1aa;  /* contrast 7.8:1 */
  --text-muted:     #71717a;  /* contrast 4.6:1 — passes AA for normal text */
  --text-disabled:  #52525b;
  --text-inverse:   #0a0a0c;

  /* Brand accent — single accent, used sparingly */
  --gold:        #f0b429;
  --gold-hover:  #f5c030;
  --gold-dim:    rgba(240, 180, 41, 0.25);
  --gold-glow:   rgba(240, 180, 41, 0.12);

  /* Signal palette — meaning-bearing, never decorative */
  --surge:    #22c55e;  /* was BREAKOUT */
  --drift:    #f59e0b;  /* was MOVE */
  --stir:     #fb923c;  /* was WATCH */
  --flat:     #71717a;  /* was IDLE */
  --cooling:  #a78bfa;  /* new — post-spike fade signal, see PR #17 backend */
  --nodata:   #3f3f46;  /* INSUFFICIENT_DATA */

  /* Signal background tints (10% alpha) for row glows */
  --surge-bg:   rgba(34, 197, 94, 0.10);
  --drift-bg:   rgba(245, 158, 11, 0.10);
  --stir-bg:    rgba(251, 146, 60, 0.10);
  --flat-bg:    transparent;
  --cooling-bg: rgba(167, 139, 250, 0.10);

  /* Numerical states */
  --price-up:   var(--surge);
  --price-down: #ef4444;

  /* Radii — Linear-style: 6, 8, 12, 16 */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-pill: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.5);
  --shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.6);
  --shadow-gold: 0 0 24px rgba(240, 180, 41, 0.18);
}
```

**Color usage rules:**

- Gold is reserved for: primary CTAs, brand wordmark, the watchlist star when active. Nothing else.
- Signal colors only appear on signal-related UI (badges, borders, sparklines that represent a signal-flagged card). Never as decoration.
- Green/red appear on price changes only. Never on success/error messages — use the elevated background + an icon for those.
- The card art is the most colorful element on any screen — everything around it should be near-monochrome to let it breathe.

### 1.3 Typography

Three faces, each with a job. No more, no less.

- **Display:** **Geist** (free, used by Vercel, distinctive without being trendy). Used for headlines, page titles, brand wordmark. Sizes 24–72px.
- **Body / UI:** **Inter** (free, ubiquitous, but excellent at small sizes and supports both Latin and CJK reasonably). Used for all UI text 11–22px.
- **Mono:** **JetBrains Mono** (free, distinctive over generic monospace). Used for **every number that represents data** — prices, percentages, deltas, sample sizes, counts, confidence scores, timestamps. This single rule does more for "feels like a financial product" than any other.

**Why these three together:** Geist + Inter + JetBrains Mono is the modern fintech/dev-tool stack (Vercel, Linear, Cursor variants all use combinations of these). It signals "current" without being faddish.

**Chinese typography:** Use **Noto Sans SC** for Simplified Chinese body text, **Noto Serif SC** for any Chinese display use. The bilingual UI must render Chinese with identical visual weight to English — no smaller, no muted, no afterthought treatment.

**Type scale (8pt-based):**

```
--font-display: 'Geist', system-ui, sans-serif;
--font-body:    'Inter', 'Noto Sans SC', system-ui, sans-serif;
--font-mono:    'JetBrains Mono', ui-monospace, monospace;

--text-2xs: 10px;   /* badges, eyebrow labels */
--text-xs:  11px;   /* secondary metadata */
--text-sm:  12px;   /* compact UI */
--text-base: 13px;  /* primary UI (smaller than web norm — financial density) */
--text-md:  14px;   /* primary body text */
--text-lg:  16px;   /* emphasis */
--text-xl:  20px;   /* small headlines */
--text-2xl: 24px;   /* section headers */
--text-3xl: 32px;   /* page titles */
--text-display: 48px; /* landing page headlines */
--text-hero: 72px;  /* landing page hero only */
```

**Mono numerical formatting:** All numbers use `font-variant-numeric: tabular-nums` so digits align in tables and on price tickers. This is non-negotiable for the financial feel.

**Line-height:** 1.5 for body, 1.2 for display, 1.4 for UI controls. Tight enough to feel dense, loose enough to read.

### 1.4 Spacing & layout

8px base grid. All spacing values are multiples of 4 or 8.

```
--space-1:  4px;
--space-2:  8px;
--space-3:  12px;
--space-4:  16px;
--space-5:  20px;
--space-6:  24px;
--space-8:  32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
--space-20: 80px;
--space-24: 96px;
```

**Container widths:**
- Marketing/landing: max-width 1280px, padded 24px on mobile, 48px on desktop
- App content: max-width 1440px (more density for serious-tool feel), padded 16px on mobile, 32px on desktop
- Card detail: max-width 1200px (focused reading)

**Nav height:** 56px on desktop, 52px on mobile.

**Card grid:** `repeat(auto-fill, minmax(340px, 1fr))` with `gap: 16px`. On mobile <640px collapse to single column with reduced padding.

### 1.5 Motion system

Motion lives in `frontend/src/styles/motion.css` as named durations and easing curves, and is referenced by name everywhere (no magic numbers in components).

```css
:root {
  /* Durations */
  --motion-instant: 80ms;   /* taps, button presses */
  --motion-fast:    150ms;  /* hover, focus, color changes */
  --motion-normal:  250ms;  /* page transitions, modal entrance */
  --motion-slow:    400ms;  /* signal-event entrance, holo activate */
  --motion-deliberate: 600ms; /* one-time celebrations (first-flip) */

  /* Easing curves — Linear-style */
  --ease-out:     cubic-bezier(0.22, 1, 0.36, 1);    /* default for entrances */
  --ease-in-out:  cubic-bezier(0.65, 0, 0.35, 1);    /* page transitions */
  --ease-snap:    cubic-bezier(0.34, 1.56, 0.64, 1); /* pop/bounce on tap */
  --ease-linear:  linear; /* the ticker only */
}
```

**Motion rules:**

1. **Default duration is `--motion-fast` (150ms).** If you need longer, justify it.
2. **`prefers-reduced-motion` is fully honored.** Every animation longer than 80ms has a reduced-motion fallback (usually opacity-only or no animation).
3. **Transform and opacity only.** No animating width/height/top/left — performance killers.
4. **Entrance is `--ease-out`; exit is `--ease-in-out`.** This is the Linear convention and it feels right.
5. **No looping animations on idle UI.** See 0.3.

**The Library:** Use **Motion** (formerly Framer Motion, package name `motion/react`). Install once; use everywhere in React. CSS keyframes only for tiny things (badge entrance, shimmer on skeleton loaders).

### 1.6 Sound system

Sound is **off by default**, opt-in via Settings → Preferences. Once enabled, only specific events play sounds. All sound files live in `frontend/public/sounds/` and are <30KB each.

**Sound events (and only these):**

| Event | File | Loudness | Description |
|---|---|---|---|
| Signal becomes SURGE on a watched card | `signal-surge.mp3` | -6 LUFS | Soft bell, rising tone, 600ms |
| Signal becomes COOLING on a watched card | `signal-cooling.mp3` | -8 LUFS | Soft descending chord, 800ms |
| Watchlist add | `watchlist-add.mp3` | -10 LUFS | Subtle UI click, 80ms |
| Watchlist remove | `watchlist-remove.mp3` | -10 LUFS | Subtle UI click, lower pitch, 80ms |
| Successful login | `auth-success.mp3` | -8 LUFS | Soft chord, 400ms |

**Feature-flagged sounds (off by default even when sound is on, decide after live test):**

| Event | File | Description |
|---|---|---|
| Primary button click | `ui-click.mp3` | Apple-style subtle click |
| Page transition | `ui-transition.mp3` | Gentle whoosh |

**Implementation:** Use the [Howler.js](https://github.com/goldfire/howler.js) library for audio playback with proper preload and error handling. Wrap in a `useSound(eventName)` hook that respects user preferences. Sound files must be commissioned or pulled from a license-permissive library — never use copyrighted audio.

**Source recommendation:** [Pixabay's free SFX](https://pixabay.com/sound-effects/) (CC0) or commission a small custom set for ~$200. Custom is worth it; even ten purpose-made sounds is part of the bargain feeling.

### 1.7 Joy moments catalog

Defines every "earned by user action" animation. Each has a precise trigger, duration, and reduced-motion fallback.

**1. Card hover — 3D tilt + holo shimmer activation**
- Trigger: cursor enters a `<CardArt>` component
- Effect: subtle 3D rotateX/rotateY based on cursor position (max ±8°), holo gradient overlay tracks cursor position
- Duration: tilt follows cursor in real time, deactivates with `--motion-fast` ease-out
- Rarity gate: full holo treatment only on cards with `rarity` in `['Rare Holo', 'Ultra Rare', 'Secret Rare']`. Common/uncommon cards get tilt only, no holo overlay.
- Reduced motion: no tilt, no shimmer. Static card with a 1px gold border on hover instead.
- Library: cherry-pick from `https://poke-holo.simey.me/` (the viral CSS-only Pokémon holo effect; license MIT)

**2. Card click — reveal animation**
- Trigger: user clicks card in grid → navigates to `/market/:id`
- Effect: card scales up from its grid position to the detail page slot using FLIP technique (First-Last-Invert-Play)
- Duration: `--motion-normal` (250ms), `--ease-out`
- Reduced motion: instant transition

**3. Number tick on price change**
- Trigger: SSE receives a price update for a visible card
- Effect: old number fades down 4px while new number fades up 4px; brief color flash (green if up, red if down) over 600ms
- Library: a simple custom hook or [`react-countup`](https://github.com/glennreyes/react-countup)
- Reduced motion: number swap without animation, color flash only

**4. Signal badge entrance**
- Trigger: a card's signal changes from `FLAT` to anything else
- Effect: badge scales from 0.8 → 1.0 with opacity 0 → 1, brief glow halo using the signal color
- Duration: `--motion-slow` (400ms), `--ease-snap`
- Reduced motion: instant appearance, no glow

**5. Watchlist star pop**
- Trigger: user clicks the watchlist star
- Effect: scale 1.0 → 1.3 → 1.0 over 200ms, soft particle burst (3-5 small gold dots) outward, fading
- Sound: `watchlist-add` if enabled
- Reduced motion: scale only, no particles

**6. Empty state copy**
Not animations, but inseparable from joy moments. Every empty state gets character. Examples:
- Alerts empty: *"Quiet on the market. We'll let you know when it isn't."*
- Watchlist empty: *"Track a card to see it move."*
- No data on chart: *"Not enough sales yet. Come back when the market has spoken."*

These get **bilingual treatment** — natural, idiomatic Chinese, not machine translation.

**7. First-flip celebration (one-time, lifetime)**
- Trigger: the first time a card in a user's watchlist enters SURGE state, ever
- Effect: brief full-screen overlay (not modal) with the card art enlarged, the SURGE badge animated in, and text: *"Your first signal. This is why you're here."* / *"你的第一个信号。这就是你来的原因。"*
- Includes a "Got it" dismiss button
- Logged in `user_milestones` table (new) so it never fires twice
- Duration: persistent until dismissed; particle effects active for 2 seconds then settle
- Sound: `signal-surge` if enabled
- Reduced motion: simpler overlay, no particles

### 1.8 i18n setup

Locked: fully bilingual UI (English + Simplified Chinese) from day one.

**Library:** `react-i18next` + `i18next` + `i18next-browser-languagedetector`.

**File layout:**
```
frontend/src/i18n/
  index.ts                       — config, init
  locales/
    en/
      common.json                — nav, buttons, generic
      market.json                — dashboard, card grid
      card-detail.json
      alerts.json
      landing.json
      onboarding.json
      empty-states.json
      errors.json
      signals.json               — signal names, descriptions
    zh-CN/
      [same set, fully translated]
```

**Conventions:**
- Every string in the codebase goes through `t('namespace.key')`. **No hardcoded English in component files** (acceptance criterion).
- Plural and interpolation handled via i18next's native syntax.
- Number formatting uses `Intl.NumberFormat` with locale awareness — Chinese users see numbers grouped per Chinese convention (10000 = 1万 in some contexts; for prices stay with conventional grouping).
- Currency stays USD for now (TCG market is dollar-denominated), but format respects locale conventions.
- Locale detection: browser preference first, user override stored in `users.preferred_locale` column (new), persists across devices on auth.
- Locale toggle: in the nav as a `EN / 中文` switcher (small, secondary).

**Translation quality bar:** Chinese strings must be reviewed by a native speaker before release. Machine translation is acceptable as a placeholder during development but **never in a shipped release**. Ivan is bilingual per the project context, so he reviews. If a string in production reads as machine-translated to him, it's a bug.

### 1.9 Tone of voice

Both languages share the same tone. Adapt the principles, not transliterate.

- **Direct, not chirpy.** *"Price dropped 18% in 24h."* not *"Whoa! 📉 Big move alert!"*
- **Confident, not hedged.** *"This signal fires when..."* not *"This signal generally tends to..."*
- **Specific, not generic.** *"23 sales in the last 24h, 4x baseline volume"* not *"High recent activity"*
- **Plain, not jargon-heavy.** *"How much money moved through this card"* not *"Notional volume traded"*
- **No exclamation marks in UI strings.** Exclamations belong on the landing page in moderation, and in celebration overlays only.

**Founder voice — the landing page.** This is the one place where personality is louder. Drafted by Ivan, polished by Claude Code, approved by Ivan. The tagline, the thesis paragraph, the "Why this exists" section all carry first-person plural ("we") or singular ("I") voice. See PR #19 for the brief.

---

## 2. Stack & Infrastructure

### 2.1 Frontend stack (locked)

| Layer | Choice | Why |
|---|---|---|
| Framework | Vite + React 18 + TypeScript | Already in place, keep |
| Styling | **Tailwind CSS 3** | Required for shadcn/ui; replaces current raw CSS approach |
| Components | **shadcn/ui** (copy-paste, owned) | Industry-standard for serious SaaS in 2026 |
| Animations | **Motion** (formerly Framer Motion) | What Magic UI/Aceternity build on |
| Animated landing components | **Aceternity UI + Magic UI** (sparingly, landing only) | The "wow" components |
| Icons | **Lucide React** | 1500+ icons, consistent 1.5px stroke, tree-shakeable |
| Data fetching | **TanStack Query v5** | Cache, refetch, background sync, optimistic updates |
| Data grid | **TanStack Table v8 + TanStack Virtual** | Scales to 50K+ rows, headless, owned UI |
| Financial charts | **TradingView Lightweight Charts** | Bloomberg-grade, 45KB, free with attribution |
| Toasts | **Sonner** | Quiet, premium, used by Vercel/Linear |
| Drawer | **Vaul** | Same author as Sonner, mobile-native feel |
| Command palette | **cmdk** | Cmd+K, used by Linear/Vercel/Notion |
| Routing | React Router v6 | Already in place, keep |
| Forms | **React Hook Form + Zod** | Industry standard, type-safe |
| Sound | **Howler.js** | Reliable, small, mobile-friendly |
| Holo effect | Adapted from `poke-holo.simey.me` (MIT) | Don't reinvent the viral one |
| i18n | **react-i18next** | Locked per section 1.8 |
| Date/time | **date-fns** (not Moment) | Tree-shakeable, modern |
| Analytics | **PostHog** | Open source, self-hostable option, generous free tier |
| Error tracking | **Sentry** | Free tier 5K errors/month, industry standard |

**The Tailwind migration is gate #1.** Until `theme.css` tokens are migrated to `tailwind.config.ts` and the existing CSS classes are replaced with utility classes (or moved to shadcn primitives), no further frontend work happens.

### 2.2 Backend stack (extended)

| Addition | Purpose |
|---|---|
| **`slowapi`** | Rate limiting per endpoint, per-user, per-IP |
| **PgBouncer** (Railway addon or standalone) | Connection pooling — critical for 100K users |
| **`pg_dump` → Cloudflare R2** (cron) | Daily backups, retain 30 days hot + monthly archive |
| **`sse-starlette`** | Server-Sent Events for real-time signal feed |
| **`structlog`** + JSON logging | Replace ad-hoc `logger.warning(json.dumps(...))` pattern |
| **`alembic` migrations** | Already in use, continue strictly |
| **`pytest-asyncio`** | Test SSE + async paths properly |
| **`prometheus-fastapi-instrumentator`** | Metrics export for future monitoring |

### 2.3 Infrastructure

**Frontend hosting: Cloudflare Pages**
- Connect to GitHub, auto-deploy on push to main
- Global edge cache, free tier handles 100K users easily
- Free SSL, free DDOS protection
- Build command: `npm run build`, output `dist/`
- Custom domain: `flashcardplanet.com` (apex) and `www`

**Backend hosting: Railway (current)** — stays for phase 1, plan to revisit at 50K MAU.

**Backups: Cloudflare R2**
- 10GB free tier, $0.015/GB/month after
- Daily pg_dump uploaded as `flashcard-planet/backups/YYYY-MM-DD.dump.gz`
- 30 days hot retention, lifecycle policy archives older to infrequent access tier
- Monthly archive copies kept indefinitely until 1 year (then manually pruned)
- Restore tested quarterly — see PR #14 acceptance criteria

**DNS: Cloudflare** (already gives you DDOS protection at the edge for free)

**Observability stack:**
- **Sentry** for errors (frontend + backend, same project, separate environments)
- **PostHog** for product analytics, session replay (off by default, opt-in for support), feature flags
- **Status page** at `status.flashcardplanet.com` — Uptime Kuma self-hosted on Railway, ~$3/month

---

## 3. The PR Sequence

The order matters. Some PRs unlock others. Don't reorder without consulting Ivan.

| PR | Goal | Est. days | Depends on |
|---|---|---|---|
| #13 | Critical bug fixes (the four issues from screenshots) | 1–2 | — |
| #14 | Backend foundation: backups, PgBouncer, rate limiting, observability | 2–3 | — |
| #15 | Frontend foundation: Tailwind + shadcn + TanStack Query + Lucide + i18n | 3–4 | #13 |
| #16 | Real sparklines + TradingView charts | 2–3 | #15 |
| #17 | Confidence scores + explainability + COOLING signal | 2–3 | #14, #16 |
| #18 | Joy moments + sound system + holo + tilt | 2–3 | #15 |
| #19 | Landing page rebuild (founder-led) | 3–4 | #15, #18 |
| #20 | Onboarding flow + first-flip celebration | 1–2 | #18 |
| #21 | Status page + methodology page + changelog | 1–2 | #15 |
| #22 | SSE real-time + virtualized grid + Cmd+K | 3–4 | #14, #15 |
| #23 | Weekly digest email | 1–2 | #14, #17 |
| #24 | Cloudflare Pages migration + bilingual final polish | 1 | all above |

**Total: ~25–35 focused workdays.** Phase 1 timeline: ~6–8 weeks at sustainable pace, accounting for review cycles, real-life interruptions, and the inevitable "this took longer than expected."

---

### PR #13 — Critical bug fixes

**Goal:** Resolve the four issues identified from production screenshots so the live product isn't visibly broken while the larger rebuild proceeds.

**Scope:**

1. **Star/badge overlap on card grid items.** In `frontend/src/components/CardGrid.tsx`, the absolute-positioned watchlist star (`top: 8; right: 8`) collides with the `<SignalBadge>` in the card header row. Move the star to overlay the `<CardArt>` thumbnail (top-left of the art, with subtle dark scrim behind it for legibility). Keep the badge in the header row.

2. **Ticker bar speed and direction.** In `frontend/src/styles/theme.css`:
   - Change `animation: scroll-ticker 35s linear infinite` to `animation: scroll-ticker 90s linear infinite`
   - **Keep right-to-left direction** (industry standard — Ivan's "left-to-right" request was driven by the ticker being too fast to read; slowing it to 90s resolves the underlying complaint). Add a brief code comment explaining the decision so future Ivan/Claude Code don't relitigate it.
   - Add `@media (prefers-reduced-motion: reduce) { .ticker-inner { animation: none; } }` and render the ticker statically (first 8 items visible, no scroll) when reduced motion is preferred.

3. **Horizontal page scrolling.** Add to `theme.css`:
   ```css
   html, body { overflow-x: hidden; max-width: 100vw; }
   ```
   Then audit and fix root cause: grep for `100vw`, `max-content`, and any `position: absolute` with negative `right:` values. Floating hero cards on landing are the most likely culprit — constrain them to a container with `overflow: hidden`.

4. **Navbar layout — reorder and group.** In `frontend/src/components/NavBar.tsx`:
   ```
   [Logo]    [Market]  [Watchlist (3)]  [Alerts •]              [PRO badge]  [Avatar ▾]
   ```
   - Watchlist before Alerts (Watchlist is the higher-frequency tab)
   - PRO badge moves to right of nav, immediately before avatar
   - Avatar opens a dropdown menu (shadcn `<DropdownMenu>` will be available after PR #15 — for now use a plain div until the foundation lands). Dropdown contains: email, "Account", "Sign out".
   - Sign out is **not** a top-level nav item.

**Files touched:**
- `frontend/src/components/CardGrid.tsx`
- `frontend/src/components/NavBar.tsx`
- `frontend/src/styles/theme.css`

**Acceptance criteria:**
- [ ] No horizontal scrollbar on any page at any viewport width from 320px to 2560px
- [ ] Ticker reads naturally — a user can follow text as it passes
- [ ] Star never overlaps the SignalBadge at any card width
- [ ] Navbar order is: Logo · Market · Watchlist · Alerts · (spacer) · PRO · Avatar
- [ ] `prefers-reduced-motion: reduce` stops the ticker entirely
- [ ] TypeScript build passes (`npx tsc --noEmit`)
- [ ] No new console errors in dev or production builds

**Codex Review prompt:**
```
Review PR #13 for Flashcard Planet. Focus on:
1. Does the star/badge fix prevent ALL overlap states, including on narrow mobile widths (320–375px) and on cards with very long names?
2. Is the ticker direction decision (right-to-left, slowed to 90s) explained in a code comment so it doesn't get re-flipped?
3. Is the horizontal-scroll root cause fixed, or is `overflow-x: hidden` papering over something that will cause clipping bugs later?
4. Does the navbar reorder break any existing tests, link styles, or active-route logic?
5. Does the prefers-reduced-motion fallback render correctly when no animation is playing?
```

---

### PR #14 — Backend foundation (backups first)

**Goal:** Get the backend ready to safely absorb scale and recover from disaster. **No user-facing work proceeds until this PR is shipped and verified.**

**Scope:**

1. **Daily PostgreSQL backups to Cloudflare R2.** This is P0.
   - New script: `scripts/backup_postgres.py` runs `pg_dump --format=custom --compress=9` against `DATABASE_URL`
   - Upload to R2 bucket `flashcard-planet-backups` with key `daily/{YYYY-MM-DD}.dump.gz`
   - Run via APScheduler at 03:30 UTC daily (after bulk-refresh, before signal sweep peaks)
   - Logs each run to `scheduler_run_log` with `job_name='postgres_backup'`
   - On failure, sends Discord alert via existing alert channel
   - **Restore drill documented in `docs/runbooks/restore-from-backup.md`** with concrete commands and a test database name

2. **PgBouncer for connection pooling.**
   - Railway: add PgBouncer plugin if available; otherwise add as a service
   - Configure transaction pool mode, max client connections 1000, default pool size 25
   - Update `DATABASE_URL` env var to point through PgBouncer
   - Verify SQLAlchemy works with transaction-mode pooling (some session features may need adjustment — server-side cursors, prepared statements)

3. **Rate limiting with `slowapi`.**
   - Apply to `/api/v1/web/*` routes
   - Anonymous: 60 requests/minute per IP
   - Authenticated free: 120 requests/minute
   - Authenticated pro: 600 requests/minute
   - Authenticated trader: 1800 requests/minute
   - Return `429` with `Retry-After` header
   - Log rate-limit hits to `audit_log` (new table — see #4 below)

4. **Audit log table.**
   - New table `audit_log` with columns: `id` (uuid), `user_id` (nullable uuid), `event_type` (varchar), `ip_address` (inet), `user_agent` (text), `metadata` (jsonb), `created_at` (timestamptz)
   - Alembic migration `0010_add_audit_log.py`
   - Indexes on `(user_id, created_at DESC)` and `(event_type, created_at DESC)`
   - Helper: `log_audit_event(event_type, request, user, metadata)` in `backend/app/services/audit_service.py`
   - Apply to: auth events, signal threshold changes, watchlist changes, rate limit hits

5. **Sentry + PostHog wiring.**
   - Add `sentry-sdk[fastapi]` to backend, `@sentry/react` to frontend
   - Init Sentry in `backend/app/main.py` and `frontend/src/main.tsx`
   - Environment-aware: `environment='production'` on Railway, `'development'` locally
   - Add PostHog backend and frontend SDKs
   - Set up basic events: `page_view`, `signal_alert_fired`, `card_watched`, `signup`, `upgrade_clicked`
   - **PII discipline:** never send raw email addresses to PostHog. Hash with SHA256 client-side before sending.

6. **`structlog` for backend logging.**
   - Replace the existing `_log_json(level, event, **fields)` pattern with `structlog`
   - JSON output in production, pretty in development
   - Bind request_id, user_id, route to every log within a request

**Files touched:**
- `backend/app/main.py`
- `backend/app/services/audit_service.py` (new)
- `backend/app/services/backup_service.py` (new)
- `backend/app/middleware/rate_limit.py` (new)
- `backend/app/alembic/versions/0010_add_audit_log.py` (new)
- `backend/app/scheduler.py` (add backup job)
- `scripts/backup_postgres.py` (new)
- `docs/runbooks/restore-from-backup.md` (new)
- `frontend/src/main.tsx`
- `requirements.txt`
- `frontend/package.json`

**Acceptance criteria:**
- [ ] `pg_dump` runs daily and appears in `scheduler_run_log` for 7 consecutive days
- [ ] A test restore from yesterday's backup completes successfully against a scratch database (run the restore drill once and document the timing)
- [ ] Rate limits return `429` when exceeded — verifiable via curl loop
- [ ] Sentry receives a test error from both backend and frontend in production
- [ ] PostHog receives at least one event in production
- [ ] `audit_log` table receives entries for at least 3 event types in production
- [ ] No regression in existing `/api/v1/web/*` response times (measure p95 before and after)
- [ ] Discord alert fires if backup job fails (test by temporarily breaking R2 credentials)

**Codex Review prompt:**
```
Review PR #14. This is the foundation PR — if anything is wrong here, every later PR inherits the bug.
Focus on:
1. Is the backup actually verified by a restore drill, or is it just "the script runs without erroring"? An untested backup is no backup.
2. Are R2 credentials stored as Railway env vars only (no secrets in repo or logs)?
3. Does PgBouncer's transaction pool mode break any code that assumes session-mode pooling? Check for: prepared statements, server-side cursors, `LISTEN/NOTIFY`, advisory locks.
4. Are rate limits applied to internal scheduler/health-check endpoints accidentally? They should be exempt.
5. Does the audit log capture enough for a future SOC2-style audit, or is it too narrow?
6. Is PII handling correct? Specifically: no raw emails or IP addresses going to PostHog without hashing.
```

---

### PR #15 — Frontend foundation

**Goal:** Establish the new visual + technical foundation. After this PR, every component in the app speaks Tailwind + shadcn + Lucide + i18n. **This is the migration PR.** It changes more files than any other but should produce zero visual regressions.

**Scope:**

1. **Install and configure Tailwind CSS.**
   - `npm install -D tailwindcss postcss autoprefixer @tailwindcss/typography`
   - Create `tailwind.config.ts` with all design tokens from section 1.2–1.5 mapped to Tailwind theme extensions
   - Replace `theme.css` color/spacing/radius/font variables with Tailwind utility classes
   - Keep custom CSS for: scrollbar styling, holo effects, complex keyframes
   - The Tailwind config exports tokens so they can be imported by Storybook later

2. **Install shadcn/ui CLI and core components.**
   - `npx shadcn-ui@latest init`
   - Configure paths to match project structure: `components/ui` lives at `frontend/src/components/ui/`
   - Add these initial primitives (each via `shadcn-ui add`): `button`, `card`, `dialog`, `dropdown-menu`, `popover`, `tabs`, `tooltip`, `select`, `switch`, `input`, `label`, `separator`, `badge`, `skeleton`, `sonner`, `command`
   - Replace existing custom components with shadcn equivalents where they exist
   - Document any project-specific overrides in `frontend/src/components/ui/README.md`

3. **Install TanStack Query.**
   - `npm install @tanstack/react-query @tanstack/react-query-devtools`
   - Set up `QueryClientProvider` in `main.tsx` with sensible defaults: 30s stale time, retry 1 on failure, refetch on window focus enabled
   - Migrate every `fetch` in `src/api/api.ts` to use `useQuery` / `useMutation` hooks in the components
   - Add query keys file: `src/api/queryKeys.ts` — single source of truth for cache keys
   - DevTools enabled in dev only

4. **Install Lucide React.**
   - `npm install lucide-react`
   - Audit every emoji in components (`grep -r "📊\|⚡\|🔔\|📈\|⭐\|☆\|🎴" frontend/src/`) and replace with Lucide icons
   - Standardize sizes: 16px in body text, 20px in buttons, 24px in nav, 32px in feature highlights
   - Stroke width 1.5px throughout
   - Create a `src/components/icons/` module that re-exports the project's icon set so swapping libraries later is one-file

5. **Install Motion (Framer Motion successor).**
   - `npm install motion`
   - Import as `import { motion } from "motion/react"`
   - Set up motion variants file: `src/lib/motion-variants.ts` with named entrance/exit variants used across the app

6. **Wire up `react-i18next`.**
   - Install `react-i18next i18next i18next-browser-languagedetector`
   - Create `src/i18n/index.ts` per layout in section 1.8
   - Build out all locale files for current app surfaces
   - Wrap `<App>` in `<I18nextProvider>` in `main.tsx`
   - Replace every hardcoded English string in the existing codebase with `t('...')` calls
   - Add language toggle component in NavBar
   - Persist user choice to `users.preferred_locale` column (new Alembic migration `0011_add_user_preferred_locale.py`)

7. **Migrate fonts.**
   - Remove current Google Fonts links from `index.html`
   - Add Geist (display), Inter (body), JetBrains Mono (mono), Noto Sans SC (Chinese body), Noto Serif SC (Chinese display)
   - Use `font-display: swap` to prevent FOIT
   - Self-host critical fonts in `public/fonts/` for first-paint speed (use `@font-face` with woff2)

8. **Storybook setup.**
   - `npx storybook@latest init`
   - Configure for Vite + React + Tailwind
   - Create stories for: `Button`, `Card`, `SignalBadge`, `Sparkline`, `CardArt`, `Skeleton`
   - Add `chromatic` (or just commit Storybook static build) for visual regression baseline

9. **Bundle size budget enforcement.**
   - Add `vite-plugin-bundle-visualizer` and run on every build
   - Add CI check: fail if main bundle exceeds 200KB gzipped (initial budget; tighten to 150KB over time)
   - Add a `BUNDLE_BUDGET.md` documenting the policy

**Files touched (selected — the migration is extensive):**
- `frontend/tailwind.config.ts` (new)
- `frontend/postcss.config.js` (new)
- `frontend/src/styles/tokens.css` (new — replaces color/spacing in theme.css)
- `frontend/src/styles/motion.css` (new)
- `frontend/src/components/ui/*` (new directory, ~15 shadcn primitives)
- `frontend/src/lib/motion-variants.ts` (new)
- `frontend/src/api/queryKeys.ts` (new)
- `frontend/src/i18n/` (new directory)
- `frontend/src/components/icons/index.ts` (new)
- `frontend/.storybook/*` (new)
- All existing component files (refactored to Tailwind + i18n)
- `frontend/package.json` (significant additions)
- `frontend/index.html` (font links updated)
- `backend/app/alembic/versions/0011_add_user_preferred_locale.py` (new)

**Acceptance criteria:**
- [ ] Visual diff vs. pre-migration is ≤ 5% on every page (the migration should produce near-identical output)
- [ ] Zero hardcoded English strings in any `.tsx` component file (`grep`-able)
- [ ] Bundle size under 200KB gzipped (main) + report on which deps are heaviest
- [ ] Zero `emoji` characters in any component file
- [ ] TypeScript strict mode passes
- [ ] All Storybook stories render without errors
- [ ] Language toggle works and persists across reload
- [ ] At least one shadcn primitive (e.g., DropdownMenu in NavBar) is wired and working

**Codex Review prompt:**
```
Review PR #15. This PR replaces the foundation of the frontend. Specific concerns:
1. Is every existing component actually migrated, or are some still using raw CSS classes from theme.css?
2. Has any UX regressed? Particularly: keyboard navigation, focus states, dark theme contrast.
3. Is i18n applied consistently? Specifically: are number formats, date formats, and pluralization handled, or only string interpolation?
4. Does the TanStack Query migration introduce any race conditions (e.g., a component that previously re-fetched on every mount now stays stale)?
5. Are shadcn components actually used, or are they installed but ignored?
6. Bundle size: what are the three heaviest dependencies, and is any of them avoidable?
7. Does the locale toggle persist to the database for authenticated users, or only localStorage?
```

---

### PR #16 — Real sparklines + TradingView charts

**Goal:** Replace the fake 2-point sparklines and the homemade SVG area chart with real, performant, financial-grade charts.

**Scope:**

1. **Backend: add `sparkline` field to `/api/v1/web/cards` response.**
   - 30 data points representing the last 7 days of price history, downsampled
   - Computed via batched SQL using `array_agg` with window functions (see the SQL pattern in this conversation's research)
   - For 100K-user scale: cache the sparkline JSON in a new `assets.sparkline_7d` JSONB column, refreshed on every bulk-refresh job run
   - Alembic migration `0012_add_assets_sparkline_cache.py`

2. **Frontend: update `CardSummary` type.**
   - Add `sparkline: number[] | null` to `frontend/src/types/api.ts`
   - Update mock data to include realistic varied sparklines

3. **Frontend: rewrite `Sparkline.tsx`.**
   - SVG, but proper smooth curve (cubic spline)
   - Gradient area fill from signal color → transparent
   - End-point dot in the signal color
   - Hover shows the value at that point (tooltip)
   - No data state: dashed line with "—" centered

4. **Frontend: install TradingView Lightweight Charts.**
   - `npm install lightweight-charts`
   - Create `frontend/src/components/PriceChart.tsx` wrapping the library
   - Configure: dark theme matching our tokens, mono font for axis labels, time-series with both TCGPlayer (gold line) and eBay (green dashed) data
   - Cursor crosshair with synchronized tooltip
   - Attribution: small "Powered by TradingView" link in the chart corner (license requirement)

5. **Frontend: use TradingView chart on CardDetailPage.**
   - Replace the homemade `<AreaChart>` SVG component
   - Same dual-source display, but now with crosshair, zoom, pan, real-time updates

**Files touched:**
- `backend/app/api/routes/web.py`
- `backend/app/services/sparkline_service.py` (new)
- `backend/app/alembic/versions/0012_add_assets_sparkline_cache.py` (new)
- `backend/app/scheduler.py` (bulk-refresh job updates sparkline column)
- `frontend/src/components/Sparkline.tsx` (rewritten)
- `frontend/src/components/PriceChart.tsx` (new)
- `frontend/src/components/CardGrid.tsx` (uses real sparkline data)
- `frontend/src/pages/CardDetailPage.tsx` (uses TradingView chart)
- `frontend/src/types/api.ts`

**Acceptance criteria:**
- [ ] No two cards have identical sparklines on the dashboard (real data, real variation)
- [ ] Sparkline computation does not regress `/api/v1/web/cards` p95 latency
- [ ] TradingView chart loads on `/market/:id` with both TCG and eBay series visible
- [ ] Chart attribution link is present and clickable
- [ ] Bundle size impact ≤ 50KB gzipped (Lightweight Charts is 45KB itself)
- [ ] Mobile chart pinch-zoom works
- [ ] Reduced motion: chart loads without animation

**Codex Review prompt:**
```
Review PR #16. Specific focus:
1. Is the sparkline query batched (one query for N cards) or N+1 (one query per card)? Verify with EXPLAIN ANALYZE.
2. Is the sparkline cache invalidation correct? If a card's price updates between bulk-refresh runs, when does the sparkline update?
3. Is the TradingView attribution link compliant with the license requirement (visible, clickable, on every chart page)?
4. Does the chart render correctly when one series has data and the other doesn't?
5. What happens to the chart when SSE (PR #22) pushes a new data point — does it append cleanly?
```

---

### PR #17 — Confidence + explainability + COOLING signal

**Goal:** Make the signal engine's reasoning visible to users. This is the PR that proves the pricing-page promise of "every number with confidence." Also introduces the fifth signal tier (COOLING) for post-spike fades.

**Scope:**

1. **Backend: add `confidence` and `reasoning` to signal computation.**
   - `asset_signals.confidence` (integer 0–100) — already exists as column per schema reference; ensure it's actually populated
   - `asset_signals.reasoning` (jsonb) — new column, stores structured evidence: sample size, baseline, current delta, comparable historicals
   - Alembic migration `0013_add_asset_signal_reasoning.py`

2. **Backend: implement COOLING signal logic.**
   - Triggered when a card was SURGE/DRIFT in the past 7 days and is now showing >15% reversal with sustained volume
   - Add detection logic to `backend/app/services/signal_service.py::sweep_signals`
   - Add to `asset_signal_history` as a recognized label

3. **Backend: signal explainability endpoint.**
   - `GET /api/v1/web/cards/:id/signal-evidence`
   - Returns the structured reasoning + 1–3 historical comparables
   - Pro-tier only; free users see a teaser with "Upgrade to see why"

4. **Frontend: confidence badge.**
   - Small mono number next to every SignalBadge: `SURGE 87` (confidence inline)
   - Color-coded: green ≥80, amber 60–79, gray <60
   - Tooltip on hover explains: "Confidence based on sample size (47 sales), match rate (92%), data freshness (2h)"

5. **Frontend: "Why?" popover on card detail.**
   - Click the signal badge on `/market/:id` → opens shadcn `<Popover>` with the structured reasoning
   - Includes a 1–3 historical comparables section: *"Last comparable: Charizard PSA 10 in March 2024, +22% then settled at +14%"*
   - Free users see a partial view + upgrade CTA

6. **Frontend: COOLING badge styling.**
   - Purple (`--cooling`) — distinguishes from SURGE
   - In signal filter pills, COOLING appears as the fifth option

7. **Update copy.**
   - Add COOLING to all signal description tables, both locales
   - English description: *"Price has reversed from a recent peak. Volume confirms selling pressure. Consider exiting if you bought into the spike."*
   - Chinese description: requires Ivan review

**Files touched:**
- `backend/app/services/signal_service.py`
- `backend/app/services/signal_explainability_service.py` (new)
- `backend/app/api/routes/web.py`
- `backend/app/alembic/versions/0013_add_asset_signal_reasoning.py` (new)
- `frontend/src/components/SignalBadge.tsx`
- `frontend/src/components/SignalReasoningPopover.tsx` (new)
- `frontend/src/pages/CardDetailPage.tsx`
- `frontend/src/pages/DashboardPage.tsx` (filter pills)
- `frontend/src/i18n/locales/{en,zh-CN}/signals.json`
- `frontend/src/lib/utils.ts` (extend `signalToMeta` to handle COOLING)

**Acceptance criteria:**
- [ ] Every signal in production has a confidence score 0–100
- [ ] COOLING signals fire on at least 5 historical cases in a backtest run
- [ ] Free user sees confidence number but not the full reasoning popover content
- [ ] Pro user sees full reasoning with at least one historical comparable
- [ ] No "INSUFFICIENT_DATA" badge is shown when confidence ≥60 — that's a contradiction
- [ ] Both English and Chinese descriptions for COOLING are reviewed by Ivan

**Codex Review prompt:**
```
Review PR #17. Focus:
1. Is the COOLING signal threshold actually catching real fades, or is it false-positive-heavy? Run a backtest on the last 30 days and report precision/recall.
2. Does the confidence calculation match what the pricing copy promises (sample size, freshness, match rate)?
3. Is the historical comparables query performant? It could become N+1 across the dashboard.
4. Is the "upgrade to see why" gate correctly preventing free users from accessing the full reasoning via direct API call?
5. Are the Chinese signal descriptions natural, or do they read like machine translations? (Ivan must review.)
```

---

### PR #18 — Joy moments + sound system + holo + tilt

**Goal:** Add the MTG-Arena-grade card moments. This is the PR that turns the product from "good dashboard" into "I'll show this to my friends."

**Scope:**

1. **3D tilt on card hover.**
   - Adapt `react-parallax-tilt` (`npm install react-parallax-tilt`) or implement custom
   - Max ±8° on each axis, follows cursor
   - Apply to `<CardArt>` component, all sizes
   - Reduced motion: replace with subtle 1px gold border on hover, no tilt

2. **Real holo shimmer on rare cards.**
   - Adapt from `https://poke-holo.simey.me/` (MIT licensed CSS)
   - Activates on cards with `rarity` in `['Rare Holo', 'Ultra Rare', 'Secret Rare', 'Rainbow Rare']`
   - Holo gradient tracks cursor position via CSS variables driven by JS (only on hover, not idle)
   - On card detail page, holo is more pronounced (slower, more saturated)

3. **Sound system foundation.**
   - Install `howler` (`npm install howler @types/howler`)
   - Create `frontend/src/hooks/useSound.ts` — accepts event name, respects user preference (from `users.sound_enabled` column, new)
   - Add Alembic migration `0014_add_user_sound_preference.py`
   - Source 5 initial sound files per section 1.6, place in `frontend/public/sounds/`
   - Add Settings → Preferences page (or section) with a toggle

4. **Signal badge entrance animation.**
   - Implement per section 1.7 #4
   - Uses Motion library, scale + opacity + glow
   - Triggered when signal state changes (TanStack Query revalidation detects the change)

5. **Watchlist star pop.**
   - Implement per section 1.7 #5
   - Scale spring + particle burst (use small inline SVG dots animating outward)
   - Plays `watchlist-add` sound

6. **Number tick on price change.**
   - Custom hook `useAnimatedNumber(value)` that tweens between old and new
   - Brief color flash via CSS variable transition
   - Applied to all price displays in CardGrid and CardDetailPage

7. **Empty state copy refresh.**
   - Audit every empty state in the app
   - Apply the tone from section 1.7 #6 — characterful, brief, bilingual
   - Some examples below; full list in `frontend/src/i18n/locales/{en,zh-CN}/empty-states.json`:
     - Alerts empty (EN): *"Quiet on the market. We'll let you know when it isn't."*
     - Alerts empty (中文): *"市场很安静。一有动静我们就告诉你。*"
     - Watchlist empty (EN): *"Track a card to see it move."*
     - Watchlist empty (中文): *"关注一张卡片,看看它的走势。"*

**Files touched:**
- `frontend/src/components/CardArt.tsx` (tilt + holo wrapper)
- `frontend/src/components/SignalBadge.tsx` (entrance animation)
- `frontend/src/components/CardGrid.tsx` (number tick)
- `frontend/src/components/WatchlistStar.tsx` (new — extracted, with pop animation)
- `frontend/src/hooks/useSound.ts` (new)
- `frontend/src/hooks/useAnimatedNumber.ts` (new)
- `frontend/src/pages/SettingsPage.tsx` (new)
- `frontend/src/styles/holo.css` (new)
- `frontend/public/sounds/*.mp3` (5 files)
- `backend/app/alembic/versions/0014_add_user_sound_preference.py` (new)
- `frontend/src/i18n/locales/{en,zh-CN}/empty-states.json`

**Acceptance criteria:**
- [ ] Tilt is smooth at 60fps on a mid-range laptop
- [ ] Holo only activates on hover, never idle, never on common-rarity cards
- [ ] `prefers-reduced-motion` disables tilt, holo motion (static gradient), particle bursts, number tick (instant swap)
- [ ] Sound preference persists across reload and across devices for authenticated users
- [ ] No sound plays in the default state (sounds default to off)
- [ ] Watchlist star pop fires on add and on remove (different sounds + lower pitch on remove)
- [ ] Empty state copy is reviewed by Ivan in both languages

**Codex Review prompt:**
```
Review PR #18. The risk in this PR is overdoing it. Specific checks:
1. Open the dashboard, do NOT interact, watch for 30 seconds. Does anything animate? If yes, that's a bug per the "idle is still" principle.
2. Hover a card with rarity 'Common'. Does it tilt but NOT holo? Both should be true.
3. Toggle prefers-reduced-motion in DevTools. Are ALL animations reduced or removed?
4. Toggle sound off. Hover a card, click a watchlist star, change pages. Is the page silent?
5. Are the sound files actually under 30KB each? Audio bloat is a real concern.
6. Are particles in the star pop using transform/opacity only (not animating top/left)?
```

---

### PR #19 — Landing page rebuild (founder-led)

**Goal:** Replace the current generic SaaS landing page with a founder-led, thesis-driven, live-data-showing page that reads "TradingView meets Linear meets Cursor with a card-game heart."

**Scope:**

1. **Wipe the current LandingPage.tsx.** Start clean.

2. **New page structure (top to bottom):**

   - **Nav (existing post-#13, post-#15)**
   - **Hero section**
     - Left: thesis-style headline + 1-paragraph founder voice (Ivan's words, polished). Sample English:
       > **The market for cards is real. The tools haven't caught up.**
       >
       > I've been investing in trading cards since [year]. For years, I tracked prices across three browser tabs and missed half the moves that mattered. Flashcard Planet is what I wish existed — signals based on real eBay sales, confidence shown on every number, and tools built for people who actually do this.
     - CTA: "Explore the Market →" + "How Signals Work →"
     - Right: **live data widget** — top 3 SURGE cards from the last 24h, with their real card art, real percentages, updating via SSE every 30s. **This is the hero. The product working on itself.**

   - **Live ticker** (existing component, polished, slower)

   - **Thesis section** — a 3-paragraph essay in Ivan's voice on why TCG investing needs better tools. This is the Cursor-style narrative. Should reflect Ivan's actual point of view on the market. Drafted by Ivan with Claude Code polish.

   - **How it works** — 3 numbered steps with screenshots of the actual product (not stock illustrations). Each step is one paragraph + one screenshot:
     1. *We track every meaningful card across TCGPlayer and eBay.*
     2. *Our signal engine flags moves with confidence, sample size, and reasoning.*
     3. *You get the signal before the market reprices.*

   - **Trust section** — *empty placeholder for now, reserve the structure.* Will eventually hold: number of cards tracked (real), number of signals fired (real), user quotes (when available), press logos (when available). Don't fake any of these; show real numbers or hide the row.

   - **Pricing teaser** — three tiers (Free / Pro / Trader) with the headline value of each, linking to `/pricing` for full comparison.

   - **Methodology link** — *"Want to know how we compute signals? Read the methodology →"*

   - **Footer** — Ivan's name + one-line bio, GitHub link, social links, status page link, methodology link, changelog link, both legal pages.

3. **Visual treatment.**
   - Hero: Aceternity-style spotlight effect *behind* the card widget, restrained
   - One animated beam connecting the live data widget to the headline text on first scroll into view (Magic UI animated beam component)
   - Thesis section: serif heading (Geist could work, or a more editorial face like Fraunces if Geist feels too neutral)
   - Screenshots: actual product screenshots in real device chrome mocks (use `https://mockuphone.com` or similar for clean device frames)

4. **Bilingual.**
   - Entire landing renders in both languages
   - Toggle in nav switches language; preference persists

**Files touched:**
- `frontend/src/pages/LandingPage.tsx` (rewritten)
- `frontend/src/components/LiveSurgeWidget.tsx` (new — fetches top 3 SURGE cards, updates via TanStack Query polling pre-#22, SSE post-#22)
- `frontend/src/components/landing/*` (new directory for landing-only components)
- `frontend/src/i18n/locales/{en,zh-CN}/landing.json`
- Aceternity/Magic UI components copy-pasted into `frontend/src/components/ui/` as needed

**Acceptance criteria:**
- [ ] Founder thesis paragraph is written by Ivan, not Claude Code
- [ ] Live data widget shows real cards, real percentages, real card art
- [ ] Page loads in <2s on slow 3G (per Chrome DevTools throttling)
- [ ] LCP <2.5s, CLS <0.1, INP <200ms (Core Web Vitals all green)
- [ ] Page renders correctly in both English and Chinese
- [ ] No placeholder lorem ipsum, no stock illustrations, no fake testimonials
- [ ] No "Built for serious collectors" or similar generic SaaS copy

**Codex Review prompt:**
```
Review PR #19. The biggest risk here is reverting to generic SaaS conventions. Specific checks:
1. Does the page have a single sentence anyone else could plausibly say? If yes, rewrite it.
2. Is the live data widget actually pulling live data, or is it a mock?
3. Are the screenshots real product screenshots, or mockups/illustrations?
4. Run a Lighthouse audit. Are all four core scores >=90?
5. Does the page lead with the thesis, or with feature bullets? If features come first, reorder.
6. Read the Chinese version aloud to yourself. Does it sound native, or translated?
```

---

### PR #20 — Onboarding flow + first-flip celebration

**Goal:** Convert first-time visitors into engaged users in the first 60 seconds. Set up the first-flip celebration moment that turns engaged users into paying users.

**Scope:**

1. **3-step onboarding overlay.**
   - Triggered first time a user lands on `/market` after sign-up
   - Step 1: "Which game do you play?" — Pokémon selected by default, others greyed with "Coming soon" labels
   - Step 2: "Pick 5 cards you own or are watching" — searchable card picker, adds to watchlist
   - Step 3: "Here's what your first signal will look like" — shows a sample signal card with all elements labeled (badge, confidence, sparkline, "why" popover)
   - Skippable at any step; resumed if abandoned

2. **First-flip celebration.**
   - When a watched card enters SURGE for the first time for that user, ever, trigger the overlay from section 1.7 #7
   - Backend: new table `user_milestones` (`user_id`, `milestone_type`, `triggered_at`, `metadata`)
   - Frontend: check on app load + listen for SSE event matching this user's watched cards

3. **Empty state nudge.**
   - If a user's watchlist is empty after 24h of signup, show a banner: *"Track a card to see signals."* + CTA to add one
   - Dismissable, doesn't reappear once dismissed

**Files touched:**
- `frontend/src/components/onboarding/OnboardingFlow.tsx` (new)
- `frontend/src/components/onboarding/FirstFlipCelebration.tsx` (new)
- `frontend/src/hooks/useOnboardingState.ts` (new)
- `backend/app/models/user_milestone.py` (new)
- `backend/app/alembic/versions/0015_add_user_milestones.py` (new)
- `backend/app/api/routes/web.py` (milestone endpoints)
- `frontend/src/i18n/locales/{en,zh-CN}/onboarding.json`

**Acceptance criteria:**
- [ ] New user lands on /market and sees onboarding within 1 second
- [ ] Skipping at step 2 leaves the watchlist empty but does not block the user
- [ ] First-flip overlay fires exactly once per user, ever
- [ ] Milestone is durable across sessions (no localStorage-only)
- [ ] Both languages tested

**Codex Review prompt:**
```
Review PR #20. Focus:
1. Onboarding can fire while a SignalBadge or Sound is also firing. Is the layering handled (z-index, no double-sounds)?
2. If a user has the first-flip event happen on the backend but is offline at the time, do they see the celebration on next visit?
3. Is the onboarding skippable in a way that doesn't penalize the user later?
4. Does the milestone table get bloated if every user has many milestones in the future? Indexes correct?
```

---

### PR #21 — Status page + methodology + changelog

**Goal:** Three pages that signal "this is a serious product" — public ops transparency, public algorithm transparency, public development transparency.

**Scope:**

1. **Status page (status.flashcardplanet.com).**
   - Deploy [Uptime Kuma](https://github.com/louislam/uptime-kuma) on Railway as a separate service
   - Configure monitors for: API health, frontend availability, scheduler heartbeat, Postgres connectivity
   - Public status page accessible at the subdomain
   - Add incident posting flow (manual, for now) for downtime communication

2. **Methodology page (`/methodology`).**
   - In-app page (not external)
   - Written by Ivan in his voice, polished by Claude Code
   - Sections: how signals are computed, what confidence means, sample size requirements, IQR outlier rejection, data sources, refresh cadence
   - Includes worked examples with real numbers
   - Bilingual

3. **Changelog page (`/changelog`).**
   - Auto-generated from git commits with `feat:` or `fix:` prefix
   - Manually-curated summary per release (Ivan writes a one-line "what's new" per significant release)
   - Markdown-based, kept in `frontend/src/content/changelog/YYYY-MM-DD.md`
   - "What's new" indicator badge in NavBar when there's an unread update (uses localStorage to track read state)

4. **About page (`/about`).**
   - Brief founder bio
   - The product thesis
   - Contact email
   - Link to methodology, changelog, status

**Files touched:**
- `frontend/src/pages/MethodologyPage.tsx` (new)
- `frontend/src/pages/ChangelogPage.tsx` (new)
- `frontend/src/pages/AboutPage.tsx` (new)
- `frontend/src/content/changelog/*.md` (new directory)
- `frontend/src/components/NavBar.tsx` (whats-new indicator)
- Uptime Kuma deployment scripts in `infra/`

**Acceptance criteria:**
- [ ] status.flashcardplanet.com responds with the public status page
- [ ] /methodology page exists in both languages
- [ ] /changelog has at least 5 historical entries summarized
- [ ] What's-new badge clears when user visits /changelog

**Codex Review prompt:**
```
Review PR #21. Focus:
1. Is the methodology page actually correct? Cross-reference with backend/app/services/signal_service.py — does the documentation match the code?
2. Does the status page show real monitor data, or is it a static placeholder?
3. Is the changelog generation automated, or does Ivan have to write it by hand for every commit?
4. Does the what's-new indicator persist correctly across sessions?
```

---

### PR #22 — SSE real-time + virtualized grid + Cmd+K

**Goal:** The product feels alive. The three power features that signal "enterprise tool."

**Scope:**

1. **Server-Sent Events for real-time signal feed.**
   - Backend: new endpoint `GET /api/v1/sse/signals` using `sse-starlette`
   - Streams events when: signal state changes, price updates, alerts fire
   - Filtered by user (only events for cards the user watches or for global movers)
   - Reconnect logic, heartbeat every 30s
   - Authenticated via cookie or token

2. **Frontend SSE consumer hook.**
   - `useSignalStream()` — subscribes on mount, unsubscribes on unmount
   - Pushes events into TanStack Query cache via `queryClient.setQueryData`
   - Drives the number tick animations (PR #18) and signal badge entrances

3. **Virtualized card grid.**
   - When card list exceeds 50 items, switch to TanStack Virtual rendering
   - Maintain 60fps scroll
   - Keep the existing card item design from PR #18; only the container changes

4. **Command palette (Cmd+K).**
   - Use `cmdk` library (already in shadcn)
   - Triggered by Cmd+K (Ctrl+K on Windows/Linux)
   - Commands: search for a card, go to a page, toggle theme, sign out, open settings
   - Fuzzy search across cards (uses an in-memory index of card names + sets, built from `/api/v1/web/cards` response)

**Files touched:**
- `backend/app/api/routes/sse.py` (new)
- `backend/app/services/sse_service.py` (new)
- `frontend/src/hooks/useSignalStream.ts` (new)
- `frontend/src/components/CardGrid.tsx` (virtualization)
- `frontend/src/components/CommandPalette.tsx` (new)
- `frontend/src/main.tsx` (mount command palette globally)

**Acceptance criteria:**
- [ ] SSE connection establishes within 1s on page load
- [ ] When a card's signal changes in the database, the dashboard reflects it within 5s
- [ ] Card grid with 1000+ items scrolls at 60fps on a mid-range laptop
- [ ] Cmd+K opens the palette; Esc closes it
- [ ] Palette can navigate to any page and find any card
- [ ] SSE reconnects cleanly after network drop

**Codex Review prompt:**
```
Review PR #22. Focus:
1. Does SSE properly close connections when users leave the page? Memory leaks are a real risk.
2. Are SSE messages filtered per user, or does every user get every event? (Privacy + bandwidth concern.)
3. Does the virtualized grid handle dynamic row heights (cards can vary in detail visible)?
4. Is the command palette accessible (arrow keys, Enter, Esc, screen reader)?
5. Does Cmd+K work on Mac AND Ctrl+K on Windows/Linux?
```

---

### PR #23 — Weekly digest email

**Goal:** The retention engine. Users who pay $12-29/month forget why if you don't remind them. Weekly digest is the answer.

**Scope:**

1. **Backend: digest computation job.**
   - Weekly scheduler job (Sunday 09:00 user-local-time, falls back to UTC if no preference)
   - For each user: compute the week's signals on their watchlist, top movers in their game, comparable hypothetical P&L
   - Email content templated, includes: 3 cards that moved into SURGE, 2 that hit COOLING, top movers across their watchlist, week's signal count

2. **Email service.**
   - Use existing email infrastructure (per project — Resend or similar)
   - HTML template matching the dark theme of the app
   - Footer with unsubscribe link

3. **Preferences page.**
   - Add to settings: digest frequency (weekly / monthly / off)
   - Stored on `users.digest_preference`

**Files touched:**
- `backend/app/services/digest_service.py` (new)
- `backend/app/scheduler.py` (weekly digest job)
- `backend/app/email/templates/weekly_digest.html` (new)
- `backend/app/email/templates/weekly_digest.txt` (new — plain text version)
- `backend/app/alembic/versions/0016_add_user_digest_preference.py` (new)
- `frontend/src/pages/SettingsPage.tsx` (add toggle)

**Acceptance criteria:**
- [ ] Digest sent to test user in production, renders correctly in Gmail/Apple Mail/Outlook
- [ ] Unsubscribe link works
- [ ] Bilingual content (preferred locale)
- [ ] No digest sent if user has 0 watched cards (silent skip)

**Codex Review prompt:**
```
Review PR #23. Focus:
1. Does the digest correctly handle users with empty watchlists, new users with <1 week of history, and inactive users?
2. Is the unsubscribe link cryptographically signed (not user_id in URL plaintext)?
3. Does the HTML email render in dark email clients vs. light? Test both.
4. Is the digest computation a separate job (won't block the bulk-refresh)?
```

---

### PR #24 — Cloudflare Pages migration + bilingual polish

**Goal:** Final infrastructure step. Move SPA to the edge for global speed, audit every translated string for quality, ship.

**Scope:**

1. **Cloudflare Pages setup.**
   - Connect GitHub repo to Cloudflare Pages project
   - Configure build: `npm run build`, output `dist/`
   - Set custom domain to `flashcardplanet.com` and `www`
   - Update DNS in Cloudflare
   - Update API CORS to allow the new origin
   - Update `VITE_API_BASE_URL` to point to Railway-hosted API

2. **Backend serving SPA: removed.**
   - `backend/app/main.py` no longer serves `dist/`
   - The Railway backend is now API-only
   - Remove `StaticFiles` mount and SPA catch-all from `site.py`

3. **Final bilingual audit.**
   - Ivan reviews every `zh-CN/*.json` file
   - Native-speaker test pass — does anything read as translated rather than written?
   - Fix flagged strings

4. **Performance audit.**
   - Lighthouse on landing, dashboard, card detail
   - All four scores ≥90
   - Bundle size under 200KB main (tighten to 150KB if possible)

**Files touched:**
- `backend/app/main.py`
- `backend/app/site.py`
- `frontend/src/env.d.ts`
- All `frontend/src/i18n/locales/zh-CN/*.json`
- Cloudflare dashboard configuration (out-of-repo)

**Acceptance criteria:**
- [ ] flashcardplanet.com served from Cloudflare edge (verify via response headers)
- [ ] TTFB <100ms globally (measure from 3 regions)
- [ ] API still reachable from new origin (CORS works)
- [ ] All Chinese strings approved by Ivan
- [ ] Lighthouse: 90+ on Performance, Accessibility, Best Practices, SEO

**Codex Review prompt:**
```
Review PR #24. Final-mile checks:
1. Does the apex domain redirect correctly to www (or vice versa, whichever is canonical)?
2. Are the API CORS headers correct for the new origin?
3. Is the old Railway-served SPA still accessible (it should NOT be — confirm 404)?
4. Are Chinese strings consistent in tone? No mixing formal/informal voice within a single surface?
```

---

## 4. Operational Guidelines

### 4.1 Handling Claude Code / Codex / Ivan three-way disagreement

Per project convention: one round of position-stating, then Ivan decides.

If Claude Code is confident a Codex comment is wrong, Claude Code states *why* with specific evidence (code line, test result, SQL output). Codex states its position with the same standard of evidence. Ivan picks. No relitigation.

If a Codex review surfaces a concern that wasn't covered by the acceptance criteria in this spec, that's a sign the spec was incomplete — surface it to Ivan via claude.ai so this spec can be updated.

### 4.2 Verifying "shipped" vs "claimed"

Every acceptance criterion is verifiable. None of them say "Claude Code believes this is done." All of them say "this can be checked by SQL query, curl request, or visual inspection in production."

For each PR, after merge:
1. Wait for Railway/Cloudflare deploy to complete (confirm deploy ID)
2. Run the SQL/curl verification from the acceptance criteria
3. Observe in production (Discord alerts, dashboard, etc.) for at least 1 cycle (e.g., wait one scheduler run before claiming the scheduler change is live)
4. Update PR with the verification evidence

A PR is **shipped** when verification passes in production, not when CI passes locally.

### 4.3 The forbidden patterns to never reintroduce

Per the project memory, three patterns have hurt this project before. Watch for all of them in every PR.

- **"Designed but never ran" pattern** — A feature exists in code but has never executed in production. Verify with logs/SQL before claiming it works.
- **"Claimed vs. shipped" gap** — Local code changes don't matter until they're committed, deployed, and observed. Confirm the deploy.
- **Scheduler time-anchor confusion** — Jobs re-anchor on every deploy. Gaps in scheduler_run_log must be interpreted against last deploy time, not wall clock.

### 4.4 Bundle size budget

| Bundle | Initial budget | Hard cap |
|---|---|---|
| Frontend main (gzipped) | 200KB | 300KB (fail CI) |
| Frontend per-route (gzipped) | 50KB | 100KB |
| Sound files (total) | 200KB | 500KB |
| Font files (total) | 150KB | 250KB |

Run `vite-bundle-visualizer` on every PR that touches frontend. If a PR adds >20KB to main, justify in the PR description.

### 4.5 Accessibility floor

WCAG AA across the entire app. Specifically:

- All text contrast ratios ≥4.5:1 for normal text, ≥3:1 for large text
- All interactive elements reachable by keyboard
- All form inputs have associated labels
- All images have alt text (card art alt = card name + set name)
- Focus indicators visible on every focusable element
- `prefers-reduced-motion` respected per motion system
- Color is never the only way to convey meaning (signals also use distinct icons and text labels)

### 4.6 What this spec doesn't cover (out of scope for phase 1)

- Payments / Stripe integration (separate spec, post-phase-1)
- Cross-TCG signals (the multi-game intelligence layer — phase 2)
- Portfolio tracking with P&L (Trader tier hero feature — phase 2)
- Public API access (Trader tier — phase 2)
- Webhooks (deferred per earlier triage)
- Mobile native apps (not in scope; PWA work covered by general responsive design)
- B2B / enterprise sales motion (not in scope)
- SOC2 / compliance certifications (audit log lays groundwork but cert is post-phase-1)

---

## 5. Final Pre-Flight Checklist for Claude Code

Before starting PR #13:

- [ ] Read sections 0, 1, 2 in full
- [ ] Have a local PostgreSQL running for testing
- [ ] Have Railway and Cloudflare accounts with R2 enabled
- [ ] Have a Sentry project created (`flashcard-planet` org if available)
- [ ] Have a PostHog project created
- [ ] Have Codex CLI v0.118.0+ working for review on every PR
- [ ] Have read `CLAUDE.md` and `handoff-usage-guide.md` in the repo
- [ ] Have Ivan available to review founder voice copy and Chinese translations

When ready:
1. Start with PR #14 (backend foundation) AND PR #13 (bug fixes) in parallel — they don't conflict
2. After both ship and verify, start PR #15 (frontend foundation)
3. After PR #15 ships, parallelize #16, #17, #18 where possible
4. PRs #19+ depend on the foundation PRs landing first

---

*End of spec. Estimated 9,500 words. Update via PR to this file as decisions evolve.*

*Next review: after PR #15 ships. Re-evaluate motion system, joy moments calibration, and Chinese translation quality based on what users actually do.*
