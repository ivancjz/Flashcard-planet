"""Inject 5 test paper predictions for Gate 4 / B2 validation.

Predictions are backdated (resolution_date in past) so the resolve-predictions
job classifies them on first run after RESOLVE_PREDICTIONS_ENABLED=true.

Expected outcomes (based on prices observed 2026-05-23):
  1. Charizard above $500      → HIT  (actual $595.18 > $500)
  2. Alakazam  below $100      → HIT  (actual $76.62 < $100)
  3. Clefairy  within $30-$45  → HIT  (actual $36.51 in band)
  4. Blastoise above $300      → MISS (actual $220.81 < $300)
  5. Chansey   below $40       → MISS (actual $53.09 > $40)
"""
import json, os, uuid
import psycopg
from datetime import datetime, timezone, timedelta

url = os.environ["DATABASE_URL"]
# psycopg3 connect() needs postgresql:// not the SQLAlchemy postgresql+psycopg:// form
if url.startswith("postgresql+psycopg://"):
    url = "postgresql://" + url[len("postgresql+psycopg://"):]
conn = psycopg.connect(url, connect_timeout=15)
cur = conn.cursor()

now = datetime.now(timezone.utc)
past = now - timedelta(days=1)     # resolution_date yesterday → eligible immediately
predicted_at = now - timedelta(days=8)  # prediction "made" 8 days ago

METHODOLOGY_VERSION = "gate4-b2-test"

predictions = [
    {
        "asset_id": "149a2f7a-5bd6-48c3-a8e5-b36b2764e51a",  # Charizard $595.18
        "prediction_text": "[GATE4-TEST] Charizard Base Set price will remain above $500 within 7 days.",
        "threshold_value": 500.00,
        "threshold_direction": "above",
        "threshold_band_high": None,
        "stated_probability": 0.7500,
        "expected_resolution": "HIT",
    },
    {
        "asset_id": "bef5a532-6ac0-4d6d-a8ad-c05024cdcc0e",  # Alakazam $76.62
        "prediction_text": "[GATE4-TEST] Alakazam Base Set price will remain below $100 within 7 days.",
        "threshold_value": 100.00,
        "threshold_direction": "below",
        "threshold_band_high": None,
        "stated_probability": 0.7500,
        "expected_resolution": "HIT",
    },
    {
        "asset_id": "a84178f6-743a-4267-bda4-b17c9ee2c201",  # Clefairy $36.51
        "prediction_text": "[GATE4-TEST] Clefairy Base Set price will trade within $30-$45 within 7 days.",
        "threshold_value": 30.00,
        "threshold_direction": "within_band",
        "threshold_band_high": 45.00,
        "stated_probability": 0.6000,
        "expected_resolution": "HIT",
    },
    {
        "asset_id": "045be0c1-44cb-49c7-b585-d81ef64213a9",  # Blastoise $220.81
        "prediction_text": "[GATE4-TEST] Blastoise Base Set price will exceed $300 within 7 days.",
        "threshold_value": 300.00,
        "threshold_direction": "above",
        "threshold_band_high": None,
        "stated_probability": 0.4000,
        "expected_resolution": "MISS",
    },
    {
        "asset_id": "fbcf0df8-e38e-493f-b732-ccbbf7c237c5",  # Chansey $53.09
        "prediction_text": "[GATE4-TEST] Chansey Base Set price will drop below $40 within 7 days.",
        "threshold_value": 40.00,
        "threshold_direction": "below",
        "threshold_band_high": None,
        "stated_probability": 0.4000,
        "expected_resolution": "MISS",
    },
]

inserted = []
for p in predictions:
    pred_id = uuid.uuid4()
    cur.execute("""
        INSERT INTO predictions (
            id, predicted_at, resolution_date, asset_id,
            prediction_text, threshold_value, threshold_currency,
            threshold_direction, threshold_band_high,
            stated_probability, methodology_version,
            is_paper, resolution_status, created_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s,
            TRUE, 'PENDING', %s
        )
    """, (
        pred_id, predicted_at, past, p["asset_id"],
        p["prediction_text"], p["threshold_value"], "USD",
        p["threshold_direction"], p["threshold_band_high"],
        p["stated_probability"], METHODOLOGY_VERSION,
        now,
    ))
    inserted.append((pred_id, p["prediction_text"][:60], p["expected_resolution"]))

conn.commit()
print(f"Inserted {len(inserted)} test predictions:")
for pred_id, text, expected in inserted:
    print(f"  {pred_id} | {text} | expected={expected}")

# Verify
cur.execute("""
    SELECT id, prediction_text, threshold_direction, threshold_value,
           threshold_band_high, resolution_status, resolution_date
    FROM predictions
    WHERE methodology_version = %s
    ORDER BY created_at
""", (METHODOLOGY_VERSION,))
rows = cur.fetchall()
print(f"\nVerification — {len(rows)} rows in DB:")
for r in rows:
    print(f"  {r[0]} | dir={r[3]} {r[2]}..{r[4]} | status={r[5]} | resolve_by={r[6].date()}")

conn.close()
