from __future__ import annotations


def alloc_new_name_sequential(*, base_name: str, used_casefold: set[str]) -> str:
    """按 `__new_{i}` 递增分配不冲突的新名字。"""

    prefix = str(base_name)
    i = 1
    while True:
        candidate = f"{prefix}__new_{i}"
        if candidate.casefold() not in used_casefold:
            used_casefold.add(candidate.casefold())
            return candidate
        i += 1


def alloc_new_name_fallback(*, base_name: str) -> str:
    """在无法获知 base 名单时用随机后缀分配新名字。"""

    from uuid import uuid4

    return f"{str(base_name)}__new_{uuid4().hex[:8]}"


def extract_int_map(*, base_report: dict[str, object], key: str) -> dict[str, int]:
    """从 base report 中抽取 {name: int} 形态映射并过滤非法值。"""

    out: dict[str, int] = {}
    raw = base_report.get(str(key))
    if not isinstance(raw, dict):
        return {}
    for k, v in raw.items():
        name = str(k or "").strip()
        if name == "":
            continue
        if not isinstance(v, int) or int(v) <= 0:
            continue
        out.setdefault(name, int(v))
    return dict(out)


__all__ = [
    "alloc_new_name_fallback",
    "alloc_new_name_sequential",
    "extract_int_map",
]

