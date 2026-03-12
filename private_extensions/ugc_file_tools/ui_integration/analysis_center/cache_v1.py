from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


CACHE_DIR_PARTS: tuple[str, ...] = ("app", "runtime", "cache", "ugc_file_tools", "analysis_center")
CACHE_FILE_SUFFIX: str = ".json"
CACHE_KEY_HEX_TRUNC_LEN: int = 16


@dataclass(frozen=True, slots=True)
class CacheHit:
    """描述一次索引缓存命中结果。"""

    cache_path: Path
    payload: dict


@dataclass(frozen=True, slots=True)
class CacheMiss:
    """描述一次索引缓存未命中的原因。"""

    reason: str
    expected_cache_path: Path


def get_analysis_center_cache_dir(*, workspace_root: Path) -> Path:
    """返回分析中心索引缓存目录路径。"""
    root = Path(workspace_root).resolve()
    return (root.joinpath(*CACHE_DIR_PARTS)).resolve()


def _normalize_rel_path(*, workspace_root: Path, file_path: Path) -> str:
    """将绝对路径归一化为 workspace_root 下的稳定相对路径字符串。"""
    p = Path(file_path).resolve()
    ws = Path(workspace_root).resolve()
    try:
        rel = p.relative_to(ws).as_posix()
    except ValueError:
        rel = p.as_posix()
    return rel.replace("\\", "/")


def compute_graph_files_fingerprint(*, workspace_root: Path, graph_code_files: list[Path]) -> str:
    """基于图源码路径与文件 stat 计算稳定指纹（用于缓存失效）。"""
    ws = Path(workspace_root).resolve()
    rows: list[str] = []
    for p in list(graph_code_files or []):
        fp = Path(p).resolve()
        if not fp.is_file():
            continue
        st = fp.stat()
        rel = _normalize_rel_path(workspace_root=ws, file_path=fp)
        rows.append(f"{rel}\t{int(st.st_mtime_ns)}\t{int(st.st_size)}")
    rows.sort(key=lambda s: str(s).casefold())
    raw = "\n".join(rows).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compute_index_cache_key(
    *,
    index_version: str,
    scope: str,
    package_id: str,
    node_defs_fp: str,
    graph_files_fingerprint: str,
) -> str:
    """根据索引版本与输入指纹计算 cache_key。"""
    parts = [
        str(index_version or "").strip(),
        str(scope or "").strip(),
        str(package_id or "").strip(),
        str(node_defs_fp or "").strip(),
        str(graph_files_fingerprint or "").strip(),
    ]
    raw = ("\n".join(parts)).encode("utf-8")
    full = hashlib.sha256(raw).hexdigest()
    return full[: int(CACHE_KEY_HEX_TRUNC_LEN)]


def get_cache_file_path(*, cache_dir: Path, index_version: str, cache_key: str) -> Path:
    """返回给定 cache_key 对应的索引缓存文件路径。"""
    safe_ver = str(index_version or "").strip().replace("/", "_").replace("\\", "_")
    safe_key = str(cache_key or "").strip()
    return (Path(cache_dir).resolve() / f"{safe_ver}__{safe_key}{CACHE_FILE_SUFFIX}").resolve()


def try_load_cached_index_payload(
    *,
    cache_path: Path,
    expected_index_version: str,
    expected_cache_key: str,
) -> CacheHit | CacheMiss:
    """尝试读取并校验缓存索引 payload。"""
    p = Path(cache_path).resolve()
    if not p.is_file():
        return CacheMiss(reason="cache 文件不存在", expected_cache_path=p)
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return CacheMiss(reason="cache JSON 不是 dict", expected_cache_path=p)
    if str(obj.get("version") or "").strip() != str(expected_index_version or "").strip():
        return CacheMiss(reason="cache version 不匹配", expected_cache_path=p)
    meta = obj.get("_cache")
    if not isinstance(meta, dict):
        return CacheMiss(reason="cache 缺少 _cache 元信息", expected_cache_path=p)
    if str(meta.get("cache_key") or "").strip() != str(expected_cache_key or "").strip():
        return CacheMiss(reason="cache_key 不匹配", expected_cache_path=p)
    return CacheHit(cache_path=p, payload=dict(obj))


def write_cached_index_payload(*, cache_path: Path, payload: dict) -> None:
    """将索引 payload 写入磁盘缓存文件。"""
    p = Path(cache_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

