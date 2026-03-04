from __future__ import annotations

from uuid import uuid4


def generate_unique_id(*, prefix: str, existing: set[str]) -> str:
    while True:
        candidate = f"{prefix}_{uuid4().hex[:8]}"
        if candidate not in existing:
            return candidate


def ensure_unique_name(*, desired: str, existing_names: set[str]) -> str:
    base = str(desired or "").strip() or "未命名"
    if base not in existing_names:
        return base
    index = 2
    while True:
        candidate = f"{base}_{index}"
        if candidate not in existing_names:
            return candidate
        index += 1


def collect_existing_names(container: object, field_name: str) -> set[str]:
    out: set[str] = set()
    if not isinstance(container, dict):
        return out
    for _rid, payload in container.items():
        if not isinstance(payload, dict):
            continue
        value = payload.get(field_name) or payload.get("name") or ""
        if isinstance(value, str) and value.strip():
            out.add(value.strip())
    return out


__all__ = [
    "collect_existing_names",
    "ensure_unique_name",
    "generate_unique_id",
]

