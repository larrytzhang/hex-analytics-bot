"""Slack event parser.

Converts raw Slack event dicts into normalized SlackRequest objects.
Validates required fields and strips bot mentions from message text.
"""

import re
from datetime import datetime, timezone

from hex.shared.errors import EventValidationError
from hex.shared.models import SlackRequest


def parse(raw_event: dict) -> SlackRequest:
    """Parse a raw Slack event dict into a SlackRequest.

    Extracts and validates all required fields, strips bot mentions
    from the text, and resolves the thread_ts for reply threading.

    Args:
        raw_event: The raw event dict from Slack's event API.

    Returns:
        A normalized SlackRequest instance.

    Raises:
        EventValidationError: If required fields are missing from the event.
    """
    # Extract the event payload (nested under 'event' key in Slack events)
    event = raw_event.get("event", raw_event)

    # Validate required fields
    required = ["channel", "text", "user", "ts"]
    missing = [f for f in required if not event.get(f)]
    if missing:
        raise EventValidationError(
            f"Slack event missing required fields: {', '.join(missing)}"
        )

    raw_text = event.get("text", "")
    clean_text = _strip_bot_mention(raw_text)

    # Resolve thread_ts: use thread_ts if present, otherwise use message ts
    thread_ts = event.get("thread_ts", event.get("ts", ""))

    return SlackRequest(
        event_id=raw_event.get("event_id", event.get("client_msg_id", "")),
        team_id=raw_event.get("team_id", event.get("team", "")),
        channel_id=event["channel"],
        thread_ts=thread_ts,
        message_ts=event["ts"],
        user_id=event["user"],
        raw_text=raw_text,
        clean_text=clean_text,
        received_at=datetime.now(timezone.utc).isoformat(),
    )


def _strip_bot_mention(text: str) -> str:
    """Remove Slack bot mention tags from message text.

    Strips patterns like '<@U12345678>' and trims whitespace.

    Args:
        text: Raw message text potentially containing bot mentions.

    Returns:
        Cleaned text with bot mentions removed.
    """
    return re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()
