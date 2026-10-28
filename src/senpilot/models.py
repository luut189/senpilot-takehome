from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from senpilot.scraper.validation import normalize_matter


class DocumentType(StrEnum):
    EXHIBITS = "Exhibits"
    KEY = "Key Documents"
    OTHER = "Other Documents"
    TRANSCRIPTS = "Transcripts"
    RECORDINGS = "Recordings"

    @property
    def slug(self) -> str:
        return self.value.lower().replace(" ", "_")


class DocumentRequest(BaseModel):
    matter_number: str
    document_type: DocumentType

    _normalize = field_validator("matter_number")(normalize_matter)


class MatterMetadata(BaseModel):
    matter_number: str
    title: str
    matter_type: str | None = None
    status: str | None = None
    category: str | None = None
    date_received: str | None = None
    decision_date: str | None = None
    outcome: str | None = None
    counts: dict[DocumentType, int] = Field(default_factory=dict)


class DocumentMetadata(BaseModel):
    document_number: str
    title: str
    date: str | None = None
    security: str | None = None
    extension: str
    position: int
    path: Path | None = None
    size: int = 0
    error: str | None = None


class ScrapeResult(BaseModel):
    matter: MatterMetadata
    document_type: DocumentType
    documents: list[DocumentMetadata] = Field(default_factory=list)

    @property
    def successful(self) -> list[DocumentMetadata]:
        return [d for d in self.documents if d.path is not None and d.error is None]


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DELIVERY_UNKNOWN = "delivery_unknown"


class JobResult(BaseModel):
    downloaded: int = 0
    attempted: int = 0
    attachment_sent: bool = False
    provider_id: str | None = None
    error: str | None = None


class InboundMessage(BaseModel):
    sender: str
    message_id: str | None = None
    request: DocumentRequest | None = None
    error: str | None = None
