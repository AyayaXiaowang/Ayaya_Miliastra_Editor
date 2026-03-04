from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from engine.graph.models.package_model import LevelVariableDefinition
from engine.resources.level_variable_registry_provider import (
    REGISTRY_FILENAME,
    load_virtual_variable_files_from_registry,
)
from engine.resources.level_variable_owner_contract import validate_and_fill_level_variable_payload_owner
from engine.resources.level_variable_schema_types import (
    CATEGORY_CUSTOM,
    CATEGORY_INGAME_SAVE,
    VariableFileInfo,
)
from engine.resources.level_variable_source_extractor import (
    check_python_source_syntax,
    try_extract_variable_file_header_and_entries_from_code,
)
from engine.type_registry import (
    TYPE_DICT,
    TYPE_COMPONENT_ID,
    TYPE_COMPONENT_ID_LIST,
    TYPE_CONFIG_ID,
    TYPE_CONFIG_ID_LIST,
    TYPE_GUID,
    TYPE_GUID_LIST,
    VARIABLE_TYPES,
    parse_typed_dict_alias,
)
from engine.utils.id_digits import is_digits_1_to_10
from engine.utils.logging.logger import log_warn
from engine.utils.resource_library_layout import discover_scoped_resource_root_directories
from engine.utils.workspace import (
    get_injected_workspace_root_or_none,
    looks_like_workspace_root,
    resolve_workspace_root,
)


class LevelVariableSchemaService:
    """关卡变量代码资源载入服务。"""

    def _get_workspace_root(self) -> Path:
        injected_root = get_injected_workspace_root_or_none()
        if injected_root is not None and looks_like_workspace_root(injected_root):
            return injected_root
        return resolve_workspace_root(start_paths=[Path(__file__).resolve()])

    @staticmethod
    def _try_extract_package_id_from_base_dir(*, base_dir: Path, workspace_root: Path) -> str | None:
        packages_root = (workspace_root / "assets" / "资源库" / "项目存档").resolve()
        resolved = base_dir.resolve()
        if not str(resolved).startswith(str(packages_root)):
            return None
        try:
            rel = resolved.relative_to(packages_root)
        except Exception:
            return None
        parts = list(rel.parts)
        if len(parts) < 3:
            return None
        return str(parts[0]).strip() or None

    @staticmethod
    def _should_skip_physical_variable_file_when_registry_enabled(py_path: Path) -> bool:
        if py_path.parent.name != CATEGORY_CUSTOM:
            return False
        stem = str(py_path.stem or "").strip()
        if stem.startswith("自动分配_"):
            return True
        if stem.startswith("UI_") and "自动生成" in stem:
            return True
        return False

    @staticmethod
    def _determine_category(parent_relative_path: str) -> str:
        if parent_relative_path.startswith(CATEGORY_INGAME_SAVE):
            return CATEGORY_INGAME_SAVE
        if parent_relative_path.startswith(CATEGORY_CUSTOM):
            return CATEGORY_CUSTOM
        return ""

    def load_all_variable_files(self, *, active_package_id: str | None = None) -> Dict[str, VariableFileInfo]:
        workspace = self._get_workspace_root()
        resource_library_root = workspace / "assets" / "资源库"
        resource_roots = discover_scoped_resource_root_directories(
            resource_library_root,
            active_package_id=active_package_id,
        )
        base_dirs = [root / "管理配置" / "关卡变量" for root in resource_roots]

        results: Dict[str, VariableFileInfo] = {}
        existing_variable_names: dict[str, Path] = {}
        for base_dir in base_dirs:
            if not base_dir.is_dir():
                continue
            self._load_one_base_dir(
                base_dir=base_dir,
                workspace=workspace,
                results=results,
                existing_variable_names=existing_variable_names,
            )
        return results

    def _load_one_base_dir(
        self,
        *,
        base_dir: Path,
        workspace: Path,
        results: Dict[str, VariableFileInfo],
        existing_variable_names: dict[str, Path],
    ) -> None:
        package_id = self._try_extract_package_id_from_base_dir(base_dir=base_dir, workspace_root=workspace)
        registry_path = (base_dir / REGISTRY_FILENAME).resolve()
        registry_required = bool(package_id)
        if registry_required and (not registry_path.is_file()):
            raise ValueError(
                "项目存档已启用『自定义变量注册表』单文件真源：缺少注册表文件。"
                f"请补齐 {REGISTRY_FILENAME} 并将自定义变量全部迁入其中（base_dir={base_dir.as_posix()}）。"
            )
        registry_enabled = bool(package_id)
        self._load_physical_files_under_base_dir(
            base_dir=base_dir,
            registry_enabled=registry_enabled,
            results=results,
            existing_variable_names=existing_variable_names,
        )
        if registry_enabled and package_id:
            self._load_virtual_files_from_registry(
                base_dir=base_dir,
                registry_path=registry_path,
                package_id=package_id,
                results=results,
                existing_variable_names=existing_variable_names,
            )

    def _load_physical_files_under_base_dir(
        self,
        *,
        base_dir: Path,
        registry_enabled: bool,
        results: Dict[str, VariableFileInfo],
        existing_variable_names: dict[str, Path],
    ) -> None:
        if registry_enabled:
            custom_dir = (base_dir / CATEGORY_CUSTOM).resolve()
            if custom_dir.is_dir():
                offenders = sorted(
                    (p for p in custom_dir.rglob("*.py") if p.is_file()),
                    key=lambda p: p.as_posix().casefold(),
                )
                if offenders:
                    preview = "\n".join(f"- {p.as_posix()}" for p in offenders[:12])
                    more = "\n- ..." if len(offenders) > 12 else ""
                    raise ValueError(
                        "已启用『自定义变量注册表』单文件真源：禁止在『自定义变量/』目录中维护散落的变量文件（请迁移到 自定义变量注册表.py 并删除这些文件）。\n"
                        f"base_dir={base_dir.as_posix()}\n"
                        f"offenders({len(offenders)}):\n{preview}{more}"
                    )
        py_paths = sorted(
            (path for path in base_dir.rglob("*.py") if path.is_file()),
            key=lambda path: path.as_posix(),
        )
        for py_path in py_paths:
            if "校验" in py_path.stem:
                continue
            if registry_enabled and self._should_skip_physical_variable_file_when_registry_enabled(py_path):
                continue
            self._try_load_one_physical_variable_file(
                base_dir=base_dir,
                py_path=py_path,
                results=results,
                existing_variable_names=existing_variable_names,
            )

    def _try_load_one_physical_variable_file(
        self,
        *,
        base_dir: Path,
        py_path: Path,
        results: Dict[str, VariableFileInfo],
        existing_variable_names: dict[str, Path],
    ) -> None:
        relative_path = py_path.relative_to(base_dir).as_posix()
        parent_relative_path = py_path.parent.relative_to(base_dir).as_posix()

        category = self._determine_category(parent_relative_path)
        if not category:
            return

        is_valid_syntax, error_preview = check_python_source_syntax(py_path)
        if not is_valid_syntax:
            log_warn(
                "[关卡变量] 变量文件语法错误，已跳过加载：{} ({})",
                py_path.as_posix(),
                error_preview,
            )
            return

        file_id, file_name, vars_list = try_extract_variable_file_header_and_entries_from_code(py_path)
        if not isinstance(file_id, str) or not file_id:
            raise ValueError(f"无效的 VARIABLE_FILE_ID（{py_path}）")
        if not isinstance(file_name, str):
            file_name = py_path.stem
        if file_id in results:
            raise ValueError(f"重复的变量文件 ID：{file_id}")
        if not isinstance(vars_list, list):
            raise ValueError(f"LEVEL_VARIABLES 未定义为列表（{py_path}）")

        variables = self._build_file_variable_payloads(
            vars_list,
            file_id=file_id,
            py_path=py_path,
            source_path=relative_path,
            source_directory=parent_relative_path,
            category=category,
            existing_variable_names=existing_variable_names,
        )

        results[file_id] = VariableFileInfo(
            file_id=file_id,
            file_name=file_name,
            category=category,
            source_path=relative_path,
            absolute_path=py_path,
            variables=variables,
        )

    def _build_file_variable_payloads(
        self,
        vars_list: List[dict],
        *,
        file_id: str,
        py_path: Path,
        source_path: str,
        source_directory: str,
        category: str,
        existing_variable_names: dict[str, Path],
    ) -> List[Dict]:
        variables: List[Dict] = []
        require_owner = str(category or "").strip() == CATEGORY_CUSTOM
        for entry in list(vars_list or []):
            payload = self._normalize_entry(entry, py_path, require_owner=require_owner)
            payload["source_path"] = source_path
            payload["source_file"] = py_path.name
            payload["source_stem"] = py_path.stem
            payload["source_directory"] = source_directory
            payload["variable_file_id"] = file_id
            variables.append(payload)
            name = str(payload.get("variable_name") or "").strip()
            if name:
                existing_variable_names.setdefault(name, py_path)
        return variables

    def _load_virtual_files_from_registry(
        self,
        *,
        base_dir: Path,
        registry_path: Path,
        package_id: str,
        results: Dict[str, VariableFileInfo],
        existing_variable_names: dict[str, Path],
    ) -> None:
        virtual_files = load_virtual_variable_files_from_registry(registry_path=registry_path, package_id=package_id)
        registry_source_path = registry_path.relative_to(base_dir).as_posix()
        for vf in virtual_files:
            self._add_one_virtual_variable_file(
                file_id=vf.file_id,
                file_name=vf.file_name,
                entries=list(vf.variables),
                registry_path=registry_path,
                registry_source_path=registry_source_path,
                results=results,
                existing_variable_names=existing_variable_names,
            )

    def _add_one_virtual_variable_file(
        self,
        *,
        file_id: str,
        file_name: str,
        entries: List[dict],
        registry_path: Path,
        registry_source_path: str,
        results: Dict[str, VariableFileInfo],
        existing_variable_names: dict[str, Path],
    ) -> None:
        if file_id in results:
            raise ValueError(
                "注册表虚拟变量文件与磁盘变量文件存在同一 VARIABLE_FILE_ID 冲突："
                f"{file_id}（registry={registry_path.as_posix()}）"
            )

        variables: list[dict] = []
        for entry in list(entries or []):
            payload = self._normalize_entry(entry, registry_path, require_owner=True)
            payload["source_path"] = registry_source_path
            payload["source_file"] = registry_path.name
            payload["source_stem"] = registry_path.stem
            payload["source_directory"] = CATEGORY_CUSTOM
            payload["variable_file_id"] = file_id

            name = str(payload.get("variable_name") or "").strip()
            if name and name in existing_variable_names:
                disk_path = existing_variable_names[name]
                raise ValueError(
                    "注册表变量名与磁盘变量文件冲突（单一真源要求全局唯一）："
                    f"{name!r}（registry={registry_path.as_posix()} disk={disk_path.as_posix()}）"
                )
            variables.append(payload)

        results[file_id] = VariableFileInfo(
            file_id=file_id,
            file_name=file_name,
            category=CATEGORY_CUSTOM,
            source_path=registry_source_path,
            absolute_path=registry_path,
            variables=variables,
        )

    def _normalize_entry(self, entry: object, py_path: Path, *, require_owner: bool) -> dict:
        if isinstance(entry, LevelVariableDefinition):
            payload = entry.serialize()
            return self._validate_payload(payload, py_path=py_path, require_owner=require_owner)

        if not isinstance(entry, dict):
            raise ValueError(f"无效的关卡变量条目类型（{py_path}）：{type(entry)!r}")

        required_keys = ["variable_id", "variable_name", "variable_type"]
        for key in required_keys:
            if key not in entry:
                raise ValueError(f"关卡变量缺少必要字段 {key}（{py_path}）")

        payload = {
            "variable_id": entry["variable_id"],
            "variable_name": entry["variable_name"],
            "variable_type": entry["variable_type"],
            "owner": entry.get("owner", ""),
            "default_value": entry.get("default_value"),
            "is_global": entry.get("is_global", True),
            "description": entry.get("description", ""),
            "metadata": entry.get("metadata", {}),
        }
        return self._validate_payload(payload, py_path=py_path, require_owner=require_owner)

    def _validate_payload(self, payload: dict, *, py_path: Path, require_owner: bool) -> dict:
        variable_id = str(payload.get("variable_id") or "").strip()
        if not variable_id:
            raise ValueError(f"关卡变量 variable_id 不能为空（{py_path}）")

        variable_type = str(payload.get("variable_type") or "").strip()
        if not variable_type:
            raise ValueError(f"关卡变量 variable_type 不能为空：{variable_id}（{py_path}）")

        variable_name = str(payload.get("variable_name") or "").strip()
        if not variable_name:
            raise ValueError(f"关卡变量 variable_name 不能为空：{variable_id}（{py_path}）")

        if bool(require_owner):
            validate_and_fill_level_variable_payload_owner(payload, py_path=py_path)

        is_typed_dict, key_type, value_type = parse_typed_dict_alias(variable_type)
        if (variable_type not in set(VARIABLE_TYPES)) and (not is_typed_dict):
            raise ValueError(f"关卡变量类型不受支持：{variable_id} -> {variable_type!r}（{py_path}）")

        if is_typed_dict:
            allowed = set(VARIABLE_TYPES) - {TYPE_DICT}
            if key_type not in allowed:
                raise ValueError(
                    f"关卡变量字典 key_type 不受支持：{variable_id} -> {variable_type!r}（key_type={key_type!r}）（{py_path}）"
                )
            if value_type not in allowed:
                raise ValueError(
                    f"关卡变量字典 value_type 不受支持：{variable_id} -> {variable_type!r}（value_type={value_type!r}）（{py_path}）"
                )

        self._validate_default_value(payload, variable_id=variable_id, variable_type=variable_type, py_path=py_path)
        return payload

    @staticmethod
    def _validate_default_value(payload: dict, *, variable_id: str, variable_type: str, py_path: Path) -> None:
        default_value = payload.get("default_value")
        id_types = {TYPE_GUID, TYPE_CONFIG_ID, TYPE_COMPONENT_ID}
        id_list_types = {TYPE_GUID_LIST, TYPE_CONFIG_ID_LIST, TYPE_COMPONENT_ID_LIST}

        if variable_type in id_types and (not is_digits_1_to_10(default_value)):
            raise ValueError(
                "关卡变量默认值必须为 1~10 位纯数字（int 或数字字符串）："
                f"{variable_id} ({variable_type}) -> {default_value!r}（{py_path}）"
            )

        if variable_type not in id_list_types:
            return

        if not isinstance(default_value, (list, tuple)):
            raise ValueError(
                "关卡变量默认值必须为列表："
                f"{variable_id} ({variable_type}) -> {default_value!r}（{py_path}）"
            )
        invalid_items = [x for x in list(default_value) if not is_digits_1_to_10(x)]
        if not invalid_items:
            return
        preview = ", ".join(repr(x) for x in invalid_items[:6])
        more = "..." if len(invalid_items) > 6 else ""
        raise ValueError(
            "关卡变量默认值列表元素必须为 1~10 位纯数字："
            f"{variable_id} ({variable_type}) -> {preview}{more}（{py_path}）"
        )


__all__ = ["LevelVariableSchemaService"]

