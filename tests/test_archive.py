import zipfile

import pytest

from senpilot.archive import create_archive
from senpilot.errors import AgentError
from senpilot.models import DocumentMetadata, InboundMessage
from senpilot.templates import payload_for, summary


def test_zip_only_successful(tmp_path, sample_result):
    sample_result.documents.append(
        DocumentMetadata(
            document_number="99999",
            title="Failed",
            extension=".pdf",
            position=1,
            error="download_timeout",
        )
    )
    path = create_archive(sample_result, tmp_path, 10000)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == ["01_12345.pdf"]


def test_zip_budget(tmp_path, sample_result):
    with pytest.raises(AgentError, match="ZIP exceeds"):
        create_archive(sample_result, tmp_path, 1)
    assert not list(tmp_path.glob("*.zip"))


def test_reject_escape(tmp_path, sample_result):
    directory = tmp_path / "other"
    directory.mkdir()
    with pytest.raises(AgentError, match="escapes"):
        create_archive(sample_result, directory, 10000)


def test_metadata_and_size_handling(tmp_path, sample_result, settings):
    message = InboundMessage(sender="a@example.com", message_id="<a@example.com>")
    archive = create_archive(sample_result, tmp_path, 10000)
    payload, attached = payload_for(message, settings, sample_result, archive, None)
    assert attached and "attachments" in payload
    assert payload["headers"]["In-Reply-To"] == "<a@example.com>"
    assert "April 07, 2025" in payload["text"]
    assert "Amount:" not in payload["text"]
    settings.max_email_bytes = 1024
    payload, attached = payload_for(message, settings, sample_result, archive, None)
    assert not attached and "attachments" not in payload
    assert "No ZIP archive is attached" in payload["text"]


def test_summary_reports_partial(sample_result):
    sample_result.documents.append(
        DocumentMetadata(
            document_number="99999",
            title="Failed",
            extension=".pdf",
            position=1,
            error="download_timeout",
        )
    )
    text = summary(sample_result, True)
    assert "attempted 2 and successfully downloaded 1" in text
    assert "99999 (download_timeout)" in text
