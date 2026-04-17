from __future__ import annotations

import os
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

resend.api_key = os.environ.get("RESEND_API_KEY", "")

_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates")
)

FROM_ADDRESS = "Flashcard Planet <login@flashcardplanet.com>"


def send_magic_link_email(to_email: str, magic_url: str) -> None:
    """Send a Magic Link login email via Resend."""
    html = _TEMPLATE_ENV.get_template("magic_link.html").render(magic_url=magic_url)
    resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": [to_email],
        "subject": "Your Flashcard Planet login link",
        "html": html,
    })
