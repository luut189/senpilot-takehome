import asyncio
from typing import Protocol

import resend
from resend.exceptions import ResendError
from resend.http_client_httpx import HTTPXClient

from senpilot.config import Settings
from senpilot.errors import DeliveryRejected, DeliveryUnknown


class EmailClient(Protocol):
    async def receive(self, email_id: str) -> dict: ...
    async def send(self, payload: dict, key: str) -> str: ...


class ResendEmail:
    def __init__(self, settings: Settings):
        # The official SDK has global configuration: one account per process.
        resend.api_key = settings.resend_api_key.get_secret_value()
        resend.default_async_http_client = HTTPXClient(timeout=settings.provider_timeout)
        self.timeout = settings.provider_timeout

    async def receive(self, email_id: str) -> dict:
        async with asyncio.timeout(self.timeout):
            value = await resend.Emails.Receiving.get_async(email_id)
        if not isinstance(value, dict) or value.get("id") != email_id:
            raise ValueError("Malformed Receiving API response")
        return value

    async def send(self, payload: dict, key: str) -> str:
        # Same in-memory payload and key across short retries. Never recreate
        # a payload after an uncertain send or after the 24-hour provider window.
        uncertain = False
        for attempt in range(3):
            try:
                async with asyncio.timeout(self.timeout):
                    value = await resend.Emails.send_async(payload, {"idempotency_key": key})
                if not isinstance(value, dict) or not isinstance(value.get("id"), str):
                    raise DeliveryUnknown("Malformed send response")
                if not value["id"]:
                    raise DeliveryUnknown("Missing send identifier")
                return value["id"]
            except ResendError as exc:
                code = str(exc.code)
                if code.startswith("4") and code not in ("408", "409", "429"):
                    if uncertain:
                        raise DeliveryUnknown("Earlier send may have succeeded") from exc
                    raise DeliveryRejected("Provider rejected email") from exc
                if code != "429":
                    uncertain = True
                retry_after = exc.headers.get("retry-after", "")
                delay = min(float(retry_after), 10) if retry_after.isdigit() else 2**attempt
            except (TimeoutError, RuntimeError):
                uncertain = True
                delay = 2**attempt
            if attempt < 2:
                await asyncio.sleep(delay)
        if uncertain:
            raise DeliveryUnknown("Provider acceptance could not be confirmed")
        raise DeliveryRejected("Provider rate limit exhausted")


class MemoryEmail:
    """Injectable local/test transport. Does not make external requests."""

    def __init__(self, messages: dict | None = None):
        self.messages = messages or {}
        self.sent: dict[str, dict] = {}

    async def receive(self, email_id: str) -> dict:
        return self.messages[email_id]

    async def send(self, payload: dict, key: str) -> str:
        self.sent.setdefault(key, payload)
        return "mock-" + key
