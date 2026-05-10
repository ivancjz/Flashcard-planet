# Task: Independent Methodology Review

You are reviewing a system audit checklist AND its execution results. Your job is NOT to re-execute the checks. Your job is to find flaws in the methodology and gaps in the evidence.

## Context

Project: Flashcard Planet (TCG investment signals SaaS, Python 3.13 / FastAPI / SQLAlchemy 2 / APScheduler / Postgres 18 on Railway).

Triggering symptom: production signal leaderboard shows ~60 cards with "0 sales" but 24h changes from +21% to +245%, all labeled Breakout or Move.

Known prior issues from project memory:
- Issue B (3 days no Pokemon data) was closed as false alarm but 7-day SQL evidence was never produced
- 97.7% of insufficient_data cases were has_baseline_no_current (stale price data)
- eBay ingest historically never ran due to APScheduler cron trigger reset on every deploy; rebuilt with interval trigger and 660s startup delay; validation pending
- Pattern: components claimed-fixed but never actually executing in production
- Claude Code has shown a pattern of confident first-round answers that get revised under evidence pressure

## Materials to Review

The audit findings are attached in the file audits/2026-05-01/findings-raw.md

## Review Dimensions

For each, give a verdict (OK / WEAK / MISSING) with specific examples:

D1. Evidence sufficiency -- Does the evidence Claude Code collected actually support each PASS/FAIL verdict?
D2. Hidden assumptions -- What schema/system assumptions does the methodology make that are not verified?
D3. Layer ordering -- Are the layer dependencies correct? Did any Layer 1 check secretly depend on a Layer 2 fact?
D4. False-pass risks -- For each PASS verdict, construct a plausible scenario where the check passed but a real bug exists.
D5. False-fail risks -- For each FAIL verdict, construct a plausible scenario where the check failed but the system is actually correct.
D6. Coverage gaps -- What classes of bug could produce the observed symptom (0 sales + high % + Breakout) that the checklist would NOT catch? List at least 3.
D7. Anti-gaming -- Given Claude Code's track record of code-reading-as-evidence, does the executed audit have enough runtime proof? Where could verdicts be tightened?
D8. Scope -- Over-scoped (lost focus) or under-scoped (missed critical areas)?

## Output

1. Per-dimension verdict with specific citations into the findings file
2. List of CONCRETE corrections -- verdicts that should change from PASS->FAIL or FAIL->PASS based on evidence quality
3. List of bug classes the audit missed entirely
4. Overall recommendation: ACCEPT FINDINGS / ACCEPT WITH CORRECTIONS / REJECT AND RE-AUDIT
