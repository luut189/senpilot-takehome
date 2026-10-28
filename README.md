# Senpilot Regulatory Document Agent

Email a matter number and document category to receive up to ten documents from
Nova Scotia's regulatory database, packaged as a ZIP with a matter summary.
Built with Python 3.12+, FastAPI, Playwright, Resend, and SQLite. No LLM is used.

## Quick start

Install [uv](https://docs.astral.sh/uv/) and GNU Make:

```sh
make setup
make fetch MATTER=M12205 CATEGORY="Other Documents" LIMIT=1
```

Setup installs locked dependencies and Chromium, including system packages that
may require sudo. It creates `.env` if absent and preserves existing settings.
The CLI needs no email credentials. It saves a ZIP to `./downloads`, prints JSON
to stdout, and logs progress to stderr. Use `OUTPUT=./downloads/run-2` for another
run; existing archives are never overwritten.

Categories: **Exhibits**, **Key Documents**, **Other Documents**, **Transcripts**,
and **Recordings**. The default limit is ten, capped by `MAX_FILES`.

## Commands

Run `make` for all commands.

| Command | Purpose |
| --- | --- |
| `make setup` | Install dependencies and Chromium; initialize `.env` |
| `make run` | Start the API and worker at `127.0.0.1:8000` |
| `make fetch` | Retrieve documents without email |
| `make check` | Run lint, formatting checks, and offline tests |
| `make test` | Run offline tests |
| `make format` | Format Python files |
| `make live-test` | Test one download against the real website |
| `make up` | Build and start Docker Compose |
| `make logs` | Follow container logs |
| `make health` | Check the local API |
| `make restart` | Recreate containers after `.env` changes |
| `make down` | Stop containers and preserve job data |

`make run HOST=0.0.0.0 PORT=8080` changes the local bind address and port.
These variables do not change Docker Compose's port mapping.

## Homelab setup

Install Docker with Compose, then:

```sh
make env
# Configure Resend in .env, as described below.
make up
make health
```

The non-root container includes Chromium. Compose persists SQLite in the `jobs`
volume, limits memory to 2 GB, and provides a 512 MB temporary filesystem. Run
**one instance and one Uvicorn worker**.

Expose HTTPS through a reverse proxy targeting `http://127.0.0.1:8000`. The port
binds to host localhost. For a containerized proxy, use a shared Docker network
and `http://agent:8000`. For temporary development, use `ngrok http 8000` or
`cloudflared tunnel --url http://localhost:8000`; temporary URLs may change.

Run `make restart` after editing `.env`. `make down` preserves data;
`docker compose down -v` deletes job history and idempotency records. Back up the
volume while the service is stopped to keep SQLite and its WAL consistent.

## Resend setup

1. Verify a sending domain. Set `RESEND_API_KEY` and `EMAIL_FROM` in `.env`.
   The key must permit receiving-email retrieval and sending.
2. Enable inbound receiving in Resend and configure its required DNS records.
3. Create a webhook for **`email.received`** at
   `https://<your-public-host>/webhooks/resend`.
4. Copy its signing secret into `RESEND_WEBHOOK_SECRET`, then `make restart`.
5. Email your receiving address: `Please send Other Documents from M12205`.

The webhook signature is verified before processing. Because the webhook does
not contain the message body, the app retrieves it through Resend's Receiving
API. Parsing accepts one distinct matter and category, recognizes singular/plural
aliases, and removes common quoted history. Invalid requests receive clarification.
Replies preserve threading when a valid message ID is available. Never commit
credentials; `.env` is excluded from Git and Docker builds.

## Architecture and behavior

FastAPI retrieves and parses the email, then persists a job in SQLite. One
background worker opens an isolated browser session, verifies the matter,
extracts metadata and all five counts, downloads the selected documents in
website order, validates a ZIP, and sends the reply. The CLI shares the scraper
and archive code. Browser automation is independent of email.

The main modules are `scraper/`, `email_parser.py`, `email_client.py`,
`archive.py`, `templates.py`, `persistence.py`, and `worker.py`. SQLite provides a
bounded durable queue and uniqueness by incoming email ID. Structured logs carry
job identifiers, matter/category, state, timing, counts, and error categories.
Full email bodies and downloaded documents are not persisted in the database.

Defaults in `.env.example`: ten files, 60 seconds per download stage, 25 MB per
file, 100 MB total downloads, 25 MB ZIP, and a 35 MB estimated email payload.
The email calculation includes base64 expansion and headroom below Resend's
[40 MB message limit](https://resend.com/docs/dashboard/emails/attachments).
Spool monitoring can briefly overshoot between checks; Compose adds a storage cap.

Failed or restricted files are reported individually, with no later substitutions.
ZIPs contain only successful downloads; oversized archives are omitted with an
explanation. Partial results, empty categories, and invalid requests remain
failed job outcomes even when an explanatory reply is accepted. Provider
acceptance does not prove inbox delivery.

Pending jobs resume after restart. Interrupted processing jobs become `failed`,
or `delivery_unknown` if sending had started, and are never resent automatically.
Short provider retries reuse the same payload and idempotency key. Check Resend
logs before acting on an uncertain delivery. For a confirmed failure, submit a
new email after fixing the cause; replaying the same ID remains a duplicate.
`/health` checks worker liveness, not external service availability.

## Testing and limitations

`make check` runs without network or credentials after Chromium is installed.
Tests use browser fixtures and mocked Resend responses, including the complete
signed-webhook → browser → ZIP → email workflow. `make live-test` is opt-in.

Latest validation: **73 tests passed**, one optional live test skipped, and Ruff
passed. Docker build, non-root Chromium, SQLite, API health, and shutdown passed.
There is one upstream Starlette TestClient deprecation warning.

Live CLI checks downloaded all ten selected M12205 Other Documents in displayed
order, verified the ZIP, retrieved one Key Document, and handled an empty category.
The first public Exhibit exceeded the default limit and was cancelled. A read-only
Resend check verified authentication and the sender domain. A real email round
trip still needs validation after the public webhook is configured.

FileMaker requires JavaScript; observed selectors are centralized but may need
maintenance when the site changes. Unknown structures fail explicitly and missing
metadata is never invented. Conflicting date labels use the matter overview's
meaning. Nonempty Transcripts/Recordings, non-PDF files, missing matters, and
session expiry need further live validation. Confidential/restricted entries are
skipped. There is no alternate attachment storage, horizontal scaling, or bounce
tracking. These tradeoffs keep the application small and maintainable.
