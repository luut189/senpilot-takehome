import base64
import json
from datetime import datetime
from pathlib import Path

from senpilot.config import Settings
from senpilot.models import InboundMessage, ScrapeResult


def readable_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%m/%d/%Y").strftime("%B %d, %Y")
    except ValueError:
        return value


def summary(result: ScrapeResult, attachment: bool, reason: str | None = None) -> str:
    matter = result.matter
    lines = ["Hi,", "", f"Matter: {matter.matter_number} — {matter.title}"]
    for label, key in (
        ("Category", "category"),
        ("Type", "matter_type"),
        ("Status", "status"),
        ("Date received", "date_received"),
        ("Decision date", "decision_date"),
        ("Outcome", "outcome"),
    ):
        value = getattr(matter, key)
        if value:
            lines.append(f"{label}: {readable_date(value) if 'date' in key else value}")
    lines += ["", "Document counts:"]
    for kind, count in matter.counts.items():
        lines.append(f"- {kind.value}: {count}")
    found = matter.counts[result.document_type]
    lines += [
        "",
        f"Found {found} {result.document_type.value}; attempted {len(result.documents)} "
        f"and successfully downloaded {len(result.successful)}.",
    ]
    failures = [d for d in result.documents if d.error]
    if failures:
        lines.append(
            "Failed documents: " + ", ".join(f"{d.document_number} ({d.error})" for d in failures)
        )
        lines.append("No later documents were substituted.")
    if attachment:
        lines.append("The ZIP archive containing the successful downloads is attached.")
    else:
        lines.append("No ZIP archive is attached.")
    if reason:
        lines.append(reason)
    return "\n".join(lines + ["", "Regards,", "Senpilot Regulatory Agent"])


def payload_for(
    message: InboundMessage,
    settings: Settings,
    result: ScrapeResult | None,
    archive: Path | None,
    error: str | None,
) -> tuple[dict, bool]:
    subject = (
        f"Documents for {message.request.matter_number} — {message.request.document_type.value}"
        if message.request
        else "Regulatory document request — clarification needed"
    )
    base = {"from": settings.email_from, "to": [message.sender], "subject": subject}
    if message.message_id:
        base["headers"] = {"In-Reply-To": message.message_id, "References": message.message_id}
    attached = archive is not None
    if archive:
        # Base64 + MIME line wrapping + 1 MB provider/text/headers allowance.
        encoded = 4 * ((archive.stat().st_size + 2) // 3)
        if encoded + 2 * ((encoded + 75) // 76) + 1_000_000 > settings.max_email_bytes:
            attached = False
            error = "The archive exceeds the email size limit and could not be attached."
    base["text"] = (
        summary(result, attached, error)
        if result
        else (
            f"Hi,\n\n{error or 'The request could not be completed.'}\n"
            "\nNo ZIP archive is attached.\n"
            "\nRegards,\nSenpilot Regulatory Agent"
        )
    )
    if attached:
        base["attachments"] = [
            {
                "filename": archive.name,
                "content": base64.b64encode(archive.read_bytes()).decode("ascii"),
            }
        ]
    if len(json.dumps(base).encode()) > settings.max_email_bytes:
        raise ValueError("Email payload exceeds configured limit")
    return base, attached
