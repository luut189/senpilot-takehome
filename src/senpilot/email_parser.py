import re
from email.utils import getaddresses
from html.parser import HTMLParser

from senpilot.models import DocumentRequest, DocumentType, InboundMessage

HELP = (
    "Please request one matter (M followed by five digits) and one category: "
    "Exhibits, Key Documents, Other Documents, Transcripts, or Recordings. "
    "Example: Please send Other Documents from M12205."
)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("blockquote", "script", "style"):
            self.hidden += 1
        if tag in ("p", "div", "br") and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("blockquote", "script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def current_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if re.match(
            r"\s*(On .+wrote:|-+\s*(Original Message|Forwarded message)|From:)", line, re.I
        ):
            break
        if not line.lstrip().startswith(">"):
            lines.append(line)
    return "\n".join(lines)


def parse_request(subject: str, text: str) -> DocumentRequest:
    content = subject + "\n" + current_text(text)
    matters = set(re.findall(r"\bM[0-9]{5}\b", content, re.I))
    matters = {m.upper() for m in matters}
    kinds = {
        kind
        for kind, pattern in (
            (DocumentType.EXHIBITS, r"\bexhibits?\b"),
            (DocumentType.KEY, r"\bkey\s+documents?\b"),
            (DocumentType.OTHER, r"\bother\s+documents?\b"),
            (DocumentType.TRANSCRIPTS, r"\btranscripts?\b"),
            (DocumentType.RECORDINGS, r"\brecordings?\b"),
        )
        if re.search(pattern, content, re.I)
    }
    if len(matters) != 1 or len(kinds) != 1:
        raise ValueError(HELP)
    return DocumentRequest(matter_number=matters.pop(), document_type=kinds.pop())


def parse_inbound(raw: dict) -> InboundMessage:
    sender = raw.get("from")
    if not isinstance(sender, str) or "\r" in sender or "\n" in sender:
        raise ValueError("Invalid sender")
    addresses = getaddresses([sender])
    if len(addresses) != 1 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", addresses[0][1]):
        raise ValueError("Invalid sender")
    sender = addresses[0][1]
    subject = raw.get("subject") or ""
    text = raw.get("text")
    if text is None:
        parser = VisibleText()
        parser.feed(raw.get("html") or "")
        text = "".join(parser.parts)
    if not isinstance(subject, str) or not isinstance(text, str):
        raise ValueError("Invalid message body")
    headers = raw.get("headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("Invalid headers")
    message_id = raw.get("message_id") or headers.get("message-id")
    if not isinstance(message_id, str) or not re.fullmatch(r"<[^\s<>]{1,250}>", message_id):
        message_id = None
    error = None
    request = None
    try:
        request = parse_request(subject, text)
    except ValueError:
        error = HELP
    return InboundMessage(sender=sender, message_id=message_id, request=request, error=error)
