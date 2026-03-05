"""外部关卡变量（代码级 schema）加载器。

从 variables_tab.py 中拆出，减少 UI 层文件的领域逻辑体积。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs
from engine.resources.level_variable_schema_view import (
    get_default_level_variable_schema_view,
)
from engine.utils.path_utils import normalize_slash


def load_external_level_variable_payloads(reference_text: object) -> list[dict[str, Any]]:
    """从 LevelVariableSchemaView 中按引用字符串解析“外部关卡变量文件”的变量列表（payload 字典）。

    匹配规则（与 UI 侧 metadata.custom_variable_file 的写法一致）：
    - 优先匹配变量文件 ID（VARIABLE_FILE_ID）；
    - 精确匹配 source_path（归一化为 "/"）；
    - 或按文件名 stem 匹配（允许只写不含扩展名的“ID 风格”）。
    """
    refs = normalize_custom_variable_file_refs(reference_text)
    if not refs:
        return []

    schema_view = get_default_level_variable_schema_view()
    variable_files = schema_view.get_all_variable_files() or {}

    # 多引用：按顺序拼接结果；同 variable_id 的重复项保留首个（避免“后面的文件覆盖前面”的隐式语义）。
    results_by_id: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []

    for reference in refs:
        normalized_ref = normalize_slash(reference)
        ref_stem = Path(normalized_ref).stem
        raw_ref = reference

        matched_file_info = None
        matched_file_id = ""

        # 先按“变量文件”维度匹配：命中则取该文件中的变量列表（保留 variable_id 等字段）。
        for file_id, file_info in variable_files.items():
            if not isinstance(file_id, str) or not file_id.strip():
                continue
            candidate_ids: list[str] = [file_id.strip()]

            source_path_value = getattr(file_info, "source_path", None)
            if isinstance(source_path_value, str) and source_path_value.strip():
                candidate_ids.append(source_path_value.strip())
                candidate_ids.append(Path(source_path_value.strip()).stem)

            matched = _match_reference(normalized_ref, raw_ref, ref_stem, candidate_ids)
            if not matched:
                continue
            matched_file_info = file_info
            matched_file_id = file_id.strip()
            break

        if matched_file_info is None:
            continue

        variables_value = getattr(matched_file_info, "variables", None)
        if not isinstance(variables_value, list):
            continue

        for payload in variables_value:
            if not isinstance(payload, dict):
                continue
            var_id = str(payload.get("variable_id") or "").strip()
            if not var_id:
                continue
            if var_id not in results_by_id:
                results_by_id[var_id] = dict(payload)
                ordered_ids.append(var_id)
            # 若重复：保持第一个来源的 payload（避免隐式覆盖）

        # 文件内变量可能没有稳定顺序约束，但我们只在第一次见到时记录一次。
        _ = matched_file_id

    return [results_by_id[var_id] for var_id in ordered_ids]


def _match_reference(
    normalized_ref: str,
    raw_ref: str,
    ref_stem: str,
    candidates: list[str],
) -> bool:
    for candidate in candidates:
        candidate_text = normalize_slash(str(candidate)).strip()
        if not candidate_text:
            continue

        # 1) 精确匹配完整相对路径（例如 自定义变量/forge_hero_player_template_variables.py）
        if candidate_text == normalized_ref:
            return True

        # 2) 变量文件 ID 精确匹配（推荐写法）
        if candidate_text == raw_ref:
            return True

        # 3) 退化为仅按文件名（不含扩展名）匹配，允许 metadata.custom_variable_file 直接填写文件名 ID
        candidate_stem = Path(candidate_text).stem
        if candidate_stem == ref_stem:
            return True

    return False


__all__ = ["load_external_level_variable_payloads"]


