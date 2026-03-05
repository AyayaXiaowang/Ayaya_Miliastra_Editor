from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable


def _ensure_graph_generater_sys_path(graph_generater_root: Path) -> None:
    root = Path(graph_generater_root).resolve()
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    assets_dir = root / "assets"
    assets_text = str(assets_dir)
    if assets_dir.is_dir() and assets_text not in sys.path:
        sys.path.insert(1, assets_text)


def _load_server_node_defs(*, graph_generater_root: Path) -> Dict[str, Any]:
    return _load_node_defs_by_scope(graph_generater_root=Path(graph_generater_root), scope="server")


def _load_client_node_defs(*, graph_generater_root: Path) -> Dict[str, Any]:
    return _load_node_defs_by_scope(graph_generater_root=Path(graph_generater_root), scope="client")


def _load_node_defs_by_scope(*, graph_generater_root: Path, scope: str) -> Dict[str, Any]:
    """加载 Graph_Generater 的 NodeDef：{节点名: NodeDef}（按 scope 过滤 server/client）。"""
    scope_norm = str(scope or "").strip().lower()
    if scope_norm not in ("server", "client"):
        raise ValueError(f"scope 不支持：{scope!r}（可选：server/client）")
    _ensure_graph_generater_sys_path(graph_generater_root)
    from engine.nodes.node_registry import get_node_registry  # type: ignore[import-not-found]
    from engine.utils.name_utils import make_valid_identifier  # type: ignore[import-not-found]

    # 导出/写回链路需要识别复合节点（GraphModel 会以普通 node title 引用 composite 节点），
    # 因此这里必须包含复合节点定义；否则会在 flow/data 端口判定阶段直接 KeyError。
    registry = get_node_registry(Path(graph_generater_root).resolve(), include_composite=True)
    library = registry.get_library()
    node_defs: Dict[str, Any] = {}

    def iter_name_aliases(node_name: str, node_def: Any) -> Iterable[str]:
        """为 NodeDef.name 补充常见别名，兼容 GraphModel/Graph Code 使用的不同调用写法。"""
        n = str(node_name or "").strip()
        if n == "":
            return
        yield n
        if "/" in n:
            yield n.replace("/", "")
            yield n.replace("/", "或")
            yield n.replace("/", "_")
        ident = str(make_valid_identifier(n) or "").strip()
        if ident and ident != n:
            yield ident
        raw_aliases = getattr(node_def, "aliases", None)
        if isinstance(raw_aliases, list):
            for a in raw_aliases:
                a_text = str(a or "").strip()
                if a_text:
                    yield a_text

    for node_def in library.values():
        if node_def is None:
            continue
        if not node_def.is_available_in_scope(str(scope_norm)):
            continue
        node_name = str(getattr(node_def, "name", "") or "").strip()
        for alias in iter_name_aliases(node_name, node_def):
            node_defs.setdefault(str(alias), node_def)
    return node_defs


def _is_flow_port_by_node_def(*, node_def: Any, port_name: str, is_input: bool) -> bool:
    resolved_port_name = str(port_name)
    # 端口名兼容：GraphModel 里可能存在历史端口名（例如 列表迭代循环 的 “列表”）
    if bool(is_input) and str(getattr(node_def, "name", "")) == "列表迭代循环" and str(port_name) == "列表":
        resolved_port_name = "迭代列表"

    # Graph_Generater 的 NodeDef.get_port_type(...) 在“缺少显式类型定义且不是流程端口名”时会抛错。
    # 写回侧这里只需要判断“是否为流程端口”，因此优先复用其命名规则，并避免调用会抛错的强约束 API。
    from engine.utils.graph.graph_utils import is_flow_port_name  # type: ignore[import-not-found]
    from engine.nodes.port_name_rules import get_dynamic_port_type  # type: ignore[import-not-found]

    if is_flow_port_name(str(resolved_port_name)):
        return True

    type_dict = node_def.input_types if bool(is_input) else node_def.output_types
    if isinstance(type_dict, dict) and str(resolved_port_name) in type_dict:
        return str(type_dict[str(resolved_port_name)]) == "流程"

    inferred = get_dynamic_port_type(str(resolved_port_name), type_dict, getattr(node_def, "dynamic_port_type", ""))
    if inferred:
        return str(inferred) == "流程"
    return False


def _resolve_input_port_name_for_type(*, node_def: Any, port_name: str) -> str:
    """将 GraphModel 中的输入端口名归一化为 NodeDef 的规范端口名（用于取类型/VarType）。"""
    if str(getattr(node_def, "name", "")) == "列表迭代循环" and str(port_name) == "列表":
        return "迭代列表"
    return str(port_name)


def _is_declared_generic_port_type(type_text: str) -> bool:
    """判断端口在 NodeDef/GraphModel 中是否声明为“泛型家族”。"""
    t = str(type_text or "").strip()
    return ("泛型" in t) or t in {"泛型列表", "泛型字典"}




# -------------------- Public helpers (reusable) --------------------


def ensure_graph_generater_sys_path(graph_generater_root: Path) -> None:
    return _ensure_graph_generater_sys_path(Path(graph_generater_root))


def load_node_defs_by_scope(*, graph_generater_root: Path, scope: str) -> Dict[str, Any]:
    return _load_node_defs_by_scope(graph_generater_root=Path(graph_generater_root), scope=str(scope))


def is_flow_port_by_node_def(*, node_def: Any, port_name: str, is_input: bool) -> bool:
    return _is_flow_port_by_node_def(node_def=node_def, port_name=str(port_name), is_input=bool(is_input))


def resolve_input_port_name_for_type(*, node_def: Any, port_name: str) -> str:
    return _resolve_input_port_name_for_type(node_def=node_def, port_name=str(port_name))


def is_declared_generic_port_type(type_text: str) -> bool:
    return _is_declared_generic_port_type(str(type_text))

