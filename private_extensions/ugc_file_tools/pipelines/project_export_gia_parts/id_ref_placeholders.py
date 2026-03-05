from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResolvedIdRefPlaceholders:
    component_name_to_id: dict[str, int] | None
    entity_name_to_guid: dict[str, int] | None
    missing_id_ref_entities: list[str]
    missing_id_ref_components: list[str]
    allow_unresolved_id_ref_placeholders: bool


def resolve_id_ref_placeholders_for_graph(
    *,
    required_component_names: set[str],
    required_entity_names: set[str],
    id_ref_gil_file: Path | None,
    id_ref_overrides: object | None = None,
) -> ResolvedIdRefPlaceholders:
    """
    根据参考 `.gil` 为 entity_key/component_key 占位符构造“名称→ID”映射。

    约束（与历史实现一致）：
    - 若用户未提供参考 GIL：允许导出，并将缺失占位符回填为 0；
    - 若提供参考 GIL 但查不到：同样允许导出，缺失占位符回填为 0（不阻断导出）。
    """
    from ugc_file_tools.id_ref_from_gil import build_id_ref_mappings_from_gil_file
    from ugc_file_tools.id_ref_overrides import IdRefOverrides, apply_id_ref_overrides

    component_name_to_id: dict[str, int] | None = None
    entity_name_to_guid: dict[str, int] | None = None
    allow_unresolved_id_ref_placeholders = False
    missing_id_ref_entities: list[str] = []
    missing_id_ref_components: list[str] = []

    if required_component_names or required_entity_names:
        if id_ref_gil_file is None:
            # 用户未选择参考 GIL：按需求允许导出，并将占位符回填为 0。
            allow_unresolved_id_ref_placeholders = True
        else:
            component_name_to_id, entity_name_to_guid = build_id_ref_mappings_from_gil_file(gil_file_path=Path(id_ref_gil_file))

        overrides_obj: IdRefOverrides | None = None
        if isinstance(id_ref_overrides, IdRefOverrides):
            overrides_obj = id_ref_overrides
        elif id_ref_overrides is not None:
            raise TypeError("id_ref_overrides must be IdRefOverrides | None")

        component_name_to_id, entity_name_to_guid = apply_id_ref_overrides(
            component_name_to_id=component_name_to_id,
            entity_name_to_guid=entity_name_to_guid,
            overrides=overrides_obj,
        )

        # 仅当提供了参考 `.gil` 时，才做“缺失列表”判定（与历史 report 口径保持一致）。
        if id_ref_gil_file is not None:
            missing_entities = sorted(
                {str(x) for x in required_entity_names if str(x) not in set((entity_name_to_guid or {}).keys())}
            )
            if missing_entities:
                # 需求：找不到也不要阻止导出；缺失的占位符回填为 0。
                missing_id_ref_entities = list(missing_entities)
                allow_unresolved_id_ref_placeholders = True

            missing_components = sorted(
                {str(x) for x in required_component_names if str(x) not in set((component_name_to_id or {}).keys())}
            )
            if missing_components:
                # 需求：找不到也不要阻止导出；缺失的占位符回填为 0。
                missing_id_ref_components = list(missing_components)
                allow_unresolved_id_ref_placeholders = True

    return ResolvedIdRefPlaceholders(
        component_name_to_id=component_name_to_id,
        entity_name_to_guid=entity_name_to_guid,
        missing_id_ref_entities=list(missing_id_ref_entities),
        missing_id_ref_components=list(missing_id_ref_components),
        allow_unresolved_id_ref_placeholders=bool(allow_unresolved_id_ref_placeholders),
    )

