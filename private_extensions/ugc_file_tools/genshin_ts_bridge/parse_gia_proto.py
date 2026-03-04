from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass(frozen=True, slots=True)
class ProtoEnum:
    name: str
    members_by_name: Dict[str, int]
    members_by_value: Dict[int, str]


def _strip_line_comment(line: str) -> str:
    idx = line.find("//")
    return line if idx < 0 else line[:idx]


def _extract_block_lines(text: str, *, begin_token: str) -> List[str]:
    lines = text.splitlines()
    start = None
    brace_depth = 0
    out: List[str] = []
    for i, raw in enumerate(lines):
        line = _strip_line_comment(raw).strip()
        if start is None:
            if line.startswith(begin_token):
                # 允许 `enum X {` 同行开括号
                start = i
                if "{" in line:
                    brace_depth += line.count("{")
                    brace_depth -= line.count("}")
                continue
        else:
            brace_depth += line.count("{")
            brace_depth -= line.count("}")
            out.append(raw)
            if brace_depth <= 0 and "}" in line:
                break
    if start is None:
        raise ValueError(f"未找到枚举定义：{begin_token}")
    return out


def _parse_enum_members(lines: List[str]) -> Tuple[Dict[str, int], Dict[int, str]]:
    by_name: Dict[str, int] = {}
    by_value: Dict[int, str] = {}
    for raw in lines:
        line = _strip_line_comment(raw).strip()
        if not line:
            continue
        if line.startswith("}"):
            break
        # 期望形态：Name = 123;
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        key = left.strip()
        right = right.strip().rstrip(";").strip()
        if key == "":
            continue
        if right == "":
            continue
        # 允许负数（例如 enum placeholder），但这里主要是正数
        value = int(right)
        by_name[key] = int(value)
        by_value[int(value)] = key
    if not by_name:
        raise ValueError("枚举成员为空或解析失败")
    return by_name, by_value


def parse_enum_from_proto(*, proto_path: Path, enum_name: str) -> ProtoEnum:
    path = Path(proto_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    text = path.read_text(encoding="utf-8")
    begin = f"enum {enum_name}"
    block_lines = _extract_block_lines(text, begin_token=begin)
    members_by_name, members_by_value = _parse_enum_members(block_lines)
    return ProtoEnum(
        name=str(enum_name),
        members_by_name=members_by_name,
        members_by_value=members_by_value,
    )

