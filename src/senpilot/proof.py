"""Milestone 1: one-document proof, deliberately limited to Other Documents.

Historical investigation helper. Use senpilot.cli for the maintained pipeline;
see README.md for setup and validation status.
"""

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright
from pydantic import BaseModel

from senpilot.scraper.selectors import (
    DIRECT_EDITOR,
    DIRECT_INPUT,
    MATTER_FIELDS,
    OTHER_DOCUMENT_FIELDS,
    URL,
)
from senpilot.scraper.validation import normalize_matter, parse_counts, safe_filename


class ProofResult(BaseModel):
    matter: dict[str, str | None]
    counts: dict[str, int]
    document: dict[str, str]
    file: str
    bytes: int
    sha256: str


async def fetch_one(matter_number: str, output: Path, *, timeout_ms: int = 60_000) -> ProofResult:
    """Download the first displayed Other Document; never substitute another row.

    Output must be a new directory so a proof cannot overwrite previous evidence.
    This proof checks size after transfer; streaming size limits belong to milestone 2.
    """
    matter_number = normalize_matter(matter_number)
    output.mkdir(parents=True, exist_ok=False)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chromium")
        try:
            async with await browser.new_context(accept_downloads=True) as context:
                page = await context.new_page()
                page.set_default_timeout(timeout_ms)
                await page.goto(URL, wait_until="domcontentloaded")
                await page.locator(DIRECT_INPUT).dblclick()
                editor = page.locator(DIRECT_EDITOR)
                await editor.fill(matter_number)
                # WebDirect's field-exit trigger performs the lookup. A second
                # Search click races navigation and can target a different layout.
                await editor.press("Tab")
                await page.locator(MATTER_FIELDS["matter_number"]).wait_for()
                matter = {}
                for key, selector in MATTER_FIELDS.items():
                    matter[key] = (await page.locator(selector).inner_text()).strip() or None
                if matter["matter_number"] != matter_number:
                    raise RuntimeError("Loaded matter does not match requested matter")
                counts = parse_counts(await page.get_by_role("button").all_inner_texts())
                if counts["Other Documents"] == 0:
                    raise RuntimeError("Requested category is empty")
                await page.get_by_role("button", name=re.compile(r"^Other Documents -")).click()
                row = (
                    page.get_by_role("row")
                    .filter(has=page.get_by_role("button", name="GO GET IT", exact=True))
                    .first
                )
                await row.wait_for()
                document = {
                    key: (await row.locator(selector).inner_text()).strip()
                    for key, selector in OTHER_DOCUMENT_FIELDS.items()
                }
                expected_name = document["document_number"] + document["extension"]
                if not re.fullmatch(r"[0-9]+\.[A-Za-z0-9]+", expected_name):
                    raise RuntimeError("Unexpected document number or extension")
                dialog = page.get_by_role("dialog")
                for attempt in range(2):
                    await row.get_by_role("button", name="GO GET IT", exact=True).click()
                    button = dialog.get_by_role("button", name=expected_name, exact=True)
                    await button.wait_for()
                    try:
                        async with page.expect_download(timeout=timeout_ms) as event:
                            await button.click(no_wait_after=True)
                        download = await event.value
                        async with asyncio.timeout(timeout_ms / 1000):
                            await download.save_as(output / safe_filename(expected_name))
                            failure = await download.failure()
                        if failure:
                            raise RuntimeError(f"Download failed: {failure}")
                        break
                    except PlaywrightTimeout:
                        if attempt == 1:
                            raise
                    finally:
                        if await dialog.count():
                            await dialog.get_by_role("button", name="Close", exact=True).click()
                path = output / safe_filename(expected_name)
                size = path.stat().st_size
                if not 0 < size <= 25 * 1024 * 1024:
                    path.unlink()
                    raise RuntimeError("Downloaded file is empty or exceeds proof size limit")
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                result = ProofResult(
                    matter=matter,
                    counts=counts,
                    document=document,
                    file=path.name,
                    bytes=size,
                    sha256=digest,
                )
                (output / "result.json").write_text(result.model_dump_json(indent=2) + "\n")
                return result
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matter", type=normalize_matter)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(fetch_one(args.matter, args.output))
    except Exception as exc:
        parser.exit(1, f"Proof failed ({type(exc).__name__}): {exc}\n")
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
