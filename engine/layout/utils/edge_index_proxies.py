"""
边索引 Copy-On-Write 代理

为跨块复制场景提供延迟克隆的边索引结构，避免在读取阶段产生额外拷贝。
"""

from __future__ import annotations

from collections.abc import MutableMapping, MutableSequence
from typing import Any, Dict, List, Set


class EdgeListProxy(MutableSequence):
    """List 代理：按需在首次写入时克隆底层列表。"""

    def __init__(self, owner: "CopyOnWriteEdgeIndex", key: str, backing: List[Any], shared: bool):
        self._owner = owner
        self._key = key
        self._backing = backing
        self._shared = shared

    def _ensure_local(self) -> List[Any]:
        if self._shared:
            self._backing = self._owner._clone_entry(self._key, self._backing)
            self._shared = False
        return self._backing

    def bind_backing(self, backing: List[Any]) -> None:
        self._backing = backing
        self._shared = False

    def __len__(self) -> int:
        return len(self._backing)

    def __getitem__(self, index):
        return self._backing[index]

    def __setitem__(self, index, value) -> None:
        self._ensure_local()[index] = value

    def __delitem__(self, index) -> None:
        del self._ensure_local()[index]

    def insert(self, index: int, value) -> None:
        self._ensure_local().insert(index, value)

    def __iter__(self):
        return iter(self._backing)

    def __repr__(self) -> str:
        return repr(list(self._backing))


class CopyOnWriteEdgeIndex(MutableMapping[str, List[Any]]):
    """延迟克隆的边索引：仅在写入或读取后可能修改时才复制列表。"""

    def __init__(self, base_index: Dict[str, List[Any]]):
        self._base_index = base_index
        self._cache: Dict[str, List[Any]] = {}
        self._proxy_cache: Dict[str, EdgeListProxy] = {}

    def _clone_entry(self, key: str, backing: List[Any]) -> List[Any]:
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        cloned = list(backing)
        self._cache[key] = cloned
        proxy = self._proxy_cache.get(key)
        if proxy is not None:
            proxy.bind_backing(cloned)
        return cloned

    def _get_proxy(self, key: str) -> EdgeListProxy:
        proxy = self._proxy_cache.get(key)
        if proxy is not None:
            return proxy
        if key in self._cache:
            backing = self._cache[key]
            shared = False
        else:
            if key not in self._base_index:
                raise KeyError(key)
            backing = self._base_index[key]
            shared = True
        proxy = EdgeListProxy(self, key, backing, shared)
        self._proxy_cache[key] = proxy
        return proxy

    def __getitem__(self, key: str) -> List[Any]:
        return self._get_proxy(key)

    def __setitem__(self, key: str, value: List[Any]) -> None:
        copied = list(value)
        self._cache[key] = copied
        self._proxy_cache[key] = EdgeListProxy(self, key, copied, shared=False)

    def __delitem__(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]
        elif key in self._base_index:
            self._cache[key] = []
        else:
            raise KeyError(key)
        self._proxy_cache.pop(key, None)

    def __iter__(self):
        seen: Set[str] = set()
        for key in self._cache:
            seen.add(key)
            yield key
        for key in self._base_index:
            if key not in seen:
                yield key

    def __len__(self) -> int:
        return len(set(self._base_index.keys()) | set(self._cache.keys()))

    def get(self, key: str, default=None):  # type: ignore[override]
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: str, default=None):  # type: ignore[override]
        if key in self:
            return self[key]
        if default is None:
            default = []
        self[key] = list(default)
        return self[key]

    def materialize(self) -> Dict[str, List[Any]]:
        combined = dict(self._base_index)
        combined.update(self._cache)
        return combined


