from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


def get_beyond_local_root_dir() -> Path:
    """
    真源存档根目录（Windows）。

    约定：
    - 通过 `Path.home()` 推导用户目录，不在源码中写死盘符/用户名。
    """

    home = Path.home().resolve()
    return (home / "AppData" / "LocalLow" / "miHoYo" / "原神" / "BeyondLocal").resolve()


@dataclass(frozen=True, slots=True)
class GilMapCandidate:
    path: Path
    mtime_ms: int


def _iter_gil_files_in_dir(dir_path: Path) -> Iterable[GilMapCandidate]:
    d = Path(dir_path).resolve()
    if not d.is_dir():
        return
    for p in d.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() != ".gil":
            continue
        st = p.stat()
        yield GilMapCandidate(path=p.resolve(), mtime_ms=int(st.st_mtime_ns // 1_000_000))


def _iter_gil_files_walk(dir_path: Path, *, max_depth: int) -> Iterable[GilMapCandidate]:
    """
    depth-limited os.walk（避免 BeyondLocal 下文件过多时无上限扫描）。
    """

    root = Path(dir_path).resolve()
    if not root.is_dir():
        return

    root_depth = len(root.parts)
    for current, dirs, files in os.walk(str(root)):
        cur_path = Path(current)
        depth = len(cur_path.parts) - root_depth
        if depth >= int(max_depth):
            dirs[:] = []
        for fn in files:
            if not str(fn).lower().endswith(".gil"):
                continue
            p = (cur_path / fn).resolve()
            if not p.is_file():
                continue
            st = p.stat()
            yield GilMapCandidate(path=p, mtime_ms=int(st.st_mtime_ns // 1_000_000))


def find_latest_beyond_local_gil_map_file() -> Path | None:
    """
    自动定位“最近修改的地图 .gil”。

    选择策略：
    - 优先在常见目录下查找（非递归）；
    - 若未找到，再对 BeyondLocal 做一次深度受限扫描（默认 4 层）。
    """

    root = get_beyond_local_root_dir()
    if not root.is_dir():
        return None

    preferred_dirs = [
        root / "SaveLevel",
        root / "SaveLevels",
        root / "saveLevel",
        root / "saveLevels",
        root / "Save",
        root / "save",
        root,
    ]

    candidates: List[GilMapCandidate] = []
    for d in preferred_dirs:
        candidates.extend(list(_iter_gil_files_in_dir(d)))
        if candidates:
            break

    if not candidates:
        candidates = list(_iter_gil_files_walk(root, max_depth=4))

    if not candidates:
        return None

    candidates.sort(key=lambda c: int(c.mtime_ms), reverse=True)
    return Path(candidates[0].path).resolve()


def find_best_beyond_local_gil_for_node_graph_id(node_graph_id_int: int, *, scan_limit: int = 120) -> Path | None:
    """
    自动定位“包含指定 NodeGraph id 的地图 .gil”。

    设计目的：多账号/多地图环境下，仅靠“最近修改”容易选错文件；该函数会优先在各玩家目录的
    `Beyond_Local_Save_Level/` 下按 mtime 从新到旧扫描，找到第一个包含目标 graph_id 的 `.gil`。
    """

    target_id = int(node_graph_id_int)
    if target_id <= 0:
        raise ValueError(f"invalid node_graph_id_int: {node_graph_id_int!r}")

    root = get_beyond_local_root_dir()
    if not root.is_dir():
        return None

    # 仅扫描玩家目录下的 Save_Level（避免误扫其它二进制/缓存目录）
    candidates: List[GilMapCandidate] = []
    for d in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if not d.is_dir():
            continue
        # 玩家目录一般是数字
        if not d.name.isdigit():
            continue
        save_dir = (d / "Beyond_Local_Save_Level").resolve()
        if not save_dir.is_dir():
            continue
        candidates.extend(list(_iter_gil_files_in_dir(save_dir)))

    if not candidates:
        return None

    candidates.sort(key=lambda c: int(c.mtime_ms), reverse=True)
    candidates = candidates[: max(int(scan_limit), 1)]

    # lazy import（避免无注入场景引入额外依赖）
    from ugc_file_tools.gil_dump_codec.gil_container import read_gil_payload_bytes
    from ugc_file_tools.save_patchers.gil_node_graph_injector import (
        find_node_graph_field_by_id,
        parse_len_fields,
    )

    for c in candidates:
        payload = read_gil_payload_bytes(Path(c.path))
        all_len_fields = []
        blob_fields = []
        parse_len_fields(payload, 0, len(payload), 0, 0, 0, 0, 0, 0, 0, all_len_fields, node_graph_blob_fields=blob_fields)

        # 与注入器保持同一套查找策略：先扫 10.1.1，未命中则回退全量扫（避免误判/不一致）
        target_field, _found_ids_blob = find_node_graph_field_by_id(
            payload=payload,
            node_graph_blob_fields=list(blob_fields),
            all_len_fields=list(all_len_fields),
            target_graph_id_int=int(target_id),
        )
        if target_field is not None:
            return Path(c.path).resolve()

    return None


def gil_contains_node_graph_id(gil_file_path: Path, node_graph_id_int: int) -> bool:
    """
    判断某个 `.gil` 是否包含指定的 NodeGraph id（基于 NodeGraph bytes 的快速签名探测）。

    注意：
    - 这是“只读扫描”，用于在多账号/多地图环境下避免选错目标地图。
    - 只做存在性判断，不解析/不写回。
    """

    target_id = int(node_graph_id_int)
    if target_id <= 0:
        raise ValueError(f"invalid node_graph_id_int: {node_graph_id_int!r}")

    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    from ugc_file_tools.gil_dump_codec.gil_container import read_gil_payload_bytes
    from ugc_file_tools.save_patchers.gil_node_graph_injector import find_node_graph_field_by_id, parse_len_fields

    payload = read_gil_payload_bytes(p)
    all_len_fields = []
    blob_fields = []
    parse_len_fields(payload, 0, len(payload), 0, 0, 0, 0, 0, 0, 0, all_len_fields, node_graph_blob_fields=blob_fields)
    target_field, _found_ids_blob = find_node_graph_field_by_id(
        payload=payload,
        node_graph_blob_fields=list(blob_fields),
        all_len_fields=list(all_len_fields),
        target_graph_id_int=int(target_id),
    )
    return target_field is not None

