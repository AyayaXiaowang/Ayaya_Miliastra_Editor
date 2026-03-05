from __future__ import annotations

"""
type_registry_bridge.py

目标：
- 让 ugc_file_tools 在“类型体系”上与 Graph_Generater 保持单一事实来源；
- 复用 Graph_Generater/engine/type_registry.py 的 VARIABLE_TYPES / 别名字典解析等规则；
- 避免在 ugc_file_tools 内维护一份平行的中文类型清单（容易漂移）。

命名约定：
- 仓库内目录名为 `Graph_Generater/`（历史拼写）。对“概念名/变量名”，推荐使用 `graph_generator`（正确拼写）。
- 为兼容历史代码，本文件保留 `graph_generater_*` 形式的函数名，并提供等价的 `graph_generator_*` 别名函数。

约束：
- 不做 I/O；
- 不使用 try/except；依赖缺失时直接抛错，便于定位。
"""

import sys
import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_CACHED_TYPE_REGISTRY: Any = None


def _default_graph_generater_root() -> Path:
    from ugc_file_tools.repo_paths import repo_root

    return repo_root()


def _default_graph_generator_root() -> Path:
    return _default_graph_generater_root()


def ensure_graph_generater_sys_path(graph_generater_root: Optional[Path] = None) -> Path:
    root = Path(graph_generater_root) if graph_generater_root is not None else _default_graph_generater_root()
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Graph_Generater 根目录不存在：{str(root)!r}")

    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    assets_dir = root / "assets"
    if assets_dir.is_dir():
        assets_text = str(assets_dir)
        if assets_text not in sys.path:
            sys.path.insert(1, assets_text)

    return root


def ensure_graph_generator_sys_path(graph_generator_root: Optional[Path] = None) -> Path:
    return ensure_graph_generater_sys_path(graph_generator_root)


def load_graph_generater_type_registry(*, graph_generater_root: Optional[Path] = None) -> Any:
    """加载 Graph_Generater 的 engine.type_registry 模块（缓存）。"""
    global _CACHED_TYPE_REGISTRY
    if _CACHED_TYPE_REGISTRY is not None:
        return _CACHED_TYPE_REGISTRY

    root = ensure_graph_generater_sys_path(graph_generater_root)

    # 重要：不要 `import engine`。
    # 目前 Graph_Generater/engine/__init__.py 可能包含额外的副作用导入（例如 validate 规则），
    # 导致仅为了获取类型表就被阻塞。`engine/type_registry.py` 设计为纯 Python / 纯数据，
    # 这里直接按文件路径加载，确保稳定。
    type_registry_path = (root / "engine" / "type_registry.py").resolve()
    if not type_registry_path.is_file():
        raise FileNotFoundError(f"Graph_Generater type_registry.py 不存在：{str(type_registry_path)!r}")

    spec = importlib.util.spec_from_file_location("graph_generater_engine_type_registry", str(type_registry_path))
    if spec is None or spec.loader is None:
        raise ValueError(f"无法为 type_registry.py 创建 module spec：{str(type_registry_path)!r}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    _CACHED_TYPE_REGISTRY = module
    return module


def load_graph_generator_type_registry(*, graph_generator_root: Optional[Path] = None) -> Any:
    return load_graph_generater_type_registry(graph_generater_root=graph_generator_root)


def is_supported_graph_variable_type_text(type_text: str, *, graph_generater_root: Optional[Path] = None) -> bool:
    tr = load_graph_generater_type_registry(graph_generater_root=graph_generater_root)
    text = str(type_text or "").strip()
    if not text:
        return False
    if text in set(tr.VARIABLE_TYPES):
        return True
    is_typed_dict, _, _ = tr.parse_typed_dict_alias(text)
    return bool(is_typed_dict)


def parse_typed_dict_alias(type_text: str, *, graph_generater_root: Optional[Path] = None) -> Tuple[bool, str, str]:
    tr = load_graph_generater_type_registry(graph_generater_root=graph_generater_root)
    return tr.parse_typed_dict_alias(str(type_text or "").strip())


def map_graph_variable_cn_type_to_var_type_int(type_text: str, *, graph_generater_root: Optional[Path] = None) -> int:
    """将 Graph_Generater 的“规范中文类型名”映射为 server VarType 数字（仅图变量允许集合）。"""
    tr = load_graph_generater_type_registry(graph_generater_root=graph_generater_root)
    t = str(type_text or "").strip()
    if t == "":
        raise ValueError("type_text 不能为空")

    # 别名字典：统一映射为 Dictionary(27)，键/值类型需由调用方另行处理
    is_typed_dict, _, _ = tr.parse_typed_dict_alias(t)
    if is_typed_dict:
        return 27

    mapping: Dict[str, int] = {
        tr.TYPE_ENTITY: 1,
        tr.TYPE_GUID: 2,
        tr.TYPE_INTEGER: 3,
        tr.TYPE_BOOLEAN: 4,
        tr.TYPE_FLOAT: 5,
        tr.TYPE_STRING: 6,
        tr.TYPE_GUID_LIST: 7,
        tr.TYPE_INTEGER_LIST: 8,
        tr.TYPE_BOOLEAN_LIST: 9,
        tr.TYPE_FLOAT_LIST: 10,
        tr.TYPE_STRING_LIST: 11,
        tr.TYPE_VECTOR3: 12,
        tr.TYPE_ENTITY_LIST: 13,
        tr.TYPE_VECTOR3_LIST: 15,
        tr.TYPE_CAMP: 17,
        tr.TYPE_CONFIG_ID: 20,
        tr.TYPE_COMPONENT_ID: 21,
        tr.TYPE_CONFIG_ID_LIST: 22,
        tr.TYPE_COMPONENT_ID_LIST: 23,
        tr.TYPE_CAMP_LIST: 24,
        tr.TYPE_STRUCT: 25,
        tr.TYPE_STRUCT_LIST: 26,
        tr.TYPE_DICT: 27,
    }

    if t not in mapping:
        raise ValueError(f"不支持的节点图变量类型（以 Graph_Generater.type_registry 为准）：{t!r}")
    return int(mapping[t])


