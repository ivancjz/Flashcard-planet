# Flashcard Planet Product Bible v2.0

Status: execution baseline
Date: 2026-07-21
Primary artifact: `Flashcard Planet Product Bible v2.0.docx`

## Product Position

Flashcard Planet is the collectibles market intelligence layer. It is not just a price checker, marketplace, or card database. The product goal is to help collectors, investors, store owners, creators, and future enterprise users understand what moved, why it moved, what evidence supports the move, and what deserves attention next.

The long-term product reference is the Bloomberg Terminal for Collectibles: a daily intelligence surface that combines market data, events, AI explanation, signals, portfolio context, and decision support.

## Operating Principle

Every feature must answer this question:

> Does this help the user make a better collecting, buying, selling, or portfolio decision?

If the answer is no, the feature is deferred.

## Core Rules

- Data before opinion.
- Evidence before recommendation.
- Explain every AI conclusion.
- Trust is the product.
- Never invent market reasons.
- If evidence is weak, say "Insufficient evidence."
- Price movement alone never creates a buy recommendation.
- Community sentiment alone never creates a buy recommendation.
- Every future AI output must include confidence and evidence.

## Product Layers

1. Market Dashboard
2. Market Intelligence Framework
3. News Center
4. Catalyst Engine
5. Signal Engine
6. Daily Market Report
7. Knowledge Base
8. Community Intelligence
9. Portfolio Intelligence
10. Decision Center

## Chapter Map

The Word document contains the complete v2 baseline:

1. Vision and Product Foundation
2. Market Intelligence Framework
3. System Architecture
4. Database Design
5. API Specification
6. AI Engine
7. Market Dashboard PRD
8. News and Catalyst PRD
9. Signals PRD
10. Daily Market Report PRD
11. Portfolio and Decision Center PRD
12. Codex Execution Plan

## First Runnable Slice

The first implementation slice is `GET /api/v1/market/overview`.

It must aggregate existing evidence into a dashboard-ready market overview:

- generated timestamp
- market sentiment
- raw market index summaries grouped by game
- top movers
- signal counts
- deterministic evidence-based commentary
- explicit evidence and confidence labels

This endpoint is intentionally rule-based in the first slice. LLM commentary comes later only after evidence records, prompt contracts, and caching are in place.

## Development Sequence

1. Land the Product Bible and execution plan.
2. Build `/api/v1/market/overview` from existing price history and signals.
3. Add frontend dashboard integration.
4. Add scheduled daily market report snapshots.
5. Add catalyst records and event-to-asset mapping.
6. Add AI explanation engine with evidence contracts.
7. Add portfolio and decision center surfaces.

## Non-Goals For This Slice

- No marketplace.
- No payment or checkout work.
- No LLM calls.
- No prediction claims.
- No new scheduler job.
- No broad frontend redesign.
- No provider ingestion rewrite.

## Acceptance Standard

Codex must implement incrementally and test first. New code must include:

- happy-path test
- insufficient-data test
- raw market segment guard test
- API route registration test

The endpoint must never fabricate market explanations. Empty or weak data must produce an explicit insufficient-data state.
