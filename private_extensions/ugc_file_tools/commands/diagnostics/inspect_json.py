from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from ugc_file_tools.console_encoding import configure_console_encoding

JsonValue = Any


@dataclass(frozen=True, slots=True)
class _PathToken:
    kind: str  # "seg" | "index"
    value: str | int


def _parse_path_tokens(path_text: str) -> list[_PathToken]:
    """
    将路径表达式解析为 token 序列。

    支持：
    - `4.10.2[0].1.102`
    - `4/10/2/0/1/102`（当走到 list 时，纯数字段会自动视为 index）
    - `a.b[0][1].c`
    """
    text = str(path_text or "").strip()
    if text in ("", "."):
        return []

    tokens: list[_PathToken] = []
    buf = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in (".", "/"):
            seg = buf.strip()
            if seg != "":
                tokens.append(_PathToken(kind="seg", value=seg))
            buf = ""
            i += 1
            continue

        if ch == "[":
            seg = buf.strip()
            if seg != "":
                tokens.append(_PathToken(kind="seg", value=seg))
            buf = ""

            j = text.find("]", i + 1)
            if j < 0:
                raise ValueError(f"路径包含未闭合的 '['：{path_text!r}")
            index_text = text[i + 1 : j].strip()
            if index_text == "":
                raise ValueError(f"路径包含空索引 '[]'：{path_text!r}")
            tokens.append(_PathToken(kind="index", value=int(index_text)))
            i = j + 1
            continue

        buf += ch
        i += 1

    tail = buf.strip()
    if tail != "":
        tokens.append(_PathToken(kind="seg", value=tail))
    return tokens


def _preview_dict_keys(value: dict[Any, Any], *, max_keys: int, sort_keys: bool) -> list[Any]:
    keys = list(value.keys())
    if sort_keys:
        keys.sort(
            key=lambda k: (
                0,
                int(k),
            )
            if isinstance(k, str) and k.isdigit()
            else (
                1,
                str(k),
            )
        )
    if max_keys <= 0:
        return []
    return keys[:max_keys]


def _format_scalar(value: JsonValue, *, max_text: int) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        preview = value[:max_text]
        suffix = "" if len(value) <= max_text else f"...(+{len(value) - max_text} chars)"
        return f"{preview!r}{suffix} (len={len(value)})"
    return repr(value)


def _describe_value(
    value: JsonValue,
    *,
    max_keys: int,
    max_items: int,
    max_text: int,
    sort_keys: bool,
) -> list[str]:
    lines: list[str] = [f"type: {type(value).__name__}"]

    if isinstance(value, dict):
        lines.append(f"len: {len(value)}")
        if max_keys > 0:
            keys_preview = _preview_dict_keys(value, max_keys=max_keys, sort_keys=sort_keys)
            lines.append(f"keys(head {len(keys_preview)}/{len(value)}): {keys_preview}")
        return lines

    if isinstance(value, list):
        lines.append(f"len: {len(value)}")
        if max_items > 0:
            sample = value[:max_items]
            lines.append(
                f"item_types(head {len(sample)}/{len(value)}): {[type(item).__name__ for item in sample]}"
            )
            if sample and isinstance(sample[0], dict) and max_keys > 0:
                keys_preview = _preview_dict_keys(sample[0], max_keys=max_keys, sort_keys=sort_keys)
                lines.append(f"first_item.keys(head {len(keys_preview)}/{len(sample[0])}): {keys_preview}")
        return lines

    lines.append(f"value: {_format_scalar(value, max_text=max_text)}")
    return lines


def _navigate_json_value(
    root_value: JsonValue, *, tokens: list[_PathToken]
) -> tuple[JsonValue, list[tuple[str, JsonValue]]]:
    current: JsonValue = root_value
    current_path = "root"
    trace: list[tuple[str, JsonValue]] = [(current_path, current)]

    for token in tokens:
        if token.kind == "seg":
            seg = str(token.value)
            if isinstance(current, dict):
                if seg in current:
                    current = current[seg]
                    current_path = f"{current_path}.{seg}"
                elif seg.isdigit() and int(seg) in current:
                    current = current[int(seg)]
                    current_path = f"{current_path}.{int(seg)}"
                else:
                    raise KeyError(f"key not found: {seg!r} (at {current_path})")
            elif isinstance(current, list):
                index = int(seg)
                current = current[index]
                current_path = f"{current_path}[{index}]"
            else:
                raise TypeError(
                    f"cannot access {seg!r}: current is {type(current).__name__} (at {current_path})"
                )

            trace.append((current_path, current))
            continue

        if token.kind == "index":
            index = int(token.value)
            if not isinstance(current, list):
                raise TypeError(
                    f"expected list for index [{index}], got {type(current).__name__} (at {current_path})"
                )
            current = current[index]
            current_path = f"{current_path}[{index}]"
            trace.append((current_path, current))
            continue

        raise ValueError(f"unknown token kind: {token.kind!r}")

    return current, trace


def main(argv: Optional[Iterable[str]] = None) -> None:
    """
    通用 JSON/字典路径查询工具。

    示例：
    - 基础摘要：python -X utf8 -m ugc_file_tools tool inspect_json --input dump.json --path 4.10.2
    - 路径 trace：python -X utf8 -m ugc_file_tools tool inspect_json --input dump.json --path 4.10.2[0].1.102 --trace
    - 输出 JSON： python -X utf8 -m ugc_file_tools tool inspect_json --input dump.json --path 4.10.2[0].1 --format json
    """
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="通用 JSON 深层路径查询/探测工具（dict/list；用于替代临时 python -c 结构探测脚本）。"
    )
    parser.add_argument("--input", required=True, help="输入 JSON 文件路径。")
    parser.add_argument("--encoding", default="utf-8", help="读取编码（默认 utf-8）。")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="要查询的路径（可重复）；支持 a.b[0].c 或 a/b/0/c；留空表示 root。",
    )
    parser.add_argument("--trace", action="store_true", help="打印 root→目标的逐步摘要（type/len/keys）。")
    parser.add_argument(
        "--format",
        choices=["info", "json", "repr"],
        default="info",
        help="输出格式：info=摘要（默认），json=输出 JSON，repr=输出 Python repr。",
    )
    parser.add_argument("--max-keys", type=int, default=20, help="dict keys 预览数量（默认 20；<=0 关闭）。")
    parser.add_argument("--max-items", type=int, default=10, help="list item_types 预览数量（默认 10；<=0 关闭）。")
    parser.add_argument("--max-text", type=int, default=200, help="字符串预览长度（默认 200）。")
    parser.add_argument(
        "--keep-order",
        action="store_true",
        help="不排序 dict keys 预览（默认会对纯数字 key 做数值排序）。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    input_path = Path(args.input)
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    root_value: JsonValue = json.loads(input_path.read_text(encoding=str(args.encoding)))

    requested_paths = list(args.path) if args.path else [""]
    sort_keys = not bool(args.keep_order)

    for path_text in requested_paths:
        tokens = _parse_path_tokens(path_text)
        value, trace = _navigate_json_value(root_value, tokens=tokens)

        print("=" * 80)
        print(f"file: {input_path}")
        print(f"path: {path_text or '<root>'}")

        if args.format == "json":
            print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False))
            continue

        if args.format == "repr":
            print(repr(value))
            continue

        if args.trace:
            for step_path, step_value in trace:
                print("-" * 80)
                print(step_path)
                for line in _describe_value(
                    step_value,
                    max_keys=int(args.max_keys),
                    max_items=int(args.max_items),
                    max_text=int(args.max_text),
                    sort_keys=sort_keys,
                ):
                    print(f"  {line}")
            continue

        for line in _describe_value(
            value,
            max_keys=int(args.max_keys),
            max_items=int(args.max_items),
            max_text=int(args.max_text),
            sort_keys=sort_keys,
        ):
            print(line)


if __name__ == "__main__":
    main()



