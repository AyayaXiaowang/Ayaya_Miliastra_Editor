# -*- coding: utf-8 -*-
"""
缓存模块
提供 OCR 和模板匹配的缓存机制
"""

import hashlib
import numpy as np
from collections import OrderedDict
from typing import Any, Tuple
import os
from contextlib import contextmanager
from PIL import Image
from engine.configs.settings import settings


class _LruCache:
    """简单的 LRU 缓存实现"""
    def __init__(self, capacity: int) -> None:
        self.capacity = int(capacity)
        self._store: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any:
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        if len(self._store) > self.capacity:
            self._store.popitem(last=False)


def create_lru_cache(capacity: int) -> _LruCache:
    """创建指定容量的 LRU 缓存，供需要轻量缓存的数据结构复用。"""
    return _LruCache(int(capacity))


def _hash_ndarray(arr: np.ndarray) -> str:
    """计算 numpy 数组的哈希值"""
    h = hashlib.blake2b(digest_size=16)
    # 将形状与 dtype 纳入哈希，避免不同视图但同字节序导致冲突
    shape_repr = (str(arr.shape) + "|" + str(arr.dtype)).encode("utf-8")
    h.update(shape_repr)
    h.update(np.ascontiguousarray(arr).tobytes())
    return h.hexdigest()


def _resolve_cache_capacity(setting_name: str, default_value: int) -> int:
    raw_value = getattr(settings, setting_name, None)
    if isinstance(raw_value, int):
        candidate = raw_value
    elif isinstance(raw_value, str) and raw_value.isdigit():
        candidate = int(raw_value)
    else:
        candidate = default_value
    if candidate <= 0:
        return default_value
    return candidate


# OCR 与模板匹配缓存（进程内 LRU）
_OCR_RESULT_CACHE = _LruCache(capacity=_resolve_cache_capacity("AUTOMATION_OCR_CACHE_CAPACITY", 512))
_TM_RESULT_CACHE = _LruCache(capacity=_resolve_cache_capacity("AUTOMATION_TEMPLATE_MATCH_CACHE_CAPACITY", 512))
_TEMPLATE_INFO_CACHE = _LruCache(capacity=_resolve_cache_capacity("AUTOMATION_TEMPLATE_INFO_CACHE_CAPACITY", 256))  # key = f"{path}|{mtime}|{size}", val=(digest_hex, (w,h), basename)


class _CaptureState:
    """封装截图与识别相关的全局状态，便于测试隔离与状态重置"""
    def __init__(self) -> None:
        self.enforce_graph_roi: bool = False
    
    def reset(self) -> None:
        """重置所有状态（用于测试隔离）"""
        self.enforce_graph_roi = False


_CAPTURE_STATE = _CaptureState()


def set_enforce_graph_roi(enable: bool) -> None:
    """开启/关闭：将 OCR/模板匹配限制到"节点图布置区域"""
    _CAPTURE_STATE.enforce_graph_roi = bool(enable)


def get_enforce_graph_roi() -> bool:
    """获取当前的强制区域限制状态"""
    return _CAPTURE_STATE.enforce_graph_roi


def reset_capture_state() -> None:
    """重置所有截图相关全局状态（用于测试环境隔离）"""
    _CAPTURE_STATE.reset()


@contextmanager
def enforce_graph_roi_context():
    """上下文管理器：确保进入时启用强制 ROI，退出时恢复原状态（异常安全）。
    
    使用示例：
        with enforce_graph_roi_context():
            # 此区域内的 OCR/模板匹配会限制到节点图区域
            pass
        # 退出后自动恢复原始状态
    """
    previous_state = _CAPTURE_STATE.enforce_graph_roi
    _CAPTURE_STATE.enforce_graph_roi = True
    try:
        yield
    finally:
        _CAPTURE_STATE.enforce_graph_roi = previous_state


def get_ocr_cache() -> _LruCache:
    """获取 OCR 缓存对象"""
    return _OCR_RESULT_CACHE


def get_template_match_cache() -> _LruCache:
    """获取模板匹配缓存对象"""
    return _TM_RESULT_CACHE


def get_template_info_cache() -> _LruCache:
    """获取模板信息缓存对象"""
    return _TEMPLATE_INFO_CACHE


def get_template_info_cached(template_path: str) -> Tuple[str, Tuple[int, int], str]:
    """获取模板图片的缓存信息（内容哈希、尺寸、文件名）
    
    Args:
        template_path: 模板图片路径
        
    Returns:
        (digest_hex, (w, h), basename)
    """
    st = os.stat(template_path)
    cache_key = f"{template_path}|{int(st.st_mtime)}|{int(st.st_size)}"
    cached = _TEMPLATE_INFO_CACHE.get(cache_key)
    if cached is not None:
        return cached  # (digest_hex, (w,h), basename)
    with open(template_path, 'rb') as f:
        data = f.read()
    digest_hex = hashlib.blake2b(data, digest_size=16).hexdigest()
    img = Image.open(template_path)
    w, h = img.size
    basename = os.path.basename(str(template_path))
    value = (digest_hex, (int(w), int(h)), basename)
    _TEMPLATE_INFO_CACHE.set(cache_key, value)
    return value

