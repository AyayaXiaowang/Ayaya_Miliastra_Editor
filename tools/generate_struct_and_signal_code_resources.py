from __future__ import annotations

"""
从现有 JSON 结构体/信号定义生成**就地的**代码级资源（每个资源一个 .py 文件）。

约定：
- 结构体代码资源目录：assets/资源库/管理配置/结构体定义
  - 不再使用单独的 `_py` 子目录，直接在该目录下为每个结构体生成一个 Python 模块；
  - 文件名为结构体 ID 的安全文件名（通过 `sanitize_resource_filename` 规范化）；
  - 每个文件导出：
    - STRUCT_ID: str
    - STRUCT_TYPE: str
    - STRUCT_PAYLOAD: Dict[str, Any]
- 信号代码资源目录：assets/资源库/管理配置/信号
  - 不再使用单独的 `_py` 子目录，直接在该目录下为每个信号生成一个 Python 模块；
  - 文件名为信号 ID 的安全文件名；
  - 每个文件导出：
    - SIGNAL_ID: str
    - SIGNAL_PAYLOAD: Dict[str, Any]

生成后的代码资源会被 `engine.resources.definition_schema_view.CodeSchemaResourceService`
优先加载，作为结构体/信号定义的代码级真相源；当这些目录不存在或为空时，
仍回退到引擎配置中的集中常量。

使用方式（在项目根目录执行）：

    python -X utf8 tools/generate_struct_and_signal_code_resources.py
"""

from pathlib import Path
from typing import Any, Dict

import json
import pprint

from engine.utils.name_utils import sanitize_resource_filename


def _load_struct_definitions(struct_dir: Path) -> Dict[str, Dict[str, Any]]:
    """从结构体定义 JSON 目录加载 {struct_id: payload}。"""
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
    """从信号聚合 JSON 目录加载 {signal_id: payload} 映射。"""
    entries: Dict[str, Dict[str, Any]] = {}

    for json_path in sorted(signal_dir.glob("*.json")):
        if not json_path.is_file():
            continue
        text = json_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            continue

        for _key, payload in data.items():
            if not isinstance(payload, dict):
                continue
            signal_id_value = payload.get("signal_id")
            signal_name_value = payload.get("signal_name")
            if not isinstance(signal_id_value, str) or not signal_id_value:
                continue
            if not isinstance(signal_name_value, str) or not signal_name_value:
                continue
            signal_id = signal_id_value
            entries[signal_id] = payload

    return entries


def _format_struct_module(struct_id: str, payload: Dict[str, Any]) -> str:
    struct_type_raw = payload.get("struct_ype", "")
    struct_type = str(struct_type_raw).strip() if isinstance(struct_type_raw, str) else ""
    if not struct_type:
        struct_type = "basic"

    struct_id_text = str(struct_id)
    name_value = payload.get("name")
    name_text = str(name_value) if isinstance(name_value, str) else struct_id_text

    normalized_payload = dict(payload)
    normalized_payload["type"] = "Struct"
    normalized_payload["struct_ype"] = struct_type
    normalized_payload["name"] = name_text

    body_text = pprint.pformat(normalized_payload, width=120, sort_dicts=False)

    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from typing import Any, Dict")
    lines.append("")
    lines.append(f'STRUCT_ID = {repr(struct_id_text)}')
    lines.append(f'STRUCT_TYPE = {repr(struct_type)}')
    lines.append("")
    lines.append("STRUCT_PAYLOAD: Dict[str, Any] = " + body_text)
    lines.append("")
    return "\n".join(lines)


def _format_signal_module(signal_id: str, payload: Dict[str, Any]) -> str:
    normalized_payload = dict(payload)
    signal_id_value = normalized_payload.get("signal_id")
    if not isinstance(signal_id_value, str) or not signal_id_value:
        normalized_payload["signal_id"] = signal_id

    body_text = pprint.pformat(normalized_payload, width=120, sort_dicts=False)

    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from typing import Any, Dict")
    lines.append("")
    lines.append(f'SIGNAL_ID = {repr(signal_id)}')
    lines.append("")
    lines.append("SIGNAL_PAYLOAD: Dict[str, Any] = " + body_text)
    lines.append("")
    return "\n".join(lines)


def _generate_struct_code_resources(
    target_root: Path,
    entries: Dict[str, Dict[str, Any]],
) -> None:
    """在目标根目录下生成结构体代码资源（一结构体一文件）。"""
    target_root.mkdir(parents=True, exist_ok=True)

    for struct_id, payload in entries.items():
        if not isinstance(payload, dict):
            continue

        safe_name = sanitize_resource_filename(struct_id)
        module_path = target_root / f"{safe_name}.py"
        module_content = _format_struct_module(struct_id, payload)
        module_path.write_text(module_content, encoding="utf-8")


def _generate_signal_code_resources(
    target_root: Path,
    entries: Dict[str, Dict[str, Any]],
) -> None:
    """在目标根目录下生成信号代码资源（一信号一文件）。"""
    target_root.mkdir(parents=True, exist_ok=True)

    for signal_id, payload in entries.items():
        if not isinstance(payload, dict):
            continue

        safe_name = sanitize_resource_filename(signal_id)
        module_path = target_root / f"{safe_name}.py"
        module_content = _format_signal_module(signal_id, payload)
        module_path.write_text(module_content, encoding="utf-8")


def main() -> None:
    workspace = Path(__file__).resolve().parents[1]

    struct_json_dir = workspace / "assets" / "资源库" / "管理配置" / "结构体定义"
    signal_json_dir = workspace / "assets" / "资源库" / "管理配置" / "信号"

    if not struct_json_dir.is_dir():
        raise SystemExit(f"找不到结构体定义目录: {struct_json_dir}")
    if not signal_json_dir.is_dir():
        raise SystemExit(f"找不到信号定义目录: {signal_json_dir}")

    struct_entries = _load_struct_definitions(struct_json_dir)
    signal_entries = _load_signal_definitions(signal_json_dir)

    if not struct_entries:
        raise SystemExit("未在结构体定义目录中找到任何 JSON 文件，无法生成结构体代码资源。")

    struct_target_root = struct_json_dir
    signal_target_root = signal_json_dir

    _generate_struct_code_resources(struct_target_root, struct_entries)
    _generate_signal_code_resources(signal_target_root, signal_entries)

    print(f"[OK] 已在目录生成结构体代码资源: {struct_target_root}")
    print(f"[OK] 已在目录生成信号代码资源: {signal_target_root}")


if __name__ == "__main__":
    main()


