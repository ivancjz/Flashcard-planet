# Flashcard Planet Developer Notes

## Alerts MVP

Flashcard Planet now supports automatic Discord DM alerts driven by the scheduler:

1. Pokemon TCG ingestion writes real `price_history` rows
2. The scheduler evaluates active alerts after ingestion
3. Triggered alerts send Discord DMs
4. Alert state is persisted so the same condition does not spam every tick

## Alert types

The current MVP supports these alert behaviors:

- Price movement alerts
  - `PRICE_UP_THRESHOLD`
  - `PRICE_DOWN_THRESHOLD`
- Target alerts
  - `TARGET_PRICE_HIT`
- Prediction alerts
  - `PREDICT_SIGNAL_CHANGE`
  - `PREDICT_UP_PROBABILITY_ABOVE`
  - `PREDICT_DOWN_PROBABILITY_ABOVE`

User-facing Discord copy refers to these as:

- price movement alerts
- target alerts
- prediction alerts

The API and database still use the enum values above for compatibility.

## Rearm behavior

### Price movement alerts

Price movement alerts use the latest real price compared with the previous real non-`sample_seed` price point.

- Up alerts trigger when the step move is greater than or equal to the configured threshold
- Down alerts trigger when the step move is less than or equal to the negative threshold
- After firing, the alert is disarmed
- It re-arms only after the step move returns inside the threshold band

Example:

- Up threshold = `5%`
- Previous real price = `100`
- Latest real price = `106`
- Result: alert fires and becomes disarmed
- If the next step move is only `+1%`, the alert re-arms
- A later move of `+5%` or more can trigger it again

### Prediction signal change alerts

`PREDICT_SIGNAL_CHANGE` stores the most recent observed prediction label in `last_observed_signal`.

- The first usable prediction initializes state only
- No DM is sent on that first observation
- A DM is sent only when the label changes later, for example `Flat -> Up`

### Prediction probability threshold alerts

Probability alerts use the existing `/predict` probability model.

- Up probability alerts fire when `Up %` crosses above the configured threshold
- Down probability alerts fire when `Down %` crosses above the configured threshold
- After firing, they are disarmed
- They re-arm only after the relevant probability drops back below the threshold

### Target alerts

Target alerts are still one-shot:

- they fire once when crossed
- they deactivate after firing

## Scheduler logs to watch

After ingestion/evaluation, look for log fields like:

- `active_alerts_checked`
- `triggered`
- `price_movement_alerts_triggered`
- `prediction_alerts_triggered`
- `alerts_rearmed`
- `notifications_sent`
- `dm_delivery_failures`
- `target_alerts_deactivated`

## Manual demo flow

Dry-run a demo alert trigger:

```powershell
python -m scripts.demo_alert_trigger --asset-name Charizard --percent-change 10
```

Commit a demo price point so the running scheduler can act on it:

```powershell
python -m scripts.demo_alert_trigger --asset-name Charizard --percent-change 10 --commit
```

This inserts a `dev_test` price row with a newer timestamp than the latest real row.

## Clean up demo data

Remove committed demo rows:

```powershell
python -m scripts.demo_alert_trigger --asset-name Charizard --cleanup
```

## Basic test command

Run the service-level alert tests with:

```powershell
python -m unittest discover -s tests -v
```

## Data health commands

To inspect tracked Pokemon coverage and history depth:

```powershell
python -m scripts.price_history_summary
```

To force one ingestion pass and print the post-run health snapshot:

```powershell
python -m scripts.ingest_pokemon_tcg
```

To force only the Scarlet & Violet 151 trial pool:

```powershell
python -m scripts.ingest_pokemon_tcg_trial
```

To force only the High-Activity Trial pool:

```powershell
python -m scripts.ingest_pokemon_tcg_high_activity_trial
```

If `POKEMON_TCG_CARD_IDS` exists in your local `.env`, that local override controls the tracked card set. Remove it or update it if you want the expanded in-code default list to apply.

The current setup compares three tracked pools side by side:

- `Base Set`
- `Scarlet & Violet 151 Trial`
- `High-Activity Trial`

When you are looking for a better movement source, compare these pool metrics after a few days:

- assets with real history
- average history depth
- assets with price changes in the last 24h and 7d
- percent of comparable rows that actually changed price
- assets with no movement across full history
- assets whose latest two prices are unchanged

`python -m scripts.price_history_summary` now ends with a short `Operator conclusion` block that tells you whether `High-Activity Trial` is actually outperforming the other two pools and whether that points toward smarter pool selection or provider #2 preparation.
