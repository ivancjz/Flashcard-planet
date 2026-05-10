# Discord Bot — Archived 2026-05-02

## What this was

A Discord slash-command bot (`main.py`) with 9 commands:
`/price`, `/predict`, `/history`, `/watch`, `/watchlist`, `/unwatch`, `/alerts`, `/topmovers`, `/topvalue`, `/alerthistory`.

Also: `api_client.py` (HTTP client wrapping the FastAPI backend) and `link_builder.py` (URL helpers).

## Why archived

The bot was fully implemented but never deployed. Zero users ever used it.
The product is web-first (FastAPI + Card Detail + Signals + Watchlist).
Discord is now an **outbound alert delivery channel only** via REST API webhook —
see `backend/app/alerting/discord.py` for the active implementation.

Archiving removes a "designed but never ran" dead surface (CLAUDE.md Lesson 2).

## Re-evaluation conditions

Do **not** redeploy unless BOTH of the following are true:

1. Pro users ≥ 30 AND at least 5 unprompted user requests for Discord slash-command integration
2. OR: at least one competitor (Card Ladder, MTGStocks, Pokelytics, Collectr) demonstrates Discord bot as a measurable acquisition channel with public evidence

If and when redeploying, the correct pattern is **webhook-outbound** (deliver content into existing community servers), not inbound bot (asking users to join ours).

## How to restore

```bash
git mv archive/discord-bot-2026/*.py bot/
git mv archive/discord-bot-2026/__init__.py bot/
# Re-add discord.py to requirements.txt
# Re-add Discord OAuth routes to backend/app/api/routes/auth.py (see git history)
# Re-add discord_client_id / discord_client_secret / discord_guild_id to config.py
```

The full implementation is intact here — restoration is a `git mv` away, not a rewrite.
