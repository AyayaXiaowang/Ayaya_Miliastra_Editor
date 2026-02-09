from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.utils.resource_library_layout import get_packages_root_dir

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


_SPECIAL_VIEW_PACKAGE_IDS: Set[str] = {"global_view"}


def _is_reserved_python_file(py_file: Path) -> bool:
    if py_file.parent.name == "__pycache__":
        return True
    if py_file.name.startswith("_"):
        return True
    if "校验" in py_file.stem:
        return True
    return False


def _extract_python_module_level_string_constant(file_path: Path, *, constant_name: str) -> str:
    constant_name_text = str(constant_name or "").strip()
    if not constant_name_text:
        return ""

    code_text = file_path.read_text(encoding="utf-8")
    # 兼容两种声明形式：
    # - SIGNAL_ID = "xxx"
    # - SIGNAL_ID: str = "xxx"
    pattern = re.compile(
        rf"^\s*{re.escape(constant_name_text)}\s*(?::\s*[^=]+)?=\s*(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)\s*(?:#.*)?$",
        flags=re.MULTILINE,
    )
    match = pattern.search(code_text)
    if not match:
        return ""
    return str(match.group("value") or "").strip()


def _scan_python_resource_id_to_paths(
    *,
    package_root_dir: Path,
    resource_type: ResourceType,
) -> Tuple[Dict[str, List[Path]], List[Path]]:
    resource_dir = package_root_dir / str(resource_type.value)
    if not resource_dir.exists() or not resource_dir.is_dir():
        return {}, []

    id_to_paths: Dict[str, List[Path]] = {}
    missing_id_files: List[Path] = []
    py_files = sorted(
        list(resource_dir.rglob("*.py")),
        key=lambda path: path.as_posix().casefold(),
    )
    for py_file in py_files:
        if not py_file.is_file():
            continue
        if _is_reserved_python_file(py_file):
            continue

        resource_id = ""
        if resource_type == ResourceType.GRAPH:
            metadata = load_graph_metadata_from_file(py_file)
            resource_id = str(metadata.graph_id or "").strip() or py_file.stem
        elif resource_type == ResourceType.SIGNAL:
            resource_id = _extract_python_module_level_string_constant(
                py_file,
                constant_name="SIGNAL_ID",
            )
            if not resource_id:
                missing_id_files.append(py_file)
                continue
        elif resource_type == ResourceType.STRUCT_DEFINITION:
            resource_id = _extract_python_module_level_string_constant(
                py_file,
                constant_name="STRUCT_ID",
            )
            if not resource_id:
                missing_id_files.append(py_file)
                continue
        else:
            raise ValueError(f"不支持的 Python 资源类型：{resource_type}")

        if not resource_id:
            continue
        id_to_paths.setdefault(resource_id, []).append(py_file)

    return id_to_paths, missing_id_files


class ResourceIdUniquenessRule(BaseComprehensiveRule):
    """资源 ID 唯一性校验（项目存档目录内）。

    说明：
    - 本规则只检查“同一项目存档目录内的重复 ID / 缺失 ID 常量”等会造成索引歧义的问题；
    - 重复 ID 在编辑期会导致索引只能选取其中一份文件，运行与编辑行为可能不一致，必须修复。
    """

    rule_id = "package.resource_id_uniqueness"
    category = "资源系统"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        package = getattr(ctx, "package", None)
        resource_manager = getattr(ctx, "resource_manager", None)
        if package is None or resource_manager is None:
            return []

        package_id = str(getattr(package, "package_id", "") or "").strip()
        if not package_id or package_id in _SPECIAL_VIEW_PACKAGE_IDS:
            return []

        package_name = str(getattr(package, "name", "") or "").strip() or package_id
        workspace_path = getattr(resource_manager, "workspace_path", None)
        if not isinstance(workspace_path, Path):
            return []

        resource_library_dir = workspace_path / "assets" / "资源库"
        packages_root_dir = get_packages_root_dir(resource_library_dir)
        package_root_dir = packages_root_dir / package_id
        if not package_root_dir.exists() or not package_root_dir.is_dir():
            return []

        issues: List[ValidationIssue] = []
        base_location = f"存档 '{package_name}' ({package_id}) > 资源 ID 唯一性"

        def _emit_duplicate(resource_type: ResourceType, resource_id: str, file_paths: List[Path]) -> None:
            ordered_paths = sorted(file_paths, key=lambda p: p.as_posix().casefold())
            shown = ordered_paths[:8]
            more = max(0, len(ordered_paths) - len(shown))
            path_lines = "\n".join(f"- {p}" for p in shown) + (f"\n- ... +{more}" if more else "")

            issues.append(
                ValidationIssue(
                    level="error",
                    category="资源系统",
                    code="RESOURCE_ID_DUPLICATED_IN_PACKAGE",
                    location=f"{base_location} > {resource_type.value} > ID={resource_id}",
                    message=(
                        "同一项目存档目录内发现重复资源 ID（索引歧义）：\n"
                        f"{path_lines}"
                    ),
                    suggestion=(
                        "请删除/合并重复文件，或修改其中一份资源的 ID（保持包内唯一）；"
                        "修复后重新刷新资源库并重新运行校验。"
                    ),
                    reference="资源索引作用域与覆盖语义：同一根目录内 ID 必须唯一",
                    detail={
                        "type": "resource_id_duplicated_in_package",
                        "package_id": package_id,
                        "resource_type": resource_type.value,
                        "resource_id": resource_id,
                        "file_paths": [str(p.as_posix()) for p in ordered_paths],
                    },
                )
            )

        def _emit_missing_id_constant(
            resource_type: ResourceType,
            file_path: Path,
            *,
            constant_name: str,
        ) -> None:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="资源系统",
                    code="RESOURCE_ID_CONSTANT_MISSING",
                    location=f"{base_location} > {resource_type.value} > {file_path.as_posix()}",
                    message=f"无法从代码级资源文件解析 {constant_name}，该文件将不会进入资源索引。",
                    suggestion=f"请在文件模块顶层添加：{constant_name} = 'xxx'（字符串常量），并确保同一项目存档内唯一。",
                    reference="资源索引（代码级资源）：ID 常量约定",
                    detail={
                        "type": "resource_id_constant_missing",
                        "package_id": package_id,
                        "resource_type": resource_type.value,
                        "file_path": str(file_path.as_posix()),
                        "constant_name": str(constant_name),
                    },
                )
            )

        # 仅对“Python 代码资源”做磁盘扫描：避免引入 JSON 解析异常导致校验流程中断。
        for resource_type in (ResourceType.GRAPH, ResourceType.SIGNAL, ResourceType.STRUCT_DEFINITION):
            id_to_paths, missing_id_files = _scan_python_resource_id_to_paths(
                package_root_dir=package_root_dir,
                resource_type=resource_type,
            )
            if resource_type == ResourceType.SIGNAL:
                for file_path in sorted(missing_id_files, key=lambda p: p.as_posix().casefold()):
                    _emit_missing_id_constant(resource_type, file_path, constant_name="SIGNAL_ID")
            if resource_type == ResourceType.STRUCT_DEFINITION:
                for file_path in sorted(missing_id_files, key=lambda p: p.as_posix().casefold()):
                    _emit_missing_id_constant(resource_type, file_path, constant_name="STRUCT_ID")
            for resource_id in sorted(id_to_paths.keys(), key=lambda text: text.casefold()):
                paths = id_to_paths[resource_id]
                if len(paths) <= 1:
                    continue
                _emit_duplicate(resource_type, resource_id, list(paths))

        return issues


__all__ = ["ResourceIdUniquenessRule"]


