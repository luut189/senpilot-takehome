import base64

import pytest

from senpilot.config import Settings
from senpilot.models import DocumentMetadata, DocumentType, MatterMetadata, ScrapeResult


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        database_path=tmp_path / "jobs.sqlite3",
        temp_root=tmp_path / "tmp",
        email_from="agent@example.com",
        resend_webhook_secret="whsec_"
        + base64.b64encode(b"test-secret-32bytes-long-enough!!").decode(),
        provider_timeout=1,
        shutdown_timeout=1,
    )


@pytest.fixture
def sample_result(tmp_path):
    file = tmp_path / "01_12345.pdf"
    file.write_bytes(b"%PDF-1.4\nfixture bytes\n%%EOF")
    return ScrapeResult(
        matter=MatterMetadata(
            matter_number="M12205",
            title="Fixture matter",
            category="Water",
            date_received="04/07/2025",
            counts={kind: 1 if kind == DocumentType.OTHER else 0 for kind in DocumentType},
        ),
        document_type=DocumentType.OTHER,
        documents=[
            DocumentMetadata(
                document_number="12345",
                title="Fixture document",
                extension=".pdf",
                position=0,
                path=file,
                size=file.stat().st_size,
            )
        ],
    )
