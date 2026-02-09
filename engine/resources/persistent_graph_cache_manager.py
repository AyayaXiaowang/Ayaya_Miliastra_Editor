"""图资源的持久化缓存管理（磁盘 persistent）。

职责：
- 计算节点定义指纹（plugins/nodes / engine/nodes / engine/graph）
- 基于文件内容哈希与指纹校验持久化缓存有效性
- 读写 `app/runtime/cache/graph_cache/<graph_id>.json`

注意：
- 本模块是“磁盘持久化缓存”，与 UI/任务清单使用的“进程内临时 graph_data 缓存”不同。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from engine.utils.cache.cache_paths import get_graph_cache_dir
from engine.utils.graph.node_defs_fingerprint import compute_node_defs_fingerprint
from engine.utils.logging.logger import log_info, log_warn
from engine.graph.common import (
    FLOW_BRANCH_PORT_ALIASES,
    FLOW_IN_PORT_NAMES,
    FLOW_OUT_PORT_NAMES,
    FLOW_PORT_PLACEHOLDER,
)


def _scan_complete_json_container_end(text: str, start_index: int) -> Optional[int]:
    """扫描从 start_index 开始的 JSON 容器（object/array）结束位置（end_exclusive）。

    说明：
    - 仅做“结构完整性”扫描：括号匹配 + 字符串/转义处理；不做语义解析。
    - 用途：避免 cache 文件被拼接/尾部残留时，直接 json.loads 触发 JSONDecodeError。

    Returns:
        end_exclusive: 容器结束的下一个索引；若无法确定完整容器，返回 None。
    """
    if start_index < 0 or start_index >= len(text):
        return None
    if text[start_index] not in "{[":
        return None

    container_stack: list[str] = []
    in_string = False
    is_escaped = False

    for cursor_index in range(start_index, len(text)):
        current_char = text[cursor_index]
        if in_string:
            if is_escaped:
                is_escaped = False
                continue
            if current_char == "\\":
                is_escaped = True
                continue
            if current_char == '"':
                in_string = False
            continue

        if current_char == '"':
            in_string = True
            continue
        if current_char in "{[":
            container_stack.append(current_char)
            continue
        if current_char in "}]":
            if not container_stack:
                return None
            open_char = container_stack.pop()
            if open_char == "{" and current_char != "}":
                return None
            if open_char == "[" and current_char != "]":
                return None
            if not container_stack:
                return cursor_index + 1
    return None


def _strip_bom_and_whitespace(text: str) -> str:
    # BOM 不是 isspace()，但在 JSON 文本中它不应参与“是否有内容”的判定
    return text.replace("\ufeff", "").strip()


def _extract_last_complete_json_container_text(text: str) -> tuple[Optional[str], bool]:
    """提取文本中最后一个完整 JSON 容器（object/array）的原始片段。

    Returns:
        - json_text: 最后一个完整容器片段（从 '{' 或 '[' 到对应闭合结束），找不到则 None。
        - needs_repair: 若原文本除该容器外仍含其它非空白内容（含多段 JSON/尾部残留），为 True。
    """
    text_length = len(text)
    cursor_index = 0
    while cursor_index < text_length and (text[cursor_index].isspace() or text[cursor_index] == "\ufeff"):
        cursor_index += 1

    last_start: Optional[int] = None
    last_end: Optional[int] = None

    while cursor_index < text_length and text[cursor_index] in "{[":
        container_start = cursor_index
        container_end = _scan_complete_json_container_end(text, container_start)
        if container_end is None:
            break
        last_start = container_start
        last_end = container_end

        cursor_index = container_end
        while cursor_index < text_length and (text[cursor_index].isspace() or text[cursor_index] == "\ufeff"):
            cursor_index += 1

    if last_start is None or last_end is None:
        return None, False

    prefix = text[:last_start]
    suffix = text[last_end:]
    needs_repair = bool(_strip_bom_and_whitespace(prefix)) or bool(_strip_bom_and_whitespace(suffix))
    return text[last_start:last_end], needs_repair


class PersistentGraphCacheManager:
    """节点图持久化缓存管理器（磁盘）。"""

    def __init__(self, workspace_path: Path) -> None:
        """
        Args:
            workspace_path: 工作区根目录（workspace_root）
        """
        self.workspace_path = workspace_path

    # ===== 公共 API =====

    def load_persistent_graph_cache(self, graph_id: str, file_path: Path) -> Optional[Dict]:
        """按图 ID 和文件路径尝试加载持久化缓存。

        使用文件内容 MD5 与节点定义指纹进行严格校验。
        """
        cache_dir = self._get_graph_cache_dir()
        cache_file = cache_dir / f"{graph_id}.json"
        if not cache_file.exists():
            return None

        data = self._read_cache_payload_dict(cache_file, graph_id=graph_id)
        if data is None:
            return None

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
        if not self._is_result_data_structurally_consistent(result_data):
            log_warn("[缓存][图] 持久化缓存结构不自洽，视为失效：{}", graph_id)
            cache_file.unlink()
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

        payload = self._read_cache_payload_dict(cache_file, graph_id=graph_id)
        if not isinstance(payload, dict):
            return None
        result = payload.get("result_data")
        if not isinstance(result, dict):
            return None
        return result

    def read_persistent_graph_cache_payload(self, graph_id: str) -> Optional[dict]:
        """读取持久化缓存文件中的原始 payload（不做哈希/指纹校验）。

        说明：
        - 与 `read_persistent_graph_cache_result_data()` 的区别在于：该方法返回包含
          file_hash/node_defs_fp/result_data/cached_at 的完整 payload，便于列表页做轻量判定；
        - 仍会执行“多段 JSON/尾部残留”的自动修复，避免缓存损坏阻断启动。
        """
        cache_dir = self._get_graph_cache_dir()
        cache_file = cache_dir / f"{graph_id}.json"
        if not cache_file.exists():
            return None
        payload = self._read_cache_payload_dict(cache_file, graph_id=graph_id)
        if not isinstance(payload, dict):
            return None
        return payload

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
        self._atomic_write_cache_payload(cache_file, payload)
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

    def _read_cache_payload_dict(self, cache_file: Path, *, graph_id: str) -> Optional[dict]:
        """读取 cache_file 中的 payload（dict）。

        兼容策略（无 try/except）：
        - 空文件：视为无缓存；
        - 拼接/尾部残留：提取最后一个完整 JSON 容器并“原子重写”为单段 JSON；
        - 不完整/结构无法闭合：删除该文件并视为无缓存（避免阻断启动）。
        """
        cache_text = cache_file.read_text(encoding="utf-8")
        if not cache_text.strip():
            return None

        container_text, needs_repair = _extract_last_complete_json_container_text(cache_text)
        if not container_text:
            log_warn("[缓存][图] 持久化缓存损坏（无法定位完整 JSON），已删除：{}", graph_id)
            cache_file.unlink()
            return None

        payload = json.loads(container_text)
        if not isinstance(payload, dict):
            log_warn("[缓存][图] 持久化缓存格式异常（非 dict），已删除：{}", graph_id)
            cache_file.unlink()
            return None

        if needs_repair:
            log_warn("[缓存][图] 持久化缓存检测到拼接/残留，已自动修复：{}", graph_id)
            self._atomic_write_cache_payload(cache_file, payload)
        return payload

    @staticmethod
    def _atomic_write_cache_payload(target_file: Path, payload: dict) -> None:
        """原子写入 JSON（使用唯一临时文件名，降低并发写入相互覆盖/交错的概率）。"""
        target_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = target_file.with_name(
            f"{target_file.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        tmp_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_file, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        tmp_file.replace(target_file)

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
        - 复合节点库：位于任一资源根目录下的 `复合节点库/`
        """
        return compute_node_defs_fingerprint(self.workspace_path)

    @staticmethod
    def _is_result_data_structurally_consistent(result_data: Dict) -> bool:
        """
        校验持久化缓存中的 result_data 是否结构自洽（节点/边引用与端口名匹配）。

        说明：
        - 该检查用于避免“旧版本节点定义/端口名变更后仍命中持久化缓存”导致 UI/校验与实际不一致；
        - 检查范围保持轻量：只验证 nodes/edges 的存在性与端口名集合匹配，不做更深的语义校验。
        """
        graph_data = result_data.get("data")
        if not isinstance(graph_data, dict):
            return False
        nodes = graph_data.get("nodes")
        edges = graph_data.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return False

        input_ports_by_node: Dict[str, set[str]] = {}
        output_ports_by_node: Dict[str, set[str]] = {}

        for node in nodes:
            if not isinstance(node, dict):
                return False
            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id:
                return False
            raw_inputs = node.get("inputs") or []
            raw_outputs = node.get("outputs") or []
            if not isinstance(raw_inputs, list) or not isinstance(raw_outputs, list):
                return False
            input_ports_by_node[node_id] = {p for p in raw_inputs if isinstance(p, str)}
            output_ports_by_node[node_id] = {p for p in raw_outputs if isinstance(p, str)}

        node_ids = set(input_ports_by_node.keys())

        for edge in edges:
            if not isinstance(edge, dict):
                return False
            src_node = edge.get("src_node")
            dst_node = edge.get("dst_node")
            src_port = edge.get("src_port")
            dst_port = edge.get("dst_port")
            if not isinstance(src_node, str) or not isinstance(dst_node, str):
                return False
            if not isinstance(src_port, str) or not isinstance(dst_port, str):
                return False
            if src_node not in node_ids or dst_node not in node_ids:
                return False

            if src_port != FLOW_PORT_PLACEHOLDER:
                valid_outputs = output_ports_by_node.get(src_node, set())
                is_flow_alias = src_port in FLOW_OUT_PORT_NAMES or src_port in FLOW_BRANCH_PORT_ALIASES
                if src_port not in valid_outputs and not is_flow_alias:
                    return False

            if dst_port != FLOW_PORT_PLACEHOLDER:
                valid_inputs = input_ports_by_node.get(dst_node, set())
                is_flow_alias = dst_port in FLOW_IN_PORT_NAMES
                if dst_port not in valid_inputs and not is_flow_alias:
                    return False

        return True


