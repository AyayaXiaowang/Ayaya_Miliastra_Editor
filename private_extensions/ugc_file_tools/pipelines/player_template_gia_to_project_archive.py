from __future__ import annotations

import json
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.gia_export.templates import (
    extract_custom_variable_defs_from_bundle,
    load_component_base_bundle_from_gia,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text


@dataclass(frozen=True, slots=True)
class ImportPlayerTemplateGiaPlan:
    """
    `.gia` 玩家模板 → 写入项目存档：
    - 战斗预设/玩家模板/*.json
    - 管理配置/关卡变量/自定义变量/*.py（VARIABLE_FILE_ID + LEVEL_VARIABLES）
    """

    input_gia_file: Path
    project_archive_path: Path
    # 可选：覆盖写入（默认 False：若目标文件存在则直接抛错）
    overwrite: bool = False
    # 可选：自定义输出变量文件 ID（VARIABLE_FILE_ID）；为空则自动生成
    output_variable_file_id: str = ""
    # 可选：自定义输出变量文件显示名（VARIABLE_FILE_NAME）；为空则自动生成
    output_variable_file_name: str = ""
    # 可选：自定义输出玩家模板 template_id；为空则自动生成
    output_template_id: str = ""


def _coerce_non_empty_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if text == "":
        raise ValueError(f"{field_name} 不能为空")
    return text


def _coerce_utf8_text(value: Any, *, field_name: str) -> str:
    if isinstance(value, str):
        if value.startswith("<binary_data>"):
            raw = parse_binary_data_hex_text(value)
            decoded = raw.decode("utf-8", errors="replace")
            return str(decoded).strip()
        return str(value).strip()
    return str(value if value is not None else "").strip()


def _build_imported_variable_id(*, package_id: str, variable_name: str) -> str:
    name = _coerce_non_empty_text(variable_name, field_name="variable_name")
    crc32 = int(zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF)
    return f"pt_{crc32:08x}__{str(package_id)}"


def _write_variable_file(
    path: Path,
    *,
    file_id: str,
    file_name: str,
    variables: List[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from engine.graph.models.package_model import LevelVariableDefinition")
    lines.append("")
    lines.append(f'VARIABLE_FILE_ID = "{file_id}"')
    lines.append(f'VARIABLE_FILE_NAME = "{file_name}"')
    lines.append("")
    lines.append("LEVEL_VARIABLES: list[LevelVariableDefinition] = [")
    for item in list(variables):
        payload = {
            "variable_id": item.get("variable_id"),
            "variable_name": item.get("variable_name"),
            "variable_type": item.get("variable_type"),
            "default_value": item.get("default_value"),
            "is_global": item.get("is_global", True),
            "description": item.get("description", ""),
            "metadata": item.get("metadata", {}),
        }
        lines.append("    LevelVariableDefinition(")
        lines.append(f"        variable_id={repr(payload['variable_id'])},")
        lines.append(f"        variable_name={repr(payload['variable_name'])},")
        lines.append(f"        variable_type={repr(payload['variable_type'])},")
        lines.append(f"        default_value={repr(payload['default_value'])},")
        lines.append(f"        is_global={repr(payload['is_global'])},")
        lines.append(f"        description={repr(payload['description'])},")
        lines.append(f"        metadata={repr(payload['metadata'])},")
        lines.append("    ),")
    lines.append("]")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_import_player_template_gia_to_project_archive(*, plan: ImportPlayerTemplateGiaPlan) -> Dict[str, Any]:
    input_gia = Path(plan.input_gia_file).resolve()
    project_root = Path(plan.project_archive_path).resolve()
    if not input_gia.is_file() or input_gia.suffix.lower() != ".gia":
        raise FileNotFoundError(str(input_gia))
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    package_id = str(project_root.name)

    # 解码 `.gia` 为 numeric_message（复用现有 .gia bundle 解码器）
    bundle = load_component_base_bundle_from_gia(
        input_gia,
        max_depth=24,
        prefer_raw_hex_for_utf8=False,
    )

    resource_entry = bundle.get("1")
    if not isinstance(resource_entry, dict):
        raise TypeError("玩家模板 .gia root_message['1'] 必须为 dict(bundle resource entry)")
    raw_name = resource_entry.get("3")
    template_name = _coerce_non_empty_text(_coerce_utf8_text(raw_name, field_name="player_template.name"), field_name="player_template.name")

    # 提取自定义变量（group1）
    custom_defs = extract_custom_variable_defs_from_bundle(bundle)

    stem = sanitize_file_stem(template_name) or sanitize_file_stem(input_gia.stem) or "imported_player_template"

    # ===== 1) 写入变量文件 =====
    variable_dir = (project_root / "管理配置" / "关卡变量" / "自定义变量").resolve()
    variable_file_id = str(plan.output_variable_file_id or "").strip()
    if variable_file_id == "":
        # 保持可读 + 稳定：使用模板名 stem + 当前时间戳防止多次导入覆盖
        ts = int(time.time())
        variable_file_id = f"imported_player_custom_variables__{package_id}__{stem}__{ts}"
    variable_file_name = str(plan.output_variable_file_name or "").strip() or f"导入_玩家模板变量__{template_name}"
    variable_file_path = (variable_dir / f"导入_玩家模板变量__{stem}.py").resolve()

    if variable_file_path.exists() and not bool(plan.overwrite):
        raise FileExistsError(f"变量文件已存在（如需覆盖请使用 --overwrite）：{str(variable_file_path)}")

    variables_payload: list[dict] = []
    for d in list(custom_defs):
        variables_payload.append(
            {
                "variable_id": _build_imported_variable_id(package_id=package_id, variable_name=d.name),
                "variable_name": str(d.name),
                "variable_type": str(d.var_type_text),
                "default_value": d.default_value,
                "is_global": True,
                "description": "由玩家模板 .gia 导入",
                "metadata": {"source": "imported_from_gia", "var_type_int": int(d.var_type_int)},
            }
        )

    _write_variable_file(
        variable_file_path,
        file_id=str(variable_file_id),
        file_name=str(variable_file_name),
        variables=variables_payload,
    )

    # ===== 2) 写入玩家模板 JSON =====
    template_dir = (project_root / "战斗预设" / "玩家模板").resolve()
    template_dir.mkdir(parents=True, exist_ok=True)
    template_json_path = (template_dir / f"{stem}.json").resolve()
    if template_json_path.exists() and not bool(plan.overwrite):
        raise FileExistsError(f"玩家模板 JSON 已存在（如需覆盖请使用 --overwrite）：{str(template_json_path)}")

    template_id = str(plan.output_template_id or "").strip()
    if template_id == "":
        template_id = f"imported_player_template__{stem}"

    template_obj: dict[str, Any] = {
        "template_id": str(template_id),
        "template_name": str(template_name),
        "description": "由玩家模板 .gia 导入",
        "level": 1,
        "default_profession_id": "",
        "metadata": {
            "custom_variable_file": str(variable_file_id),
            "player_editor": {
                "player": {
                    "graphs": [],
                    "graph_variable_overrides": {},
                    "custom_variables": [],
                },
                "role": {
                    "graphs": [],
                    "graph_variable_overrides": {},
                },
            },
        },
    }
    template_json_path.write_text(json.dumps(template_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "input_gia_file": str(input_gia),
        "project_archive": str(project_root),
        "template_name": str(template_name),
        "custom_variables_count": int(len(custom_defs)),
        "output_player_template_json": str(template_json_path),
        "output_variable_file": str(variable_file_path),
        "output_variable_file_id": str(variable_file_id),
    }


__all__ = [
    "ImportPlayerTemplateGiaPlan",
    "run_import_player_template_gia_to_project_archive",
]

