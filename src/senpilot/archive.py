import zipfile
from pathlib import Path

from senpilot.errors import AgentError
from senpilot.models import ScrapeResult


def create_archive(result: ScrapeResult, directory: Path, maximum: int) -> Path | None:
    if not result.successful:
        return None
    path = directory / f"{result.matter.matter_number}_{result.document_type.slug}.zip"
    root = directory.resolve()
    names = set()
    try:
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for document in result.successful:
                source = document.path
                if source.is_symlink() or not source.resolve().is_relative_to(root):
                    raise AgentError("archive", "Document path escapes job directory")
                if source.name in names or not source.is_file() or source.stat().st_size == 0:
                    raise AgentError("archive", "Invalid or duplicate archive member")
                names.add(source.name)
                archive.write(source, source.name)
        if path.stat().st_size > maximum:
            raise AgentError("archive_size", "ZIP exceeds attachment size limit")
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None or len(archive.infolist()) != len(names):
                raise AgentError("archive", "ZIP integrity check failed")
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise
