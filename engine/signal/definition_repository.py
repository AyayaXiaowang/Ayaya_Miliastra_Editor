from __future__ import annotations

from typing import Any, Dict, Optional, Set, Tuple

from importlib import import_module

from engine.type_registry import VARIABLE_TYPES, is_dict_type_name


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
        self._errors_by_id: Dict[str, str] | None = None
        self._id_by_name: Dict[str, str] | None = None
        self._allowed_params_by_id: Dict[str, Set[str]] | None = None

    def invalidate_cache(self) -> None:
        """使仓库内派生缓存失效。

        注意：
        - 该方法不会替换底层 schema view 对象；
        - 仅清空本仓库基于 schema 聚合得到的二级缓存（payload/name_index/allowed_params）。
        """
        self._all_payloads = None
        self._errors_by_id = None
        self._id_by_name = None
        self._allowed_params_by_id = None

    @staticmethod
    def _safe_text(value: object) -> str:
        return str(value).strip() if isinstance(value, str) else ""

    def _try_validate_signal_payload(
        self,
        *,
        signal_id: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, f"信号定义 payload 非 dict：{signal_id}"

        payload_signal_id = self._safe_text(payload.get("signal_id")) or signal_id
        if payload_signal_id != signal_id:
            return (
                False,
                f"信号定义 payload.signal_id 与 SIGNAL_ID 不一致：{signal_id} -> {payload_signal_id!r}",
            )

        signal_name = self._safe_text(payload.get("signal_name"))
        if not signal_name:
            return False, f"信号定义缺少 signal_name：{signal_id}"

        parameters = payload.get("parameters") or []
        if not isinstance(parameters, list):
            return False, f"信号定义 parameters 必须为列表：{signal_id}"

        seen_param_names: Set[str] = set()
        for index, entry in enumerate(parameters):
            if not isinstance(entry, dict):
                return False, f"信号参数条目不是 dict：{signal_id}.parameters[{index}]"
            name_text = self._safe_text(entry.get("name"))
            if not name_text:
                return False, f"信号参数缺少 name：{signal_id}.parameters[{index}]"
            if name_text in seen_param_names:
                return False, f"信号参数 name 重复：{signal_id} -> {name_text}"
            seen_param_names.add(name_text)

            type_text = self._safe_text(entry.get("parameter_type"))
            if not type_text:
                return False, f"信号参数缺少 parameter_type：{signal_id}.parameters[{index}]"
            if is_dict_type_name(type_text):
                return (
                    False,
                    f"信号参数类型严禁使用字典：{signal_id}.parameters[{index}] -> {type_text!r}",
                )
            if type_text not in set(VARIABLE_TYPES):
                return (
                    False,
                    f"信号参数类型不受支持：{signal_id}.parameters[{index}] -> {type_text!r}",
                )

        return True, ""

    def get_all_payloads(self) -> Dict[str, Dict[str, Any]]:
        """返回 {signal_id: payload} 的浅拷贝视图（payload 为 dict 副本）。"""
        if self._all_payloads is None:
            raw = self._schema_view.get_all_signal_definitions()
            payloads: Dict[str, Dict[str, Any]] = {}
            errors_by_id: Dict[str, str] = {}
            for key, payload in raw.items():
                if not isinstance(payload, dict):
                    signal_id = str(key).strip()
                    if signal_id:
                        errors_by_id[signal_id] = f"信号定义 payload 非 dict：{signal_id}"
                    continue
                signal_id = str(key).strip()
                if not signal_id:
                    continue
                copied = dict(payload)
                is_valid, error_message = self._try_validate_signal_payload(
                    signal_id=signal_id,
                    payload=copied,
                )
                if not is_valid:
                    errors_by_id[signal_id] = error_message or f"信号定义无效：{signal_id}"
                    continue
                payloads[signal_id] = copied
            self._all_payloads = payloads
            self._errors_by_id = errors_by_id
        return dict(self._all_payloads)

    def get_payload(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取单个信号定义 payload 的副本，未找到时返回 None。"""
        key = str(signal_id or "").strip()
        if not key:
            return None
        all_payloads = self.get_all_payloads()
        payload = all_payloads.get(key)
        # 兼容：允许用“去掉 __<package_id> 后缀的 ID 前缀”反查到某个真实 signal_id，
        # 以便在校验层给出“误用 ID”而非“未知信号”的更友好提示。
        # 例如：signal_all_supported_types_example → signal_all_supported_types_example__测试基础内容
        if payload is None and "__" not in key:
            prefix = f"{key}__"
            candidates = [
                sid
                for sid in all_payloads.keys()
                if isinstance(sid, str) and sid.startswith(prefix)
            ]
            if candidates:
                candidates.sort(key=lambda x: str(x).casefold())
                payload = all_payloads.get(candidates[0])
        if payload is None:
            return None
        return dict(payload)

    def get_errors(self) -> Dict[str, str]:
        """返回 {signal_id: error_message}（仅包含校验失败的信号定义）。"""
        _ = self.get_all_payloads()
        if self._errors_by_id is None:
            return {}
        return dict(self._errors_by_id)

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


def invalidate_default_signal_repository_cache() -> None:
    """使进程级默认信号仓库的二级缓存失效。"""
    global _default_repo
    if _default_repo is not None:
        _default_repo.invalidate_cache()


