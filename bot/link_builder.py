from urllib.parse import urlencode

from backend.app.core.config import get_settings

BASE_URL: str = get_settings().backend_base_url.rstrip("/")


def make_web_link(path: str, source_context: dict) -> str:
    params: dict[str, str] = {
        "utm_source": "discord",
        "utm_medium": source_context["command_type"],
        "utm_campaign": source_context["campaign"],
        "from": "discord",
    }
    if source_context.get("signal_type"):
        params["utm_content"] = source_context["signal_type"]
    if source_context.get("card_id"):
        params["ref"] = str(source_context["card_id"])
    if source_context.get("user_tier"):
        params["tier"] = source_context["user_tier"]
    return f"{BASE_URL}{path}?{urlencode(params)}"
