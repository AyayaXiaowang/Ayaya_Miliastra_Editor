from __future__ import annotations

from typing import Any, Dict, List, Tuple, Union

from .types import ExtractedSpec, NormalizedSpec


def _ensure_category_with_suffix(category_text: str) -> str:
    """
    统一类别名为“带‘节点’后缀”的内部表示。
    例如：'执行' -> '执行节点'，'执行节点' 保持不变。
    """
    category_clean = str(category_text or "").strip()
    if category_clean.endswith("节点"):
        return category_clean
    return f"{category_clean}节点"


def _pairs_to_type_dict(pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """
    将 [(端口名, 类型名)] 转换为 {端口名: 类型名}。
    非法项会被跳过（保证标准化输出健壮）。
    """
    result: Dict[str, str] = {}
    for pair in list(pairs or []):
        # 允许 tuple/list 两种形式
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            port_name_text = str(pair[0])
            type_name_text = str(pair[1])
            if port_name_text != "" and type_name_text != "":
                result[port_name_text] = type_name_text
    return result


def normalize_specs(extracted_items: List[Union[ExtractedSpec, Dict[str, Any]]]) -> List[NormalizedSpec]:
    """
    将 AST 提取的原始项标准化为统一结构：
    - 统一类别后缀（内部一律使用“...节点”）
    - 生成标准键 standard_key = '类别/名称'
    - 将 inputs/outputs 的 (name, type) 列表转换为 input_types/output_types 字典
    
    约定：
    - 负责字段命名与结构统一，不做跨项校验（校验交给 validator）
    - 输出仍为“列表”，每项是单个节点的中间表述（供后续合并与索引）
    """
    if not isinstance(extracted_items, list):
        raise TypeError("extracted_items 必须是列表")

    normalized_list: List[NormalizedSpec] = []

    for raw in extracted_items:
        # 统一读取字段（支持 ExtractedSpec 或 dict）
        if isinstance(raw, ExtractedSpec):
            name_text = str(raw.name or "").strip()
            category_text = str(raw.category or "").strip()
            file_path = raw.file_path
            inputs_pairs = list(raw.inputs or [])
            outputs_pairs = list(raw.outputs or [])
            aliases_list = list(raw.aliases or [])
            scopes_list = list(raw.scopes or [])
            description_text = str(raw.description or "")
            mount_restrictions_list = list(raw.mount_restrictions or [])
            doc_reference_text = str(raw.doc_reference or "")
            dynamic_port_type_text = str(raw.dynamic_port_type or "")
            input_generic_constraints = dict(raw.input_generic_constraints or {})
            output_generic_constraints = dict(raw.output_generic_constraints or {})
            input_enum_options = dict(raw.input_enum_options or {})
            output_enum_options = dict(raw.output_enum_options or {})
        elif isinstance(raw, dict):
            name_text = str(raw.get("name", "") or "").strip()
            category_text = str(raw.get("category", "") or "").strip()
            file_path = raw.get("file_path")
            inputs_pairs = list(raw.get("inputs") or [])
            outputs_pairs = list(raw.get("outputs") or [])
            aliases_list = list(raw.get("aliases") or [])
            scopes_list = list(raw.get("scopes") or [])
            description_text = str(raw.get("description") or "")
            mount_restrictions_list = list(raw.get("mount_restrictions") or [])
            doc_reference_text = str(raw.get("doc_reference") or "")
            dynamic_port_type_text = str(raw.get("dynamic_port_type") or "")
            input_generic_constraints = dict(raw.get("input_generic_constraints") or {})
            output_generic_constraints = dict(raw.get("output_generic_constraints") or {})
            input_enum_options = dict(raw.get("input_enum_options") or {})
            output_enum_options = dict(raw.get("output_enum_options") or {})
        else:
            # 跳过未知项类型，保持稳健
            continue
        if name_text == "" or category_text == "":
            # 缺失关键信息时，保留到后续 validator 处理；此处仍然产出占位项以便统一流程
            category_standard = _ensure_category_with_suffix(category_text)
            standard_key = f"{category_standard}/{name_text}"
            normalized_list.append(NormalizedSpec(
                file_path=file_path,
                standard_key=standard_key,
                category_standard=category_standard,
                name=name_text,
                input_types={},
                output_types={},
                aliases=aliases_list,
                scopes=scopes_list,
                description=description_text,
                mount_restrictions=mount_restrictions_list,
                doc_reference=doc_reference_text,
                dynamic_port_type=dynamic_port_type_text,
                inputs=[],
                outputs=[],
                input_generic_constraints={},
                output_generic_constraints={},
                input_enum_options=input_enum_options,
                output_enum_options=output_enum_options,
            ))
            continue

        category_standard = _ensure_category_with_suffix(category_text)
        standard_key = f"{category_standard}/{name_text}"

        input_types = _pairs_to_type_dict(inputs_pairs)
        output_types = _pairs_to_type_dict(outputs_pairs)

        normalized_list.append(NormalizedSpec(
            file_path=file_path,
            standard_key=standard_key,
            category_standard=category_standard,
            name=name_text,
            input_types=input_types,
            output_types=output_types,
            aliases=aliases_list,
            scopes=scopes_list,
            description=description_text,
            mount_restrictions=mount_restrictions_list,
            doc_reference=doc_reference_text,
            dynamic_port_type=dynamic_port_type_text,
            inputs=inputs_pairs,
            outputs=outputs_pairs,
            input_generic_constraints=input_generic_constraints,
            output_generic_constraints=output_generic_constraints,
            input_enum_options=input_enum_options,
            output_enum_options=output_enum_options,
        ))

    return normalized_list


