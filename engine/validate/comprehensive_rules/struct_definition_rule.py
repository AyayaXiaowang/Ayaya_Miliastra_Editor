from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.struct import get_default_struct_repository
from engine.validate.struct_definition_folder_policy import (
    infer_expected_struct_type_from_source_path,
    infer_struct_type_from_payload,
)

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


_STRUCT_TYPE_CONSTANT_RE = re.compile(
    r"^\s*STRUCT_TYPE\s*(?::\s*[^=]+)?=\s*(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)\s*(?:#.*)?$",
    flags=re.MULTILINE,
)


def _extract_struct_type_constant(source_path: Path) -> str:
    text = source_path.read_text(encoding="utf-8-sig")
    match = _STRUCT_TYPE_CONSTANT_RE.search(text)
    if not match:
        return ""
    return str(match.group("value") or "").strip()


class StructDefinitionRule(BaseComprehensiveRule):
    """结构体定义本身的有效性校验（不依赖节点图是否使用）。"""

    rule_id = "package.struct_definitions"
    category = "结构体系统"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_struct_definitions(self.validator)


def validate_struct_definitions(validator) -> List[ValidationIssue]:
    repo = get_default_struct_repository()
    errors = repo.get_errors()
    schema_view = get_default_definition_schema_view()
    sources = schema_view.get_all_struct_definition_sources()
    raw_payloads = schema_view.get_all_struct_definitions() or {}

    issues: List[ValidationIssue] = []

    # 1) 定义本身合法性（仓库归一化/强校验失败）
    for struct_id in sorted(errors.keys()):
        message = str(errors.get(struct_id) or "").strip() or "结构体定义无效"
        source_path = sources.get(struct_id)
        source_text = str(source_path.as_posix()) if isinstance(source_path, Path) else ""
        location = f"结构体定义 STRUCT_ID={struct_id}"
        if source_text:
            location = f"{location} @ {source_text}"

        issues.append(
            ValidationIssue(
                level="error",
                category="结构体系统",
                code="STRUCT_DEFINITION_INVALID",
                location=location,
                message=message,
                suggestion=(
                    "请修正该结构体定义文件中的 STRUCT_PAYLOAD：\n"
                    "- 字段类型为 GUID/配置ID/元件ID（及其列表）时，默认值必须为 1~10 位纯数字；\n"
                    "- 禁止 UUID 字符串或空字符串占位。\n"
                    "修正后请重新运行项目存档校验。"
                ),
                reference="节点图变量声明设计.md: 结构体定义与默认值约束",
                detail={
                    "type": "struct_definition_invalid",
                    "struct_id": struct_id,
                    "source_path": source_text or None,
                },
            )
        )

    # 2) 目录即分类：结构体定义文件放置目录与 struct_type 必须一致（避免 UI 分类漂移）
    for struct_id in sorted(sources.keys()):
        source_path = sources.get(struct_id)
        if not isinstance(source_path, Path):
            continue
        expected_type = infer_expected_struct_type_from_source_path(source_path)
        if not expected_type:
            continue
        payload = raw_payloads.get(struct_id)
        if not isinstance(payload, dict):
            continue
        payload_struct_type = infer_struct_type_from_payload(payload)
        constant_struct_type = _extract_struct_type_constant(source_path)

        if payload_struct_type == expected_type and constant_struct_type == expected_type:
            continue

        source_text = source_path.as_posix()
        location = f"结构体定义 STRUCT_ID={struct_id} @ {source_text}"
        issues.append(
            ValidationIssue(
                level="error",
                category="结构体系统",
                code="STRUCT_DEFINITION_FOLDER_TYPE_MISMATCH",
                location=location,
                message=(
                    "结构体定义所在目录的分类与结构体类型声明不一致：\n"
                    f"- 目录期望: {expected_type}\n"
                    f"- STRUCT_PAYLOAD: {payload_struct_type or '<empty>'}\n"
                    f"- STRUCT_TYPE: {constant_struct_type or '<missing>'}"
                ),
                suggestion=(
                    "请将该文件中的 STRUCT_TYPE 与 STRUCT_PAYLOAD['struct_ype/struct_type'] 修正为目录期望类型，"
                    "或将文件移动到对应的目录（基础结构体/局内存档结构体）。\n"
                    "可使用工具自动修正：python -X utf8 -m app.cli.graph_tools validate-project --package-id <项目存档ID> --fix"
                ),
                reference="管理配置/结构体定义: 目录即分类（basic vs ingame_save）",
                detail={
                    "type": "struct_definition_folder_type_mismatch",
                    "struct_id": struct_id,
                    "source_path": source_text,
                    "expected_struct_type": expected_type,
                    "payload_struct_type": payload_struct_type,
                    "constant_struct_type": constant_struct_type or None,
                },
            )
        )

    return issues


__all__ = ["StructDefinitionRule", "validate_struct_definitions"]


