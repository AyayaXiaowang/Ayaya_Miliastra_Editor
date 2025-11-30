"""图资源的持久化缓存管理。

本模块将原先 `ResourceManager` 中与“节点图持久化缓存”相关的逻辑提取出来，
职责包括：

- 计算节点定义指纹（plugins/nodes / engine/nodes / engine/graph）
- 基于文件内容哈希与指纹校验持久化缓存有效性
- 读写 `app/runtime/cache/graph_cache/<graph_id>.json`
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from engine.utils.logging.logger import log_info
from engine.utils.graph.node_defs_fingerprint import compute_node_defs_fingerprint
from engine.utils.cache.cache_paths import get_graph_cache_dir


class GraphCacheManager:
    """节点图持久化缓存管理器。"""

    def __init__(self, workspace_path: Path) -> None:
        """
        Args:
            workspace_path: 工作空间根目录（Graph_Generater）
        """
        self.workspace_path = workspace_path

    # ===== 公共 API =====

    def load_persistent_graph_cache(
        self, graph_id: str, file_path: Path
    ) -> Optional[Dict]:
        """按图 ID 和文件路径尝试加载持久化缓存。

        使用文件内容 MD5 与节点定义指纹进行严格校验。
        """
        cache_dir = self._get_graph_cache_dir()
        cache_file = cache_dir / f"{graph_id}.json"
        if not cache_file.exists():
            return None

        with open(cache_file, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)

        required_keys = {"file_hash", "node_defs_fp", "result_data"}
        if not all(key in data for key in required_keys):
            return None

        current_hash = self._compute_file_md5(file_path)
        current_fp = self._compute_node_defs_fingerprint()
        if data.get("file_hash") != current_hash:
            return None
        if data.get("node_defs_fp") != current_fp:
            return None

        result_data = data.get("result_data")
        if not isinstance(result_data, dict):
            return None
        return result_data

    def read_persistent_graph_cache_result_data(self, graph_id: str) -> Optional[Dict]:
        """读取现有持久化缓存中的 result_data（不做哈希与指纹校验）。

        用于 UI 在已知缓存有效的前提下做增量更新。
        """
        cache_dir = self._get_graph_cache_dir()
        cache_file = cache_dir / f"{graph_id}.json"
        if not cache_file.exists():
            return None

        with open(cache_file, "r", encoding="utf-8") as file_obj:
            payload = json.load(file_obj)
        if not isinstance(payload, dict):
            return None
        result = payload.get("result_data")
        if not isinstance(result, dict):
            return None
        return result

    def save_persistent_graph_cache(
        self,
        graph_id: str,
        file_path: Path,
        result_data: Dict,
    ) -> None:
        """写入或覆盖节点图的持久化缓存文件。"""
        cache_dir = self._get_graph_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{graph_id}.json"
        log_info("[缓存][图] 写入持久化缓存：{} -> {}", graph_id, cache_file)
        payload = {
            "file_hash": self._compute_file_md5(file_path),
            "node_defs_fp": self._compute_node_defs_fingerprint(),
            "result_data": result_data,
            "cached_at": datetime.now().isoformat(),
        }
        with open(cache_file, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        log_info("[缓存][图] 持久化缓存写入完成：{}", graph_id)

    def clear_all_persistent_graph_cache(self) -> int:
        """清空磁盘上的全部节点图持久化缓存。

        Returns:
            被删除的缓存文件数量。
        """
        cache_dir = self._get_graph_cache_dir()
        if not cache_dir.exists():
            return 0
        removed_files = 0
        for json_file in cache_dir.glob("*.json"):
            json_file.unlink()
            removed_files += 1
        if not any(cache_dir.iterdir()):
            cache_dir.rmdir()
        return removed_files

    def clear_persistent_graph_cache_for(self, graph_id: str) -> int:
        """按图 ID 清除单个节点图的持久化缓存文件。"""
        cache_dir = self._get_graph_cache_dir()
        cache_file = cache_dir / f"{graph_id}.json"
        if cache_file.exists():
            cache_file.unlink()
            if not any(cache_dir.iterdir()):
                cache_dir.rmdir()
            return 1
        return 0

    # ===== 内部实现 =====

    def _get_graph_cache_dir(self) -> Path:
        return get_graph_cache_dir(self.workspace_path)

    @staticmethod
    def _compute_file_md5(file_path: Path) -> str:
        md5 = hashlib.md5()
        with open(file_path, "rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()

    def _compute_node_defs_fingerprint(self) -> str:
        """计算用于图缓存失效的节点定义指纹。
        
        与 `engine.nodes.NodeRegistry` 共享统一实现，基于以下目录的 *.py 文件数与最新修改时间：
        - 实现库：`plugins/nodes/`
        - 节点定义/加载核心：`engine/nodes/`
        - 图解析与生成核心：`engine/graph/`
        - 复合节点库：`assets/资源库/复合节点库/`
        """
        return compute_node_defs_fingerprint(self.workspace_path)


