from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from private_extensions.ugc_file_tools.genshin_ts_bridge.paths import resolve_paths


def _strip_line_comment(line: str) -> str:
    idx = line.find("//")
    return line if idx < 0 else line[:idx]


def _read_text(path: Path) -> str:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p.read_text(encoding="utf-8")


def _parse_ts_export_const_object(text: str, *, const_name: str) -> Dict[str, int]:
    # 解析 `export const NODE_ID = { ... }`
    token = f"export const {const_name} ="
    idx = text.find(token)
    if idx < 0:
        raise ValueError(f"未找到 {token}")
    brace_start = text.find("{", idx)
    if brace_start < 0:
        raise ValueError(f"{const_name} 缺少 '{{' 起始")

    i = brace_start
    depth = 0
    end = None
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end is None:
        raise ValueError(f"{const_name} 缺少 '}}' 结束")

    body = text[brace_start + 1 : end]
    out: Dict[str, int] = {}
    for raw in body.splitlines():
        line = _strip_line_comment(raw).strip().rstrip(",").strip()
        if not line:
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        value_text = v.strip()
        if key.startswith("'") or key.startswith('"'):
            key = key.strip("'\"")
        if key == "":
            continue
        # 只解析明确数值的条目（跳过引用/表达式）
        if value_text.startswith("NODE_ID.") or value_text.startswith("CLIENT_NODE_ID."):
            continue
        if value_text.startswith("-") or value_text[:1].isdigit():
            out[key] = int(value_text)
    if not out:
        raise ValueError(f"{const_name} 解析结果为空")
    return out


def _extract_node_pin_records_array_text(text: str) -> str:
    token = "export const NODE_PIN_RECORDS ="
    idx = text.find(token)
    if idx < 0:
        raise ValueError("未找到 export const NODE_PIN_RECORDS =")
    bracket_start = text.find("[", idx)
    if bracket_start < 0:
        raise ValueError("NODE_PIN_RECORDS 缺少 '[' 起始")

    i = bracket_start
    depth = 0
    in_str = False
    str_quote = ""
    end = None
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == str_quote:
                in_str = False
            i += 1
            continue
        if ch in {"'", '"'}:
            in_str = True
            str_quote = ch
            i += 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end is None:
        raise ValueError("NODE_PIN_RECORDS 缺少 ']' 结束")
    return text[bracket_start : end + 1]


def _strip_ts_comments(text: str) -> str:
    """移除 `//...` 与 `/*...*/` 注释（极简实现）。

    说明：NodeEditorPack 的 node_pin_records.ts 在数组内部包含大量行注释；若不先移除，
    js-like parser 会把 `/` 当作 token 导致失败。
    """
    out_chars: List[str] = []
    i = 0
    in_str = False
    str_quote = ""
    in_block = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_block:
            if ch == "*" and nxt == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue

        if in_str:
            out_chars.append(ch)
            if ch == str_quote:
                in_str = False
            i += 1
            continue

        # string start
        if ch in {"'", '"'}:
            in_str = True
            str_quote = ch
            out_chars.append(ch)
            i += 1
            continue

        # block comment start
        if ch == "/" and nxt == "*":
            in_block = True
            i += 2
            continue

        # line comment start
        if ch == "/" and nxt == "/":
            # skip until newline (keep newline)
            i += 2
            while i < len(text) and text[i] not in {"\n"}:
                i += 1
            continue

        out_chars.append(ch)
        i += 1

    return "".join(out_chars)


def _parse_js_like_array(array_text: str) -> List[Any]:
    """
    极简 parser：解析一个 JS/TS 风格的数组字面量（只支持 string/number/object/array/bool/null）。

    说明：
    - 仅用于解析 genshin-ts/NodeEditorPack 的“静态数据表”文件（node_pin_records.ts / concrete_map.ts）。
    - 不支持表达式（例如 new Map(...)）——调用方应先提取其内部数组再交给本函数。
    """
    s = _strip_ts_comments(array_text)
    i = 0

    def skip_ws() -> None:
        nonlocal i
        while i < len(s) and s[i] in " \t\r\n":
            i += 1

    def expect(ch: str) -> None:
        nonlocal i
        skip_ws()
        if i >= len(s) or s[i] != ch:
            raise ValueError(f"期望字符 {ch!r}，但遇到: {s[i:i+10]!r}")
        i += 1

    def parse_string() -> str:
        nonlocal i
        skip_ws()
        if i >= len(s) or s[i] not in {"'", '"'}:
            raise ValueError("期望字符串")
        quote = s[i]
        i += 1
        start = i
        while i < len(s) and s[i] != quote:
            i += 1
        if i >= len(s):
            raise ValueError("字符串未闭合")
        out = s[start:i]
        i += 1
        return out

    def parse_number() -> int:
        nonlocal i
        skip_ws()
        start = i
        if i < len(s) and s[i] == "-":
            i += 1
        while i < len(s) and s[i].isdigit():
            i += 1
        if start == i:
            raise ValueError("期望数字")
        return int(s[start:i])

    def parse_identifier() -> str:
        nonlocal i
        skip_ws()
        start = i
        while i < len(s) and (s[i].isalnum() or s[i] in {"_", "$"}):
            i += 1
        if start == i:
            raise ValueError("期望标识符")
        return s[start:i]

    def parse_value() -> Any:
        nonlocal i
        skip_ws()
        if i >= len(s):
            raise ValueError("unexpected eof")
        ch = s[i]
        if ch in {"'", '"'}:
            return parse_string()
        if ch == "{":
            return parse_object()
        if ch == "[":
            return parse_array()
        if ch == "-" or ch.isdigit():
            return parse_number()
        ident = parse_identifier()
        if ident == "null":
            return None
        if ident == "true":
            return True
        if ident == "false":
            return False
        # 兜底：保留原标识符（此处只用于静态表，正常不该出现复杂表达式）
        return ident

    def parse_array() -> List[Any]:
        nonlocal i
        items: List[Any] = []
        expect("[")
        while True:
            skip_ws()
            if i < len(s) and s[i] == "]":
                i += 1
                break
            items.append(parse_value())
            skip_ws()
            if i < len(s) and s[i] == ",":
                i += 1
                continue
            skip_ws()
            if i < len(s) and s[i] == "]":
                i += 1
                break
        return items

    def parse_object() -> Dict[str, Any]:
        nonlocal i
        obj: Dict[str, Any] = {}
        expect("{")
        while True:
            skip_ws()
            if i < len(s) and s[i] == "}":
                i += 1
                break
            key = parse_identifier()
            expect(":")
            val = parse_value()
            obj[key] = val
            skip_ws()
            if i < len(s) and s[i] == ",":
                i += 1
                continue
            skip_ws()
            if i < len(s) and s[i] == "}":
                i += 1
                break
        return obj

    parsed = parse_array()
    if not isinstance(parsed, list):
        raise ValueError("array parse result is not list")
    return parsed


def _parse_js_like_records_array(array_text: str) -> List[Dict[str, Any]]:
    # 极简 parser：解析由 `{ name: 'x', id: 1, inputs: ['Str'], outputs: [] }` 组成的数组
    # 支持字段：name/category/id/inputs/outputs/reflectMap
    parsed = _parse_js_like_array(array_text)
    # 过滤非 dict
    records: List[Dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            records.append(item)
    if not records:
        raise ValueError("NODE_PIN_RECORDS 解析结果为空")
    return records


def _extract_concrete_map_maps_array_text(text: str) -> str:
    anchor = "export const CONCRETE_MAP"
    start = text.find(anchor)
    if start < 0:
        raise ValueError("未找到 export const CONCRETE_MAP")
    token = "maps:"
    idx = text.find(token, start)
    if idx < 0:
        raise ValueError("未找到 CONCRETE_MAP.maps")
    bracket_start = text.find("[", idx)
    if bracket_start < 0:
        raise ValueError("CONCRETE_MAP.maps 缺少 '[' 起始")

    i = bracket_start
    depth = 0
    in_str = False
    str_quote = ""
    end = None
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == str_quote:
                in_str = False
            i += 1
            continue
        if ch in {"'", '"'}:
            in_str = True
            str_quote = ch
            i += 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end is None:
        raise ValueError("CONCRETE_MAP.maps 缺少 ']' 结束")
    return text[bracket_start : end + 1]


def _extract_concrete_map_pins_array_text(text: str) -> str:
    anchor = "export const CONCRETE_MAP"
    start = text.find(anchor)
    if start < 0:
        raise ValueError("未找到 export const CONCRETE_MAP")
    token = "pins: new Map"
    idx = text.find(token, start)
    if idx < 0:
        raise ValueError("未找到 CONCRETE_MAP.pins")
    bracket_start = text.find("[", idx)
    if bracket_start < 0:
        raise ValueError("CONCRETE_MAP.pins 缺少 '[' 起始")

    i = bracket_start
    depth = 0
    in_str = False
    str_quote = ""
    end = None
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == str_quote:
                in_str = False
            i += 1
            continue
        if ch in {"'", '"'}:
            in_str = True
            str_quote = ch
            i += 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end is None:
        raise ValueError("CONCRETE_MAP.pins 缺少 ']' 结束")
    return text[bracket_start : end + 1]


@dataclass(frozen=True, slots=True)
class ExportNodeSchemaResult:
    node_id_count: int
    node_records_count: int
    output_json: str


def export_node_schema_to_refs_dir() -> ExportNodeSchemaResult:
    p = resolve_paths()
    node_id_text = _read_text(p.node_id_ts_path)
    pin_text = _read_text(p.node_pin_records_ts_path)
    concrete_map_text = _read_text(p.concrete_map_ts_path)

    # NODE_ID（包含大量别名）
    node_id_map = _parse_ts_export_const_object(node_id_text, const_name="NODE_ID")

    # NODE_PIN_RECORDS（generic id -> inputs/outputs 类型表达式）
    array_text = _extract_node_pin_records_array_text(pin_text)
    node_records = _parse_js_like_records_array(array_text)

    # CONCRETE_MAP（generic_id + pin(kind/index) -> indexOfConcrete 映射）
    maps_array_text = _extract_concrete_map_maps_array_text(concrete_map_text)
    pins_array_text = _extract_concrete_map_pins_array_text(concrete_map_text)
    parsed_maps = _parse_js_like_array(maps_array_text)
    parsed_pins = _parse_js_like_array(pins_array_text)

    concrete_maps: List[List[int]] = []
    for item in parsed_maps:
        if not isinstance(item, list):
            continue
        row: List[int] = []
        for v in item:
            if isinstance(v, int):
                row.append(int(v))
        if row:
            concrete_maps.append(row)
    if not concrete_maps:
        raise ValueError("CONCRETE_MAP.maps 解析结果为空")

    concrete_pins: Dict[str, int] = {}
    for item in parsed_pins:
        if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[0], str) and isinstance(item[1], int):
            key = str(item[0]).strip()
            if key == "":
                continue
            concrete_pins[key] = int(item[1])
    if not concrete_pins:
        raise ValueError("CONCRETE_MAP.pins 解析结果为空")

    # 导出
    refs_dir = p.graph_generater_root / "private_extensions" / "ugc_file_tools" / "refs" / "genshin_ts"
    refs_dir.mkdir(parents=True, exist_ok=True)
    out_path = refs_dir / "genshin_ts__node_schema.report.json"

    payload = {
        "node_id_alias_map": node_id_map,  # alias -> concrete/generic nodeId（按文件定义）
        "node_pin_records": node_records,  # list[{id,name,inputs,outputs,reflectMap?,category?}]
        "concrete_map": {
            "maps": concrete_maps,
            "pins": concrete_pins,
        },
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return ExportNodeSchemaResult(
        node_id_count=len(node_id_map),
        node_records_count=len(node_records),
        output_json=str(out_path),
    )


def export_node_schema_to_out_dir() -> ExportNodeSchemaResult:
    # backward-compatible alias
    return export_node_schema_to_refs_dir()


def main() -> None:
    res = export_node_schema_to_refs_dir()
    print(str(res.output_json))


if __name__ == "__main__":
    main()

