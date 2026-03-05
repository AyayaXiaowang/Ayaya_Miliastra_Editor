from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json_file(json_file_path: Path) -> Any:
    if not json_file_path.is_file():
        raise FileNotFoundError(f"json file not found: {str(json_file_path)!r}")
    return json.loads(json_file_path.read_text(encoding="utf-8"))


def write_json_file(json_file_path: Path, python_object: Any) -> None:
    json_file_path.parent.mkdir(parents=True, exist_ok=True)
    json_file_path.write_text(
        json.dumps(python_object, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


