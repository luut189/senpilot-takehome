import json

import pytest
import resend
from resend.http_client_async import AsyncHTTPClient

from senpilot.email_client import ResendEmail
from senpilot.errors import DeliveryRejected, DeliveryUnknown


class MockHTTP(AsyncHTTPClient):
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def request(self, method, url, headers, **kwargs):
        self.calls.append((method, url, headers, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        status, body = response
        return json.dumps(body).encode(), status, {"content-type": "application/json"}


@pytest.mark.asyncio
async def test_official_sdk_methods_and_idempotency(settings, monkeypatch):
    transport = ResendEmail(settings)
    monkeypatch.setattr(resend, "api_key", "re_fixture")
    http = MockHTTP(
        [(200, {"id": "incoming", "text": "exhibits M12205"}), (200, {"id": "outgoing"})]
    )
    monkeypatch.setattr(resend, "default_async_http_client", http)
    assert (await transport.receive("incoming"))["text"] == "exhibits M12205"
    assert (
        await transport.send(
            {"from": "a@example.com", "to": ["b@example.com"], "text": "test", "subject": "test"},
            "stable-key",
        )
        == "outgoing"
    )
    assert http.calls[0][1].endswith("/emails/receiving/incoming")
    assert http.calls[1][2]["Idempotency-Key"] == "stable-key"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,exception", [({"name": "validation_error", "message": "bad"}, DeliveryRejected)]
)
async def test_rejected(settings, monkeypatch, body, exception):
    transport = ResendEmail(settings)
    monkeypatch.setattr(resend, "api_key", "re_fixture")
    monkeypatch.setattr(resend, "default_async_http_client", MockHTTP([(422, body)]))
    with pytest.raises(exception):
        await transport.send({}, "key")


@pytest.mark.asyncio
async def test_malformed_send_is_unknown(settings, monkeypatch):
    transport = ResendEmail(settings)
    monkeypatch.setattr(resend, "api_key", "re_fixture")
    monkeypatch.setattr(resend, "default_async_http_client", MockHTTP([(200, {})]))
    with pytest.raises(DeliveryUnknown):
        await transport.send({}, "key")


@pytest.mark.asyncio
async def test_transient_retry_keeps_same_payload_and_key(settings, monkeypatch):
    import senpilot.email_client as module

    async def no_wait(_):
        pass

    monkeypatch.setattr(module.asyncio, "sleep", no_wait)
    transport = ResendEmail(settings)
    monkeypatch.setattr(resend, "api_key", "re_fixture")
    http = MockHTTP(
        [(429, {"name": "rate_limit_exceeded", "message": "limited"}), (200, {"id": "accepted"})]
    )
    monkeypatch.setattr(resend, "default_async_http_client", http)
    assert await transport.send({"text": "same payload"}, "same-key") == "accepted"
    assert len(http.calls) == 2
    assert all(c[2]["Idempotency-Key"] == "same-key" for c in http.calls)
    assert http.calls[0][3] == http.calls[1][3]


@pytest.mark.asyncio
async def test_timeout_stays_unknown_after_retries(settings, monkeypatch):
    import senpilot.email_client as module

    async def no_wait(_):
        pass

    monkeypatch.setattr(module.asyncio, "sleep", no_wait)
    transport = ResendEmail(settings)
    monkeypatch.setattr(resend, "api_key", "re_fixture")
    monkeypatch.setattr(
        resend,
        "default_async_http_client",
        MockHTTP([TimeoutError(), TimeoutError(), TimeoutError()]),
    )
    with pytest.raises(DeliveryUnknown):
        await transport.send({}, "same-key")
