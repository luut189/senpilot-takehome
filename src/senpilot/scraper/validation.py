"""Pure validation shared by the proof and later pipeline."""

import re
import unicodedata
from pathlib import PurePosixPath

CATEGORIES = ("Exhibits", "Key Documents", "Other Documents", "Transcripts", "Recordings")


def normalize_matter(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"M[0-9]{5}", value):
        raise ValueError("Matter number must be M followed by five digits, e.g. M12205")
    return value


def parse_counts(labels: list[str]) -> dict[str, int]:
    counts = {}
    for category in CATEGORIES:
        matches = [
            re.fullmatch(rf"{re.escape(category)}\s*-\s*([0-9]+)", s.strip()) for s in labels
        ]
        values = [int(m.group(1)) for m in matches if m]
        if len(values) != 1:
            raise ValueError(f"Expected exactly one count for {category}")
        counts[category] = values[0]
    return counts


def safe_filename(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', "_", value).strip(" .")
    if not value:
        return "document"
    path = PurePosixPath(value)
    suffix = path.suffix[:20]
    stem = path.stem[:150].rstrip(" .") or "document"
    if stem.upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    }:
        stem = "_" + stem
    return stem + suffix
