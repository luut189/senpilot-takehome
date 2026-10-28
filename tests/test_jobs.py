import asyncio
import json

import pytest

from senpilot.email_client import MemoryEmail
from senpilot.errors import DeliveryRejected, DeliveryUnknown
from senpilot.models import DocumentRequest, DocumentType, InboundMessage, JobStatus
from senpilot.persistence import JobStore
from senpilot.worker import Worker


class FixtureScraper:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def fetch_matter_documents(self, request, output, limit):
        self.calls += 1
        result = self.result.model_copy(deep=True)
        for doc in result.successful:
            path = output / doc.path.name
            path.write_bytes(doc.path.read_bytes())
            doc.path = path
        return result


def message():
    return InboundMessage(
        sender="alice@example.com",
        request=DocumentRequest(matter_number="M12205", document_type=DocumentType.OTHER),
    )


@pytest.mark.asyncio
async def test_worker_success_and_cleanup(settings, sample_result):
    store = JobStore(settings.database_path, 10)
    email = MemoryEmail()
    worker = Worker(settings, store, FixtureScraper(sample_result), email)
    job = store.add("email-1", message())
    assert store.add("email-1", message()) == job
    worker.start()
    for _ in range(100):
        if store.get(job)["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    await worker.stop()
    row = store.get(job)
    assert row["status"] == "completed"
    result = json.loads(row["result"])
    assert result["attachment_sent"] and result["provider_id"]
    assert len(email.sent) == 1
    assert not list(settings.temp_root.iterdir())
    store.close()


@pytest.mark.parametrize(
    "exception,status", [(DeliveryUnknown, "delivery_unknown"), (DeliveryRejected, "failed")]
)
@pytest.mark.asyncio
async def test_send_failure(settings, sample_result, exception, status):
    class BrokenEmail(MemoryEmail):
        async def send(self, payload, key):
            raise exception("fixture")

    store = JobStore(settings.database_path, 10)
    job = store.add("email-1", message())
    worker = Worker(settings, store, FixtureScraper(sample_result), BrokenEmail())
    await worker.process(store.claim())
    assert store.get(job)["status"] == status
    assert not json.loads(store.get(job)["result"])["attachment_sent"]
    store.close()


def test_restart_and_queue_capacity(settings):
    store = JobStore(settings.database_path, 2)
    pending = store.add("pending", message())
    store.add("second", message())
    with pytest.raises(OverflowError):
        store.add("third", message())
    row = store.claim()
    store.mark_sending(row["id"])
    store.close()
    store = JobStore(settings.database_path, 2)
    store.recover()
    assert store.get(pending)["status"] == JobStatus.DELIVERY_UNKNOWN
    assert store.claim()["email_id"] == "second"
    store.recover()
    assert store.by_email("second")["status"] == "failed"
    assert store.claim() is None
    store.close()


@pytest.mark.asyncio
async def test_invalid_request_gets_help(settings):
    store = JobStore(settings.database_path, 10)
    job = store.add(
        "invalid", InboundMessage(sender="alice@example.com", error="Please specify a matter")
    )
    email = MemoryEmail()
    await Worker(settings, store, None, email).process(store.claim())
    assert store.get(job)["status"] == "failed"
    payload = next(iter(email.sent.values()))
    assert "Please specify a matter" in payload["text"] and "attachments" not in payload
    store.close()


@pytest.mark.asyncio
async def test_oversized_archive_sends_explanation_only(settings, sample_result):
    settings.max_zip_bytes = 1
    store = JobStore(settings.database_path, 10)
    job = store.add("oversize", message())
    email = MemoryEmail()
    await Worker(settings, store, FixtureScraper(sample_result), email).process(store.claim())
    result = json.loads(store.get(job)["result"])
    assert result["error"] == "archive_size" and not result["attachment_sent"]
    assert result["downloaded"] == 1 and result["provider_id"]
    payload = next(iter(email.sent.values()))
    assert "attachments" not in payload and "No ZIP archive is attached" in payload["text"]
    store.close()


@pytest.mark.asyncio
async def test_cancel_during_send_never_requeues(settings, sample_result):
    entered = asyncio.Event()

    class SlowEmail(MemoryEmail):
        async def send(self, payload, key):
            entered.set()
            await asyncio.Event().wait()

    store = JobStore(settings.database_path, 10)
    job = store.add("cancelled", message())
    worker = Worker(settings, store, FixtureScraper(sample_result), SlowEmail())
    task = asyncio.create_task(worker.process(store.claim()))
    await entered.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert store.get(job)["status"] == "delivery_unknown"
    assert not list(settings.temp_root.iterdir())
    store.recover()
    assert store.claim() is None
    store.close()
