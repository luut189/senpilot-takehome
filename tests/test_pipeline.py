"""Offline webhook → real browser fixture → ZIP → mocked provider integration."""

import asyncio
import base64
import io
import json
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from playwright.async_api import async_playwright
from test_webhooks import EMAIL_ID, signed

from senpilot.email_client import MemoryEmail
from senpilot.main import create_app
from senpilot.scraper.client import Scraper


@pytest.mark.asyncio
async def test_full_pipeline(settings):
    fixture = Path(__file__).with_name("fixtures").joinpath("webdirect.html").read_text()
    delivered = asyncio.Event()

    class FixtureScraper(Scraper):
        async def fetch_matter_documents(self, request, output, limit=10):
            spool = output / ".browser"
            spool.mkdir()
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(channel="chromium", downloads_path=spool)
                try:
                    context = await browser.new_context(accept_downloads=True)
                    await context.route(
                        "**/*", lambda route: route.fulfill(content_type="text/html", body=fixture)
                    )
                    page = await context.new_page()
                    page.set_default_timeout(3000)
                    return await self._fetch(page, request, output, spool, limit)
                finally:
                    await browser.close()

    class Email(MemoryEmail):
        async def send(self, payload, key):
            identifier = await super().send(payload, key)
            delivered.set()
            return identifier

    email = Email(
        {
            EMAIL_ID: {
                "id": EMAIL_ID,
                "from": "requester@example.com",
                "subject": "Other Documents for M12205",
                "text": "Please send them.",
                "message_id": "<original@example.com>",
            }
        }
    )
    app = create_app(settings, email=email, scraper=FixtureScraper(settings))
    body = json.dumps({"type": "email.received", "data": {"email_id": EMAIL_ID}}).encode()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/resend", content=body, headers=signed(settings, body)
            )
            assert response.status_code == 200
            job_id = response.json()["job_id"]
            await asyncio.wait_for(delivered.wait(), 30)
            row = app.state.store.get(job_id)
            assert row["status"] == "completed"
            assert json.loads(row["result"])["attachment_sent"] is True
            duplicate = await client.post(
                "/webhooks/resend", content=body, headers=signed(settings, body)
            )
            assert duplicate.json()["status"] == "duplicate"
            assert len(email.sent) == 1
            payload = next(iter(email.sent.values()))
            assert payload["to"] == ["requester@example.com"]
            assert payload["headers"]["In-Reply-To"] == "<original@example.com>"
            with ZipFile(io.BytesIO(base64.b64decode(payload["attachments"][0]["content"]))) as z:
                assert len(z.namelist()) == 10
                assert z.testzip() is None
            assert list(settings.temp_root.iterdir()) == []
