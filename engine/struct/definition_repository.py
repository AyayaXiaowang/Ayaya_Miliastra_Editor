from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from engine.type_registry import (
    TYPE_COMPONENT_ID,
    TYPE_COMPONENT_ID_LIST,
    TYPE_CONFIG_ID,
    TYPE_CONFIG_ID_LIST,
    TYPE_GUID,
    TYPE_GUID_LIST,
)
from engine.utils.id_digits import is_digits_1_to_10


@dataclass(frozen=True)
class StructFieldDefinition:
    """结构体字段定义（只读视图）。"""

    field_name: str
    param_type: str
    default_value: Dict[str, Any] | None = None
    length: int | None = None


class StructDefinitionRepository:
    """基于 DefinitionSchemaView 的结构体定义只读仓库（结构归一化 + 只读视图）。

    职责：
    - 统一从代码级 Schema 视图加载 `{struct_id: payload}` 映射；
    - 提供按 ID / 显示名解析结构体的轻量接口；
    - 提供结构体字段集合视图，供解析器 / UI / 校验规则复用；
    - 在仓库边界处做**结构归一化**：兼容旧/新两种结构体 payload 形态，输出统一的
      `{type: "Struct", struct_type, struct_name, fields}` 结构，避免调用侧到处读取旧字段。

    备注：
    - 旧结构体 schema（常见于局内存档结构体）使用字段：`struct_ype/struct_name/value/key/lenth`；
    - 新结构体 schema 使用字段：`struct_type/struct_name/fields/field_name/length`。
    - 仓库将旧 schema 归一化为新 schema 的字段名，但不会修改 assets 中的源文件。
    """

    # 归一化后的结构体定义 payload（STRUCT_PAYLOAD）允许的顶层字段集合（严格）
    # 注意：结构体定义只保留 `struct_name` 作为唯一名称字段；不再支持额外的 `name`。
    _ALLOWED_PAYLOAD_KEYS: Set[str] = {"type", "struct_type", "struct_name", "fields"}
    # 归一化后的字段定义允许字段集合（严格）
    _ALLOWED_FIELD_KEYS: Set[str] = {"field_name", "param_type", "default_value", "length"}
    _ID_TYPES: Set[str] = {TYPE_GUID, TYPE_CONFIG_ID, TYPE_COMPONENT_ID}
    _ID_LIST_TYPES: Set[str] = {TYPE_GUID_LIST, TYPE_CONFIG_ID_LIST, TYPE_COMPONENT_ID_LIST}

    def __init__(self) -> None:
        # 延迟导入 DefinitionSchemaView，避免在引擎初始化早期引入
        # `engine.resources` → `GlobalResourceView` → `engine.struct` 的循环依赖。
        module = import_module("engine.resources.definition_schema_view")
        get_schema_view = getattr(module, "get_default_definition_schema_view")
        self._schema_view = get_schema_view()
        self._all_payloads: Dict[str, Dict[str, Any]] | None = None
        self._errors_by_id: Dict[str, str] | None = None
        self._id_by_name: Dict[str, str] | None = None
        self._fields_by_id: Dict[str, List[StructFieldDefinition]] | None = None

    def invalidate_cache(self) -> None:
        """使仓库内派生缓存失效。"""
        self._all_payloads = None
        self._errors_by_id = None
        self._id_by_name = None
        self._fields_by_id = None

    @staticmethod
    def _safe_str(value: object) -> str:
        return str(value).strip() if isinstance(value, str) else ""

    def _try_validate_normalized_payload(
        self,
        struct_id: str,
        payload: Mapping[str, Any],
    ) -> Tuple[bool, str]:
        """校验“归一化后的结构体 payload”。返回 (is_valid, error_message)。"""

        if not isinstance(payload, Mapping):
            return False, f"结构体定义 payload 非 dict: {struct_id}"

        payload_keys = set(payload.keys())
        unknown = sorted(k for k in payload_keys if k not in self._ALLOWED_PAYLOAD_KEYS)
        if unknown:
            return False, f"结构体定义包含未知字段：{struct_id} -> {unknown}"

        type_value = payload.get("type")
        if type_value != "Struct":
            return (
                False,
                f"结构体定义.type 必须为 'Struct'：{struct_id} -> {type_value!r}",
            )

        struct_type = payload.get("struct_type")
        if not isinstance(struct_type, str) or not struct_type.strip():
            return False, f"结构体定义.struct_type 必须为非空字符串：{struct_id}"

        struct_name = payload.get("struct_name")
        if not isinstance(struct_name, str) or not struct_name.strip():
            return False, f"结构体定义.struct_name 必须为非空字符串：{struct_id}"

        fields_value = payload.get("fields")
        if not isinstance(fields_value, Sequence) or isinstance(fields_value, (str, bytes)):
            return False, f"结构体定义.fields 必须为列表：{struct_id}"

        for index, entry in enumerate(fields_value):
            if not isinstance(entry, Mapping):
                return False, f"结构体定义.fields[{index}] 不是 dict：{struct_id}"
            entry_keys = set(entry.keys())
            unknown_field = sorted(k for k in entry_keys if k not in self._ALLOWED_FIELD_KEYS)
            if unknown_field:
                return (
                    False,
                    f"结构体定义字段包含未知字段：{struct_id}.fields[{index}] -> {unknown_field}",
                )

            field_name = entry.get("field_name")
            if not isinstance(field_name, str) or not field_name.strip():
                return (
                    False,
                    f"结构体字段.field_name 必须为非空字符串：{struct_id}.fields[{index}]",
                )

            param_type = entry.get("param_type")
            if not isinstance(param_type, str) or not param_type.strip():
                return (
                    False,
                    f"结构体字段.param_type 必须为非空字符串：{struct_id}.fields[{index}]",
                )

            length = entry.get("length")
            if length is not None and not isinstance(length, int):
                return (
                    False,
                    f"结构体字段.length 必须为 int 或省略：{struct_id}.fields[{index}] -> {length!r}",
                )

            default_value = entry.get("default_value")
            if default_value is not None and not isinstance(default_value, Mapping):
                return (
                    False,
                    f"结构体字段.default_value 必须为 dict 或省略：{struct_id}.fields[{index}]",
                )

            # ===== ID 类型默认值强约束 =====
            #
            # 约定：GUID/配置ID/元件ID 在引擎内是数字 ID（可用字符串包裹数字）形式的标识，
            # 因此结构体字段默认值若声明为这些类型，必须满足“1~10 位纯数字”。
            if default_value is not None:
                normalized_param_type = str(param_type).strip()
                if (normalized_param_type in self._ID_TYPES) or (
                    normalized_param_type in self._ID_LIST_TYPES
                ):
                    dv_type = default_value.get("param_type")
                    if not isinstance(dv_type, str) or dv_type.strip() != normalized_param_type:
                        return (
                            False,
                            f"结构体字段.default_value.param_type 必须与字段类型一致："
                            f"{struct_id}.fields[{index}] -> {dv_type!r}（期望 {normalized_param_type!r}）",
                        )

                    if "value" not in default_value:
                        return (
                            False,
                            f"结构体字段.default_value 缺少 value：{struct_id}.fields[{index}]",
                        )

                    raw_value = default_value.get("value")
                    if normalized_param_type in self._ID_TYPES:
                        if not is_digits_1_to_10(raw_value):
                            return (
                                False,
                                f"结构体字段默认值必须为 1~10 位纯数字："
                                f"{struct_id}.fields[{index}] ({normalized_param_type}) -> {raw_value!r}",
                            )
                    if normalized_param_type in self._ID_LIST_TYPES:
                        if not isinstance(raw_value, Sequence) or isinstance(
                            raw_value, (str, bytes)
                        ):
                            return (
                                False,
                                f"结构体字段默认值必须为列表："
                                f"{struct_id}.fields[{index}] ({normalized_param_type}) -> {raw_value!r}",
                            )
                        invalid_items = [x for x in list(raw_value) if not is_digits_1_to_10(x)]
                        if invalid_items:
                            preview = ", ".join(repr(x) for x in invalid_items[:6])
                            more = "..." if len(invalid_items) > 6 else ""
                            return (
                                False,
                                f"结构体字段默认值列表元素必须为 1~10 位纯数字："
                                f"{struct_id}.fields[{index}] ({normalized_param_type}) -> {preview}{more}",
                            )

        return True, ""

    def _try_normalize_payload(
        self,
        struct_id: str,
        payload: Mapping[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """将旧/新 schema 结构体 payload 归一化为统一结构。"""

        def normalize_text(value: object) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value.strip()
            return str(value).strip()

        # ---- 新 schema：{type: "Struct", struct_type, struct_name, fields: [{field_name, ...}]} ----
        type_value = payload.get("type")
        if type_value == "Struct" and isinstance(payload.get("fields"), Sequence):
            normalized = dict(payload)
            is_valid, error_message = self._try_validate_normalized_payload(
                struct_id,
                normalized,
            )
            if not is_valid:
                return None, error_message
            return normalized, ""

        # ---- 旧 schema：{type: "结构体", struct_ype, struct_name, value: [{key, param_type, lenth?, value?}]} ----
        value_entries = payload.get("value")
        if isinstance(value_entries, Sequence) and not isinstance(value_entries, (str, bytes)):
            struct_type_text = normalize_text(payload.get("struct_type") or payload.get("struct_ype"))
            struct_name_text = normalize_text(payload.get("struct_name"))
            if not struct_name_text:
                return None, f"结构体定义.struct_name 不能为空：{struct_id}"

            fields: List[Dict[str, Any]] = []
            for index, entry in enumerate(value_entries):
                if not isinstance(entry, Mapping):
                    return None, f"结构体定义.value[{index}] 不是 dict：{struct_id}"

                field_name = normalize_text(entry.get("field_name") or entry.get("key"))
                param_type = normalize_text(entry.get("param_type"))
                if not field_name:
                    return None, f"结构体字段名为空：{struct_id}.value[{index}]"
                if not param_type:
                    return None, f"结构体字段 param_type 为空：{struct_id}.{field_name}"

                length_value = entry.get("length")
                if not isinstance(length_value, int):
                    length_value = entry.get("lenth")
                length = int(length_value) if isinstance(length_value, int) else None

                default_value_raw = entry.get("default_value")
                # 旧 schema 中可能使用 "value" 存储默认值（局内存档结构体通常不允许）
                if default_value_raw is None and isinstance(entry.get("value"), Mapping):
                    default_value_raw = entry.get("value")
                default_value = dict(default_value_raw) if isinstance(default_value_raw, Mapping) else None

                field_payload: Dict[str, Any] = {
                    "field_name": field_name,
                    "param_type": param_type,
                }
                if default_value is not None:
                    field_payload["default_value"] = default_value
                if length is not None:
                    field_payload["length"] = length
                fields.append(field_payload)

            normalized_payload: Dict[str, Any] = {
                "type": "Struct",
                "struct_type": struct_type_text,
                "struct_name": struct_name_text,
                "fields": fields,
            }

            is_valid, error_message = self._try_validate_normalized_payload(
                struct_id,
                normalized_payload,
            )
            if not is_valid:
                return None, error_message
            return normalized_payload, ""

        return None, f"无法识别结构体 payload schema：{struct_id}"

    def _materialize_payloads(self) -> None:
        if self._all_payloads is not None:
            return
        raw_struct_definitions = self._schema_view.get_all_struct_definitions() or {}
        payloads: Dict[str, Dict[str, Any]] = {}
        errors_by_id: Dict[str, str] = {}
        for key, payload in raw_struct_definitions.items():
            if not isinstance(key, str):
                continue
            struct_id = key.strip()
            if not struct_id:
                continue
            if not isinstance(payload, Mapping):
                errors_by_id[struct_id] = f"结构体定义 payload 非 dict: {struct_id}"
                continue

            normalized_payload, error_message = self._try_normalize_payload(struct_id, payload)
            if normalized_payload is None:
                errors_by_id[struct_id] = error_message or f"结构体定义无效：{struct_id}"
                continue

            payloads[struct_id] = dict(normalized_payload)
        self._all_payloads = payloads
        self._errors_by_id = errors_by_id

    def get_errors(self) -> Dict[str, str]:
        """返回 {struct_id: error_message}（仅包含无法归一化/校验失败的定义）。"""
        self._materialize_payloads()
        if self._errors_by_id is None:
            return {}
        return dict(self._errors_by_id)

    def get_all_payloads(self) -> Dict[str, Dict[str, Any]]:
        """返回 {struct_id: payload} 的浅拷贝视图（payload 为 dict 副本）。"""
        self._materialize_payloads()
        if self._all_payloads is None:
            return {}
        return {struct_id: dict(payload) for struct_id, payload in self._all_payloads.items()}

    def get_payload(self, struct_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取单个结构体定义 payload 的副本，未找到时返回 None。"""
        text = str(struct_id or "").strip()
        if not text:
            return None
        payload = self.get_all_payloads().get(text)
        if payload is None:
            return None
        return dict(payload)

    def _ensure_name_index(self) -> None:
        if self._id_by_name is not None:
            return
        self._id_by_name = {}
        for struct_id, payload in self.get_all_payloads().items():
            name_value = payload.get("struct_name")
            if not isinstance(name_value, str):
                continue
            text = name_value.strip()
            if not text:
                continue
            # 不在仓库内部抛错，避免影响上层 UI/校验流程；重复由调用侧根据 get_errors 处理。
            if text in self._id_by_name:
                continue
            self._id_by_name[text] = struct_id

    def resolve_id_by_name(self, struct_name: str) -> str:
        """根据显示名称解析结构体 ID，解析失败返回空字符串。"""
        text = str(struct_name or "").strip()
        if not text:
            return ""
        self._ensure_name_index()
        if self._id_by_name is None:
            return ""
        struct_id = self._id_by_name.get(text)
        if struct_id is None:
            return ""
        return struct_id

    def _ensure_fields_index(self) -> None:
        if self._fields_by_id is not None:
            return
        fields_by_id: Dict[str, List[StructFieldDefinition]] = {}
        for struct_id, payload in self.get_all_payloads().items():
            fields_value = payload.get("fields") or []
            if not isinstance(fields_value, Sequence) or isinstance(fields_value, (str, bytes)):
                fields_by_id[struct_id] = []
                continue
            fields: List[StructFieldDefinition] = []
            for entry in fields_value:
                if not isinstance(entry, Mapping):
                    continue
                field_name = self._safe_str(entry.get("field_name"))
                param_type = self._safe_str(entry.get("param_type"))
                if not field_name or not param_type:
                    continue
                default_value_raw = entry.get("default_value")
                default_value = dict(default_value_raw) if isinstance(default_value_raw, Mapping) else None
                length_value = entry.get("length")
                length = int(length_value) if isinstance(length_value, int) else None
                fields.append(
                    StructFieldDefinition(
                        field_name=field_name,
                        param_type=param_type,
                        default_value=default_value,
                        length=length,
                    )
                )
            fields_by_id[struct_id] = fields
        self._fields_by_id = fields_by_id

    def get_fields(self, struct_id: str) -> List[StructFieldDefinition]:
        """返回结构体字段定义列表（保持定义顺序），未找到返回空列表。"""
        text = str(struct_id or "").strip()
        if not text:
            return []
        self._ensure_fields_index()
        if self._fields_by_id is None:
            return []
        return list(self._fields_by_id.get(text) or [])

    def get_field_names(self, struct_id: str) -> List[str]:
        return [field.field_name for field in self.get_fields(struct_id)]

    def get_struct_type(self, struct_id: str) -> str:
        payload = self.get_payload(struct_id) or {}
        raw = payload.get("struct_type")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return ""

    def is_basic(self, struct_id: str) -> bool:
        return self.get_struct_type(struct_id) == "basic"


_default_repo: StructDefinitionRepository | None = None


def get_default_struct_repository() -> StructDefinitionRepository:
    """获取进程级默认的结构体定义仓库实例。"""
    global _default_repo
    if _default_repo is None:
        _default_repo = StructDefinitionRepository()
    return _default_repo


def invalidate_default_struct_repository_cache() -> None:
    """使进程级默认结构体仓库的二级缓存失效。"""
    global _default_repo
    if _default_repo is not None:
        _default_repo.invalidate_cache()


