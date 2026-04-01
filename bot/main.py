import logging
from datetime import UTC, datetime
from decimal import Decimal

import discord
from discord import app_commands
from discord.ext import commands

from backend.app.core.config import get_settings
from bot.api_client import BackendClient

logging.basicConfig(level=logging.INFO)

settings = get_settings()
client = BackendClient()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

EMBED_COLOR_INFO = discord.Color.blue()
EMBED_COLOR_SUCCESS = discord.Color.green()
EMBED_COLOR_WARNING = discord.Color.orange()


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


def format_timestamp(value: str | datetime | None) -> str:
    if value is None:
        return "Unknown"

    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return discord.utils.format_dt(parsed, style="f")


def add_embed_field(embed: discord.Embed, name: str, value: object | None, *, inline: bool = True) -> None:
    text = str(value).strip() if value not in (None, "") else "Not set"
    embed.add_field(name=name, value=text, inline=inline)


def build_price_embed(item: dict, match_count: int) -> discord.Embed:
    embed = discord.Embed(
        title="Asset Quote",
        description="Latest captured pricing snapshot.",
        color=EMBED_COLOR_INFO,
    )
    add_embed_field(embed, "Name", item.get("name"))
    add_embed_field(embed, "Category", item.get("category"))
    add_embed_field(embed, "Set", item.get("set_name"))
    add_embed_field(embed, "Latest Price", format_price(item.get("latest_price"), item.get("currency")))
    add_embed_field(embed, "Currency", item.get("currency"))
    add_embed_field(embed, "Source", item.get("source"))
    add_embed_field(embed, "Captured At", format_timestamp(item.get("captured_at")), inline=False)
    if match_count > 1:
        embed.set_footer(text=f"{match_count} matches found. Showing the top result.")
    return embed


def build_topmovers_embed(movers: list[dict], limit: int) -> discord.Embed:
    lines = []
    for index, item in enumerate(movers, start=1):
        percent = Decimal(str(item["percent_change"]))
        sign = "+" if percent >= 0 else ""
        lines.append(
            f"`{index}.` **{item['name']}**\n"
            f"{format_price(item['latest_price'])} | {sign}{format_number(percent)}%"
        )

    embed = discord.Embed(
        title="Top Movers",
        description="\n".join(lines),
        color=EMBED_COLOR_INFO,
    )
    embed.set_footer(text=f"Showing {len(movers)} of {limit} requested mover(s).")
    return embed


def build_watch_embed(
    asset_name: str,
    threshold_up_percent: float | None,
    threshold_down_percent: float | None,
    target_price: float | None,
) -> discord.Embed:
    alerts = []
    if threshold_up_percent is not None:
        alerts.append(f"Up {format_percent(threshold_up_percent)}")
    if threshold_down_percent is not None:
        alerts.append(f"Down {format_percent(threshold_down_percent)}")

    embed = discord.Embed(
        title="Watch Added",
        description="This asset is now on your watchlist.",
        color=EMBED_COLOR_SUCCESS,
    )
    add_embed_field(embed, "Asset", asset_name, inline=False)
    add_embed_field(embed, "Alert Thresholds", " | ".join(alerts) if alerts else "None configured", inline=False)
    add_embed_field(embed, "Target Price", format_price(target_price), inline=False)
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

    await interaction.followup.send(embed=build_price_embed(results[0], len(results)))


@bot.tree.command(name="watch", description="Add an asset to your watchlist.")
@app_commands.describe(
    asset_name="Exact asset name from the API seed data",
    threshold_up_percent="Alert when price rises by this percent",
    threshold_down_percent="Alert when price falls by this percent",
    target_price="Alert when price reaches this value",
)
async def watch(
    interaction: discord.Interaction,
    asset_name: str,
    threshold_up_percent: float | None = None,
    threshold_down_percent: float | None = None,
    target_price: float | None = None,
) -> None:
    await interaction.response.defer(thinking=True)
    try:
        result = await client.create_watch(
            discord_user_id=str(interaction.user.id),
            asset_name=asset_name,
            threshold_up_percent=threshold_up_percent,
            threshold_down_percent=threshold_down_percent,
            target_price=target_price,
        )
    except Exception as exc:
        await interaction.followup.send(f"Watch setup failed: {exc}")
        return

    await interaction.followup.send(
        content=result["message"],
        embed=build_watch_embed(
            asset_name=asset_name,
            threshold_up_percent=threshold_up_percent,
            threshold_down_percent=threshold_down_percent,
            target_price=target_price,
        ),
    )


@bot.tree.command(name="unwatch", description="Remove an asset from your watchlist.")
@app_commands.describe(asset_name="Exact asset name to stop watching")
async def unwatch(interaction: discord.Interaction, asset_name: str) -> None:
    await interaction.response.defer(thinking=True)
    try:
        result = await client.delete_watch(discord_user_id=str(interaction.user.id), asset_name=asset_name)
    except Exception as exc:
        await interaction.followup.send(f"Unwatch failed: {exc}")
        return

    await interaction.followup.send(content=result["message"], embed=build_unwatch_embed(asset_name))


@bot.tree.command(name="watchlist", description="Show your current watchlist.")
async def watchlist(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        items = await client.fetch_watchlist(str(interaction.user.id))
    except Exception as exc:
        await interaction.followup.send(f"Could not load your watchlist: {exc}")
        return

    if not items:
        await interaction.followup.send(embed=build_empty_watchlist_embed())
        return

    await interaction.followup.send(embed=build_watchlist_embed(items))


@bot.tree.command(name="topmovers", description="Show the biggest movers from the latest sample data.")
@app_commands.describe(limit="Number of assets to show")
async def topmovers(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 5) -> None:
    await interaction.response.defer(thinking=True)
    try:
        movers = await client.fetch_top_movers(limit=limit)
    except Exception as exc:
        await interaction.followup.send(f"Could not load top movers: {exc}")
        return

    if not movers:
        await interaction.followup.send("No movers available yet.")
        return

    await interaction.followup.send(embed=build_topmovers_embed(movers, limit))


def run() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required to run the Discord bot.")
    bot.run(settings.bot_token)


if __name__ == "__main__":
    run()
