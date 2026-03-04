from __future__ import annotations

"""
report_gil_dump_json_diff.py

用途：
- 将两份 `.gil` 的 payload 解码为 dump-json（数值键 JSON，顶层形态 `{"4": <payload_root>}`），
  并对两份 dump-json 做深度 diff，输出“差异路径清单 + 摘要报告”。

设计目标：
- 纯 Python；不依赖外部 DLL。
- fail-fast：不使用 try/except；遇到不支持/不一致结构直接抛错。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_dump_json_object
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


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


def _try_get_value_by_tokens(root_value: JsonValue, *, tokens: list[_PathToken]) -> Tuple[bool, JsonValue]:
    """
    安全导航：不抛 KeyError/IndexError（用于 `--path` 可选 diff 子树）。

    返回：
    - (True, value)：路径存在
    - (False, None)：路径不存在或类型不匹配
    """
    current: JsonValue = root_value
    for token in tokens:
        if token.kind == "seg":
            seg = str(token.value)
            if isinstance(current, dict):
                if seg in current:
                    current = current[seg]
                    continue
                if seg.isdigit() and int(seg) in current:
                    current = current[int(seg)]
                    continue
                return (False, None)
            if isinstance(current, list):
                if not seg.isdigit():
                    return (False, None)
                index = int(seg)
                if 0 <= index < len(current):
                    current = current[index]
                    continue
                return (False, None)
            return (False, None)

        if token.kind == "index":
            index = int(token.value)
            if not isinstance(current, list):
                return (False, None)
            if 0 <= index < len(current):
                current = current[index]
                continue
            return (False, None)

        raise ValueError(f"unknown token kind: {token.kind!r}")

    return (True, current)


def _sort_key_for_dump_json_key(key: Any) -> Tuple[int, int, str]:
    if isinstance(key, str) and key.isdigit():
        return (0, int(key), key)
    return (1, 0, str(key))


def _summarize_value(value: JsonValue) -> JsonValue:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if len(value) <= 200:
            return value
        return {"kind": "string", "length": len(value), "preview": value[:200]}
    if isinstance(value, list):
        head = value[:12]
        return {"kind": "list", "length": len(value), "head": [_summarize_value(x) for x in head]}
    if isinstance(value, dict):
        keys = [str(k) for k in value.keys()]
        keys_sorted = sorted(keys, key=lambda k: _sort_key_for_dump_json_key(k))
        return {"kind": "dict", "length": len(keys_sorted), "keys_head": keys_sorted[:30]}
    return {"kind": "unknown", "python_type": type(value).__name__}


def _format_path_dot(path: Sequence[str | int]) -> str:
    parts: List[str] = []
    for seg in path:
        if isinstance(seg, int):
            parts.append(f"[{int(seg)}]")
            continue
        text = str(seg)
        if not parts:
            parts.append(text)
        else:
            parts.append("." + text)
    return "".join(parts)


def _format_path_slash(path: Sequence[str | int]) -> str:
    return "/".join(str(int(x)) if isinstance(x, int) else str(x) for x in path)


def _diff_dump_json(
    a: JsonValue,
    b: JsonValue,
    *,
    max_diff_items: int,
    max_depth: int,
    base_path: Optional[List[str | int]] = None,
    label_a: str = "a",
    label_b: str = "b",
) -> Dict[str, Any]:
    """
    深度 diff：输出路径级差异清单（截断可控）。

    说明：
    - dict：对比 key 集合；缺失 key 只记录一条（不展开子树）。
    - list：对比长度；共享前缀逐项递归；extra items 记录为缺失项（受 max_diff_items 截断）。
    """
    base_path = list(base_path or [])
    diffs: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    truncated = False

    # stack item: (path, depth, a_value, b_value)
    stack: List[Tuple[List[str | int], int, JsonValue, JsonValue]] = [(base_path, 0, a, b)]

    def push(path: List[str | int], depth: int, av: JsonValue, bv: JsonValue) -> None:
        stack.append((path, depth, av, bv))

    def add_diff(kind: str, *, path: List[str | int], a_value: JsonValue, b_value: JsonValue) -> None:
        nonlocal truncated
        counts[kind] = int(counts.get(kind, 0)) + 1
        if int(max_diff_items) > 0 and len(diffs) >= int(max_diff_items):
            truncated = True
            return
        diffs.append(
            {
                "kind": str(kind),
                "path": list(path),
                "path_dot": _format_path_dot(path),
                "path_slash": _format_path_slash(path),
                f"{label_a}": _summarize_value(a_value),
                f"{label_b}": _summarize_value(b_value),
                f"{label_a}_type": type(a_value).__name__,
                f"{label_b}_type": type(b_value).__name__,
            }
        )

    while stack:
        path, depth, av, bv = stack.pop()
        if truncated:
            break

        if av is bv:
            continue
        if av == bv:
            continue

        if int(max_depth) > 0 and int(depth) >= int(max_depth):
            add_diff("max_depth_reached", path=path, a_value=av, b_value=bv)
            continue

        if type(av) is not type(bv):
            add_diff("type_mismatch", path=path, a_value=av, b_value=bv)
            continue

        if isinstance(av, dict):
            keys_a = set(av.keys())
            keys_b = set(bv.keys())

            missing_in_a = sorted(list(keys_b - keys_a), key=_sort_key_for_dump_json_key)
            missing_in_b = sorted(list(keys_a - keys_b), key=_sort_key_for_dump_json_key)
            shared = sorted(list(keys_a & keys_b), key=_sort_key_for_dump_json_key)

            for k in missing_in_a:
                add_diff("missing_in_a", path=[*path, str(k)], a_value=None, b_value=bv.get(k))
                if truncated:
                    break
            for k in missing_in_b:
                add_diff("missing_in_b", path=[*path, str(k)], a_value=av.get(k), b_value=None)
                if truncated:
                    break

            # LIFO stack：倒序 push，保证 pop 时按 shared 的正序处理
            for k in reversed(shared):
                child_path = [*path, str(k)]
                push(child_path, depth + 1, av.get(k), bv.get(k))
            continue

        if isinstance(av, list):
            len_a = len(av)
            len_b = len(bv)
            if int(len_a) != int(len_b):
                add_diff("list_length_mismatch", path=path, a_value=len_a, b_value=len_b)

            shared_len = min(len_a, len_b)
            # 共享前缀逐项 diff
            for i in range(shared_len - 1, -1, -1):
                push([*path, int(i)], depth + 1, av[int(i)], bv[int(i)])

            # extra items：只记录缺失项，不展开子树
            if len_b > shared_len:
                for i in range(shared_len, len_b):
                    add_diff("missing_in_a", path=[*path, int(i)], a_value=None, b_value=bv[int(i)])
                    if truncated:
                        break
            if len_a > shared_len:
                for i in range(shared_len, len_a):
                    add_diff("missing_in_b", path=[*path, int(i)], a_value=av[int(i)], b_value=None)
                    if truncated:
                        break
            continue

        # scalar / other
        add_diff("value_mismatch", path=path, a_value=av, b_value=bv)

    counts_sorted = [{"kind": str(k), "count": int(v)} for k, v in sorted(counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))]
    return {
        "diff_items_count": int(sum(int(v) for v in counts.values())),
        "diff_items_written": int(len(diffs)),
        "diff_kind_counts": counts_sorted,
        "diff_items": diffs,
        "truncated": bool(truncated),
        "limits": {"max_diff_items": int(max_diff_items), "max_depth": int(max_depth)},
    }


def _ensure_directory(target_dir: Path) -> None:
    Path(target_dir).mkdir(parents=True, exist_ok=True)


def _write_json_file(target_path: Path, payload: Any) -> None:
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text_file(target_path: Path, text: str) -> None:
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_path).write_text(str(text or ""), encoding="utf-8")


def build_report(
    a_gil_file: Path,
    b_gil_file: Path,
    *,
    output_dir: Path,
    max_decode_depth: int = 32,
    prefer_raw_hex_for_utf8: bool = False,
    max_diff_items: int = 5000,
    max_diff_depth: int = 256,
    label_a: str = "a",
    label_b: str = "b",
    dump_dump_json: bool = True,
    paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    a_gil_file = Path(a_gil_file).resolve()
    b_gil_file = Path(b_gil_file).resolve()
    if not a_gil_file.is_file():
        raise FileNotFoundError(str(a_gil_file))
    if not b_gil_file.is_file():
        raise FileNotFoundError(str(b_gil_file))

    output_dir = resolve_output_dir_path_in_out_dir(Path(output_dir), default_dir_name="gil_dump_json_diff")
    _ensure_directory(output_dir)

    dump_a: Dict[str, Any] = load_gil_payload_as_dump_json_object(
        a_gil_file, max_depth=int(max_decode_depth), prefer_raw_hex_for_utf8=bool(prefer_raw_hex_for_utf8)
    )
    dump_b: Dict[str, Any] = load_gil_payload_as_dump_json_object(
        b_gil_file, max_depth=int(max_decode_depth), prefer_raw_hex_for_utf8=bool(prefer_raw_hex_for_utf8)
    )

    a_dump_path = output_dir / f"{label_a}.dump.json"
    b_dump_path = output_dir / f"{label_b}.dump.json"
    if dump_dump_json:
        _write_json_file(a_dump_path, dump_a)
        _write_json_file(b_dump_path, dump_b)

    requested_paths = list(paths or [])
    if not requested_paths:
        requested_paths = [""]

    per_path_results: List[Dict[str, Any]] = []
    summary_lines: List[str] = []
    summary_lines.append("## GIL dump-json diff 报告")
    summary_lines.append("")
    summary_lines.append(f"- {label_a}: `{a_gil_file}`")
    summary_lines.append(f"- {label_b}: `{b_gil_file}`")
    summary_lines.append(f"- max_decode_depth: {int(max_decode_depth)}")
    summary_lines.append(f"- prefer_raw_hex_for_utf8: {bool(prefer_raw_hex_for_utf8)}")
    summary_lines.append(f"- max_diff_items: {int(max_diff_items)}（0=不截断）")
    summary_lines.append(f"- max_diff_depth: {int(max_diff_depth)}（0=不限制）")
    summary_lines.append("")

    for path_text in requested_paths:
        tokens = _parse_path_tokens(path_text)
        ok_a, sub_a = _try_get_value_by_tokens(dump_a, tokens=tokens)
        ok_b, sub_b = _try_get_value_by_tokens(dump_b, tokens=tokens)
        base_path = [t.value for t in tokens]

        if not ok_a or not ok_b:
            # 不在此处抛错：保留 diff 证据，便于用户快速定位“路径只存在一侧”的情况
            result = {
                "path": str(path_text or "<root>"),
                "path_tokens": list(base_path),
                "status": "path_missing",
                f"missing_in_{label_a}": bool(not ok_a),
                f"missing_in_{label_b}": bool(not ok_b),
                f"{label_a}": _summarize_value(sub_a if ok_a else None),
                f"{label_b}": _summarize_value(sub_b if ok_b else None),
                "diff": _diff_dump_json(
                    sub_a if ok_a else None,
                    sub_b if ok_b else None,
                    max_diff_items=int(max_diff_items),
                    max_depth=int(max_diff_depth),
                    base_path=list(base_path),
                    label_a=str(label_a),
                    label_b=str(label_b),
                ),
            }
        else:
            result = {
                "path": str(path_text or "<root>"),
                "path_tokens": list(base_path),
                "status": "ok",
                "diff": _diff_dump_json(
                    sub_a,
                    sub_b,
                    max_diff_items=int(max_diff_items),
                    max_depth=int(max_diff_depth),
                    base_path=list(base_path),
                    label_a=str(label_a),
                    label_b=str(label_b),
                ),
            }

        per_path_results.append(result)
        diff = result.get("diff") or {}
        summary_lines.append(f"### path: {result.get('path')}")
        summary_lines.append("")
        summary_lines.append(f"- status: {result.get('status')}")
        summary_lines.append(f"- diff_items_count: {diff.get('diff_items_count')}")
        summary_lines.append(f"- diff_items_written: {diff.get('diff_items_written')}")
        summary_lines.append(f"- truncated: {diff.get('truncated')}")
        summary_lines.append("")

    report_path = output_dir / "report.json"
    _write_json_file(
        report_path,
        {
            "label_a": str(label_a),
            "label_b": str(label_b),
            "a_gil_file": str(a_gil_file),
            "b_gil_file": str(b_gil_file),
            "output_dir": str(output_dir),
            "decode_options": {
                "max_depth": int(max_decode_depth),
                "prefer_raw_hex_for_utf8": bool(prefer_raw_hex_for_utf8),
            },
            "diff_options": {
                "max_diff_items": int(max_diff_items),
                "max_diff_depth": int(max_diff_depth),
                "paths": requested_paths,
            },
            "files": {
                f"{label_a}_dump_json": str(a_dump_path) if dump_dump_json else None,
                f"{label_b}_dump_json": str(b_dump_path) if dump_dump_json else None,
                "summary_md": "summary.md",
            },
            "paths": per_path_results,
        },
    )

    summary_md_path = output_dir / "summary.md"
    _write_text_file(summary_md_path, "\n".join(summary_lines) + "\n")

    index_path = output_dir / "index.json"
    _write_json_file(
        index_path,
        {
            "label_a": str(label_a),
            "label_b": str(label_b),
            "a_gil_file": str(a_gil_file),
            "b_gil_file": str(b_gil_file),
            "output_dir": str(output_dir),
            "files": {
                "report_json": str(report_path.relative_to(output_dir)).replace("\\", "/"),
                "summary_md": str(summary_md_path.relative_to(output_dir)).replace("\\", "/"),
                f"{label_a}_dump_json": (f"{label_a}.dump.json" if dump_dump_json else None),
                f"{label_b}_dump_json": (f"{label_b}.dump.json" if dump_dump_json else None),
            },
            "paths": [
                {
                    "path": item.get("path"),
                    "status": item.get("status"),
                    "diff_items_count": (item.get("diff") or {}).get("diff_items_count"),
                    "diff_items_written": (item.get("diff") or {}).get("diff_items_written"),
                    "diff_kind_counts": (item.get("diff") or {}).get("diff_kind_counts"),
                    "truncated": (item.get("diff") or {}).get("truncated"),
                }
                for item in list(per_path_results)
            ],
        },
    )

    claude_path = output_dir / "claude.md"
    _write_text_file(
        claude_path,
        "\n".join(
            [
                "## 目录用途",
                "- 存放 `report_gil_dump_json_diff` 生成的对照报告：将两份 `.gil` 解码为 dump-json（数值键 JSON）并输出深度 diff（按路径列出差异）。",
                "",
                "## 当前状态",
                f"- 当前来源：`{a_gil_file}` vs `{b_gil_file}`",
                f"- paths: {requested_paths if requested_paths else ['<root>']}",
                f"- max_diff_items: {int(max_diff_items)}",
                "",
                "## 注意事项",
                "- dump-json 顶层固定为 `{\"4\": <payload_root>}`（对齐工具链中间表示）。",
                "- 本目录为分析产物，可随时删除重建。",
                "- 本文件不记录修改历史，仅保持用途/状态/注意事项的实时描述。",
                "",
                "---",
                "注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。",
                "",
            ]
        ),
    )

    return {
        "output_dir": str(output_dir),
        "index": str(index_path),
        "report": str(report_path),
        "summary_md": str(summary_md_path),
        f"{label_a}_dump_json": str(a_dump_path) if dump_dump_json else None,
        f"{label_b}_dump_json": str(b_dump_path) if dump_dump_json else None,
    }


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="对比两份 .gil 的 dump-json(payload 数值键 JSON)，输出深度 diff 报告（写入 ugc_file_tools/out/）。"
    )
    argument_parser.add_argument("--a-gil", dest="a_gil_file", required=True, help="输入 .gil A 路径")
    argument_parser.add_argument("--b-gil", dest="b_gil_file", required=True, help="输入 .gil B 路径")
    argument_parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="gil_dump_json_diff",
        help="输出目录（默认：gil_dump_json_diff；实际会被收口到 ugc_file_tools/out/ 下）。",
    )
    argument_parser.add_argument(
        "--max-decode-depth",
        dest="max_decode_depth",
        type=int,
        default=32,
        help="dump-json 解码深度上限（默认 32）。",
    )
    argument_parser.add_argument(
        "--prefer-raw-hex-for-utf8",
        dest="prefer_raw_hex_for_utf8",
        action="store_true",
        help="更保守的 dump-json：utf8 节点也优先转为 `<binary_data>`（便于 lossless 对照）。",
    )
    argument_parser.add_argument(
        "--max-diff-items",
        dest="max_diff_items",
        type=int,
        default=5000,
        help="diff 明细最大条目数（默认 5000；0=不截断，可能生成很大的报告）。",
    )
    argument_parser.add_argument(
        "--max-diff-depth",
        dest="max_diff_depth",
        type=int,
        default=256,
        help="diff 递归深度上限（默认 256；0=不限制）。",
    )
    argument_parser.add_argument(
        "--label-a",
        dest="label_a",
        default="a",
        help="报告中 A 的标签（默认 a）。",
    )
    argument_parser.add_argument(
        "--label-b",
        dest="label_b",
        default="b",
        help="报告中 B 的标签（默认 b）。",
    )
    argument_parser.add_argument(
        "--no-dump-json",
        dest="no_dump_json",
        action="store_true",
        help="不落盘两侧 dump-json（只落盘 report/summary）。",
    )
    argument_parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        default=[],
        help="仅对比指定子树路径（可重复）；路径语法同 inspect_json，例如 `4.10.5` 或 `4/10/5`。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    result = build_report(
        Path(arguments.a_gil_file),
        Path(arguments.b_gil_file),
        output_dir=Path(arguments.output_dir),
        max_decode_depth=int(arguments.max_decode_depth),
        prefer_raw_hex_for_utf8=bool(arguments.prefer_raw_hex_for_utf8),
        max_diff_items=int(arguments.max_diff_items),
        max_diff_depth=int(arguments.max_diff_depth),
        label_a=str(arguments.label_a),
        label_b=str(arguments.label_b),
        dump_dump_json=(not bool(arguments.no_dump_json)),
        paths=list(arguments.paths or []),
    )

    print("=" * 80)
    print("GIL dump-json diff 报告生成完成：")
    print(f"- output_dir: {result.get('output_dir')}")
    print(f"- index: {result.get('index')}")
    print(f"- report: {result.get('report')}")
    print(f"- summary_md: {result.get('summary_md')}")
    print(f"- {arguments.label_a}.dump.json: {result.get(str(arguments.label_a) + '_dump_json')}")
    print(f"- {arguments.label_b}.dump.json: {result.get(str(arguments.label_b) + '_dump_json')}")
    print("=" * 80)


if __name__ == "__main__":
    main()

