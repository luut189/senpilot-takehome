import json
import logging

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from senpilot.errors import AgentError
from senpilot.logging import JsonFormatter
from senpilot.models import DocumentRequest, DocumentType
from senpilot.scraper.client import Scraper, browser_diagnostics


@pytest.mark.parametrize(
    "exception,reason",
    [
        (
            PlaywrightError(
                "BrowserType.launch: Target page, context or browser has been closed\n"
                "[pid=114][err] chrome_crashpad_handler: --database is required"
            ),
            "crashpad_database_unavailable",
        ),
        (
            PlaywrightError(
                "Page.goto: net::ERR_CONNECTION_RESET at https://example.com/?secret=hidden"
            ),
            "ERR_CONNECTION_RESET",
        ),
        (
            PlaywrightError("BrowserType.launch: Executable doesn't exist at /private/path"),
            "browser_not_installed",
        ),
        (
            PlaywrightError("Page.goto: Target page, context or browser has been closed"),
            "browser_closed",
        ),
        (PlaywrightTimeout("Locator.click: Timeout exceeded; private page text"), "timeout"),
        (PlaywrightError("Unrecognized failure with private page text"), "playwright_error"),
    ],
)
def test_safe_diagnostics(exception, reason):
    details = browser_diagnostics(exception)
    assert details["error_reason"] == reason
    record = logging.makeLogRecord({"msg": "browser_failed", "levelname": "ERROR", **details})
    encoded = JsonFormatter().format(record)
    assert json.loads(encoded)["error_reason"] == reason
    assert not any(value in encoded for value in ["hidden", "private", "https://", "secret"])


@pytest.mark.asyncio
async def test_network_failure_logged_and_cleanup_preserved(settings, tmp_path, caplog):
    class BrokenSite(Scraper):
        async def _fetch(self, *args):
            raise PlaywrightError(
                "Page.goto: net::ERR_CONNECTION_RESET at https://example.com/?secret=hidden"
            )

    request = DocumentRequest(matter_number="M12205", document_type=DocumentType.OTHER)
    with pytest.raises(AgentError) as error:
        await BrokenSite(settings).fetch_matter_documents(request, tmp_path, 1)
    assert error.value.category == "browser_session"
    record = next(r for r in caplog.records if r.message == "browser_failed")
    assert record.operation == "Page.goto"
    assert record.error_reason == "ERR_CONNECTION_RESET"
    assert record.stage == "matter_fetch"
    assert record.matter_number == "M12205"
    assert not (tmp_path / ".browser").exists()
