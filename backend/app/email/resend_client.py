from __future__ import annotations

from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from backend.app.core.config import get_settings

_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates")
)

FROM_ADDRESS = "Flashcard Planet <login@flashcardplanet.com>"


def send_waitlist_confirmation_email(to_email: str) -> None:
    """Send a Pro waitlist confirmation email via Resend."""
    resend.api_key = get_settings().resend_api_key
    html = _TEMPLATE_ENV.get_template("waitlist_confirmation.html").render()
    resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": [to_email],
        "subject": "You're on the Flashcard Planet Pro waitlist",
        "html": html,
    })


def send_magic_link_email(to_email: str, magic_url: str) -> None:
    """Send a Magic Link login email via Resend."""
    resend.api_key = get_settings().resend_api_key
    html = _TEMPLATE_ENV.get_template("magic_link.html").render(magic_url=magic_url)
    resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": [to_email],
        "subject": "Your Flashcard Planet login link",
        "html": html,
    })
