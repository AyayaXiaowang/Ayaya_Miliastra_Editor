from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from importlib.machinery import SourceFileLoader

from engine.graph.models.package_model import LevelVariableDefinition


# 变量文件分类常量
CATEGORY_CUSTOM = "自定义变量"
CATEGORY_INGAME_SAVE = "自定义变量-局内存档变量"


@dataclass
class VariableFileInfo:
    """变量文件元信息"""

    file_id: str
    file_name: str
    category: str  # CATEGORY_CUSTOM 或 CATEGORY_INGAME_SAVE
    source_path: str  # 相对于关卡变量目录的路径
    variables: List[Dict] = field(default_factory=list)


class LevelVariableSchemaService:
    """关卡变量代码资源载入服务。

    约定：
    - 根目录：assets/资源库/管理配置/关卡变量
    - 子目录：
      - `自定义变量/`：普通自定义变量
      - `自定义变量-局内存档变量/`：局内存档变量
    - 每个 .py 文件导出：
      - VARIABLE_FILE_ID: str（文件唯一标识）
      - VARIABLE_FILE_NAME: str（文件显示名）
      - LEVEL_VARIABLES: list（变量定义列表）
    - 每条关卡变量记录在载入时自动附加来源信息，供 UI 侧按文件进行分组展示。
    """

    def _get_workspace_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def load_all_variable_files(self) -> Dict[str, VariableFileInfo]:
        """加载所有变量文件，返回 {file_id: VariableFileInfo}。"""
        workspace = self._get_workspace_root()
        base_dir = workspace / "assets" / "资源库" / "管理配置" / "关卡变量"
        if not base_dir.is_dir():
            return {}

        results: Dict[str, VariableFileInfo] = {}

        py_paths = sorted(
            (path for path in base_dir.rglob("*.py") if path.is_file()),
            key=lambda path: path.as_posix(),
        )

        for py_path in py_paths:
            # 跳过校验脚本（如 校验关卡变量.py），这些不是真正的变量定义文件
            if "校验" in py_path.stem:
                continue

            relative_path = py_path.relative_to(base_dir).as_posix()
            parent_relative_path = py_path.parent.relative_to(base_dir).as_posix()

            # 确定分类
            category = self._determine_category(parent_relative_path)
            if not category:
                continue  # 跳过不在预期子目录中的文件

            module_name = f"code_level_variable_{abs(hash(py_path.as_posix()))}"
            loader = SourceFileLoader(module_name, str(py_path))
            module = loader.load_module()

            # 读取文件级常量
            file_id = getattr(module, "VARIABLE_FILE_ID", None)
            file_name = getattr(module, "VARIABLE_FILE_NAME", None)

            if not isinstance(file_id, str) or not file_id:
                raise ValueError(f"无效的 VARIABLE_FILE_ID（{py_path}）")
            if not isinstance(file_name, str):
                file_name = py_path.stem  # 兼容：若无显示名则使用文件名

            if file_id in results:
                raise ValueError(f"重复的变量文件 ID：{file_id}")

            # 读取变量列表
            vars_list = getattr(module, "LEVEL_VARIABLES", None)
            if not isinstance(vars_list, list):
                raise ValueError(f"LEVEL_VARIABLES 未定义为列表（{py_path}）")

            variables: List[Dict] = []
            for entry in vars_list:
                payload = self._normalize_entry(entry, py_path)
                payload["source_path"] = relative_path
                payload["source_file"] = py_path.name
                payload["source_stem"] = py_path.stem
                payload["source_directory"] = parent_relative_path
                payload["variable_file_id"] = file_id  # 关联到所属文件
                variables.append(payload)

            results[file_id] = VariableFileInfo(
                file_id=file_id,
                file_name=file_name,
                category=category,
                source_path=relative_path,
                variables=variables,
            )

        return results

    def load_all_level_variables_from_code(self) -> Dict[str, Dict]:
        """加载所有变量，返回 {variable_id: payload}（兼容旧接口）。"""
        file_infos = self.load_all_variable_files()
        results: Dict[str, Dict] = {}

        for file_info in file_infos.values():
            for var_payload in file_info.variables:
                variable_id = var_payload["variable_id"]
                if variable_id in results:
                    raise ValueError(f"重复的关卡变量 ID：{variable_id}")
                results[variable_id] = var_payload

        return results

    @staticmethod
    def _determine_category(parent_relative_path: str) -> str:
        """根据父目录路径确定变量分类。"""
        if parent_relative_path.startswith(CATEGORY_INGAME_SAVE):
            return CATEGORY_INGAME_SAVE
        if parent_relative_path.startswith(CATEGORY_CUSTOM):
            return CATEGORY_CUSTOM
        return ""

    @staticmethod
    def _normalize_entry(entry, py_path: Path) -> Dict:
        if isinstance(entry, LevelVariableDefinition):
            return entry.serialize()
        if not isinstance(entry, dict):
            raise ValueError(f"无效的关卡变量条目类型（{py_path}）：{type(entry)!r}")

        required_keys = ["variable_id", "variable_name", "variable_type"]
        for key in required_keys:
            if key not in entry:
                raise ValueError(f"关卡变量缺少必要字段 {key}（{py_path}）")

        return {
            "variable_id": entry["variable_id"],
            "variable_name": entry.get("variable_name", entry.get("name", "")),
            "variable_type": entry["variable_type"],
            "default_value": entry.get("default_value"),
            "is_global": entry.get("is_global", True),
            "description": entry.get("description", ""),
            "metadata": entry.get("metadata", {}),
        }


class LevelVariableSchemaView:
    """关卡变量聚合视图（只读缓存）。"""

    def __init__(self, schema_service: LevelVariableSchemaService | None = None) -> None:
        self._schema_service = schema_service or LevelVariableSchemaService()
        self._variables: Dict[str, Dict] | None = None
        self._variable_files: Dict[str, VariableFileInfo] | None = None

    def _ensure_loaded(self) -> None:
        """确保数据已加载。"""
        if self._variable_files is None:
            self._variable_files = self._schema_service.load_all_variable_files()
            # 同时构建变量平铺视图
            self._variables = {}
            for file_info in self._variable_files.values():
                for var_payload in file_info.variables:
                    variable_id = var_payload["variable_id"]
                    self._variables[variable_id] = var_payload

    def get_all_variables(self) -> Dict[str, Dict]:
        """返回 {variable_id: payload}（兼容旧接口）。"""
        self._ensure_loaded()
        return self._variables or {}

    def get_all_variable_files(self) -> Dict[str, VariableFileInfo]:
        """返回所有变量文件信息 {file_id: VariableFileInfo}。"""
        self._ensure_loaded()
        return self._variable_files or {}

    def get_variable_file(self, file_id: str) -> VariableFileInfo | None:
        """根据文件 ID 获取变量文件信息。"""
        self._ensure_loaded()
        if self._variable_files is None:
            return None
        return self._variable_files.get(file_id)

    def get_variables_by_file_id(self, file_id: str) -> List[Dict]:
        """根据文件 ID 获取该文件中的所有变量。"""
        file_info = self.get_variable_file(file_id)
        if file_info is None:
            return []
        return list(file_info.variables)

    def get_custom_variable_files(self) -> Dict[str, VariableFileInfo]:
        """获取所有普通自定义变量文件。"""
        self._ensure_loaded()
        if self._variable_files is None:
            return {}
        return {
            file_id: info
            for file_id, info in self._variable_files.items()
            if info.category == CATEGORY_CUSTOM
        }

    def get_ingame_save_variable_files(self) -> Dict[str, VariableFileInfo]:
        """获取所有局内存档变量文件。"""
        self._ensure_loaded()
        if self._variable_files is None:
            return {}
        return {
            file_id: info
            for file_id, info in self._variable_files.items()
            if info.category == CATEGORY_INGAME_SAVE
        }

    def invalidate_cache(self) -> None:
        """使缓存失效，下次访问时重新加载。"""
        self._variables = None
        self._variable_files = None


_default_level_variable_schema_view: LevelVariableSchemaView | None = None


def get_default_level_variable_schema_view() -> LevelVariableSchemaView:
    global _default_level_variable_schema_view
    if _default_level_variable_schema_view is None:
        _default_level_variable_schema_view = LevelVariableSchemaView()
    return _default_level_variable_schema_view


def invalidate_default_level_variable_cache() -> None:
    """使默认视图的缓存失效。"""
    global _default_level_variable_schema_view
    if _default_level_variable_schema_view is not None:
        _default_level_variable_schema_view.invalidate_cache()
