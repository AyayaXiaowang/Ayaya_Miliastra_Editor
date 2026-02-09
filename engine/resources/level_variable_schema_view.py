from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from importlib.machinery import SourceFileLoader

from engine.graph.models.package_model import LevelVariableDefinition

from engine.utils.resource_library_layout import discover_scoped_resource_root_directories
from engine.utils.logging.logger import log_warn
from engine.utils.id_digits import is_digits_1_to_10
from engine.utils.source_text import read_text
from engine.utils.workspace import (
    get_injected_workspace_root_or_none,
    looks_like_workspace_root,
    resolve_workspace_root,
)
from engine.type_registry import (
    VARIABLE_TYPES,
    TYPE_COMPONENT_ID,
    TYPE_COMPONENT_ID_LIST,
    TYPE_CONFIG_ID,
    TYPE_CONFIG_ID_LIST,
    TYPE_GUID,
    TYPE_GUID_LIST,
    parse_typed_dict_alias,
)


# 变量文件分类常量
CATEGORY_CUSTOM = "自定义变量"
CATEGORY_INGAME_SAVE = "自定义变量-局内存档变量"


_SYNTAX_CHECK_SNIPPET = (
    "import sys;"
    "code=sys.stdin.read();"
    "compile(code, sys.argv[1], 'exec')"
)


def _check_python_source_syntax(py_path: Path) -> tuple[bool, str]:
    """检查 py_path 的 Python 语法是否有效（不导入模块、不执行顶层代码）。

    说明：
    - 该检查用于 UI 热重载/文件监控场景：编辑器保存过程中可能短暂出现“半写入/中间态”，
      直接 import 会抛出 SyntaxError 并阻断图解析链路；
    - 这里通过子进程 compile 预检语法，失败则跳过该变量文件并输出 warning。
    """

    # 注意：不要在父进程使用 `text=True + input=str` 传 stdin：
    # - 即使源文件本身是合法 UTF-8，也可能在“外部工具写入/半写入/剪贴板残留”等场景下
    #   混入不可编码字符（例如孤立 surrogate），导致父进程在编码 stdin 时抛 UnicodeEncodeError；
    # - 这里改为直接传 bytes，避免父进程编码阶段的环境差异与异常中断。
    code_bytes = py_path.read_bytes()
    completed = subprocess.run(
        # 强制子进程使用 UTF-8 读取 stdin，避免 Windows 默认代码页导致的 surrogateescape 误判。
        [sys.executable, "-X", "utf8", "-c", _SYNTAX_CHECK_SNIPPET, str(py_path)],
        capture_output=True,
        input=code_bytes,
    )
    if completed.returncode == 0:
        return True, ""

    # completed.stderr/stdout 为 bytes（未指定 text=True），这里按 UTF-8 解码用于提示。
    stderr_text = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
    stdout_text = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
    raw_message = (stderr_text or stdout_text).strip()
    if not raw_message:
        return False, "unknown syntax error"
    # 取最后一行（通常为 SyntaxError/IndentationError 等摘要），避免刷屏
    last_line = raw_message.splitlines()[-1].strip()
    return False, last_line


@dataclass
class VariableFileInfo:
    """变量文件元信息"""

    file_id: str
    file_name: str
    category: str  # CATEGORY_CUSTOM 或 CATEGORY_INGAME_SAVE
    source_path: str  # 相对于关卡变量目录的路径
    absolute_path: Path  # 物理文件绝对路径（用于按项目存档目录过滤/归属判断）
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
        injected_root = get_injected_workspace_root_or_none()
        if injected_root is not None and looks_like_workspace_root(injected_root):
            return injected_root
        return resolve_workspace_root(start_paths=[Path(__file__).resolve()])

    def load_all_variable_files(self, *, active_package_id: str | None = None) -> Dict[str, VariableFileInfo]:
        """加载所有变量文件，返回 {file_id: VariableFileInfo}。"""
        workspace = self._get_workspace_root()
        resource_library_root = workspace / "assets" / "资源库"
        resource_roots = discover_scoped_resource_root_directories(
            resource_library_root,
            active_package_id=active_package_id,
        )
        base_dirs = [root / "管理配置" / "关卡变量" for root in resource_roots]

        results: Dict[str, VariableFileInfo] = {}

        for base_dir in base_dirs:
            if not base_dir.is_dir():
                continue

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

                is_valid_syntax, error_preview = _check_python_source_syntax(py_path)
                if not is_valid_syntax:
                    log_warn(
                        "[关卡变量] 变量文件语法错误，已跳过加载：{} ({})",
                        py_path.as_posix(),
                        error_preview,
                    )
                    continue

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
                    absolute_path=py_path,
                    variables=variables,
                )

        return results

    def load_all_level_variables_from_code(self, *, active_package_id: str | None = None) -> Dict[str, Dict]:
        """加载所有变量，返回 {variable_id: payload}（兼容旧接口）。"""
        file_infos = self.load_all_variable_files(active_package_id=active_package_id)
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

        payload = {
            "variable_id": entry["variable_id"],
            "variable_name": entry["variable_name"],
            "variable_type": entry["variable_type"],
            "default_value": entry.get("default_value"),
            "is_global": entry.get("is_global", True),
            "description": entry.get("description", ""),
            "metadata": entry.get("metadata", {}),
        }

        # ===== 类型与默认值强校验（运行期必须保证一致）=====
        variable_id = str(payload.get("variable_id") or "").strip()
        if not variable_id:
            raise ValueError(f"关卡变量 variable_id 不能为空（{py_path}）")

        variable_type = str(payload.get("variable_type") or "").strip()
        if not variable_type:
            raise ValueError(f"关卡变量 variable_type 不能为空：{variable_id}（{py_path}）")

        variable_name = str(payload.get("variable_name") or "").strip()
        if not variable_name:
            raise ValueError(f"关卡变量 variable_name 不能为空：{variable_id}（{py_path}）")

        # 允许：规范中文类型名（VARIABLE_TYPES）与“别名字典类型”（parse_typed_dict_alias 可解析）
        if (variable_type not in set(VARIABLE_TYPES)) and (not parse_typed_dict_alias(variable_type)[0]):
            raise ValueError(
                f"关卡变量类型不受支持：{variable_id} -> {variable_type!r}（{py_path}）"
            )

        default_value = payload.get("default_value")
        id_types = {TYPE_GUID, TYPE_CONFIG_ID, TYPE_COMPONENT_ID}
        id_list_types = {TYPE_GUID_LIST, TYPE_CONFIG_ID_LIST, TYPE_COMPONENT_ID_LIST}

        if variable_type in id_types:
            if not is_digits_1_to_10(default_value):
                raise ValueError(
                    "关卡变量默认值必须为 1~10 位纯数字（int 或数字字符串）："
                    f"{variable_id} ({variable_type}) -> {default_value!r}（{py_path}）"
                )

        if variable_type in id_list_types:
            if not isinstance(default_value, (list, tuple)):
                raise ValueError(
                    "关卡变量默认值必须为列表："
                    f"{variable_id} ({variable_type}) -> {default_value!r}（{py_path}）"
                )
            invalid_items = [x for x in list(default_value) if not is_digits_1_to_10(x)]
            if invalid_items:
                preview = ", ".join(repr(x) for x in invalid_items[:6])
                more = "..." if len(invalid_items) > 6 else ""
                raise ValueError(
                    "关卡变量默认值列表元素必须为 1~10 位纯数字："
                    f"{variable_id} ({variable_type}) -> {preview}{more}（{py_path}）"
                )

        return payload


class LevelVariableSchemaView:
    """关卡变量聚合视图（只读缓存）。"""

    def __init__(self, schema_service: LevelVariableSchemaService | None = None) -> None:
        self._schema_service = schema_service or LevelVariableSchemaService()
        # 当前作用域：None 表示仅共享根；str 表示共享根 + 指定项目存档根。
        self._active_package_id: str | None = None
        self._variables: Dict[str, Dict] | None = None
        self._variable_files: Dict[str, VariableFileInfo] | None = None

    def set_active_package_id(self, package_id: str | None) -> None:
        """设置关卡变量 Schema 的项目存档作用域。

        约定：
        - None / "global_view" / "unclassified_view"：仅共享根；
        - 其它非空字符串：共享根 + 指定项目存档根。
        """
        normalized = str(package_id or "").strip()
        if normalized in {"global_view", "unclassified_view"}:
            normalized = ""
        normalized_or_none: str | None = normalized or None
        if normalized_or_none == self._active_package_id:
            return
        self._active_package_id = normalized_or_none
        self.invalidate_cache()

    def _ensure_loaded(self) -> None:
        """确保数据已加载。"""
        if self._variable_files is None:
            self._variable_files = self._schema_service.load_all_variable_files(
                active_package_id=self._active_package_id
            )
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


def set_default_level_variable_schema_view_active_package_id(package_id: str | None) -> None:
    """同步默认 LevelVariableSchemaView 的作用域（共享根 / 共享+当前存档）。"""
    schema_view = get_default_level_variable_schema_view()
    set_active = getattr(schema_view, "set_active_package_id", None)
    if callable(set_active):
        set_active(package_id)


def invalidate_default_level_variable_cache() -> None:
    """使默认视图的缓存失效。"""
    global _default_level_variable_schema_view
    if _default_level_variable_schema_view is not None:
        _default_level_variable_schema_view.invalidate_cache()
