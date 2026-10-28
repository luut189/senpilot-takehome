import base64
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from senpilot.email_client import MemoryEmail
from senpilot.main import create_app

EMAIL_ID = "7c05b465-c0b2-4657-b0d4-d2abae08f44c"


def signed(settings, body, timestamp=None):
    timestamp = str(timestamp or int(time.time()))
    key = base64.b64decode(settings.resend_webhook_secret.get_secret_value()[6:])
    signature = base64.b64encode(
        hmac.new(key, b"event-1." + timestamp.encode() + b"." + body, hashlib.sha256).digest()
    ).decode()
    return {"svix-id": "event-1", "svix-timestamp": timestamp, "svix-signature": "v1," + signature}


def test_signature_receiving_and_duplicate(settings):
    transport = MemoryEmail(
        {
            EMAIL_ID: {
                "id": EMAIL_ID,
                "from": "a@example.com",
                "subject": "Missing request",
                "text": "hello",
            }
        }
    )
    app = create_app(settings, email=transport)
    body = json.dumps({"type": "email.received", "data": {"email_id": EMAIL_ID}}).encode()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/webhooks/resend", content=body).status_code == 401
        assert (
            client.post(
                "/webhooks/resend", content=body + b" ", headers=signed(settings, body)
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/webhooks/resend",
                content=body,
                headers=signed(settings, body, int(time.time()) - 600),
            ).status_code
            == 401
        )
        first = client.post("/webhooks/resend", content=body, headers=signed(settings, body))
        assert first.status_code == 200
        second = client.post("/webhooks/resend", content=body, headers=signed(settings, body))
        assert second.json()["status"] == "duplicate"
        assert first.json()["job_id"] == second.json()["job_id"]
    assert len(transport.sent) == 1


def test_receiving_failure_not_acknowledged(settings):
    app = create_app(settings, email=MemoryEmail())
    body = json.dumps({"type": "email.received", "data": {"email_id": EMAIL_ID}}).encode()
    with TestClient(app) as client:
        assert (
            client.post(
                "/webhooks/resend", content=body, headers=signed(settings, body)
            ).status_code
            == 502
        )


def test_unrelated_event_ignored(settings):
    body = b'{"type":"email.sent"}'
    with TestClient(create_app(settings, email=MemoryEmail())) as client:
        assert (
            client.post("/webhooks/resend", content=body, headers=signed(settings, body)).json()[
                "status"
            ]
            == "ignored"
        )
