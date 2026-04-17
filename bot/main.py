import logging
from datetime import UTC, datetime
from decimal import Decimal

import discord
from discord import app_commands
from discord.ext import commands

from backend.app.core.config import get_settings
from bot.api_client import BackendClient, TierError
from bot.link_builder import make_web_link

DELIVERY_STATUS_LABELS = {
    "sent": "Delivered",
    "failed": "Failed to deliver",
}

logging.basicConfig(level=logging.INFO)

settings = get_settings()
client = BackendClient()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

EMBED_COLOR_INFO = discord.Color.blue()
EMBED_COLOR_SUCCESS = discord.Color.green()
EMBED_COLOR_WARNING = discord.Color.orange()
EMBED_COLOR_DANGER = discord.Color.red()


def format_number(value: object | None) -> str:
    if value is None:
        return "Not set"

    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.to_integral():
        return f"{decimal_value:.0f}"
    return f"{decimal_value:.2f}"


def format_percent(value: object | None) -> str:
    if value is None:
        return "Not set"
    return f"{format_number(value)}%"


def format_price(value: object | None, currency: str | None = None) -> str:
    if value is None:
        return "Not set"

    amount = format_number(value)
    if currency:
        return f"{amount} {currency}"
    return amount


def parse_datetime(value: str | int | float | datetime | None) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=UTC)
    elif isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return None
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.fromtimestamp(float(raw_value), tz=UTC)
            except ValueError:
                return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_relative_time(value: str | int | float | datetime | None, *, now: datetime | None = None) -> str | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return None

    reference_time = now or datetime.now(UTC)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)
    else:
        reference_time = reference_time.astimezone(UTC)

    delta_seconds = int((reference_time - parsed).total_seconds())
    absolute_seconds = abs(delta_seconds)

    if absolute_seconds < 60:
        return "just now" if delta_seconds >= 0 else "in <1m"

    if absolute_seconds < 3600:
        amount = absolute_seconds // 60
        unit = "m"
    elif absolute_seconds < 86400:
        amount = absolute_seconds // 3600
        unit = "h"
    else:
        amount = absolute_seconds // 86400
        unit = "d"

    if delta_seconds >= 0:
        return f"{amount}{unit} ago"
    return f"in {amount}{unit}"


def format_history_timestamp(value: str | int | float | datetime | None, *, now: datetime | None = None) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "Unknown"

    absolute_time = parsed.strftime("%Y-%m-%d %H:%M")
    relative_time = format_relative_time(parsed, now=now)
    if relative_time:
        return f"{absolute_time} ({relative_time})"
    return absolute_time


def add_embed_field(embed: discord.Embed, name: str, value: object | None, *, inline: bool = True) -> None:
    text = str(value).strip() if value not in (None, "") else "Not set"
    embed.add_field(name=name, value=text, inline=inline)


def format_labeled_text(label: str, value: object | None) -> str:
    text = str(value).strip() if value not in (None, "") else "Not set"
    return f"{label}: {text}"


def format_asset_summary(item: dict, *, include_category: bool = False) -> str:
    lines = [f"**{item.get('name', 'Unknown asset')}**"]
    if item.get("set_name"):
        lines.append(format_labeled_text("Set", item.get("set_name")))
    if include_category and item.get("category"):
        lines.append(format_labeled_text("Category", item.get("category")))
    return "\n".join(lines)


def join_blocks(blocks: list[str]) -> str:
    return "\n\n".join(block for block in blocks if block)


def format_signed_price_change(value: Decimal, currency: str | None = None) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{format_price(abs(value), currency)}"


def format_liquidity_summary(item: dict) -> str:
    if item.get("liquidity_score") is None and not item.get("liquidity_label"):
        return "Not set"
    label = item.get("liquidity_label") or "Liquidity"
    score = item.get("liquidity_score")
    if score is None:
        return str(label)
    return f"{label} ({format_number(score)}/100)"


def format_activity_summary(item: dict) -> str:
    parts = []
    if item.get("sales_count_7d") is not None:
        parts.append(f"7d rows {format_number(item['sales_count_7d'])}")
    if item.get("sales_count_30d") is not None:
        parts.append(f"30d rows {format_number(item['sales_count_30d'])}")
    if item.get("days_since_last_sale") is not None:
        parts.append(f"Last real {format_number(item['days_since_last_sale'])}d ago")
    if item.get("source_count") is not None:
        parts.append(f"Sources {format_number(item['source_count'])}")
    return " | ".join(parts) if parts else "Not set"


def format_alert_confidence_summary(item: dict) -> str:
    if item.get("alert_confidence") is None and not item.get("alert_confidence_label"):
        return "Not set"
    label = item.get("alert_confidence_label") or "Confidence"
    score = item.get("alert_confidence")
    if score is None:
        return str(label)
    return f"{label} ({format_number(score)}/100)"


def build_history_movement_summary(history_rows: list[dict], default_currency: str | None = None) -> str:
    if not history_rows:
        return "No returned points yet."

    prices = [Decimal(str(row.get("price"))) for row in history_rows]
    currency = history_rows[0].get("currency") or default_currency

    if len(prices) == 1:
        return "Only 1 returned point."

    change_count = sum(1 for current, previous in zip(prices, prices[1:]) if current != previous)
    if change_count == 0:
        return "No change across returned points."

    latest_move = prices[0] - prices[1]
    return "\n".join(
        [
            f"{change_count} change{'s' if change_count != 1 else ''} across {len(prices)} returned points.",
            f"Latest move: {format_signed_price_change(latest_move, currency)} vs previous point.",
        ]
    )


def build_price_embed(item: dict, match_count: int) -> discord.Embed:
    embed = discord.Embed(
        title="Asset Quote",
        description=format_asset_summary(item, include_category=True),
        color=EMBED_COLOR_INFO,
    )
    if item.get("image_url"):
        embed.set_thumbnail(url=item["image_url"])
    add_embed_field(embed, "Latest price", format_price(item.get("latest_price"), item.get("currency")))
    if item.get("percent_change") is not None:
        add_embed_field(
            embed,
            "Recent move",
            (
                f"{format_signed_price_change(Decimal(str(item.get('absolute_change') or '0')) , item.get('currency'))} | "
                f"{format_percent(item.get('percent_change'))}"
            ),
            inline=False,
        )
    add_embed_field(embed, "Liquidity", format_liquidity_summary(item), inline=False)
    add_embed_field(embed, "Activity", format_activity_summary(item), inline=False)
    if item.get("alert_confidence") is not None:
        add_embed_field(embed, "Alert confidence", format_alert_confidence_summary(item), inline=False)
    add_embed_field(embed, "Source", item.get("source"))
    add_embed_field(embed, "Captured at", format_history_timestamp(item.get("captured_at")), inline=False)
    if match_count > 1:
        embed.set_footer(text=f"{match_count} matches found. Showing the top result.")
    return embed


def build_topmovers_embed(movers: list[dict], limit: int) -> discord.Embed:
    blocks = []
    for index, item in enumerate(movers, start=1):
        percent = Decimal(str(item["percent_change"]))
        sign = "+" if percent >= 0 else ""
        blocks.append(
            "\n".join(
                [
                    f"`{index}.` **{item['name']}**",
                    f"{format_price(item['latest_price'])} | {sign}{format_number(percent)}%",
                    f"Liquidity: {format_liquidity_summary(item)} | Confidence: {format_alert_confidence_summary(item)}",
                    format_activity_summary(item),
                ]
            )
        )

    embed = discord.Embed(
        title="Top Movers",
        description=join_blocks(blocks),
        color=EMBED_COLOR_INFO,
    )
    embed.set_footer(text=f"Showing {len(movers)} of {limit} requested mover(s).")
    return embed


def build_topvalue_embed(items: list[dict], limit: int) -> discord.Embed:
    blocks = []
    for index, item in enumerate(items, start=1):
        supporting_line = None
        if item.get("set_name"):
            supporting_line = format_labeled_text("Set", item["set_name"])
        elif item.get("category"):
            supporting_line = format_labeled_text("Category", item["category"])
        blocks.append(
            "\n".join(
                line
                for line in [
                    f"`{index}.` **{item['name']}** - {format_price(item.get('latest_price'), item.get('currency'))}",
                    supporting_line,
                ]
                if line
            )
        )

    embed = discord.Embed(
        title="Top Value",
        description=join_blocks(blocks),
        color=EMBED_COLOR_INFO,
    )
    if items:
        embed.set_footer(
            text=(
                f"Showing {len(items)} of {limit} requested asset(s). "
                f"Latest update: {format_history_timestamp(items[0].get('captured_at'))}."
            )
        )
    else:
        embed.set_footer(text=f"Showing 0 of {limit} requested asset(s).")
    return embed


def get_prediction_embed_color(prediction: str) -> discord.Color:
    if prediction == "Up":
        return EMBED_COLOR_SUCCESS
    if prediction == "Down":
        return EMBED_COLOR_DANGER
    if prediction == "Flat":
        return EMBED_COLOR_WARNING
    return EMBED_COLOR_INFO


def build_prediction_embed(item: dict, match_count: int) -> discord.Embed:
    embed = discord.Embed(
        title="Price Prediction",
        description=format_asset_summary(item),
        color=get_prediction_embed_color(item.get("prediction", "")),
    )
    if item.get("image_url"):
        embed.set_thumbnail(url=item["image_url"])
    add_embed_field(embed, "Current price", format_price(item.get("current_price"), item.get("currency")))
    add_embed_field(embed, "Prediction", item.get("prediction"))
    add_embed_field(
        embed,
        "Probabilities",
        "\n".join(
            [
                format_labeled_text("Up", format_percent(item.get("up_probability"))),
                format_labeled_text("Down", format_percent(item.get("down_probability"))),
                format_labeled_text("Flat", format_percent(item.get("flat_probability"))),
            ]
        ),
        inline=False,
    )
    add_embed_field(embed, "Points used", item.get("points_used"))
    add_embed_field(embed, "Captured at", format_history_timestamp(item.get("captured_at")), inline=False)
    add_embed_field(embed, "Reason", item.get("reason"), inline=False)
    if match_count > 1:
        embed.set_footer(text=f"{match_count} matches found. Showing the top result.")
    return embed


def build_history_embed(item: dict, limit: int, *, now: datetime | None = None) -> discord.Embed:
    history_rows = item.get("history", [])
    lines = []
    number_width = len(str(len(history_rows))) if history_rows else 1
    for index, row in enumerate(history_rows, start=1):
        point_type = row.get("event_type") or row.get("point_type") or "unknown"
        real_data_label = "real" if row.get("is_real_data", True) else "sample"
        lines.append(
            f"`{index:>{number_width}}.` {format_history_timestamp(row.get('captured_at'), now=now)} | "
            f"{format_price(row.get('price'), row.get('currency'))} | {point_type} | {real_data_label}"
        )

    embed = discord.Embed(
        title="Price History",
        description="\n".join(lines) if lines else "No recent real price history found.",
        color=EMBED_COLOR_INFO,
    )
    if item.get("image_url"):
        embed.set_thumbnail(url=item["image_url"])
    add_embed_field(embed, "Asset", item.get("name"), inline=False)
    if item.get("set_name"):
        add_embed_field(embed, "Set", item.get("set_name"), inline=False)
    add_embed_field(
        embed,
        "Recent movement",
        build_history_movement_summary(history_rows, item.get("currency")),
        inline=False,
    )
    add_embed_field(embed, "Liquidity", format_liquidity_summary(item), inline=False)
    add_embed_field(embed, "Activity", format_activity_summary(item), inline=False)
    add_embed_field(embed, "Current price", format_price(item.get("current_price"), item.get("currency")))
    add_embed_field(embed, "Points returned", item.get("points_returned"))
    embed.set_footer(text=f"Showing {item.get('points_returned', 0)} of {limit} requested history point(s).")
    return embed


def build_watch_embed(
    result: dict,
    asset_name: str,
    threshold_up_percent: float | None,
    threshold_down_percent: float | None,
    target_price: float | None,
    predict_signal_change: bool | None,
    predict_up_probability_above: float | None,
    predict_down_probability_above: float | None,
) -> discord.Embed:
    price_alerts = []
    if threshold_up_percent is not None:
        price_alerts.append(f"Up {format_percent(threshold_up_percent)}")
    if threshold_down_percent is not None:
        price_alerts.append(f"Down {format_percent(threshold_down_percent)}")

    prediction_alerts = []
    if predict_signal_change:
        prediction_alerts.append("Signal change")
    if predict_up_probability_above is not None:
        prediction_alerts.append(f"Up >= {format_percent(predict_up_probability_above)}")
    if predict_down_probability_above is not None:
        prediction_alerts.append(f"Down >= {format_percent(predict_down_probability_above)}")

    embed = discord.Embed(
        title="Watch Saved",
        description=result.get("message", "Your watchlist settings are active."),
        color=EMBED_COLOR_SUCCESS,
    )
    add_embed_field(embed, "Asset", asset_name, inline=False)
    add_embed_field(
        embed,
        "Watch Status",
        "Created new watch" if result.get("created_watchlist") else "Updated existing watch",
        inline=False,
    )
    add_embed_field(
        embed,
        "Price Alerts",
        " | ".join(price_alerts) if price_alerts else "None configured",
        inline=False,
    )
    add_embed_field(
        embed,
        "Prediction Alerts",
        " | ".join(prediction_alerts) if prediction_alerts else "None configured",
        inline=False,
    )
    add_embed_field(embed, "Target Price", format_price(target_price), inline=False)
    add_embed_field(
        embed,
        "Rules Added",
        ", ".join(result.get("added_rule_labels", [])) if result.get("added_rule_labels") else "No new alert rules",
        inline=False,
    )
    return embed


def build_unwatch_embed(asset_name: str) -> discord.Embed:
    return discord.Embed(
        title="Watch Removed",
        description=f"Stopped watching **{asset_name}**.",
        color=EMBED_COLOR_WARNING,
    )


def build_watchlist_embed(items: list[dict]) -> discord.Embed:
    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(
            f"`{index}.` **{item['name']}**\n"
            f"Up: {format_percent(item.get('threshold_up_percent'))} | "
            f"Down: {format_percent(item.get('threshold_down_percent'))} | "
            f"Target: {format_price(item.get('target_price'))}"
        )

    embed = discord.Embed(
        title="Your Watchlist",
        description="\n".join(lines),
        color=EMBED_COLOR_INFO,
    )
    embed.set_footer(text=f"{len(items)} watch item(s)")
    return embed


def build_empty_watchlist_embed() -> discord.Embed:
    return discord.Embed(
        title="Your Watchlist",
        description="You are not watching any assets yet. Add one with `/watch` to get started.",
        color=EMBED_COLOR_INFO,
    )


def build_alerts_embed(items: list[dict]) -> discord.Embed:
    blocks = []
    for index, item in enumerate(items, start=1):
        if item.get("target_price") is not None:
            comparator = ">=" if item.get("direction") == "ABOVE" else "<="
            rule_text = format_labeled_text(
                "Rule",
                f"Target {comparator} {format_price(item.get('target_price'), item.get('currency'))}",
            )
        elif item.get("alert_type") == "PREDICT_SIGNAL_CHANGE":
            rule_text = format_labeled_text("Rule", "Prediction signal changes")
        elif item.get("alert_type") == "PREDICT_UP_PROBABILITY_ABOVE":
            rule_text = format_labeled_text(
                "Rule",
                f"Predict Up >= {format_percent(item.get('threshold_percent'))}",
            )
        elif item.get("alert_type") == "PREDICT_DOWN_PROBABILITY_ABOVE":
            rule_text = format_labeled_text(
                "Rule",
                f"Predict Down >= {format_percent(item.get('threshold_percent'))}",
            )
        elif item.get("threshold_percent") is not None:
            direction = "Up" if item.get("alert_type") == "PRICE_UP_THRESHOLD" else "Down"
            rule_text = format_labeled_text(
                "Rule",
                f"Price {direction.lower()} {format_percent(item.get('threshold_percent'))} vs previous real price",
            )
        else:
            rule_text = format_labeled_text("Rule", item.get("alert_type", "Unknown"))

        if item.get("alert_type") == "PREDICT_SIGNAL_CHANGE":
            armed_text = "Tracking changes"
        else:
            armed_text = "Armed" if item.get("is_armed") else "Waiting to rearm"
        triggered_text = (
            format_history_timestamp(item.get("last_triggered_at"))
            if item.get("last_triggered_at")
            else "Pending"
        )
        latest_price = format_price(item.get("latest_price"), item.get("currency"))
        block_lines = [
            f"`{index}.` **{item['asset_name']}**",
            rule_text,
            format_labeled_text("Status", f"Active | {armed_text}"),
            format_labeled_text("Triggered", triggered_text),
            format_labeled_text("Latest", latest_price),
        ]
        if item.get("current_prediction") and item.get("current_prediction") != "Not enough data":
            block_lines.append(
                f"Prediction: {item['current_prediction']} | "
                f"Up {format_percent(item.get('up_probability'))} | "
                f"Down {format_percent(item.get('down_probability'))} | "
                f"Flat {format_percent(item.get('flat_probability'))}"
            )
        elif item.get("current_prediction") == "Not enough data":
            block_lines.append("Prediction: Not enough data yet")
        if item.get("alert_type") == "PREDICT_SIGNAL_CHANGE" and item.get("last_observed_signal"):
            block_lines.append(format_labeled_text("Last observed signal", item["last_observed_signal"]))
        blocks.append("\n".join(block_lines))

    embed = discord.Embed(
        title="Active Alerts",
        description=join_blocks(blocks),
        color=EMBED_COLOR_INFO,
    )
    embed.set_footer(text=f"{len(items)} active alert(s)")
    return embed


def build_empty_alerts_embed() -> discord.Embed:
    return discord.Embed(
        title="Active Alerts",
        description="You do not have any active alerts yet. Add one with `/watch` to get started.",
        color=EMBED_COLOR_INFO,
    )


def build_alert_history_embed(items: list[dict], limit: int) -> discord.Embed:
    blocks = []
    for index, item in enumerate(items, start=1):
        alert_type = item.get("alert_type", "Unknown")
        triggered_at = format_history_timestamp(item.get("triggered_at"))
        price_line = format_price(item.get("price_at_trigger"), item.get("currency"))
        delivery = DELIVERY_STATUS_LABELS.get(item.get("delivery_status", ""), item.get("delivery_status", ""))

        parts = [
            f"`{index}.` **{item.get('asset_name', 'Unknown')}**",
            format_labeled_text("Type", alert_type),
            format_labeled_text("Triggered", triggered_at),
            format_labeled_text("Price", price_line),
        ]
        if item.get("percent_change") is not None:
            percent = Decimal(str(item["percent_change"]))
            sign = "+" if percent >= 0 else ""
            parts.append(format_labeled_text("Move", f"{sign}{format_number(percent)}%"))
        parts.append(format_labeled_text("Status", delivery))
        blocks.append("\n".join(parts))

    embed = discord.Embed(
        title="Alert History",
        description=join_blocks(blocks) if blocks else "No alert history found.",
        color=EMBED_COLOR_INFO,
    )
    embed.set_footer(text=f"Showing {len(items)} of up to {limit} recent trigger(s).")
    return embed


def build_empty_alert_history_embed() -> discord.Embed:
    return discord.Embed(
        title="Alert History",
        description="No alerts have fired yet. Add a watch with `/watch` and they will appear here once triggered.",
        color=EMBED_COLOR_INFO,
    )


def get_test_guild() -> discord.Object | None:
    guild_id = settings.discord_guild_id.strip()
    if not guild_id:
        return None
    return discord.Object(id=int(guild_id))


async def sync_commands() -> None:
    guild = get_test_guild()
    if guild is not None:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        logging.info(
            "Synced %s guild command(s) to guild %s: %s",
            len(synced),
            guild.id,
            ", ".join(command.name for command in synced) or "<none>",
        )
        return

    synced = await bot.tree.sync()
    logging.info(
        "Synced %s global command(s): %s",
        len(synced),
        ", ".join(command.name for command in synced) or "<none>",
    )


@bot.event
async def setup_hook() -> None:
    await sync_commands()


@bot.event
async def on_ready() -> None:
    logging.info("Discord bot connected as %s", bot.user)
    guild = get_test_guild()
    if guild is not None:
        logging.info("Using test guild %s for slash commands.", guild.id)
    else:
        logging.info("No DISCORD_GUILD_ID configured; using global slash commands.")


@bot.tree.command(name="price", description="Get the latest known price for an asset.")
@app_commands.describe(name="Asset name, for example Pikachu or LeBron James")
async def price(interaction: discord.Interaction, name: str) -> None:
    await interaction.response.defer(thinking=True)
    try:
        results = await client.fetch_price(name)
    except Exception as exc:
        await interaction.followup.send(f"Price lookup failed: {exc}")
        return

    if not results:
        await interaction.followup.send(f"No assets found for `{name}`.")
        return

    embed = build_price_embed(results[0], len(results))
    embed.url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="predict", description="Predict short-term price direction for a tracked asset.")
@app_commands.describe(name="Asset name, for example Pikachu or Charizard")
async def predict(interaction: discord.Interaction, name: str) -> None:
    await interaction.response.defer(thinking=True)
    try:
        results = await client.fetch_prediction(name)
    except Exception as exc:
        await interaction.followup.send(f"Prediction lookup failed: {exc}")
        return

    if not results:
        await interaction.followup.send(f"No assets found for `{name}`.")
        return

    embed = build_prediction_embed(results[0], len(results))
    embed.url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="history", description="Show recent real price history for a tracked asset.")
@app_commands.describe(name="Asset name, for example Pikachu or Charizard", limit="Number of history points to show")
async def history(
    interaction: discord.Interaction,
    name: str,
    limit: app_commands.Range[int, 1, 10] = 5,
) -> None:
    await interaction.response.defer(thinking=True)
    try:
        result = await client.fetch_history(name, limit=limit)
    except Exception as exc:
        await interaction.followup.send(f"History lookup failed: {exc}")
        return

    embed = build_history_embed(result, limit)
    embed.url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="watch", description="Add an asset to your watchlist.")
@app_commands.describe(
    asset_name="Exact tracked asset name, for example Charizard",
    threshold_up_percent="Alert when price rises by this percent versus the previous real price point",
    threshold_down_percent="Alert when price falls by this percent versus the previous real price point",
    target_price="Alert when price reaches this value",
    predict_signal_change="Alert when the prediction label changes, for example Flat to Up",
    predict_up_probability_above="Alert when predict Up probability crosses above this percent",
    predict_down_probability_above="Alert when predict Down probability crosses above this percent",
)
async def watch(
    interaction: discord.Interaction,
    asset_name: str,
    threshold_up_percent: float | None = None,
    threshold_down_percent: float | None = None,
    target_price: float | None = None,
    predict_signal_change: bool | None = None,
    predict_up_probability_above: float | None = None,
    predict_down_probability_above: float | None = None,
) -> None:
    await interaction.response.defer(thinking=True)
    try:
        result = await client.create_watch(
            discord_user_id=str(interaction.user.id),
            asset_name=asset_name,
            threshold_up_percent=threshold_up_percent,
            threshold_down_percent=threshold_down_percent,
            target_price=target_price,
            predict_signal_change=predict_signal_change,
            predict_up_probability_above=predict_up_probability_above,
            predict_down_probability_above=predict_down_probability_above,
        )
    except TierError as exc:
        embed = discord.Embed(
            title="Watchlist limit reached",
            description=(
                f"{exc}\n\n"
                f"[Upgrade to Pro]({exc.upgrade_url}) for unlimited watchlists."
            ),
            color=EMBED_COLOR_WARNING,
        )
        embed.url = make_web_link("/upgrade-from-discord", {"command_type": "slash_command", "campaign": "pro_conversion"})
        await interaction.followup.send(embed=embed)
        return
    except Exception as exc:
        await interaction.followup.send(f"Watch setup failed: {exc}")
        return

    embed = build_watch_embed(
        result=result,
        asset_name=asset_name,
        threshold_up_percent=threshold_up_percent,
        threshold_down_percent=threshold_down_percent,
        target_price=target_price,
        predict_signal_change=predict_signal_change,
        predict_up_probability_above=predict_up_probability_above,
        predict_down_probability_above=predict_down_probability_above,
    )
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(content=result["message"], embed=embed)


@bot.tree.command(name="unwatch", description="Remove an asset from your watchlist.")
@app_commands.describe(asset_name="Exact asset name to stop watching")
async def unwatch(interaction: discord.Interaction, asset_name: str) -> None:
    await interaction.response.defer(thinking=True)
    try:
        result = await client.delete_watch(discord_user_id=str(interaction.user.id), asset_name=asset_name)
    except Exception as exc:
        await interaction.followup.send(f"Unwatch failed: {exc}")
        return

    embed = build_unwatch_embed(asset_name)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(content=result["message"], embed=embed)


@bot.tree.command(name="watchlist", description="Show your current watchlist.")
async def watchlist(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        items = await client.fetch_watchlist(str(interaction.user.id))
    except Exception as exc:
        await interaction.followup.send(f"Could not load your watchlist: {exc}")
        return

    if not items:
        embed = build_empty_watchlist_embed()
        embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
        await interaction.followup.send(embed=embed)
        return

    embed = build_watchlist_embed(items)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="alerts", description="Show your active alert rules and trigger status.")
async def alerts(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        items = await client.fetch_alerts(str(interaction.user.id))
    except Exception as exc:
        await interaction.followup.send(f"Could not load your alerts: {exc}")
        return

    if not items:
        embed = build_empty_alerts_embed()
        embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
        await interaction.followup.send(embed=embed)
        return

    embed = build_alerts_embed(items)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="topmovers", description="Show the biggest movers from the latest tracked prices.")
@app_commands.describe(limit="Number of assets to show")
async def topmovers(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 5) -> None:
    await interaction.response.defer(thinking=True)
    try:
        movers = await client.fetch_top_movers(limit=limit)
    except Exception as exc:
        await interaction.followup.send(f"Could not load top movers: {exc}")
        return

    if not movers:
        await interaction.followup.send(
            "No meaningful movers available yet. Real price history is loading, but the latest tracked snapshots do not show non-zero movement."
        )
        return

    embed = build_topmovers_embed(movers, limit)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="topvalue", description="Show the highest-value tracked assets by latest real price.")
@app_commands.describe(limit="Number of assets to show")
async def topvalue(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 10) -> None:
    await interaction.response.defer(thinking=True)
    try:
        items = await client.fetch_top_value(limit=limit)
    except Exception as exc:
        await interaction.followup.send(f"Could not load top value assets: {exc}")
        return

    if not items:
        await interaction.followup.send("No top value assets available yet.")
        return

    embed = build_topvalue_embed(items, limit)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="alerthistory", description="Show your recent alert trigger history.")
@app_commands.describe(
    limit="Number of recent triggers to show (max 20)",
    asset_name="Filter by asset name",
)
async def alerthistory(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, 20] = 10,
    asset_name: str | None = None,
) -> None:
    await interaction.response.defer(thinking=True)
    try:
        items = await client.fetch_alert_history(
            str(interaction.user.id), limit=limit, asset_name=asset_name
        )
    except Exception as exc:
        await interaction.followup.send(f"Could not load alert history: {exc}")
        return

    if not items:
        embed = build_empty_alert_history_embed()
        embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
        await interaction.followup.send(embed=embed)
        return

    embed = build_alert_history_embed(items, limit)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(embed=embed)


def run() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required to run the Discord bot.")
    bot.run(settings.bot_token)


if __name__ == "__main__":
    run()
