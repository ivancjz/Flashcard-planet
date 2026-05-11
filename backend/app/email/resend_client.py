from __future__ import annotations

from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from backend.app.core.config import get_settings

_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates")
)

# TODO: switch back to login@flashcardplanet.com once domain verified in Resend
FROM_ADDRESS = "Flashcard Planet <onboarding@resend.dev>"


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


def send_trial_started_email(to_email: str, trial_ends_at: str) -> None:
    """Send a trial-started welcome email via Resend."""
    settings = get_settings()
    app_url = settings.app_url or "https://flashcard-planet.up.railway.app"
    resend.api_key = settings.resend_api_key
    html = _TEMPLATE_ENV.get_template("trial_started.html").render(
        app_url=app_url,
        trial_ends_at=trial_ends_at,
    )
    resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": [to_email],
        "subject": "Your 7-day Pro trial has started",
        "html": html,
    })


def send_trial_expiring_soon_email(to_email: str, trial_ends_at: str, app_url: str) -> None:
    """Send a day-6 conversion email via Resend."""
    resend.api_key = get_settings().resend_api_key
    html = _TEMPLATE_ENV.get_template("trial_expiring_soon.html").render(
        app_url=app_url,
        trial_ends_at=trial_ends_at,
    )
    resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": [to_email],
        "subject": "Your Pro trial ends tomorrow — keep your access",
        "html": html,
    })


def send_digest_email(to_email: str, subject: str, html: str) -> None:
    """Send a Market Digest email via Resend."""
    resend.api_key = get_settings().resend_api_key
    resend.Emails.send({
        "from": FROM_ADDRESS,
        "to": [to_email],
        "subject": subject,
        "html": html,
    })
