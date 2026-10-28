import json
import logging
from contextvars import ContextVar

job_context: ContextVar[str | None] = ContextVar("job_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        result = {"level": record.levelname, "event": record.getMessage()}
        if job_context.get():
            result["job_id"] = job_context.get()
        for key in (
            "job_id",
            "matter_number",
            "document_type",
            "state",
            "downloaded",
            "duration",
            "error_category",
            "document_number",
            "stage",
            "error_type",
            "error_reason",
            "operation",
        ):
            if hasattr(record, key):
                result[key] = getattr(record, key)
        return json.dumps(result)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
