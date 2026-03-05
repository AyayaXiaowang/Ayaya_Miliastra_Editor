from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.ui_schema_library.library import find_schema_ids_by_label, load_schema_record

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
)
from .web_ui_import_constants import UI_SCHEMA_LABEL_TEXTBOX
from .web_ui_import_rect import has_rect_transform_state, try_extract_textbox_text_node, try_extract_widget_name


COMPONENT_SLOT_INDEX_TEXTBOX_STYLE = 1
COMPONENT_SLOT_INDEX_TEXTBOX = 3

# TextBox 的 component_list[3]（经验上为 TextBoxComponent）在不同模板来源下可能缺少 header 字段。
# 实测：缺失时会导致导出网页/运行时文本渲染不一致，因此写回阶段显式补齐这些字段，避免依赖 schema library 的“富模板”。
EMPTY_BINARY_DATA_TEXT = "<binary_data> "
TEXTBOX_COMPONENT3_FIELD501_KIND = 9
TEXTBOX_COMPONENT3_FIELD502_STYLE = 25
TEXTBOX_COMPONENT3_FIELD503_KIND = 10
TEXTBOX_COMPONENT3_FIELD503_STYLE = 25
TEXTBOX_COMPONENT3_FIELD503_FLAG = 1


def _has_non_empty_textbox_style_component_slot(record: Dict[str, Any]) -> bool:
    """
    TextBox record 约定：
    - record['505'] 是 component_list（list）
    - component_list[1] 通常为“样式/容器组件（component1）”，必须是结构化 dict

    经验：当 component_list[1] 被写成 0 字节 bytes（或被序列化为 `<binary_data>`）时，
    后续网页导出会出现文本/样式缺失或回退默认值。
    """
    comp_list = record.get("505")
    if not isinstance(comp_list, list):
        return False
    if len(comp_list) <= COMPONENT_SLOT_INDEX_TEXTBOX_STYLE:
        return False
    slot = comp_list[COMPONENT_SLOT_INDEX_TEXTBOX_STYLE]
    return isinstance(slot, dict) and bool(slot)


def choose_textbox_record_template(ui_record_list: List[Any]) -> Optional[Dict[str, Any]]:
    """
    选择一个可作为“克隆模板”的 TextBox UI record：
    - 必须能定位到 text_node（见 `try_extract_textbox_text_node`）
    - 必须包含 RectTransform state0（用于写回坐标）
    - 要求无 children（避免处理子树克隆）

    返回 None 表示未找到。
    """
    best_score: Optional[int] = None
    best_record: Optional[Dict[str, Any]] = None

    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        # 必须具备非空 component1（样式/容器组件），否则 clone 会扩散“空槽位”
        if not _has_non_empty_textbox_style_component_slot(record):
            continue
        if not has_rect_transform_state(record, state_index=0):
            continue
        children = _get_children_guids_from_parent_record(record)
        if children:
            continue
        text_node = try_extract_textbox_text_node(record)
        if text_node is None:
            continue

        score = 0
        name = try_extract_widget_name(record)
        if name == "文本框":
            score += 10

        # 偏好“默认对齐/最少字段”的模板（更像“基底”）
        if "503" not in text_node:
            score += 2
        if "504" not in text_node:
            score += 2

        if best_score is None or score > best_score:
            best_score = score
            best_record = record

    return best_record


def try_load_textbox_record_template_from_ui_schema_library() -> Optional[Dict[str, Any]]:
    """
    优先从 `ui_schema_library` 中读取已标注为 textbox 的模板 record。
    这允许“只依赖一次样本存档做沉淀”，后续在任意 base `.gil` 中复用该结构。
    """
    schema_ids = find_schema_ids_by_label(UI_SCHEMA_LABEL_TEXTBOX)
    if not schema_ids:
        return None
    candidates: List[Dict[str, Any]] = []
    for sid in schema_ids:
        candidates.append(load_schema_record(sid))
    return choose_textbox_record_template(candidates)


def write_textbox_text_and_style(
    record: Dict[str, Any],
    *,
    text_content: str,
    background_color: str,
    font_size: int,
    alignment_h: str,
    alignment_v: str,
) -> Dict[str, Optional[int]]:
    """
    写回 TextBox 的文本与样式字段，并返回写入后的“raw code 摘要”（用于报告）。
    """
    comp_list = record.get("505")
    if not isinstance(comp_list, list) or len(comp_list) <= COMPONENT_SLOT_INDEX_TEXTBOX:
        raise TypeError("record['505'] 缺失或不是 list，无法定位 TextBox component_list[3]")
    component3 = comp_list[COMPONENT_SLOT_INDEX_TEXTBOX]
    if not isinstance(component3, dict):
        raise TypeError("record['505'][3] 不是 dict，无法写回 TextBox component3 header 字段")

    # 补齐 component3 header（保持与“富模板”一致）
    if "19" not in component3:
        component3["19"] = EMPTY_BINARY_DATA_TEXT
    if "501" not in component3:
        component3["501"] = int(TEXTBOX_COMPONENT3_FIELD501_KIND)
    if "502" not in component3:
        component3["502"] = int(TEXTBOX_COMPONENT3_FIELD502_STYLE)
    node503_component3 = component3.get("503")
    if not isinstance(node503_component3, dict):
        node503_component3 = {}
        component3["503"] = node503_component3
    if "501" not in node503_component3:
        node503_component3["501"] = int(TEXTBOX_COMPONENT3_FIELD503_KIND)
    if "502" not in node503_component3:
        node503_component3["502"] = int(TEXTBOX_COMPONENT3_FIELD503_STYLE)
    if "503" not in node503_component3:
        node503_component3["503"] = int(TEXTBOX_COMPONENT3_FIELD503_FLAG)

    node19 = try_extract_textbox_text_node(record)
    if node19 is None:
        raise RuntimeError("record 不包含可识别的 TextBox 文本节点（node19）")

    node505 = node19.get("505")
    if not isinstance(node505, dict):
        node505 = {}
        node19["505"] = node505
    node505["501"] = str(text_content or "")

    # 背景色（用于阴影层）：以“黑色半透明底板”表达 shadow overlay（支持 alpha 的控件形态）。
    # 注意：
    # - 写回必须是“显式开关”：当来源不是阴影底板时，需要清掉 node19['501']，避免从模板 record 继承导致“所有文本都有黑底”。
    # - alpha 档位由编辑器/样本决定；HTML/Workbench 侧会以 #0E0E0E73/#0E0E0E40 或等价 rgba 标注来源。
    bg = str(background_color or "").strip().lower()
    if bg in (
        "黑色半透明",
        "rgba(14, 14, 14, 0.45)",
        "rgba(14,14,14,0.45)",
        "#0e0e0e73",
        "rgba(14, 14, 14, 0.25)",
        "rgba(14,14,14,0.25)",
        "#0e0e0e40",
    ):
        node19["501"] = 1
    else:
        # 非阴影底板：显式关掉（避免模板默认值污染导致“所有文本都有黑底”）
        node19["501"] = 0

    font_size_int = int(font_size)
    if font_size_int < 8:
        font_size_int = 8
    if font_size_int > 72:
        font_size_int = 72
    node19["502"] = int(font_size_int)

    h = str(alignment_h or "").strip()
    v = str(alignment_v or "").strip()
    if h == "":
        h = "左侧对齐"
    if v == "":
        v = "垂直居中"

    h_code: Optional[int] = None
    if h in ("左侧对齐", "左对齐", "left", "Left"):
        if "503" in node19:
            del node19["503"]
        h_code = None
    elif h in ("水平居中", "居中", "center", "Center"):
        node19["503"] = 1
        h_code = 1
    elif h in ("右侧对齐", "右对齐", "right", "Right"):
        node19["503"] = 2
        h_code = 2

    v_code: Optional[int] = None
    # 样本推断：缺失字段表示“顶部对齐”
    if v in ("顶部对齐", "顶对齐", "top", "Top"):
        if "504" in node19:
            del node19["504"]
        v_code = None
    elif v in ("垂直居中", "居中", "center", "Center"):
        node19["504"] = 1
        v_code = 1
    elif v in ("底部对齐", "底对齐", "bottom", "Bottom"):
        node19["504"] = 2
        v_code = 2

    # 返回写回后的 raw code（未知语义字段保留，便于继续逆向）
    out_h_code: Optional[int] = int(node19["503"]) if isinstance(node19.get("503"), int) else None
    out_v_code: Optional[int] = int(node19["504"]) if isinstance(node19.get("504"), int) else None
    out_flag_501: Optional[int] = int(node19["501"]) if isinstance(node19.get("501"), int) else None

    return {
        "flag_501": out_flag_501,
        "font_size_502": int(node19.get("502") or 0) if isinstance(node19.get("502"), int) else None,
        "align_h_503": out_h_code,
        "align_v_504": out_v_code,
        "requested_align_h_code": h_code,
        "requested_align_v_code": v_code,
    }

