from __future__ import annotations

from typing import Any, Dict, Optional, Set

from importlib import import_module


class SignalDefinitionRepository:
    """基于 DefinitionSchemaView 的信号定义只读仓库。

    职责：
    - 统一从代码级 Schema 视图加载 `{signal_id: payload}` 映射；
    - 提供按 ID / 名称查找信号的轻量接口；
    - 提供“每个信号允许的参数名集合”视图，供代码规则与图规则复用。
    """

    def __init__(self) -> None:
        # 延迟导入 DefinitionSchemaView，避免在引擎初始化早期引入
        # `engine.resources` → `GlobalResourceView` → `engine.signal` 的循环依赖。
        module = import_module("engine.resources.definition_schema_view")
        get_schema_view = getattr(module, "get_default_definition_schema_view")
        self._schema_view = get_schema_view()
        self._all_payloads: Dict[str, Dict[str, Any]] | None = None
        self._id_by_name: Dict[str, str] | None = None
        self._allowed_params_by_id: Dict[str, Set[str]] | None = None

    def get_all_payloads(self) -> Dict[str, Dict[str, Any]]:
        """返回 {signal_id: payload} 的浅拷贝视图（payload 为 dict 副本）。"""
        if self._all_payloads is None:
            raw = self._schema_view.get_all_signal_definitions()
            payloads: Dict[str, Dict[str, Any]] = {}
            for key, payload in raw.items():
                if not isinstance(payload, dict):
                    continue
                signal_id = str(key)
                payloads[signal_id] = dict(payload)
            self._all_payloads = payloads
        return dict(self._all_payloads)

    def get_payload(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取单个信号定义 payload 的副本，未找到时返回 None。"""
        if not signal_id:
            return None
        all_payloads = self.get_all_payloads()
        payload = all_payloads.get(str(signal_id))
        if payload is None:
            return None
        return dict(payload)

    def _ensure_name_index(self) -> None:
        if self._id_by_name is not None:
            return
        self._id_by_name = {}
        for signal_id, payload in self.get_all_payloads().items():
            name_value = payload.get("signal_name")
            if not isinstance(name_value, str):
                continue
            text = name_value.strip()
            if not text:
                continue
            # 仅在首次出现时记录，避免同名信号产生不确定行为
            if text not in self._id_by_name:
                self._id_by_name[text] = signal_id

    def resolve_id_by_name(self, signal_name: str) -> str:
        """根据显示名称解析信号 ID，解析失败返回空字符串。"""
        text = str(signal_name).strip()
        if not text:
            return ""
        self._ensure_name_index()
        if self._id_by_name is None:
            return ""
        signal_id = self._id_by_name.get(text)
        if signal_id is None:
            return ""
        return signal_id

    def get_allowed_param_names_by_id(self) -> Dict[str, Set[str]]:
        """返回 {signal_id: {param_name,...}} 视图，用于参数名合法性校验。"""
        if self._allowed_params_by_id is None:
            allowed: Dict[str, Set[str]] = {}
            for signal_id, payload in self.get_all_payloads().items():
                params_field = payload.get("parameters") or []
                names: Set[str] = set()
                if isinstance(params_field, list):
                    for entry in params_field:
                        if not isinstance(entry, dict):
                            continue
                        name_value = entry.get("name")
                        if not isinstance(name_value, str):
                            continue
                        text = name_value.strip()
                        if text:
                            names.add(text)
                allowed[signal_id] = names
            self._allowed_params_by_id = allowed
        # 返回浅拷贝，防止调用方意外修改内部缓存
        return {signal_id: set(names) for signal_id, names in self._allowed_params_by_id.items()}


_default_repo: SignalDefinitionRepository | None = None


def get_default_signal_repository() -> SignalDefinitionRepository:
    """获取进程级默认的信号定义仓库实例。"""
    global _default_repo
    if _default_repo is None:
        _default_repo = SignalDefinitionRepository()
    return _default_repo


