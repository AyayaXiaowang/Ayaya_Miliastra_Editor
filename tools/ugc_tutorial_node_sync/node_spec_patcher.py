from __future__ import annotations

"""改写节点实现文件中的 @node_spec(inputs/outputs) 列表文本。"""

import re
from pathlib import Path
from typing import List, Optional, Tuple


def patch_node_spec_ports_in_file(*, file_path: Path, new_inputs: List[Tuple[str, str]], new_outputs: List[Tuple[str, str]]) -> None:
    # Patch @node_spec(inputs/outputs) list literals in-place without importing the target module.
    src = file_path.read_text(encoding="utf-8")
    decorator_start = src.find("@node_spec(")
    if decorator_start < 0:
        raise ValueError(f"@node_spec( not found: {str(file_path)}")

    def _scan_to_matching_paren(text: str, start_idx: int) -> int:
        # Scan forward to find the matching ')' for the @node_spec( call.
        if start_idx < 0 or start_idx >= len(text):
            raise ValueError("start_idx out of range")
        i = start_idx
        if not text.startswith("@node_spec(", i):
            raise ValueError("scan start is not @node_spec(")
        i = i + len("@node_spec(")
        depth = 1
        in_string: Optional[str] = None
        escape = False
        while i < len(text):
            ch = text[i]
            if in_string is not None:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == in_string:
                    in_string = None
                i += 1
                continue

            if ch in {"'", '"'}:
                in_string = ch
                i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        raise ValueError("Unclosed @node_spec(...) call (missing ')')")

    decorator_end = _scan_to_matching_paren(src, decorator_start)
    deco_text = src[decorator_start : decorator_end + 1]

    def _find_matching_bracket(text: str, open_idx: int) -> int:
        # Scan forward to find the matching ']' for a list literal.
        if open_idx < 0 or open_idx >= len(text) or text[open_idx] != "[":
            raise ValueError("open_idx is not '['")
        i = open_idx + 1
        depth = 1
        in_string: Optional[str] = None
        escape = False
        while i < len(text):
            ch = text[i]
            if in_string is not None:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == in_string:
                    in_string = None
                i += 1
                continue

            if ch in {"'", '"'}:
                in_string = ch
                i += 1
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        raise ValueError("Unclosed '[' in node_spec keyword list literal")

    def _replace_kw_list_literal(text: str, kw: str, new_list_literal: str) -> str:
        # Replace a keyword list literal value (e.g. inputs=[...]) inside the decorator call text.
        m = re.search(rf"\b{re.escape(kw)}\s*=\s*", text)
        if m is None:
            raise ValueError(f"keyword not found in @node_spec: {kw!r}")
        j = m.end()
        while j < len(text) and text[j].isspace():
            j += 1
        if j >= len(text) or text[j] != "[":
            raise ValueError(f"@node_spec keyword '{kw}' is not a list literal (expect '[')")
        k = _find_matching_bracket(text, j)
        return text[:j] + new_list_literal + text[k + 1 :]

    new_inputs_literal = repr([(n, t) for (n, t) in new_inputs])
    new_outputs_literal = repr([(n, t) for (n, t) in new_outputs])

    deco_text = _replace_kw_list_literal(deco_text, "inputs", new_inputs_literal)
    deco_text = _replace_kw_list_literal(deco_text, "outputs", new_outputs_literal)

    patched = src[:decorator_start] + deco_text + src[decorator_end + 1 :]
    file_path.write_text(patched, encoding="utf-8")

