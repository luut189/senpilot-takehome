# Milestone 1 — live scraper investigation

Inspected on **2026-10-27** using Chromium through `playwright-cli`. The target
was https://uarb.novascotia.ca/fmi/webd/UARB15. No assignment PDF was present in
the workspace; the supplied written specification was used.

## Evidence

Opened **M12205**, extracted its live matter screen, selected **Other Documents**,
opened the first displayed document through **GO GET IT → Download Files →
102674.pdf**, and saved a nonempty PDF. Playwright returned `failure: null`.

The operation was repeated in a fresh browser session. The second session's
initial download event timed out after 30 seconds. Closing the dialog, reopening
GO GET IT for the **same document**, and waiting up to 60 seconds succeeded.
Both files have identical sizes and SHA-256 hashes:

- Local evidence: `proof-downloads/102674.pdf` and `proof-downloads/clean-102674.pdf`
- Size: **170,571 bytes** each
- SHA-256: `6a3b3b90596df09605d7a978caf32d7bdbefb4f0b68648388733c2376d45757f`
- `file` identifies a PDF document, version 1.6.
- This is evidence of downloading a PDF, not a claim of full PDF semantic validation.

The two downloaded binaries are ignored by Git; their evidence is recorded in
`docs/proof-result.json`. Live data may change; these are observations, not defaults.

| Field on matter screen | Observed value |
| --- | --- |
| Matter No | M12205 |
| Title - Description | Halifax Regional Water Commission - Windsor Street Exchange Redevelopment Project - $69,275,000 |
| Type | Capital Expenditure Approvals |
| Status | Closed |
| Category | Water |
| Date Received | 04/07/2025 |
| Decision Date | 10/23/2025 |
| Outcome | Directions given |
| Exhibits | 13 |
| Key Documents | 6 |
| Other Documents | 43 |
| Transcripts | 0 |
| Recordings | 0 |

The amount is embedded in the title, not a separately verified financial field.
The document-list layout labels the second date **Date Final Submissions**, while
the matter overview labels it **Decision Date**. Preserve the overview label and
record this inconsistency; do not silently relabel it as final filing.

## Verified interaction details

1. No login was required. The initial URL redirects with `?redirected=true` and
   then loads a FileMaker WebDirect/Vaadin application. Plain HTTP text retrieval
   yields only “Enable JavaScript in your browser to use this application.”
2. The direct-matter input is a custom `.fm_object_254 .text` element, not an
   HTML input or textarea. Double-click it and wait for `contenteditable=true`
   before filling. Typing too early was observed to open **M00001**, making an
   exact post-navigation matter check essential.
3. Pressing **Tab** commits the input and triggers the matter lookup. Do not
   subsequently click Search: the matter is already opening and the original
   search button disappears. There are multiple unrelated Search buttons.
4. The overview field selectors are isolated in `scraper/selectors.py`. Layout
   object numbers are reused on other screens; extract overview metadata before
   entering the category. They are observed selectors, not a public API contract.
5. Category buttons have accessible names such as `Other Documents - 43`.
   All five counts can be read before entering any category.
6. Other Documents uses a virtualized `role=grid`, with `aria-rowcount=43`.
   At the inspected viewport only eight rows were mounted. Its vertical scroller
   is `.v-grid-scroller-vertical` (375px viewport, 2924px scroll extent).
   A first-ten implementation must scroll and wait for new row identities; it
   cannot just call `all()` once. Scrolling/order recovery has **not yet been
   validated**, and the proof intentionally retrieves only the first row.
7. The first displayed Other Document was **102674**, **Board Order**, dated
   **07/08/2026**, marked **Public**, extension **.pdf**. The next seven displayed
   IDs were 102454, 102417, 102329, 102330, 102293, 102295, 102266. Do not sort them.
8. GO GET IT opens an intermediate Download Files dialog. Its filename is a
   button, not a link. Install a download listener **before** clicking that button.
   The observed URL is session-specific under `/fmi/webd/APP/connector/.../dl/`.
   Never persist that URL as a reusable download link.
9. Clicking the filename disables that button. One transfer stalled without
   producing a download event. Reopen the dialog for a bounded retry; never
   repeatedly click the disabled button or replace the document with a later row.
10. Save List ran a server script and offered **OtherDocumentsList.pdf** through
    the same download dialog. This is not a CSV/JSON metadata API. The list PDF
    was not downloaded or parsed; there is no reason to add that dependency.
11. Clicking **Transcripts - 0** produced **No Matching Records / Click Ok to
    return to Matter**. The known zero count allows avoiding that navigation.
12. During early exploratory interactions, “No Matching Records” and
    “Relationship Not Found” dialogs occurred. Their cause is not established.
    A later clean single-document run reached the normal download dialog. Do
    not treat every “No Matching Records” as proof the matter is missing.

## Limits and remaining investigation

- The Python Playwright package could not be installed: PyPI DNS resolution was
  unavailable in the execution environment. A copied local uv cache did not
  contain a usable complete dependency set. No credentials were involved.
- `senpilot.proof` is a Python port of the observed workflow. It was syntax
  checked but **not executed**. Its one-document scope is explicit; it is not
  the milestone-2 fetch CLI or the complete scraper.
- `scripts/prove-scraper.js` preserves the browser procedure for repetition.
  The individual live steps ran successfully. A later attempt to run the saved
  script as a whole was blocked by the CLI daemon's cache directory being
  read-only; do not count that saved-script attempt as a successful run.
- Missing-matter behavior, actual scroll traversal, all category row schemas,
  non-PDF transfers, session expiration, and download-size enforcement during
  transfer still require validation. No rate limit was observed; that does not
  establish the absence of one. Use one active browser job.
- The proof checks file size after transfer. It does not yet provide the full
  application's required bounded transfer storage, archive, jobs, or email flow.

## Checks actually executed

`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`: **9 passed**.
These tests cover identifier validation, count parsing, and safe filenames. They
are also pytest-compatible but were executed with unittest because dependencies
were unavailable. They do not validate browser behavior.

`.venv/bin/python -m compileall -q src tests`: passed.

`file` and `sha256sum` were run on the downloaded evidence. pytest,
pytest-asyncio, Ruff, Python browser integration tests, and Docker checks have
**not** run. No Resend request or outgoing email was sent.
