from __future__ import annotations

from pathlib import Path
from typing import Dict

from importlib.machinery import SourceFileLoader

from engine.configs.specialized.struct_definitions_data import (
    STRUCT_DEFINITION_PAYLOADS,
)
from engine.configs.specialized.signal_definitions_data import (
    SIGNAL_DEFINITION_PAYLOADS,
)


class CodeSchemaResourceService:
    """结构体 / 信号的代码级 Schema 载入服务（当前基于集中常量实现）。

    设计目标：
    - 为结构体与信号提供统一、只读的 {id: payload} 视图；
    - 隔离具体数据来源（目前为 Python 常量，后续可以切换为 assets 代码资源）；
    - 不在导入阶段访问磁盘或 ResourceManager，避免循环依赖。
    """

    def _get_workspace_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _load_struct_definitions_from_code(self) -> Dict[str, Dict]:
        """从 assets 代码资源中加载结构体定义，返回 {struct_id: payload}。

        约定：
        - 根目录：assets/资源库/管理配置/结构体定义
        - 子目录：按需分组的子文件夹（可选），例如 basic/、ingame_save/ 等
        - 每个 .py 文件导出：
          - STRUCT_ID: str
          - STRUCT_PAYLOAD: dict
        """
        workspace = self._get_workspace_root()
        base_dir = workspace / "assets" / "资源库" / "管理配置" / "结构体定义"
        if not base_dir.is_dir():
            return {}

        results: Dict[str, Dict] = {}

        for py_path in base_dir.rglob("*.py"):
            module_name = f"code_struct_resource_{abs(hash(py_path.as_posix()))}"
            loader = SourceFileLoader(module_name, str(py_path))
            module = loader.load_module()

            struct_id_value = getattr(module, "STRUCT_ID", None)
            payload_value = getattr(module, "STRUCT_PAYLOAD", None)

            if not isinstance(struct_id_value, str) or not struct_id_value:
                raise ValueError(f"无效的 STRUCT_ID（{py_path}）")
            if not isinstance(payload_value, dict):
                raise ValueError(f"无效的 STRUCT_PAYLOAD（{py_path}）")

            struct_id = struct_id_value
            if struct_id in results:
                raise ValueError(f"重复的结构体 ID：{struct_id}")

            results[struct_id] = dict(payload_value)

        return results

    def _load_signal_definitions_from_code(self) -> Dict[str, Dict]:
        """从 assets 代码资源中加载信号定义，返回 {signal_id: payload}。

        约定：
        - 根目录：assets/资源库/管理配置/信号
        - 每个 .py 文件导出：
          - SIGNAL_ID: str
          - SIGNAL_PAYLOAD: dict
        """
        workspace = self._get_workspace_root()
        base_dir = workspace / "assets" / "资源库" / "管理配置" / "信号"
        if not base_dir.is_dir():
            return {}

        results: Dict[str, Dict] = {}

        for py_path in base_dir.rglob("*.py"):
            module_name = f"code_signal_resource_{abs(hash(py_path.as_posix()))}"
            loader = SourceFileLoader(module_name, str(py_path))
            module = loader.load_module()

            signal_id_value = getattr(module, "SIGNAL_ID", None)
            payload_value = getattr(module, "SIGNAL_PAYLOAD", None)

            if not isinstance(signal_id_value, str) or not signal_id_value:
                raise ValueError(f"无效的 SIGNAL_ID（{py_path}）")
            if not isinstance(payload_value, dict):
                raise ValueError(f"无效的 SIGNAL_PAYLOAD（{py_path}）")

            signal_id = signal_id_value
            if signal_id in results:
                raise ValueError(f"重复的信号 ID：{signal_id}")

            results[signal_id] = dict(payload_value)

        return results

    def load_all_struct_definitions(self) -> Dict[str, Dict]:
        """加载所有结构体定义，返回 {struct_id: payload}。

        优先从 assets 代码资源（ResourceType.STRUCT_DEFINITION_CODE）加载，
        若未配置则回退到引擎配置中的集中常量。
        """
        code_results = self._load_struct_definitions_from_code()
        if code_results:
            return code_results

        results: Dict[str, Dict] = {}
        for struct_id, payload in STRUCT_DEFINITION_PAYLOADS.items():
            if not isinstance(payload, dict):
                continue
            results[str(struct_id)] = dict(payload)
        return results

    def load_all_signal_definitions(self) -> Dict[str, Dict]:
        """加载所有信号定义，返回 {signal_id: payload}。

        优先从 assets 代码资源（ResourceType.SIGNAL_DEFINITION_CODE）加载，
        若未配置则回退到引擎配置中的集中常量。
        """
        code_results = self._load_signal_definitions_from_code()
        if code_results:
            return code_results

        results: Dict[str, Dict] = {}
        for signal_id, payload in SIGNAL_DEFINITION_PAYLOADS.items():
            if not isinstance(payload, dict):
                continue
            results[str(signal_id)] = dict(payload)
        return results


class DefinitionSchemaView:
    """结构体 / 信号 Schema 聚合视图（进程内缓存，只读）。"""

    def __init__(self, schema_service: CodeSchemaResourceService | None = None) -> None:
        self._schema_service = schema_service or CodeSchemaResourceService()
        self._struct_definitions: Dict[str, Dict] | None = None
        self._signal_definitions: Dict[str, Dict] | None = None

    def get_all_struct_definitions(self) -> Dict[str, Dict]:
        """返回 {struct_id: payload}，payload 为结构体定义原始字典的副本。"""
        if self._struct_definitions is None:
            self._struct_definitions = self._schema_service.load_all_struct_definitions()
        return self._struct_definitions

    def get_all_signal_definitions(self) -> Dict[str, Dict]:
        """返回 {signal_id: payload}，payload 为信号定义原始字典的副本。"""
        if self._signal_definitions is None:
            self._signal_definitions = self._schema_service.load_all_signal_definitions()
        return self._signal_definitions


_default_schema_view: DefinitionSchemaView | None = None


def get_default_definition_schema_view() -> DefinitionSchemaView:
    """获取进程级默认 DefinitionSchemaView 实例（带缓存）。"""
    global _default_schema_view
    if _default_schema_view is None:
        _default_schema_view = DefinitionSchemaView()
    return _default_schema_view


