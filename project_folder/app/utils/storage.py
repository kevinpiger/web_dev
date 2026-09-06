"""File storage helpers, rooted at settings.STORAGE_PATH. Blocks path traversal."""

import re
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")

CHUNK_SIZE = 1024 * 1024  # 1 MiB


def sanitize_filename(filename: str) -> str:
    """Strip path separators and `..` so only a bare, safe filename remains."""
    name = Path(filename).name
    name = name.replace("..", "")
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)
    return name or "file"


def resolve(rel_path: str) -> Path:
    """Relative path -> absolute path, guaranteed to stay under STORAGE_PATH."""
    root = Path(settings.STORAGE_PATH).resolve()
    candidate = (root / rel_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes storage root: {rel_path}")
    return candidate


async def save_stream(rel_path: str, upload_file: UploadFile) -> int:
    """Stream upload_file to rel_path (under STORAGE_PATH). Returns bytes written."""
    destination = resolve(rel_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    bytes_written = 0
    with destination.open("wb") as out_file:
        while chunk := await upload_file.read(CHUNK_SIZE):
            out_file.write(chunk)
            bytes_written += len(chunk)
    return bytes_written


def open_file(rel_path: str):
    return resolve(rel_path).open("rb")


def delete(rel_path: str) -> None:
    """Delete the file at rel_path if it exists. Used to clean up failed uploads only."""
    path = resolve(rel_path)
    if path.exists():
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass


def exists(rel_path: str) -> bool:
    return resolve(rel_path).exists()
