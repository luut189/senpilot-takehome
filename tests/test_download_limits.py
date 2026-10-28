import asyncio

import pytest

from senpilot.errors import AgentError
from senpilot.scraper.client import save_download


class Download:
    def __init__(self, content, stalled=False):
        self.content, self.stalled = content, stalled
        self.cancelled = self.deleted = False

    async def save_as(self, path):
        path.write_bytes(self.content)
        if self.stalled:
            await asyncio.Event().wait()

    async def failure(self):
        return None

    async def cancel(self):
        self.cancelled = True

    async def delete(self):
        self.deleted = True


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"", b"too many bytes"])
async def test_empty_or_oversized_transfer_is_removed(tmp_path, content):
    spool = tmp_path / "spool"
    spool.mkdir()
    path = tmp_path / "output.pdf"
    download = Download(content)
    with pytest.raises(AgentError, match="empty or too large"):
        await save_download(download, path, spool, maximum=4, timeout=1)
    assert download.cancelled and download.deleted
    assert not path.exists()


@pytest.mark.asyncio
async def test_transfer_timeout_cancels_and_removes_partial_file(tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    path = tmp_path / "partial.pdf"
    download = Download(b"partial", stalled=True)
    with pytest.raises(TimeoutError):
        await save_download(download, path, spool, maximum=100, timeout=1)
    assert download.cancelled and download.deleted
    assert not path.exists()


@pytest.mark.asyncio
async def test_spool_budget_cancels_transfer_before_completion(tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / "browser-transfer").write_bytes(b"oversized")
    path = tmp_path / "partial.pdf"
    download = Download(b"partial", stalled=True)
    with pytest.raises(AgentError, match="size budget"):
        await save_download(download, path, spool, maximum=4, timeout=1)
    assert download.cancelled and download.deleted
    assert not path.exists()
