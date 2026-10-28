import asyncio
import fcntl
import json
import logging
from contextlib import asynccontextmanager
from email.utils import parseaddr
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from svix.webhooks import Webhook, WebhookVerificationError

from senpilot.config import Settings
from senpilot.email_client import ResendEmail
from senpilot.email_parser import parse_inbound
from senpilot.logging import configure_logging
from senpilot.persistence import JobStore
from senpilot.scraper.client import Scraper
from senpilot.worker import Worker

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, email=None, scraper=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        lock = settings.database_path.with_suffix(".lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError("Only one application instance may use this database") from None
        store = JobStore(settings.database_path, settings.queue_capacity)
        app.state.store = store
        app.state.email = email or ResendEmail(settings)
        worker = Worker(settings, store, scraper or Scraper(settings), app.state.email)
        app.state.worker = worker
        app.state.ingress_lock = asyncio.Lock()
        worker.start()
        try:
            yield
        finally:
            await worker.stop()
            store.close()
            lock.close()

    app = FastAPI(title="Senpilot Regulatory Document Agent", lifespan=lifespan)

    @app.get("/health")
    async def health():
        running = not app.state.worker.task.done()
        return JSONResponse(
            {"status": "ok" if running else "unhealthy", "worker_running": running},
            status_code=200 if running else 503,
        )

    @app.post("/webhooks/resend")
    async def webhook(request: Request):
        if not settings.resend_webhook_secret.get_secret_value():
            raise HTTPException(503, "Webhook secret is not configured")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                raise HTTPException(413, "Webhook payload too large")
        try:
            Webhook(settings.resend_webhook_secret.get_secret_value()).verify(
                bytes(body), dict(request.headers)
            )
            event = json.loads(body)
        except (WebhookVerificationError, ValueError, json.JSONDecodeError):
            raise HTTPException(401, "Invalid webhook signature") from None
        if not isinstance(event, dict):
            raise HTTPException(400, "Invalid event")
        if event.get("type") != "email.received":
            return {"status": "ignored"}
        try:
            email_id = str(UUID(event["data"]["email_id"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise HTTPException(400, "Invalid incoming email ID") from None
        existing = app.state.store.by_email(email_id)
        if existing:
            return {"status": "duplicate", "job_id": existing["id"]}
        if app.state.ingress_lock.locked():
            raise HTTPException(503, "Receiving API busy; retry later")
        async with app.state.ingress_lock:
            existing = app.state.store.by_email(email_id)
            if existing:
                return {"status": "duplicate", "job_id": existing["id"]}
            try:
                raw = await app.state.email.receive(email_id)
                message = parse_inbound(raw)
                if (
                    settings.email_from
                    and message.sender.casefold() == parseaddr(settings.email_from)[1].casefold()
                ):
                    return {"status": "ignored"}
                job_id = app.state.store.add(email_id, message)
            except OverflowError:
                raise HTTPException(503, "Job queue full; retry later") from None
            except Exception:
                # Non-2xx asks Resend to retry retrieval; no phantom accepted job.
                raise HTTPException(502, "Unable to retrieve or validate incoming email") from None
            app.state.worker.wake.set()
            log.info("job_queued", extra={"job_id": job_id, "state": "pending"})
        return {"status": "accepted", "job_id": job_id}

    return app


app = create_app()
