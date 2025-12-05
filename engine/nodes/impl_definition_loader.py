from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any

from .node_definition_loader import NodeDef
from engine.utils.logging.logger import log_info
from engine.configs.settings import settings
from .pipeline.runner import run_pipeline


def load_all_nodes_from_impl(workspace_path: Path, include_composite: bool = True, verbose: bool = False) -> Dict[str, NodeDef]:
    """从 node_implementations 反射加载带有 @node_spec 装饰器的实现函数，构建 NodeDef 库。

    说明：此加载器以实现为唯一权威来源。
    """
    library: Dict[str, NodeDef] = {}

    # 规范工作区路径为绝对路径，避免 Windows 下相对路径导致 relative_to 失败
    workspace_root = workspace_path.resolve()

    # V2 管线（唯一实现）：只解析不导入
    index = run_pipeline(workspace_root)
    by_key: Dict[str, Any] = index.get("by_key", {}) if isinstance(index, dict) else {}
    alias_to_key: Dict[str, str] = index.get("alias_to_key", {}) if isinstance(index, dict) else {}

    def _pair_names(pairs: List[Any]) -> List[str]:
        names: List[str] = []
        for pair in list(pairs or []):
            if isinstance(pair, (list, tuple)) and len(pair) >= 1:
                name_text = str(pair[0])
                if name_text != "":
                    names.append(name_text)
        return names

    # 以 by_key 为权威，构建 NodeDef 对象
    for node_key, item in by_key.items():
        if not isinstance(item, dict):
            continue
        name_text = str(item.get("name", "") or "")
        category_standard = str(item.get("category_standard", "") or item.get("category", "") or "")
        if name_text == "" or category_standard == "":
            continue

        inputs_pairs = list(item.get("inputs") or [])
        outputs_pairs = list(item.get("outputs") or [])
        input_types = dict(item.get("input_types") or {})
        output_types = dict(item.get("output_types") or {})
        input_names = _pair_names(inputs_pairs) or list(input_types.keys())
        output_names = _pair_names(outputs_pairs) or list(output_types.keys())

        node = NodeDef(
            name=name_text,
            category=category_standard,
            inputs=input_names,
            outputs=output_names,
            description=str(item.get("description") or ""),
            scopes=list(item.get("scopes") or []),
            mount_restrictions=list(item.get("mount_restrictions") or []),
            doc_reference=str(item.get("doc_reference") or ""),
            input_types=input_types,
            output_types=output_types,
            dynamic_port_type=str(item.get("dynamic_port_type") or ""),
            is_composite=False,
            composite_id="",
            input_generic_constraints=dict(item.get("input_generic_constraints") or {}),
            output_generic_constraints=dict(item.get("output_generic_constraints") or {}),
            input_enum_options=dict(item.get("input_enum_options") or {}),
            output_enum_options=dict(item.get("output_enum_options") or {}),
        )
        library[node_key] = node

    # 为别名注册直达键（保持对外输入兼容）
    if getattr(settings, "NODE_ALIAS_INJECT_IN_LIBRARY", True):
        for alias_key, mapped_key in alias_to_key.items():
            if mapped_key in library and alias_key not in library:
                library[alias_key] = library[mapped_key]

    if verbose or getattr(settings, "NODE_LOADING_VERBOSE", False):
        log_info("V2 管线加载完成，共 {} 条（含别名条目）", len(library))
    return library
