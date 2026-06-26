import re
from pathlib import Path
from fastapi import HTTPException
from app.config import settings


def resolve_safe_path(base_dir: Path, relative_path: str) -> Path:
    base = base_dir.resolve()
    target = (base / relative_path).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Path traversal detected")
    return target


def sanitize_text_input(text: str, max_length: int = 10000) -> str:
    text = text.strip()
    if len(text) > max_length:
        raise HTTPException(status_code=400, detail=f"Input too long (max {max_length} chars)")
    dangerous = re.compile(r"[<>\"'`;\\]")
    return dangerous.sub("", text)


def validate_model_name(model: str) -> str:
    allowed = re.compile(r"^[\w\-:.]+$")
    if not allowed.match(model):
        raise HTTPException(status_code=400, detail=f"Invalid model name: {model}")
    return model
