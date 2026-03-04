from __future__ import annotations

import base64
import json
import zlib
from pathlib import Path


def list_html_files(dir_path: Path) -> list[str]:
    if not dir_path.is_dir():
        return []
    out: list[str] = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if name.lower().endswith(".html") or name.lower().endswith(".htm"):
            out.append(name)
    out.sort(key=lambda x: x.lower())
    return out


def decode_utf8_b64(text: str) -> str:
    raw = base64.b64decode(str(text or "").strip() or b"")
    return raw.decode("utf-8")


def encode_utf8_b64(text: str) -> str:
    raw = str(text or "").encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def crc32_hex(text: str) -> str:
    v = zlib.crc32(str(text).encode("utf-8")) & 0xFFFFFFFF
    return f"{v:08x}"


def read_json(path: Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"json 不是对象：{path}")
    return payload


def write_json(path: Path, payload: dict) -> None:
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "crc32_hex",
    "decode_utf8_b64",
    "encode_utf8_b64",
    "list_html_files",
    "read_json",
    "write_json",
]

