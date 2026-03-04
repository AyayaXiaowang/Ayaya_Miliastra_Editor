from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RegistryEditResult:
    old_literal: str
    new_literal: str


def _find_enclosing_call_start(text: str, *, needle_pos: int, call_name: str) -> int:
    want = f"{call_name}("
    idx = text.rfind(want, 0, needle_pos)
    if idx < 0:
        raise ValueError(f"未找到 {call_name}( 调用块（pos={needle_pos}）")
    return idx


def _scan_python_literal_end(text: str, *, start: int) -> int:
    i = int(start)
    n = len(text)
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    quote: str | None = None
    escape = False
    while i < n:
        ch = text[i]
        if quote is not None:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue

        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            if depth_paren > 0:
                depth_paren -= 1
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            if depth_brace > 0:
                depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            if depth_bracket > 0:
                depth_bracket -= 1

        if (depth_paren, depth_brace, depth_bracket) == (0, 0, 0) and ch == ",":
            return i

        i += 1

    raise ValueError("无法定位 Python literal 结束位置（未找到顶层逗号）")


def replace_auto_custom_variable_default_value(
    *,
    registry_path: Path,
    variable_id: str,
    new_default_value: Any,
) -> RegistryEditResult:
    path = Path(registry_path).resolve()
    text = path.read_text(encoding="utf-8")
    vid = str(variable_id or "").strip()
    if not vid:
        raise ValueError("variable_id 不能为空")

    needle = f'variable_id="{vid}"'
    pos = text.find(needle)
    if pos < 0:
        needle = f"variable_id='{vid}'"
        pos = text.find(needle)
    if pos < 0:
        raise ValueError(f"{path}: 未找到 variable_id={vid!r} 的声明")

    call_start = _find_enclosing_call_start(text, needle_pos=pos, call_name="AutoCustomVariableDeclaration")
    block_text = text[call_start:pos]
    dv_key = "default_value="
    dv_rel = block_text.rfind(dv_key)
    if dv_rel < 0:
        raise ValueError(f"{path}: 未在声明块内找到 default_value=（variable_id={vid!r}）")

    dv_start = call_start + dv_rel + len(dv_key)
    dv_end = _scan_python_literal_end(text, start=dv_start)
    old_literal = text[dv_start:dv_end].strip()
    new_literal = repr(new_default_value)

    new_text = text[:dv_start] + new_literal + text[dv_end:]
    path.write_text(new_text, encoding="utf-8")
    return RegistryEditResult(old_literal=old_literal, new_literal=new_literal)


__all__ = [
    "RegistryEditResult",
    "replace_auto_custom_variable_default_value",
]

