import asyncio
import logging
import re
import shutil
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from senpilot.config import Settings
from senpilot.errors import AgentError
from senpilot.models import DocumentMetadata, DocumentRequest, MatterMetadata, ScrapeResult
from senpilot.scraper.selectors import DIRECT_EDITOR, DIRECT_INPUT, MATTER_FIELDS, URL
from senpilot.scraper.validation import parse_counts, safe_filename

log = logging.getLogger(__name__)

# FileMaker's rows are recycled. Read the rendered position along with all field
# values atomically, then address a document by identity, never a stale row index.
ROW_DATA = """rows => rows.map(row => ({
 fields: [...row.querySelectorAll('.fm-textarea .text')].map(e => e.innerText.trim()),
 y: Number((row.style.transform.match(/translate3d\\([^,]+,\\s*([\\d.]+)px/) || [])[1]),
 height: parseFloat(row.style.height)
}))"""


def parse_row(raw: dict) -> DocumentMetadata:
    fields = [v for v in raw["fields"] if v]
    ids = [v for v in fields if re.fullmatch(r"(?:[0-9]{5,}|[A-Z]+-[0-9]+(?:\.[0-9]+)?)", v)]
    extensions = [v for v in fields if re.fullmatch(r"\.[A-Za-z0-9]{1,12}", v)]
    dates = [v for v in fields if re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", v)]
    security = [v for v in fields if v.lower() in ("public", "confidential", "restricted")]
    remaining = [
        v
        for v in fields
        if v not in ids + extensions + dates + security
        and not re.fullmatch(r"(?:E|Ex)[- ]?[0-9]+(?:\.[0-9]+)?", v, re.I)
    ]
    if len(ids) != 1 or len(extensions) != 1 or len(remaining) != 1 or len(dates) > 1:
        raise AgentError("website_structure", "Unrecognized document row fields")
    height, y = raw["height"], raw["y"]
    if not height or y is None or y < 0 or y % height:
        raise AgentError("website_structure", "Cannot determine displayed document order")
    return DocumentMetadata(
        document_number=ids[0],
        title=remaining[0],
        date=dates[0] if dates else None,
        security=security[0] if security else None,
        extension=extensions[0],
        position=int(y / height),
    )


async def save_download(download, path: Path, spool: Path, maximum: int, timeout: int):
    """Monitor browser spool size while transfer completes; cancel excess transfers.

    The polling interval bounds detection latency, not byte overshoot. Docker's
    tmpfs cap provides a second disk bound. A final size check is authoritative.
    """
    task = asyncio.create_task(download.save_as(path))
    try:
        async with asyncio.timeout(timeout):
            while not task.done():
                size = sum(p.stat().st_size for p in spool.rglob("*") if p.is_file())
                if size > maximum:
                    raise AgentError("file_size", "Download exceeds configured size budget")
                await asyncio.wait({task}, timeout=0.1)
            await task
            if await download.failure():
                raise AgentError("file_download", "Browser reported a failed download")
            if not 0 < path.stat().st_size <= maximum:
                raise AgentError("file_size", "Downloaded file is empty or too large")
    except BaseException:
        await download.cancel()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        path.unlink(missing_ok=True)
        raise
    finally:
        await download.delete()


class Scraper:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch_matter_documents(
        self, request: DocumentRequest, output: Path, limit: int = 10
    ) -> ScrapeResult:
        if not 1 <= limit <= 10:
            raise ValueError("limit must be between 1 and 10")
        output.mkdir(parents=True, exist_ok=True)
        spool = output / ".browser"
        spool.mkdir(exist_ok=False)
        try:
            async with asyncio.timeout(self.settings.job_timeout):
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(
                        channel=self.settings.chromium_channel,
                        downloads_path=spool,
                        headless=self.settings.headless,
                    )
                    try:
                        context = await browser.new_context(accept_downloads=True)
                        page = await context.new_page()
                        page.set_default_timeout(self.settings.navigation_timeout * 1000)
                        return await self._fetch(page, request, output, spool, limit)
                    finally:
                        await browser.close()
        except AgentError:
            raise
        except (PlaywrightTimeout, TimeoutError) as exc:
            raise AgentError("navigation_timeout", "The regulatory site timed out") from exc
        except PlaywrightError as exc:
            raise AgentError("browser_session", "Browser or website session failed") from exc
        finally:
            shutil.rmtree(spool, ignore_errors=True)

    async def _fetch(self, page, request, output, spool, limit):
        await page.goto(URL, wait_until="domcontentloaded")
        await page.locator(DIRECT_INPUT).dblclick()
        editor = page.locator(DIRECT_EDITOR)
        await editor.fill(request.matter_number)
        await editor.press("Tab")
        await (
            page.locator(MATTER_FIELDS["matter_number"])
            .or_(page.get_by_role("dialog"))
            .first.wait_for()
        )
        if await page.get_by_role("dialog").count():
            text = await page.get_by_role("dialog").inner_text()
            if re.search(r"no matching records|not found", text, re.I):
                raise AgentError("matter_not_found", "The requested matter was not found")
            raise AgentError("website_structure", "Unexpected matter lookup dialog")
        fields = {
            key: (await page.locator(selector).inner_text()).strip() or None
            for key, selector in MATTER_FIELDS.items()
        }
        if fields["matter_number"] != request.matter_number:
            raise AgentError("website_structure", "Website returned a different matter")
        try:
            counts = parse_counts(await page.get_by_role("button").all_inner_texts())
            matter = MatterMetadata(**fields, counts=counts)
        except ValueError as exc:
            raise AgentError("website_structure", "Matter metadata is incomplete") from exc
        result = ScrapeResult(matter=matter, document_type=request.document_type)
        wanted = min(limit, counts[request.document_type])
        if wanted == 0:
            return result
        await page.get_by_role(
            "button", name=re.compile(rf"^{re.escape(request.document_type.value)} -")
        ).click()
        rows = page.get_by_role("row").filter(
            has=page.get_by_role("button", name="GO GET IT", exact=True)
        )
        await rows.first.wait_for()
        scroller = page.locator(".v-grid-scroller-vertical")
        selected = {}
        height = None
        for _ in range(12):
            raw_rows = await rows.evaluate_all(ROW_DATA)
            for raw in raw_rows:
                doc = parse_row(raw)
                if doc.position < wanted:
                    previous = selected.get(doc.position)
                    if previous and previous.document_number != doc.document_number:
                        raise AgentError("website_structure", "Listing changed during enumeration")
                    selected[doc.position] = doc
                height = raw["height"]
            if set(selected) == set(range(wanted)):
                break
            before = await rows.all_inner_texts()
            await scroller.evaluate("e => { e.scrollTop += e.clientHeight; }")
            await page.wait_for_function(
                "old => [...document.querySelectorAll('tr[role=row]')]"
                ".map(e=>e.innerText).join('|') !== old",
                arg="|".join(before),
            )
        if set(selected) != set(range(wanted)):
            raise AgentError(
                "website_structure", "Could not enumerate the first requested documents"
            )
        result.documents = [selected[i] for i in range(wanted)]
        total = 0
        for doc in result.documents:
            log.info(
                "download_started",
                extra={
                    "matter_number": request.matter_number,
                    "document_type": request.document_type.value,
                    "document_number": doc.document_number,
                },
            )
            try:
                if total >= self.settings.max_total_bytes:
                    raise AgentError("total_size", "Total download budget exhausted")
                await scroller.evaluate("(e, y) => { e.scrollTop = y; }", doc.position * height)
                row = rows.filter(has=page.get_by_text(doc.document_number, exact=True))
                await row.wait_for()
                await self._download(
                    page,
                    row,
                    doc,
                    output,
                    spool,
                    min(self.settings.max_file_bytes, self.settings.max_total_bytes - total),
                )
                total += doc.size
            except (AgentError, PlaywrightError, TimeoutError) as exc:
                doc.error = (
                    exc.category
                    if isinstance(exc, AgentError)
                    else (
                        "download_timeout"
                        if isinstance(exc, (PlaywrightTimeout, TimeoutError))
                        else "file_download"
                    )
                )
                log.warning(
                    "download_failed",
                    extra={"document_number": doc.document_number, "error_category": doc.error},
                )
        return result

    async def _download(self, page, row, doc, output, spool, budget):
        dialog = page.get_by_role("dialog")
        for attempt in range(2):
            await row.get_by_role("button", name="GO GET IT", exact=True).click()
            try:
                button = dialog.get_by_role(
                    "button", name=re.compile(r"^[^/\\]+\.[A-Za-z0-9]{1,12}$")
                )
                await button.wait_for()
                # The dialog can render before WebDirect finishes its server
                # action. Wait for its client and outstanding requests to settle.
                await page.wait_for_function(
                    "() => Object.values(window.vaadin?.clients || {})"
                    ".every(client => !client.isActive())"
                )
                await page.wait_for_load_state("networkidle")
                log.info("download_dialog_ready", extra={"document_number": doc.document_number})
                if await button.count() != 1:
                    raise AgentError("website_structure", "Expected one file for selected document")
                name = (await button.inner_text()).strip()
                # Exhibit labels differ from the server's filename. Read the
                # actual filename from this selected row's download dialog.
                path = output / f"{doc.position + 1:02d}_{safe_filename(name)}"
                async with page.expect_download(
                    timeout=self.settings.download_timeout * 1000
                ) as event:
                    await button.click()
                    # WebDirect holds the export request while this dialog is
                    # open. Close it before awaiting the download event.
                    await dialog.get_by_role("button", name="Close", exact=True).click()
                    log.info(
                        "download_dialog_closed", extra={"document_number": doc.document_number}
                    )
                download = await event.value
                log.info(
                    "download_transfer_started", extra={"document_number": doc.document_number}
                )
                await save_download(download, path, spool, budget, self.settings.download_timeout)
                doc.path = path
                doc.size = path.stat().st_size
                return
            except (PlaywrightTimeout, TimeoutError):
                if attempt:
                    raise
            finally:
                if await dialog.count():
                    close = dialog.get_by_role("button", name=re.compile(r"^(Close|OK)$"))
                    if await close.count() == 1:
                        await close.click()
                    else:
                        raise AgentError("website_structure", "Cannot close download dialog safely")
