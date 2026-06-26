import os
import re
from pathlib import Path
from fastapi import UploadFile, HTTPException
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

SAFE_FILENAME_RE = re.compile(r"[^\w\-. ]")
MAX_FILENAME_LENGTH = 200


def sanitize_filename(filename: str) -> str:
    name = Path(filename).stem
    ext = Path(filename).suffix.lower()
    name = SAFE_FILENAME_RE.sub("_", name)
    name = name[:MAX_FILENAME_LENGTH - len(ext)]
    return f"{name}{ext}" if name else f"file{ext}"


def validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Extension '{ext}' not allowed. Allowed: {settings.allowed_extensions}",
        )
    return ext


def validate_file_size(file_size: int):
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_file_size_mb} MB",
        )


def validate_path_safety(base_dir: Path, target_path: Path):
    try:
        target_path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path detected")


async def validate_upload_file(file: UploadFile) -> tuple[str, int]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    validate_extension(file.filename)

    content = await file.read(1024)
    await file.seek(0)

    file_size = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        file_size += len(chunk)
        if file_size > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size of {settings.max_file_size_mb} MB",
            )

    await file.seek(0)
    safe_name = sanitize_filename(file.filename)
    return safe_name, file_size
