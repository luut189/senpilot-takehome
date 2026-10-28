from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from senpilot.errors import AgentError
from senpilot.models import DocumentRequest, DocumentType
from senpilot.scraper.client import Scraper, parse_row


@pytest.mark.parametrize(
    "fields",
    [
        ["102674", "Board Order", "07/08/2026", "Public", ".pdf"],
        ["Board Order", "07/08/2026", "Public", "102674", ".pdf"],
    ],
)
def test_observed_row_orders(fields):
    doc = parse_row({"fields": fields, "y": 68, "height": 68})
    assert doc.document_number == "102674" and doc.position == 1


def test_unexpected_row_fails_closed():
    with pytest.raises(AgentError):
        parse_row({"fields": ["102674", "title", "unexpected field", ".pdf"], "y": 0, "height": 68})


@pytest.mark.asyncio
async def test_captured_live_exhibit_dom():
    from senpilot.scraper.client import ROW_DATA

    html = Path(__file__).with_name("fixtures").joinpath("observed_exhibit.html").read_text()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chromium")
        try:
            page = await browser.new_page()
            await page.set_content(html)
            rows = await page.get_by_role("row").evaluate_all(ROW_DATA)
            document = parse_row(rows[0])
            assert document.document_number == "H-1"
            assert document.title == "Application"
        finally:
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_virtual_order_limit_and_partial_download(tmp_path, settings, failure):
    settings.download_timeout = 1
    settings.navigation_timeout = 3
    fixture = Path(__file__).with_name("fixtures").joinpath("webdirect.html").read_text()
    if failure:
        fixture = fixture.replace(
            "const fail = Number(params.get('fail') || -1);", "const fail = 1;"
        )
    spool = tmp_path / ".browser"
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
            result = await Scraper(settings)._fetch(
                page,
                DocumentRequest(matter_number="M12205", document_type=DocumentType.OTHER),
                tmp_path,
                spool,
                10,
            )
            assert [d.document_number for d in result.documents] == [
                str(10000 + i) for i in range(10)
            ]
            assert len(result.successful) == (9 if failure else 10)
            if failure:
                assert result.documents[1].error == "download_timeout"
            assert all(d.path.stat().st_size > 0 for d in result.successful)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_live_m12205_opt_in(tmp_path):
    import os

    if os.getenv("SENPILOT_LIVE_TEST") != "1":
        pytest.skip("Set SENPILOT_LIVE_TEST=1 to access the live site")
    from senpilot.config import Settings

    result = await Scraper(Settings()).fetch_matter_documents(
        DocumentRequest(matter_number="M12205", document_type=DocumentType.OTHER), tmp_path, 1
    )
    assert result.matter.matter_number == "M12205"
    assert len(result.successful) == 1
