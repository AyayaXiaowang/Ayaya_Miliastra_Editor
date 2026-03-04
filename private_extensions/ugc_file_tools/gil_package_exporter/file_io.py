from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

_INVALID_FILENAME_CHARACTERS = set('<>:"/\\|?*')


def _ensure_directory(directory_path: Path) -> None:
    directory_path.mkdir(parents=True, exist_ok=True)


def _write_json_file(file_path: Path, python_object: Any) -> None:
    _ensure_directory(file_path.parent)
    file_path.write_text(
        json.dumps(python_object, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_text_file(file_path: Path, text: str) -> None:
    _ensure_directory(file_path.parent)
    file_path.write_text(text, encoding="utf-8")


def _sanitize_filename(file_name: str, max_length: int = 120) -> str:
    cleaned_characters: List[str] = []
    for character in file_name:
        if character in _INVALID_FILENAME_CHARACTERS or ord(character) < 32:
            cleaned_characters.append("_")
        else:
            cleaned_characters.append(character)

    cleaned = "".join(cleaned_characters).strip()
    cleaned = cleaned.rstrip(". ")
    if cleaned == "":
        cleaned = "unnamed"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(". ")
    if cleaned == "":
        cleaned = "unnamed"
    return cleaned




def write_text_file(file_path: Path, text: str) -> None:
    return _write_text_file(Path(file_path), str(text))

