# Senpilot Regulatory Document Agent

Implementation is staged in the requested milestones:

1. **Prove the scraper:** live M12205 lookup, metadata/count extraction, and a
   real one-document download demonstrated. See [evidence and investigation](docs/investigation.md).
   The Python port still needs execution with installed dependencies.
2. **Complete local pipeline:** pending — virtualized first-ten enumeration,
   all category layouts, partial results, size limits, ZIP creation, fetch CLI.
3. **Get Resend working:** pending — signature verification, Receiving API,
   SQLite jobs, bounded worker, outbound replies and delivery idempotency.
4. **Polish:** pending — full integration suite, structured logs, Docker/Compose,
   configuration and operational documentation.

The first milestone intentionally does not introduce email or infrastructure
before verifying the real website. This repository is **not yet the completed
email application**. No assignment PDF was available locally.

## Repeating the Python proof

Python 3.12+ and uv are required. On a machine with PyPI and browser-download access:

```sh
uv sync
uv run playwright install --with-deps chromium
uv run python -m senpilot.proof M12205 --output ./proof-downloads/python-run-1
```

Choose a new output directory for each run. The proof reads the live matter
overview, verifies its identifier, records all five counts, and attempts the first
Other Document through the site's download dialog, with one retry for a download
event timeout. It writes the file and `result.json`. Exceptions exit nonzero.

This Python port has **not yet been run**: package installation was blocked by
PyPI DNS access in the implementation environment. There is no lockfile yet
because dependency resolution did not complete. The proof is limited to one
Other Document and checks size after transfer; it is not the final fetch CLI.

The independent investigation procedure is also preserved in
`scripts/prove-scraper.js`, for environments with `playwright-cli` installed:

```sh
playwright-cli -s=proof open
playwright-cli -s=proof run-code "$(cat scripts/prove-scraper.js)"
playwright-cli -s=proof close
```

The script contains a fixed representative matter solely for the optional live
proof. Application selectors and parsing do not hardcode matter metadata/counts.
See the investigation for the distinction between verified individual steps and
the saved script's execution status.

## Tests

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The pure validation tests also run without third-party dependencies:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

**Executed:** 9 unittest tests passed, source compilation passed, two live PDFs
downloaded with identical SHA-256 hashes. **Not executed:** pytest, Ruff, Python
Playwright integration, Docker, or Resend. Normal validation tests have no network
or credential requirements; the proof command intentionally accesses the live site.

## Implementation notes

`scraper/selectors.py` contains the inspected FileMaker layout selectors.
`scraper/validation.py` contains independently tested validation. `proof.py`
combines those with Playwright and a Pydantic evidence model. Later milestones
will reuse these pieces behind the scraper interface.

Matter overview fields must be read before switching layouts. FileMaker reuses
object numbers across screens, and its date labels are inconsistent. Counts must
be present and unambiguous; an absent count is never treated as zero. Metadata in
`docs/proof-result.json` is historical evidence only.
