import argparse
import asyncio
import shutil
import tempfile
from pathlib import Path

from senpilot.archive import create_archive
from senpilot.config import Settings
from senpilot.logging import configure_logging
from senpilot.models import DocumentRequest, DocumentType
from senpilot.scraper.client import Scraper


async def fetch(args):
    settings = Settings()
    request = DocumentRequest(matter_number=args.matter, document_type=args.category)
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="senpilot-") as temporary:
        root = Path(temporary)
        result = await Scraper(settings).fetch_matter_documents(request, root, args.limit)
        archive = create_archive(result, root, settings.max_zip_bytes)
        if archive:
            destination = args.output / archive.name
            # Exclusive creation avoids silently overwriting previous results.
            with destination.open("xb") as target, archive.open("rb") as source:
                shutil.copyfileobj(source, target)
        manifest = result.model_dump(mode="json")
        for doc in manifest["documents"]:
            if doc["path"]:
                doc["path"] = Path(doc["path"]).name
        import json

        print(
            json.dumps(
                {
                    "archive": str(args.output / archive.name) if archive else None,
                    "result": manifest,
                },
                indent=2,
            )
        )
        return 0 if len(result.successful) == len(result.documents) else 2


def main():
    parser = argparse.ArgumentParser(description="Fetch regulatory documents without email")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("fetch")
    command.add_argument("matter")
    command.add_argument("category", choices=list(DocumentType))
    command.add_argument("--output", type=Path, default=Path("downloads"))
    command.add_argument("--limit", type=int, choices=range(1, 11), default=10)
    args = parser.parse_args()
    configure_logging()
    try:
        code = asyncio.run(fetch(args))
    except Exception as exc:
        parser.exit(1, f"Fetch failed ({type(exc).__name__}): {exc}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
