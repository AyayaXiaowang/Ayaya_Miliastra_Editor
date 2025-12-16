from __future__ import annotations

from .management_sections_base import *
from engine.configs.specialized.node_graph_configs import (
    STRUCT_TYPE_BASIC,
    STRUCT_TYPE_INGAME_SAVE,
    InGameSaveStructDefinition,
)
from engine.resources.definition_schema_view import (
    get_default_definition_schema_view,
)


class StructDefinitionSection(BaseManagementSection):
    """结构体定义管理 Section（对应资源类型 `STRUCT_DEFINITION`）。

    新设计约定：
    - 数据来源：结构体定义 Schema 视图（`DefinitionSchemaView`）中的代码级结构体定义；
    - 过滤规则：
      - `<全部资源>` 视图：展示全部结构体定义；
      - 具体存档视图：仅展示该存档索引 `resources.management["struct_definitions"]`
        中声明包含的结构体 ID；
      - `<未分类资源>` 视图：展示未被任何存档纳入的结构体（基于索引反查）。
    - 结构体定义的增删改需在 Python 模块中完成，本 Section 在当前版本中仅提供浏览与归属管理。
    """

    section_key = "struct_definitions"
    tree_label = "🧬 基础结构体定义"
    type_name = "基础结构体"
    struct_type: str = STRUCT_TYPE_BASIC

    # 基于 ResourceManager 实例的结构体记录缓存：
    # id(resource_manager) -> List[(struct_id, payload)]
    _STRUCT_RECORDS_CACHE: Dict[int, List[Tuple[str, Dict[str, object]]]] = {}

    @classmethod
    def _invalidate_struct_records_cache(cls, resource_manager: ResourceManager) -> None:
        """当结构体定义被增删改时，显式失效对应 ResourceManager 的缓存。"""
        cache_key = id(resource_manager)
        if cache_key in cls._STRUCT_RECORDS_CACHE:
            del cls._STRUCT_RECORDS_CACHE[cache_key]

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        resource_manager = self._get_resource_manager_from_package(package)
        if resource_manager is None:
            return []

        all_records = self._load_struct_records(resource_manager)
        package_id_value = getattr(package, "package_id", "") or ""
        package_id = str(package_id_value)

        if package_id in ("", "global_view"):
            for struct_id, payload in all_records:
                if not self._matches_struct_type(payload):
                    continue
                yield self._build_row_data(struct_id, payload)
            return

        if package_id == "unclassified_view":
            membership_index = self._build_struct_membership_index_for_unclassified_view(package)
            for struct_id, payload in all_records:
                if not self._matches_struct_type(payload):
                    continue
                if not membership_index.get(struct_id):
                    yield self._build_row_data(struct_id, payload)
            return

        package_index = getattr(package, "package_index", None)
        if package_index is None:
            return []
        struct_ids_for_package = set(
            package_index.resources.management.get("struct_definitions", [])
        )

        for struct_id, payload in all_records:
            if not self._matches_struct_type(payload):
                continue
            if struct_id in struct_ids_for_package:
                yield self._build_row_data(struct_id, payload)

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

    @classmethod
    def _load_struct_records(
        cls,
        resource_manager: ResourceManager,
    ) -> Iterable[Tuple[str, Dict[str, object]]]:
        """加载所有结构体定义记录，并在进程内按 ResourceManager 维度做缓存。

        设计目标：
        - 避免在管理页面每次切换到“结构体定义”时都重新遍历代码级定义；
        - 返回结构与旧实现保持一致（返回 payload 副本），
          通过显式失效缓存的方式与增删改操作保持一致（虽然当前版本不再支持增删改）。
        """
        cache_key = id(resource_manager)
        cached_records = cls._STRUCT_RECORDS_CACHE.get(cache_key)
        if cached_records is not None:
            return cached_records

        records: List[Tuple[str, Dict[str, object]]] = []
        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()

        for struct_id, payload in all_structs.items():
            if not isinstance(payload, dict):
                continue
            records.append((struct_id, dict(payload)))

        cls._STRUCT_RECORDS_CACHE[cache_key] = records
        return records

    @staticmethod
    def _build_struct_membership_index_for_unclassified_view(
        unclassified_view: ManagementPackage,
    ) -> Dict[str, set[str]]:
        if not isinstance(unclassified_view, UnclassifiedResourceView):
            return {}
        package_index_manager = getattr(unclassified_view, "package_index_manager", None)
        if package_index_manager is None:
            return {}

        membership: Dict[str, set[str]] = {}
        packages = package_index_manager.list_packages()
        for package_info in packages:
            package_id_value = package_info.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value:
                continue
            package_index = package_index_manager.load_package_index(package_id_value)
            if not package_index:
                continue
            struct_ids_value = package_index.resources.management.get("struct_definitions", [])
            if not isinstance(struct_ids_value, list):
                continue
            for struct_id in struct_ids_value:
                if not isinstance(struct_id, str) or not struct_id:
                    continue
                bucket = membership.setdefault(struct_id, set())
                bucket.add(package_id_value)
        return membership

    def _build_row_data(self, struct_id: str, payload: Mapping[str, object]) -> ManagementRowData:
        display_name = self._get_struct_display_name(struct_id, payload)
        field_count = self._calculate_field_count(payload)
        attr1_text = f"字段数量: {field_count}"
        description_text = str(payload.get("description", ""))
        return ManagementRowData(
            name=display_name,
            type_name=self.type_name,
            attr1=attr1_text,
            attr2="",
            attr3="",
            description=description_text,
            last_modified="",
            user_data=(self.section_key, struct_id),
        )

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

    def _build_row_data(self, struct_id: str, payload: Mapping[str, object]) -> ManagementRowData:
        """在列表中为局内存档结构体额外展示“列表字段与长度定义”摘要。"""
        display_name = self._get_struct_display_name(struct_id, payload)
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