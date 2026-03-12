"""Gateway-specific helpers for SlackResponse.

Imports SlackResponse from shared/models.py (the canonical type)
and provides gateway-level formatting utilities.
"""

from hex.shared.models import SlackResponse, ResponseType


def is_text_only(response: SlackResponse) -> bool:
    """Check if a response is text-only (no image).

    Args:
        response: The SlackResponse to check.

    Returns:
        True if the response type is TEXT, False otherwise.
    """
    return response.response_type == ResponseType.TEXT
