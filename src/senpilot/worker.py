import asyncio
import logging
import tempfile
import time
from pathlib import Path

from senpilot.archive import create_archive
from senpilot.errors import AgentError, DeliveryRejected, DeliveryUnknown
from senpilot.logging import job_context
from senpilot.models import InboundMessage, JobResult, JobStatus
from senpilot.templates import payload_for

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, settings, store, scraper, email):
        self.settings, self.store, self.scraper, self.email = settings, store, scraper, email
        self.wake = asyncio.Event()
        self.stopping = False
        self.task = None

    def start(self):
        self.store.recover()
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        self.stopping = True
        self.wake.set()
        try:
            await asyncio.wait_for(asyncio.shield(self.task), self.settings.shutdown_timeout)
        except TimeoutError:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def run(self):
        while not self.stopping:
            self.wake.clear()
            row = self.store.claim()
            if row is None:
                await self.wake.wait()
            else:
                await self.process(row)

    async def process(self, row):
        started = time.monotonic()
        job_id = row["id"]
        token = job_context.set(job_id)
        log.info("job_processing", extra={"job_id": job_id, "state": "processing"})
        message = InboundMessage.model_validate_json(row["message"])
        result = JobResult()
        sending = False
        self.settings.temp_root.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(
                prefix=f"{job_id}-", dir=self.settings.temp_root
            ) as tmp:
                root = Path(tmp)
                scrape = None
                archive = None
                error = message.error
                if message.request:
                    try:
                        scrape = await self.scraper.fetch_matter_documents(
                            message.request, root, self.settings.max_files
                        )
                        result.downloaded = len(scrape.successful)
                        result.attempted = len(scrape.documents)
                        archive = create_archive(scrape, root, self.settings.max_zip_bytes)
                        if not scrape.documents:
                            error = "The requested document category is empty."
                            result.error = "category_empty"
                        elif result.downloaded != result.attempted:
                            result.error = (
                                "partial_download" if result.downloaded else "all_downloads_failed"
                            )
                    except AgentError as exc:
                        result.error = exc.category
                        error = str(exc)
                    except Exception:
                        result.error = "internal"
                        error = "An internal error prevented completion. Please try again later."
                else:
                    result.error = "invalid_request"
                payload, attached = payload_for(message, self.settings, scrape, archive, error)
                if archive and not attached:
                    result.error = "email_size"
                self.store.mark_sending(job_id)
                sending = True
                result.provider_id = await self.email.send(payload, f"senpilot/{job_id}")
                result.attachment_sent = attached
                status = JobStatus.FAILED if result.error else JobStatus.COMPLETED
                self.store.finish(job_id, status, result)
        except DeliveryRejected:
            result.error = "delivery_rejected"
            self.store.finish(job_id, JobStatus.FAILED, result)
        except DeliveryUnknown:
            result.error = "delivery_unknown"
            self.store.finish(job_id, JobStatus.DELIVERY_UNKNOWN, result)
        except BaseException as exc:
            result.error = "interrupted" if isinstance(exc, asyncio.CancelledError) else "internal"
            self.store.finish(
                job_id, JobStatus.DELIVERY_UNKNOWN if sending else JobStatus.FAILED, result
            )
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
        finally:
            log.info(
                "job_finished",
                extra={
                    "job_id": job_id,
                    "matter_number": message.request.matter_number if message.request else None,
                    "document_type": message.request.document_type if message.request else None,
                    "state": self.store.get(job_id)["status"],
                    "downloaded": result.downloaded,
                    "duration": round(time.monotonic() - started, 3),
                    "error_category": result.error,
                },
            )
            job_context.reset(token)
