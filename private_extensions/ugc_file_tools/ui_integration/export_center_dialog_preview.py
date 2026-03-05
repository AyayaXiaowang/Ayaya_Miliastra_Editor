from __future__ import annotations

from .export_center_dialog_types import ExportCenterPreview


def build_export_center_preview(
    *,
    QtWidgets: object,
    Colors: object,
    ThemeManager: object,
    dialog: object,
) -> ExportCenterPreview:
    preview_frame = QtWidgets.QFrame(dialog)
    preview_frame.setStyleSheet(f"background-color: {Colors.BG_CARD}; border-radius: 4px; padding: 8px;")
    preview_layout = QtWidgets.QVBoxLayout(preview_frame)
    preview_layout.setContentsMargins(0, 0, 0, 0)

    preview_label = QtWidgets.QLabel("预览摘要:", preview_frame)
    preview_label.setStyleSheet("font-weight: bold;")
    preview_layout.addWidget(preview_label)

    preview = QtWidgets.QLabel("", preview_frame)
    preview.setWordWrap(True)
    preview.setStyleSheet(ThemeManager.subtle_info_style())
    preview_layout.addWidget(preview)

    id_ref_usage_sep = QtWidgets.QFrame(preview_frame)
    id_ref_usage_sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    id_ref_usage_sep.setStyleSheet(f"color: {Colors.BORDER_LIGHT};")
    id_ref_usage_sep.setVisible(False)
    preview_layout.addWidget(id_ref_usage_sep)

    id_ref_usage_label = QtWidgets.QLabel("节点图占位符（entity_key/component_key）:", preview_frame)
    id_ref_usage_label.setStyleSheet("font-weight: bold;")
    id_ref_usage_label.setVisible(False)
    preview_layout.addWidget(id_ref_usage_label)

    id_ref_usage_text = QtWidgets.QPlainTextEdit(preview_frame)
    id_ref_usage_text.setReadOnly(True)
    id_ref_usage_text.setPlaceholderText("未检测到 entity_key/component_key 占位符。")
    id_ref_usage_text.setMaximumHeight(140)
    id_ref_usage_text.setStyleSheet(
        f"color: {Colors.TEXT_SECONDARY};"
        f"background-color: {Colors.BG_MAIN};"
        f"border: 1px solid {Colors.BORDER_LIGHT};"
        "border-radius: 4px;"
        "font-size: 11px;"
    )
    id_ref_usage_text.setVisible(False)
    preview_layout.addWidget(id_ref_usage_text)

    return ExportCenterPreview(
        frame=preview_frame,
        preview=preview,
        id_ref_usage_sep=id_ref_usage_sep,
        id_ref_usage_label=id_ref_usage_label,
        id_ref_usage_text=id_ref_usage_text,
    )

