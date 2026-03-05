from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GraphSelection:
    """
    “用户选了哪些节点图”的统一模型（UI → pipeline 之间的唯一口径）。

    设计目标：
    - 统一承载来自不同 UI 入口的“选图结果”（当前图/单图/选择导出），减少 graph_keys / graph_code_files / items 三套并存；
    - 以 graph_code_files 为主（支持 project/shared 混选），并携带 graph_source_roots 用于稳定分配 graph_id_int。
    """

    graph_code_files: list[Path]
    graph_source_roots: list[Path]

    def has_graphs(self) -> bool:
        return bool(self.graph_code_files)

    def include_shared(self) -> bool:
        # 约定：graph_source_roots 至少包含 project_root；当包含 shared_root 时长度 >= 2。
        return len(self.graph_source_roots) >= 2


def _dedupe_paths_keep_order(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for p in list(paths):
        rp = Path(p).resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(rp)
    return out


def build_graph_selection_from_graph_files(*, graph_code_files: list[Path], graph_source_roots: list[Path]) -> GraphSelection:
    files = _dedupe_paths_keep_order([Path(p).resolve() for p in list(graph_code_files or []) if p is not None])
    roots = _dedupe_paths_keep_order([Path(p).resolve() for p in list(graph_source_roots or []) if p is not None])
    if not roots:
        raise ValueError("graph_source_roots 不能为空（至少应包含 project_root）")
    return GraphSelection(graph_code_files=list(files), graph_source_roots=list(roots))


def build_graph_selection_from_resource_items(
    *,
    selected_items: list[object],
    workspace_root: Path,
    package_id: str,
) -> GraphSelection:
    """
    从资源选择器返回的 items 里提取 graphs，并计算 graph_source_roots（project + 可选 shared）。

    约束：
    - items 只要满足 duck-typing：category/source_root/absolute_path 三个属性即可；
    - graph_source_roots 以“分配 graph_id_int 的全量扫描根”为目的：当显式导出子集时仍保持 id 分配稳定。
    """
    from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir

    ws_root = Path(workspace_root).resolve()
    resource_library_root = (ws_root / "assets" / "资源库").resolve()
    packages_root = get_packages_root_dir(resource_library_root).resolve()
    shared_root = get_shared_root_dir(resource_library_root).resolve()
    project_root = (packages_root / str(package_id)).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    graph_files: list[Path] = []
    include_shared = False

    for it in list(selected_items or []):
        category = str(getattr(it, "category", "") or "").strip()
        if category != "graphs":
            continue
        abs_path = getattr(it, "absolute_path", None)
        if abs_path is None:
            continue
        graph_files.append(Path(abs_path).resolve())
        if str(getattr(it, "source_root", "") or "").strip() == "shared":
            include_shared = True

    roots = [Path(project_root).resolve()]
    if include_shared:
        roots.append(Path(shared_root).resolve())

    return build_graph_selection_from_graph_files(graph_code_files=graph_files, graph_source_roots=roots)

