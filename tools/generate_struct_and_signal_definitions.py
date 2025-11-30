from __future__ import annotations

"""
一次性工具脚本：从现有 JSON 结构体定义与信号聚合文件生成
`engine.configs.specialized.struct_definitions_data` 与
`engine.configs.specialized.signal_definitions_data` 两个 Python 模块。

设计目标：
- 将当前 assets/资源库/管理配置 下的结构体与信号定义“固化”为 Python 常量，
  便于后续在引擎与编辑器中以代码形式引用；
- 生成的模块只包含纯 Python 字典与简单辅助函数，不再在运行时依赖 JSON 文件；
- 本脚本本身仅作为开发期工具使用，不参与运行时逻辑。

使用方式（在项目根目录执行）：

    python -X utf8 tools/generate_struct_and_signal_definitions.py

执行完成后会覆盖生成：
- engine/configs/specialized/struct_definitions_data.py
- engine/configs/specialized/signal_definitions_data.py
"""

import json
from pathlib import Path
from typing import Any, Dict


def _load_struct_definitions(struct_dir: Path) -> Dict[str, Dict[str, Any]]:
    """从结构体定义 JSON 目录加载 {struct_id: payload} 映射。

    约定：
    - struct_id 使用文件名（不含扩展名），例如 `玩家存档.json` -> "玩家存档"；
    - payload 为原始 JSON 字典，保持与现有 Struct JSON 结构一致。
    """
    entries: Dict[str, Dict[str, Any]] = {}

    for json_path in sorted(struct_dir.glob("*.json")):
        if not json_path.is_file():
            continue
        text = json_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            continue
        struct_id = json_path.stem
        entries[struct_id] = data
    return entries


def _load_signal_definitions(signal_dir: Path) -> Dict[str, Dict[str, Any]]:
    """从信号聚合 JSON 目录加载 {signal_id: payload} 映射。

    约定：
    - 每个 JSON 文件为一个聚合资源，内容为 {signal_id: payload} 字典；
    - payload 中必须包含 "signal_id" 与 "signal_name" 字段才视为有效信号；
    - 顶层的管理字段（如 "updated_at"）会被忽略。
    """
    entries: Dict[str, Dict[str, Any]] = {}

    for json_path in sorted(signal_dir.glob("*.json")):
        if not json_path.is_file():
            continue
        text = json_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            continue

        for key, payload in data.items():
            if not isinstance(payload, dict):
                continue
            signal_id_value = payload.get("signal_id")
            signal_name_value = payload.get("signal_name")
            if not isinstance(signal_id_value, str) or not signal_id_value:
                continue
            if not isinstance(signal_name_value, str) or not signal_name_value:
                continue
            signal_id = signal_id_value
            # 若多个聚合文件中出现重复 ID，后出现的覆盖前者
            entries[signal_id] = payload

    return entries


def _format_dict_literal(mapping: Dict[str, Dict[str, Any]], var_name: str) -> str:
    """将 {key: payload} 映射格式化为 Python 字典字面量代码片段。"""
    lines: list[str] = []
    lines.append(f"{var_name}: Dict[str, Dict[str, Any]] = {{")
    for key in sorted(mapping.keys()):
        payload = mapping[key]
        key_repr = repr(key)
        payload_repr = repr(payload)
        lines.append(f"    {key_repr}: {payload_repr},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_struct_definitions_module(target_path: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    """生成 struct_definitions_data.py 模块。"""
    header_lines: list[str] = [
        "from __future__ import annotations",
        "",
        "from typing import Any, Dict",
        "",
        "# 本文件由 tools/generate_struct_and_signal_definitions.py 自动生成。",
        "# 结构体定义以 Python 字典常量形式固化为 STRUCT_DEFINITION_PAYLOADS。",
        "# 运行时不再依赖 assets/资源库/管理配置/结构体定义 下的 JSON 文件。",
        "",
    ]
    body = _format_dict_literal(entries, "STRUCT_DEFINITION_PAYLOADS")

    helper_lines: list[str] = [
        "def list_struct_ids() -> list[str]:",
        '    """返回所有可用的结构体 ID 列表（排序后）。"""',
        "    return sorted(STRUCT_DEFINITION_PAYLOADS.keys())",
        "",
        "def get_struct_payload(struct_id: str) -> Dict[str, Any] | None:",
        '    """按 ID 获取单个结构体定义载荷的浅拷贝，未找到时返回 None。"""',
        "    key = str(struct_id)",
        "    payload = STRUCT_DEFINITION_PAYLOADS.get(key)",
        "    if payload is None:",
        "        return None",
        "    return dict(payload)",
        "",
    ]

    content = "\n".join(header_lines + [body] + helper_lines)
    target_path.write_text(content, encoding="utf-8")


def _generate_signal_definitions_module(target_path: Path, entries: Dict[str, Dict[str, Any]]) -> None:
    """生成 signal_definitions_data.py 模块。"""
    header_lines: list[str] = [
        "from __future__ import annotations",
        "",
        "from typing import Any, Dict",
        "",
        "# 本文件由 tools/generate_struct_and_signal_definitions.py 自动生成。",
        "# 信号定义以 Python 字典常量形式固化为 SIGNAL_DEFINITION_PAYLOADS。",
        "# 运行时不再依赖 assets/资源库/管理配置/信号 下的聚合 JSON 文件。",
        "",
    ]
    body = _format_dict_literal(entries, "SIGNAL_DEFINITION_PAYLOADS")

    helper_lines: list[str] = [
        "def list_signal_ids() -> list[str]:",
        '    """返回所有可用的信号 ID 列表（排序后）。"""',
        "    return sorted(SIGNAL_DEFINITION_PAYLOADS.keys())",
        "",
        "def get_signal_payload(signal_id: str) -> Dict[str, Any] | None:",
        '    """按 ID 获取单个信号定义载荷的浅拷贝，未找到时返回 None。"""',
        "    key = str(signal_id)",
        "    payload = SIGNAL_DEFINITION_PAYLOADS.get(key)",
        "    if payload is None:",
        "        return None",
        "    return dict(payload)",
        "",
    ]

    content = "\n".join(header_lines + [body] + helper_lines)
    target_path.write_text(content, encoding="utf-8")


def main() -> None:
    workspace = Path(__file__).resolve().parents[1]

    struct_dir = workspace / "assets" / "资源库" / "管理配置" / "结构体定义"
    signal_dir = workspace / "assets" / "资源库" / "管理配置" / "信号"
    target_configs_dir = workspace / "engine" / "configs" / "specialized"

    if not struct_dir.is_dir():
        raise SystemExit(f"找不到结构体定义目录: {struct_dir}")
    if not signal_dir.is_dir():
        raise SystemExit(f"找不到信号定义目录: {signal_dir}")
    if not target_configs_dir.is_dir():
        raise SystemExit(f"找不到目标配置目录: {target_configs_dir}")

    struct_entries = _load_struct_definitions(struct_dir)
    signal_entries = _load_signal_definitions(signal_dir)

    if not struct_entries:
        raise SystemExit("未在结构体定义目录中找到任何 JSON 文件，无法生成模块。")

    struct_module_path = target_configs_dir / "struct_definitions_data.py"
    signal_module_path = target_configs_dir / "signal_definitions_data.py"

    _generate_struct_definitions_module(struct_module_path, struct_entries)
    _generate_signal_definitions_module(signal_module_path, signal_entries)

    print(f"[OK] 已生成结构体定义模块: {struct_module_path}")
    print(f"[OK] 已生成信号定义模块: {signal_module_path}")


if __name__ == "__main__":
    main()


