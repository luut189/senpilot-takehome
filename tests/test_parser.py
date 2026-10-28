import pytest

from senpilot.email_parser import parse_inbound, parse_request
from senpilot.models import DocumentType


@pytest.mark.parametrize(
    "body,kind",
    [
        ("Please send Other Documents from M12205", DocumentType.OTHER),
        ("Can I get the transcripts for m12383?", DocumentType.TRANSCRIPTS),
        ("Hi Agent, I need key documents relating to M12205", DocumentType.KEY),
        ("Please retrieve exhibits for matter M12205", DocumentType.EXHIBITS),
        ("recording for M12205", DocumentType.RECORDINGS),
        ("key document M12205", DocumentType.KEY),
        ("other document M12205", DocumentType.OTHER),
        ("exhibit M12205", DocumentType.EXHIBITS),
        ("transcript M12205", DocumentType.TRANSCRIPTS),
    ],
)
def test_requests(body, kind):
    assert parse_request("", body).document_type == kind


@pytest.mark.parametrize(
    "body",
    [
        "exhibits",
        "M12205",
        "exhibits M12205 M12383",
        "exhibits and transcripts M12205",
        "exhibits M1234",
        "exhibits M122050",
        "exhibits XM12205",
    ],
)
def test_invalid(body):
    with pytest.raises(ValueError, match="Please request"):
        parse_request("", body)


def test_repeated_request_is_not_ambiguous():
    assert parse_request("M12205 Exhibits", "m12205 exhibit").matter_number == "M12205"


def test_quoted_history():
    assert (
        parse_request("", "Exhibits M12205\nOn Monday, A wrote:\nTranscripts M12383").document_type
        == DocumentType.EXHIBITS
    )


def test_html_history_and_thread_header():
    message = parse_inbound(
        {
            "from": "Alice <alice@example.com>",
            "subject": "",
            "text": None,
            "html": "<p>Exhibits M12205</p><blockquote>Recordings M12383</blockquote>",
            "message_id": "<original@example.com>",
        }
    )
    assert message.sender == "alice@example.com"
    assert message.message_id == "<original@example.com>"
    assert message.request.document_type == DocumentType.EXHIBITS


def test_unsafe_sender():
    with pytest.raises(ValueError):
        parse_inbound({"from": "a@example.com\nBcc: b@example.com"})
