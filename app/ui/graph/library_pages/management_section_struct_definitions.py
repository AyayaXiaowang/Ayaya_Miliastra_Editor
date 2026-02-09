from __future__ import annotations

from .management_sections_base import *
from engine.configs.specialized.node_graph_configs import (
    STRUCT_TYPE_BASIC,
    STRUCT_TYPE_INGAME_SAVE,
    InGameSaveStructDefinition,
)

class StructDefinitionSection(BaseManagementSection):
    """结构体定义管理 Section（对应资源类型 `STRUCT_DEFINITION`）。

    新设计约定：
    - 数据来源：当前视图绑定的 `ResourceManager` 索引（目录即存档模式：共享根 + 当前项目存档根）。
      - `<共享资源>` 视图下 `ResourceManager` 仅扫描共享根目录；
      - 具体存档视图下 `ResourceManager` 扫描（共享根 + 当前存档根目录）。
    - 展示规则：
      - 仅展示当前视图作用域内的结构体定义（避免“共享视图混入其他存档结构体”导致归属与徽章失真）；
      - 列表展示名以 `struct_name` 为主，但当 `struct_name != struct_id` 时会附带 `struct_id` 以消除同名歧义。
    - 结构体定义的增删改需在 Python 模块中完成，本 Section 在当前版本中仅提供浏览与归属管理。
    """

    section_key = "struct_definitions"
    tree_label = "🧬 基础结构体定义"
    type_name = "基础结构体"
    struct_type: str = STRUCT_TYPE_BASIC

    @staticmethod
    def _invalidate_struct_records_cache(resource_manager: ResourceManager) -> None:
        """兼容入口：用于在资源库刷新时失效结构体记录缓存。

        当前版本结构体定义列表不在 UI 层做额外缓存；保留该方法以兼容旧调用方。
        """
        _ = resource_manager
        return

    def _load_struct_records(
        self,
        resource_manager: ResourceManager,
    ) -> List[Tuple[str, Dict[str, object]]]:
        """读取当前 ResourceManager 可见范围内的结构体定义记录（按 struct_id 排序）。

        注意：
        - 本方法不做结构体类型过滤；调用方可使用 `_matches_struct_type` 自行筛选。
        """
        struct_ids = resource_manager.list_resources(ResourceType.STRUCT_DEFINITION)
        normalized_ids = [
            str(value).strip()
            for value in struct_ids
            if isinstance(value, str) and str(value).strip()
        ]
        normalized_ids.sort(key=lambda text: text.casefold())

        records: List[Tuple[str, Dict[str, object]]] = []
        for struct_id in normalized_ids:
            payload = resource_manager.load_resource(
                ResourceType.STRUCT_DEFINITION,
                struct_id,
            )
            if not isinstance(payload, dict):
                continue
            records.append((struct_id, payload))
        return records

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        resource_manager = self._get_resource_manager_from_package(package)
        if resource_manager is None:
            return []

        entries: List[Tuple[str, Dict[str, object], str]] = []
        records = self._load_struct_records(resource_manager)
        for struct_id, payload in records:
            if not self._matches_struct_type(payload):
                continue
            base_name = self._get_struct_display_name(struct_id, payload)
            entries.append((struct_id, payload, base_name))

        # 仅当存在同名结构体时才在显示名中做消歧：避免“名字（完整ID）”导致过长且重复。
        name_counts: Dict[str, int] = {}
        for _struct_id, _payload, base_name in entries:
            key = str(base_name or "").strip().casefold()
            if not key:
                continue
            name_counts[key] = name_counts.get(key, 0) + 1

        for struct_id, payload, base_name in entries:
            key = str(base_name or "").strip().casefold()
            needs_disambiguation = bool(key) and name_counts.get(key, 0) > 1
            yield self._build_row_data(
                struct_id,
                payload,
                base_name=base_name,
                needs_disambiguation=needs_disambiguation,
            )

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        from app.ui.foundation import dialog_utils

        dialog_utils.show_warning_dialog(
            parent_widget,
            "提示",
            "结构体定义已迁移为代码级定义，当前版本请在 Python 模块中新增结构体。",
        )
        return False

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        from app.ui.foundation import dialog_utils

        dialog_utils.show_warning_dialog(
            parent_widget,
            "提示",
            "结构体定义已迁移为代码级定义，当前版本请在 Python 模块中编辑结构体。",
        )
        return False

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        from app.ui.foundation import dialog_utils

        dialog_utils.show_warning_dialog(
            None,
            "提示",
            "结构体定义已迁移为代码级定义，当前版本不支持在管理面板中删除结构体。",
        )
        return False

    @staticmethod
    def _get_resource_manager_from_package(package: ManagementPackage) -> Optional[ResourceManager]:
        candidate = getattr(package, "resource_manager", None)
        if isinstance(candidate, ResourceManager):
            return candidate
        return None

    def _build_row_data(
        self,
        struct_id: str,
        payload: Mapping[str, object],
        *,
        base_name: str,
        needs_disambiguation: bool,
    ) -> ManagementRowData:
        base_name_text = str(base_name or "").strip()
        if not base_name_text:
            base_name_text = struct_id

        display_name = base_name_text
        if needs_disambiguation:
            suffix = self._extract_struct_id_suffix(base_name_text, struct_id)
            if suffix:
                display_name = f"{base_name_text}（{suffix}）"
            else:
                display_name = f"{base_name_text}（{struct_id}）"
        field_count = self._calculate_field_count(payload)
        attr1_text = f"字段数量: {field_count}"
        attr2_text = f"ID: {struct_id}"
        description_text = str(payload.get("description", ""))
        return ManagementRowData(
            name=display_name,
            type_name=self.type_name,
            attr1=attr1_text,
            attr2=attr2_text,
            attr3="",
            description=description_text,
            last_modified="",
            user_data=(self.section_key, struct_id),
        )

    @staticmethod
    def _extract_struct_id_suffix(base_name: str, struct_id: str) -> str:
        """从 struct_id 中提取用于 UI 消歧的短后缀。

        目标：
        - 对形如 `<name>__后缀` 的 STRUCT_ID，仅展示 “后缀”，避免重复显示 `<name>`；
        - 对不符合约定的 ID，尽量提取最后一段 `__xxx` 作为后缀；若仍无法提取则返回空。
        """
        base = str(base_name or "").strip()
        sid = str(struct_id or "").strip()
        if not base or not sid or sid == base:
            return ""

        if sid.startswith(base):
            suffix = sid[len(base) :].strip()
            suffix = suffix.lstrip("_-").strip()
            if suffix:
                return suffix

        if "__" in sid:
            suffix = sid.split("__")[-1].strip()
            suffix = suffix.lstrip("_-").strip()
            if suffix and suffix != base:
                return suffix

        return ""

    @staticmethod
    def _get_struct_display_name(struct_id: str, payload: Mapping[str, object]) -> str:
        name_value = payload.get("name")
        if isinstance(name_value, str) and name_value:
            return name_value
        struct_name_value = payload.get("struct_name")
        if isinstance(struct_name_value, str) and struct_name_value:
            return struct_name_value
        return struct_id

    @staticmethod
    def _calculate_field_count(payload: Mapping[str, object]) -> int:
        value_entries = payload.get("value")
        if isinstance(value_entries, Sequence):
            count = 0
            for entry in value_entries:
                if isinstance(entry, Mapping):
                    count += 1
            if count:
                return count
        fields_entries = payload.get("fields")
        if isinstance(fields_entries, Sequence):
            count = 0
            for entry in fields_entries:
                if isinstance(entry, Mapping):
                    count += 1
            if count:
                return count
        members_entries = payload.get("members")
        if isinstance(members_entries, Mapping):
            return len(members_entries)
        return 0

    @staticmethod
    def _extract_initial_fields_from_struct_data(
        data: Mapping[str, object],
    ) -> Tuple[str, List[Dict[str, object]]]:
        """从结构体载荷中提取名称与字段列表，供编辑对话框与右侧面板使用。

        返回值：
        - 结构体名称（优先使用 `name`，回退到 `struct_name` 字段）；
        - 字段列表，每项包含：
          - name: 字段名
          - type_name: 规范化后的类型名（用于下拉框展示与匹配）
          - raw_type_name: 原始类型名（用于保持与现有数据一致）
          - value_node: 原始 value 节点（仅在基于 `value` 列表的结构体中存在）。
        """
        name_value = data.get("name") or data.get("struct_name")
        initial_name = name_value if isinstance(name_value, str) else ""

        initial_fields: List[Dict[str, object]] = []

        value_entries = data.get("value")
        if isinstance(value_entries, Sequence):
            for entry in value_entries:
                if not isinstance(entry, Mapping):
                    continue
                field_name_value = entry.get("key")
                type_value = entry.get("param_type")
                field_name = (
                    str(field_name_value).strip()
                    if isinstance(field_name_value, str)
                    else ""
                )
                raw_type_name = (
                    str(type_value).strip() if isinstance(type_value, str) else ""
                )
                canonical_type_name = (
                    param_type_to_canonical(raw_type_name) if raw_type_name else ""
                )
                field_dict: Dict[str, object] = {
                    "name": field_name,
                    "type_name": canonical_type_name,
                    "raw_type_name": raw_type_name,
                    "value_node": entry.get("value"),
                }
                # 透传列表长度等元数据（主要用于局内存档结构体的 lenth）
                if "lenth" in entry:
                    field_dict["lenth"] = entry.get("lenth")
                initial_fields.append(field_dict)
        else:
            fields_entries = data.get("fields")
            if isinstance(fields_entries, Sequence):
                for entry in fields_entries:
                    if not isinstance(entry, Mapping):
                        continue
                    field_name_value = entry.get("field_name")
                    type_value = entry.get("param_type")
                    default_value_node = entry.get("default_value")
                    field_name = (
                        str(field_name_value).strip()
                        if isinstance(field_name_value, str)
                        else ""
                    )
                    raw_type_name = (
                        str(type_value).strip()
                        if isinstance(type_value, str)
                        else ""
                    )
                    canonical_type_name = (
                        param_type_to_canonical(raw_type_name) if raw_type_name else ""
                    )
                    field_dict: Dict[str, object] = {
                        "name": field_name,
                        "type_name": canonical_type_name,
                        "raw_type_name": raw_type_name,
                        "value_node": default_value_node,
                    }
                    length_value = entry.get("length")
                    if isinstance(length_value, int):
                        # 兼容 StructDefinitionEditorWidget 对局内存档结构体的元数据字段命名
                        field_dict["lenth"] = length_value
                    initial_fields.append(field_dict)
            else:
                members_value = data.get("members")
                if isinstance(members_value, Mapping):
                    for key, type_name in members_value.items():
                        if not isinstance(key, str):
                            continue
                        canonical_type_name = str(type_name)
                        initial_fields.append(
                            {
                                "name": key,
                                "type_name": canonical_type_name,
                                "raw_type_name": "",
                                "value_node": None,
                            }
                        )

        return initial_name, initial_fields

    @staticmethod
    def _get_struct_type_from_payload(payload: Mapping[str, object]) -> str:
        """从 Struct JSON 载荷中解析结构体类型标识。

        默认值为基础结构体类型，用于处理未写入 struct_ype 字段的配置。
        """
        raw_value = payload.get("struct_ype")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        raw_struct_type = payload.get("struct_type")
        if isinstance(raw_struct_type, str) and raw_struct_type.strip():
            return raw_struct_type.strip()
        return STRUCT_TYPE_BASIC

    def _matches_struct_type(self, payload: Mapping[str, object]) -> bool:
        """当前 Section 是否应展示给定结构体记录。"""
        struct_type_value = self._get_struct_type_from_payload(payload)
        return struct_type_value == self.struct_type


class InGameSaveStructDefinitionSection(StructDefinitionSection):
    """局内存档结构体定义管理 Section。

    与基础结构体共用同一资源类型与索引字段，但仅展示与维护
    struct_ype == "ingame_save" 的结构体定义，并在编辑时限制字段类型。
    """

    section_key = "ingame_struct_definitions"
    tree_label = "💾 局内存档结构体定义"
    type_name = "局内存档结构体"
    struct_type: str = STRUCT_TYPE_INGAME_SAVE

    @staticmethod
    def _get_supported_types() -> List[str]:
        """局内存档结构体可选字段类型列表（不包含字典）。"""
        struct_definition_config = InGameSaveStructDefinition()
        supported_types_value = struct_definition_config.supported_types
        if not isinstance(supported_types_value, Sequence):
            return []

        normalized_types: List[str] = []
        seen_types: set[str] = set()
        for raw_name in supported_types_value:
            if not isinstance(raw_name, str):
                continue
            canonical_name = normalize_canonical_type_name(raw_name)
            if not canonical_name or canonical_name in seen_types:
                continue
            seen_types.add(canonical_name)
            normalized_types.append(canonical_name)
        return normalized_types

    def _build_row_data(
        self,
        struct_id: str,
        payload: Mapping[str, object],
        *,
        base_name: str,
        needs_disambiguation: bool,
    ) -> ManagementRowData:
        """在列表中为局内存档结构体额外展示“列表字段与长度定义”摘要。

        注意：该方法签名必须与 StructDefinitionSection._build_row_data 对齐，
        因为 iter_rows 会以关键字参数方式传入 base_name/needs_disambiguation。
        """
        base_name_text = str(base_name or "").strip()
        if not base_name_text:
            base_name_text = struct_id

        display_name = base_name_text
        if needs_disambiguation:
            suffix = self._extract_struct_id_suffix(base_name_text, struct_id)
            if suffix:
                display_name = f"{base_name_text}（{suffix}）"
            else:
                display_name = f"{base_name_text}（{struct_id}）"
        field_count = self._calculate_field_count(payload)
        attr1_text = f"字段数量: {field_count}"

        value_entries = payload.get("value")
        list_field_summaries: List[str] = []
        list_field_count = 0
        if isinstance(value_entries, Sequence):
            for entry in value_entries:
                if not isinstance(entry, Mapping):
                    continue
                field_name_value = entry.get("key")
                param_type_value = entry.get("param_type")
                field_name = str(field_name_value).strip() if isinstance(field_name_value, str) else ""
                param_type = str(param_type_value).strip() if isinstance(param_type_value, str) else ""
                if not field_name or not param_type:
                    continue
                if not param_type.endswith("列表") or param_type == "结构体列表":
                    continue
                list_field_count += 1
                length_value = entry.get("lenth")
                if isinstance(length_value, (int, float)):
                    length_int = int(length_value)
                    if length_int > 0 and len(list_field_summaries) < 3:
                        list_field_summaries.append(f"{field_name}={length_int}")

        if list_field_count > 0:
            if list_field_summaries:
                summary_text = "；".join(list_field_summaries)
                attr2_text = f"列表字段: {list_field_count}（{summary_text}...）"
            else:
                attr2_text = f"列表字段: {list_field_count}"
        else:
            attr2_text = "无列表字段"

        attr3_text = f"ID: {struct_id}"
        description_text = str(payload.get("description", ""))
        return ManagementRowData(
            name=display_name,
            type_name=self.type_name,
            attr1=attr1_text,
            attr2=attr2_text,
            attr3=attr3_text,
            description=description_text,
            last_modified="",
            user_data=(self.section_key, struct_id),
        )