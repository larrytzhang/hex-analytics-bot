"""Gateway-specific helpers for SlackRequest.

Imports SlackRequest from shared/models.py (the canonical type)
and provides gateway-level parsing utilities.
"""

import re

from hex.shared.models import SlackRequest


def strip_bot_mention(text: str) -> str:
    """Remove Slack bot mention tags from message text.

    Strips patterns like '<@U12345678>' from the beginning of the text
    and trims whitespace.

    Args:
        text: Raw Slack message text potentially containing bot mentions.

    Returns:
        Cleaned text with bot mentions removed.
    """
    cleaned = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    return cleaned
