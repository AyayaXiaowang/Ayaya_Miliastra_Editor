from __future__ import annotations

from pathlib import Path

from engine.utils.path_utils import normalize_slash


def sanitize_folder_path(folder_path: str) -> str:
    """标准化 folder_path（统一使用 / 作为分隔符，且不保留首尾 /）。"""

    return normalize_slash(str(folder_path or "")).strip("/")


def infer_graph_type_and_folder_path(graph_file: Path) -> tuple[str, str]:
    """从节点图文件路径推断 (graph_type, folder_path)。

    约定节点图位于任意路径下的：
    - `.../节点图/<server|client>/<folder...>/<file>.py`

    返回：
    - graph_type: "server"/"client"（若无法推断则返回空字符串）
    - folder_path: 相对 type 目录的文件夹路径（根目录返回空字符串）
    """

    normalized = normalize_slash(graph_file.as_posix())
    for graph_type in ("server", "client"):
        marker = f"/节点图/{graph_type}/"
        if marker not in normalized:
            continue
        tail = normalized.split(marker, 1)[1]
        parts = [p for p in str(tail or "").split("/") if p]
        if not parts:
            return graph_type, ""
        folder_path = "/".join(parts[:-1])
        return graph_type, sanitize_folder_path(folder_path) if folder_path else ""
    return "", ""



