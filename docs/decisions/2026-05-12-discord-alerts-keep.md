# Decision: Keep Discord REST API alerts (TASK-306)

**Date:** 2026-05-12  
**Status:** DECIDED — keep as-is  
**Trigger:** TASK-306 evaluation (TASK-104 completed 2026-05-02)

---

## Decision

**Keep `alert_service.py`'s Discord REST API webhook path.** Do not replace with Sentry, Healthchecks.io, or email for operational alerts.

---

## Evaluation

### Current state

21 `send_discord_alert()` callsites across `scheduler.py`, `routes.py`, and `alerting/`. Uses a single Discord webhook URL (`DISCORD_ALERT_WEBHOOK_URL` env var). Alert levels: `error`, `warning`, `info`. Format: Discord embed with title + body text. Zero ongoing cost. Works reliably.

Alert categories in production:
- **Scheduler errors**: start_run failures, job exceptions, zero-output warnings
- **Data anomalies**: heartbeat checks, 25h absence, zero-output windows
- **User-facing alerts**: price movement alerts (different path — `alerting/discord.py` direct webhook)

### Alternative: Sentry (error tracking)

**Pros:** Rich stack traces, issue grouping, error rate trends, breadcrumbs.  
**Cons:** Free tier is 5k errors/month (scheduler fires up to ~96/day × 9 jobs = ~864 events/day — would hit free tier in days). Paid plan: $26/month. Overkill for a solo operator; Sentry's UI adds no value over Railway logs + Discord embeds for this use case.

**Verdict: reject.** Railway logs already capture stack traces. Discord alert → Railway log is a sufficient investigation path.

### Alternative: Healthchecks.io (job heartbeat)

**Pros:** Cron-style "expected ping" monitoring. Alerts if a job hasn't run in N minutes. Dead-simple.  
**Cons:** The 25h absence check in `_send_heartbeat()` already implements this logic with Discord delivery. Free tier: 20 checks. Adding a third-party dependency for a feature we already have built is pure debt.

**Verdict: reject.** Our in-house heartbeat does the same job.

### Alternative: Email (digest)

**Pros:** Mobile-friendly, no Discord dependency, archivable.  
**Cons:** Operator already has Discord on mobile. Email delivery adds Resend cost ($0 under 100/day but another moving part). The market digest (TASK-301e) uses email correctly — that's user-facing, async content. Operational alerts are urgent, synchronous, Discord-appropriate.

**Verdict: reject for operational alerts.** Email is right for user digests (TASK-301e), not for "bulk-set-price-refresh wrote 0 records" alerts at 3am.

---

## Re-evaluate if

- Operator switches off Discord entirely (currently the only outbound alert channel)
- Alert volume exceeds ~50 Discord messages/day (Discord rate limits: 5 webhooks/sec, 30/min — not a concern at current scale)
- A second team member joins who doesn't use Discord
- Pro launch produces user-facing alert volume that saturates the operational channel

---

## What to monitor (not change)

The `health_warnings` addition to `/admin/stats` (TASK-T07, 2026-05-12) reduces reliance on Discord for routine health checks. Ivan can now `curl /admin/stats | jq .health_warnings` instead of waiting for a Discord alert. This is the right direction — reduce alert fatigue, not add more tools.
