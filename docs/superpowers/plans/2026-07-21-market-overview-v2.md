# Plan: Market Overview v2 Slice

Date: 2026-07-21

## Goal

Create the first executable Flashcard Planet v2 market intelligence slice:

```text
GET /api/v1/market/overview
```

## Constraints

- Reuse existing models and services where practical.
- Keep the first slice deterministic.
- Do not call LLM providers.
- Do not add scheduler jobs yet.
- Do not redesign the frontend in this step.
- Filter price movement evidence to raw market segment observations.

## Implementation Steps

1. Add market overview schemas.
2. Add market overview service.
3. Add market route.
4. Register route under the configured API prefix.
5. Add tests before production code:
   - service returns grouped game indexes and movers from raw observations
   - service ignores graded observations
   - service returns insufficient-data state when there are no comparable raw price series
   - API route returns the overview payload
   - API router includes `/api/v1/market/overview`
6. Run targeted tests.

## Response Contract

```json
{
  "generated_at": "datetime",
  "market_sentiment": "bullish | neutral | bearish | insufficient_data",
  "confidence_label": "high | medium | low | insufficient",
  "indexes": [
    {
      "game": "pokemon",
      "label": "Pokemon Market",
      "change_pct": "12.34",
      "direction": "up",
      "observed_assets": 2,
      "current_assets": 4,
      "confidence_label": "low"
    }
  ],
  "top_movers": [],
  "signal_summary": [],
  "commentary": "Evidence-based summary.",
  "evidence": []
}
```

## Verification

Run:

```text
pytest tests/test_market_overview_service.py tests/test_market_overview_api.py
```

If targeted tests pass, optionally run adjacent price and signal tests.
