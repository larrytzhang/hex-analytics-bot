"""Slack response sender.

Sends SlackResponse payloads back to Slack channels using the
Slack SDK's WebClient. Wraps calls with rate limiter for 429 handling.
"""

import logging

from hex.shared.errors import ResponseDeliveryError
from hex.shared.models import ResponseType, SlackResponse

from hex.gateway.middleware.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class ResponseSender:
    """Sends formatted responses back to Slack.

    Uses the Slack WebClient to post messages in-thread.
    All outbound calls are wrapped with the rate limiter.

    Attributes:
        _client:       Slack AsyncWebClient for API calls.
        _rate_limiter: RateLimiter for 429 retry handling.
    """

    def __init__(self, client, rate_limiter: RateLimiter) -> None:
        """Initialize the response sender.

        Args:
            client:       Slack AsyncWebClient instance.
            rate_limiter: RateLimiter for handling 429 responses.
        """
        self._client = client
        self._rate_limiter = rate_limiter

    async def send(self, response: SlackResponse) -> None:
        """Send a SlackResponse back to the Slack channel.

        Posts text messages in-thread. For TEXT_AND_IMAGE responses,
        sends just the text (image upload is handled by the orchestrator
        via files_upload_v2).

        Args:
            response: The SlackResponse payload to send.

        Raises:
            ResponseDeliveryError: If the Slack API call fails after retries.
        """
        try:
            if response.response_type in (ResponseType.TEXT, ResponseType.TEXT_AND_IMAGE):
                await self._rate_limiter.call_with_retry(
                    self._client.chat_postMessage,
                    channel=response.channel_id,
                    thread_ts=response.thread_ts,
                    text=response.text,
                )
            logger.info(
                "Response sent to channel=%s thread=%s type=%s",
                response.channel_id,
                response.thread_ts,
                response.response_type.name,
            )
        except ResponseDeliveryError:
            raise
        except Exception as e:
            error_msg = str(e)
            # Permanent errors (channel_not_found) — log, do NOT retry
            if "channel_not_found" in error_msg or "not_in_channel" in error_msg:
                logger.error("Permanent Slack error (no retry): %s", error_msg)
                raise ResponseDeliveryError(f"Permanent Slack error: {e}") from e

            # Transient errors — retry up to 2 times
            for attempt in range(2):
                try:
                    await self._client.chat_postMessage(
                        channel=response.channel_id,
                        thread_ts=response.thread_ts,
                        text=response.text,
                    )
                    return
                except Exception:
                    if attempt == 1:
                        raise ResponseDeliveryError(
                            f"Slack send failed after retries: {e}"
                        ) from e
