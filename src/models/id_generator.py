from __future__ import annotations

from pathlib import Path


def next_available_id(directory: str | Path, prefix: str, width: int) -> str:
    """Return an ID greater than every valid JSON ID already in ``directory``.

    Filenames that do not match ``<prefix><numeric suffix>.json`` are ignored.
    The caller should still create the destination file in exclusive mode to
    prevent overwrites if two writers run concurrently.
    """
    if not prefix:
        raise ValueError("prefix must not be empty")
    if width < 1:
        raise ValueError("width must be at least 1")

    root = Path(directory)
    highest_suffix = 0
    for path in root.glob(f"{prefix}*.json"):
        suffix = path.stem.removeprefix(prefix)
        if suffix.isdigit():
            highest_suffix = max(highest_suffix, int(suffix))

    return f"{prefix}{highest_suffix + 1:0{width}d}"
