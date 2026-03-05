from __future__ import annotations


def open_export_center_gil_ui_layout_conflicts_dialog(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    parent_dialog: object,
    conflict_layouts: list[dict[str, object]],
) -> list[dict[str, str]] | None:
    """
    导出中心（GIL）：UI 布局同名冲突检查对话框。

    输入 conflict_layouts item schema（dict）：
    - layout_name: str
    - existing_guid: int（可选）

    返回：
    - 用户取消：None
    - 用户确认：list[{"layout_name": str, "action": "overwrite"|"add"|"skip"}]
    """
    items: list[dict[str, object]] = []
    for idx, raw in enumerate(list(conflict_layouts or [])):
        if not isinstance(raw, dict):
            raise TypeError(f"conflict_layouts[{idx}] must be dict")
        layout_name = str(raw.get("layout_name") or "").strip()
        if layout_name == "":
            raise ValueError(f"conflict_layouts[{idx}].layout_name 不能为空")
        existing_guid = raw.get("existing_guid", None)
        if existing_guid is not None and not isinstance(existing_guid, int):
            raise TypeError(f"conflict_layouts[{idx}].existing_guid must be int or None")
        items.append({"layout_name": layout_name, "existing_guid": existing_guid})

    dlg = QtWidgets.QDialog(parent_dialog)
    dlg.setWindowTitle("资源冲突检查（GIL）")
    dlg.setModal(True)
    dlg.resize(980, 640)
    dlg.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_MAIN}; }}")

    root = QtWidgets.QVBoxLayout(dlg)
    root.setContentsMargins(Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE)
    root.setSpacing(Sizes.SPACING_MEDIUM)

    tip = QtWidgets.QLabel(
        "检测到基础 .gil 已存在同名 UI 布局。\n"
        "你可以逐个选择：覆盖（写入同名布局）/ 新增（创建新布局，避免覆盖旧布局）/ 不导出（跳过该布局）。\n"
        "\n"
        "提示：该弹窗仅在“启用 UI 写回 (界面)”开启时出现。\n"
        "若你只是选择了“UI 回填记录”（用于 ui_key→GUID 回填），但不希望写回 UI，请回到上一步关闭 UI 写回后再导出。",
        dlg,
    )
    tip.setWordWrap(True)
    tip.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
    root.addWidget(tip)

    search_edit = QtWidgets.QLineEdit(dlg)
    search_edit.setPlaceholderText("搜索布局名（支持模糊匹配）")
    root.addWidget(search_edit)

    table = QtWidgets.QTableWidget(dlg)
    table.setColumnCount(4)
    table.setHorizontalHeaderLabels(["资源类型", "名称", "基础GIL GUID", "处理方式"])
    table.setRowCount(len(items))
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    root.addWidget(table, 1)

    action_combos: list[object] = []
    for row, it in enumerate(items):
        layout_name = str(it["layout_name"])
        existing_guid = it.get("existing_guid", None)

        item_type = QtWidgets.QTableWidgetItem("布局")
        item_type.setForeground(QtCore.Qt.GlobalColor.white)
        table.setItem(row, 0, item_type)

        item_name = QtWidgets.QTableWidgetItem(layout_name)
        table.setItem(row, 1, item_name)

        guid_text = "" if existing_guid is None else str(int(existing_guid))
        item_guid = QtWidgets.QTableWidgetItem(guid_text)
        table.setItem(row, 2, item_guid)

        combo = QtWidgets.QComboBox(table)
        combo.addItem("覆盖（默认）", "overwrite")
        combo.addItem("新增（创建新布局）", "add")
        combo.addItem("不导出（跳过）", "skip")
        combo.setCurrentIndex(0)
        table.setCellWidget(row, 3, combo)
        action_combos.append(combo)

    def _apply_filter() -> None:
        q = str(search_edit.text() or "").strip().casefold()
        for row, it in enumerate(items):
            if q == "":
                table.setRowHidden(row, False)
                continue
            name = str(it.get("layout_name") or "").casefold()
            table.setRowHidden(row, q not in name)

    search_edit.textChanged.connect(_apply_filter)

    btn_row = QtWidgets.QWidget(dlg)
    btn_layout = QtWidgets.QHBoxLayout(btn_row)
    btn_layout.setContentsMargins(0, 0, 0, 0)
    btn_layout.setSpacing(Sizes.SPACING_SMALL)

    all_overwrite_btn = QtWidgets.QPushButton("全部覆盖", btn_row)
    all_overwrite_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    all_add_btn = QtWidgets.QPushButton("全部新增", btn_row)
    all_add_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    all_skip_btn = QtWidgets.QPushButton("全部不导出", btn_row)
    all_skip_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(all_overwrite_btn)
    btn_layout.addWidget(all_add_btn)
    btn_layout.addWidget(all_skip_btn)
    btn_layout.addStretch(1)

    cancel_btn = QtWidgets.QPushButton("取消", btn_row)
    cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    ok_btn = QtWidgets.QPushButton("继续导出", btn_row)
    ok_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(ok_btn)
    root.addWidget(btn_row)

    def _set_all(action: str) -> None:
        for row, combo in enumerate(action_combos):
            if table.isRowHidden(row):
                continue
            for i in range(combo.count()):
                if str(combo.itemData(i) or "") == action:
                    combo.setCurrentIndex(i)
                    break

    all_overwrite_btn.clicked.connect(lambda: _set_all("overwrite"))
    all_add_btn.clicked.connect(lambda: _set_all("add"))
    all_skip_btn.clicked.connect(lambda: _set_all("skip"))

    ok_btn.clicked.connect(dlg.accept)
    cancel_btn.clicked.connect(dlg.reject)

    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    out: list[dict[str, str]] = []
    for row, it in enumerate(items):
        combo = action_combos[row]
        action = str(combo.currentData() or "overwrite").strip().lower()
        if action not in {"overwrite", "add", "skip"}:
            raise ValueError(f"unexpected action from combobox: {action!r}")
        out.append({"layout_name": str(it["layout_name"]), "action": action})
    return out


__all__ = ["open_export_center_gil_ui_layout_conflicts_dialog"]


def open_export_center_gil_node_graph_conflicts_dialog(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    parent_dialog: object,
    conflict_graphs: list[dict[str, object]],
) -> list[dict[str, str]] | None:
    """
    导出中心（GIL）：节点图同名冲突检查对话框。

    输入 conflict_graphs item schema（dict）：
    - graph_code_file: str（绝对路径）
    - scope: str（"server"|"client"）
    - graph_name: str
    - existing_graph_id_int: int（可选）

    返回：
    - 用户取消：None
    - 用户确认：list[{"graph_code_file": str, "action": "overwrite"|"add"|"skip"}]
    """
    items: list[dict[str, object]] = []
    for idx, raw in enumerate(list(conflict_graphs or [])):
        if not isinstance(raw, dict):
            raise TypeError(f"conflict_graphs[{idx}] must be dict")
        graph_code_file = str(raw.get("graph_code_file") or "").strip()
        if graph_code_file == "":
            raise ValueError(f"conflict_graphs[{idx}].graph_code_file 不能为空")
        scope = str(raw.get("scope") or "").strip().lower()
        if scope not in {"server", "client"}:
            raise ValueError(f"conflict_graphs[{idx}].scope 仅支持 server/client，实际为：{scope!r}")
        graph_name = str(raw.get("graph_name") or "").strip()
        if graph_name == "":
            raise ValueError(f"conflict_graphs[{idx}].graph_name 不能为空")
        existing_id = raw.get("existing_graph_id_int", None)
        if existing_id is not None and not isinstance(existing_id, int):
            raise TypeError(f"conflict_graphs[{idx}].existing_graph_id_int must be int or None")
        items.append(
            {
                "graph_code_file": graph_code_file,
                "scope": scope,
                "graph_name": graph_name,
                "existing_graph_id_int": existing_id,
            }
        )

    dlg = QtWidgets.QDialog(parent_dialog)
    dlg.setWindowTitle("资源冲突检查（GIL）")
    dlg.setModal(True)
    dlg.resize(980, 640)
    dlg.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_MAIN}; }}")

    root = QtWidgets.QVBoxLayout(dlg)
    root.setContentsMargins(Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE)
    root.setSpacing(Sizes.SPACING_MEDIUM)

    tip = QtWidgets.QLabel(
        "检测到基础 .gil 已存在同名节点图（同 scope + 同 graph_name）。\n"
        "你可以逐个选择：覆盖（写入同名节点图）/ 新增（创建新节点图，自动生成新名字）/ 不导出（跳过该图）。",
        dlg,
    )
    tip.setWordWrap(True)
    tip.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
    root.addWidget(tip)

    search_edit = QtWidgets.QLineEdit(dlg)
    search_edit.setPlaceholderText("搜索节点图名（支持模糊匹配）")
    root.addWidget(search_edit)

    table = QtWidgets.QTableWidget(dlg)
    table.setColumnCount(4)
    table.setHorizontalHeaderLabels(["资源类型", "名称", "基础GIL graph_id_int", "处理方式"])
    table.setRowCount(len(items))
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    root.addWidget(table, 1)

    action_combos: list[object] = []
    for row, it in enumerate(items):
        graph_name = str(it["graph_name"])
        scope = str(it["scope"])
        graph_code_file = str(it["graph_code_file"])
        existing_id = it.get("existing_graph_id_int", None)

        item_type = QtWidgets.QTableWidgetItem(f"节点图({scope})")
        item_type.setForeground(QtCore.Qt.GlobalColor.white)
        item_type.setToolTip(graph_code_file)
        table.setItem(row, 0, item_type)

        item_name = QtWidgets.QTableWidgetItem(graph_name)
        item_name.setToolTip(graph_code_file)
        table.setItem(row, 1, item_name)

        id_text = "" if existing_id is None else str(int(existing_id))
        item_id = QtWidgets.QTableWidgetItem(id_text)
        item_id.setToolTip(graph_code_file)
        table.setItem(row, 2, item_id)

        combo = QtWidgets.QComboBox(table)
        combo.addItem("覆盖（默认）", "overwrite")
        combo.addItem("新增（创建新节点图）", "add")
        combo.addItem("不导出（跳过）", "skip")
        combo.setCurrentIndex(0)
        table.setCellWidget(row, 3, combo)
        action_combos.append(combo)

    def _apply_filter() -> None:
        q = str(search_edit.text() or "").strip().casefold()
        for row, it in enumerate(items):
            if q == "":
                table.setRowHidden(row, False)
                continue
            name = str(it.get("graph_name") or "").casefold()
            table.setRowHidden(row, q not in name)

    search_edit.textChanged.connect(_apply_filter)

    btn_row = QtWidgets.QWidget(dlg)
    btn_layout = QtWidgets.QHBoxLayout(btn_row)
    btn_layout.setContentsMargins(0, 0, 0, 0)
    btn_layout.setSpacing(Sizes.SPACING_SMALL)

    all_overwrite_btn = QtWidgets.QPushButton("全部覆盖", btn_row)
    all_overwrite_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    all_add_btn = QtWidgets.QPushButton("全部新增", btn_row)
    all_add_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    all_skip_btn = QtWidgets.QPushButton("全部不导出", btn_row)
    all_skip_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(all_overwrite_btn)
    btn_layout.addWidget(all_add_btn)
    btn_layout.addWidget(all_skip_btn)
    btn_layout.addStretch(1)

    cancel_btn = QtWidgets.QPushButton("取消", btn_row)
    cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    ok_btn = QtWidgets.QPushButton("继续导出", btn_row)
    ok_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(ok_btn)
    root.addWidget(btn_row)

    def _set_all(action: str) -> None:
        for row, combo in enumerate(action_combos):
            if table.isRowHidden(row):
                continue
            for i in range(combo.count()):
                if str(combo.itemData(i) or "") == action:
                    combo.setCurrentIndex(i)
                    break

    all_overwrite_btn.clicked.connect(lambda: _set_all("overwrite"))
    all_add_btn.clicked.connect(lambda: _set_all("add"))
    all_skip_btn.clicked.connect(lambda: _set_all("skip"))

    ok_btn.clicked.connect(dlg.accept)
    cancel_btn.clicked.connect(dlg.reject)

    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    out: list[dict[str, str]] = []
    for row, it in enumerate(items):
        combo = action_combos[row]
        action = str(combo.currentData() or "overwrite").strip().lower()
        if action not in {"overwrite", "add", "skip"}:
            raise ValueError(f"unexpected action from combobox: {action!r}")
        out.append({"graph_code_file": str(it["graph_code_file"]), "action": action})
    return out


__all__.append("open_export_center_gil_node_graph_conflicts_dialog")


def open_export_center_gil_template_conflicts_dialog(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    parent_dialog: object,
    conflict_templates: list[dict[str, object]],
) -> list[dict[str, str]] | None:
    """
    导出中心（GIL）：元件模板同名冲突检查对话框。

    输入 conflict_templates item schema（dict）：
    - template_json_file: str（绝对路径）
    - template_name: str
    - existing_template_id_int: int（可选）

    返回：
    - 用户取消：None
    - 用户确认：list[{"template_json_file": str, "action": "overwrite"|"add"|"skip"}]
    """
    items: list[dict[str, object]] = []
    for idx, raw in enumerate(list(conflict_templates or [])):
        if not isinstance(raw, dict):
            raise TypeError(f"conflict_templates[{idx}] must be dict")
        template_json_file = str(raw.get("template_json_file") or "").strip()
        if template_json_file == "":
            raise ValueError(f"conflict_templates[{idx}].template_json_file 不能为空")
        template_name = str(raw.get("template_name") or "").strip()
        if template_name == "":
            raise ValueError(f"conflict_templates[{idx}].template_name 不能为空")
        existing_id = raw.get("existing_template_id_int", None)
        if existing_id is not None and not isinstance(existing_id, int):
            raise TypeError(f"conflict_templates[{idx}].existing_template_id_int must be int or None")
        items.append(
            {
                "template_json_file": template_json_file,
                "template_name": template_name,
                "existing_template_id_int": existing_id,
            }
        )

    dlg = QtWidgets.QDialog(parent_dialog)
    dlg.setWindowTitle("资源冲突检查（GIL）")
    dlg.setModal(True)
    dlg.resize(980, 640)
    dlg.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_MAIN}; }}")

    root = QtWidgets.QVBoxLayout(dlg)
    root.setContentsMargins(Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE)
    root.setSpacing(Sizes.SPACING_MEDIUM)

    tip = QtWidgets.QLabel(
        "检测到基础 .gil 已存在同名元件模板。\n"
        "你可以逐个选择：覆盖（写入同名模板）/ 新增（创建新模板，避免覆盖旧模板）/ 不导出（跳过该模板）。",
        dlg,
    )
    tip.setWordWrap(True)
    tip.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
    root.addWidget(tip)

    search_edit = QtWidgets.QLineEdit(dlg)
    search_edit.setPlaceholderText("搜索元件名（支持模糊匹配）")
    root.addWidget(search_edit)

    table = QtWidgets.QTableWidget(dlg)
    table.setColumnCount(4)
    table.setHorizontalHeaderLabels(["资源类型", "名称", "基础GIL template_id_int", "处理方式"])
    table.setRowCount(len(items))
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    root.addWidget(table, 1)

    action_combos: list[object] = []
    for row, it in enumerate(items):
        template_name = str(it["template_name"])
        template_json_file = str(it["template_json_file"])
        existing_id = it.get("existing_template_id_int", None)

        item_type = QtWidgets.QTableWidgetItem("元件模板")
        item_type.setForeground(QtCore.Qt.GlobalColor.white)
        item_type.setToolTip(template_json_file)
        table.setItem(row, 0, item_type)

        item_name = QtWidgets.QTableWidgetItem(template_name)
        item_name.setToolTip(template_json_file)
        table.setItem(row, 1, item_name)

        id_text = "" if existing_id is None else str(int(existing_id))
        item_id = QtWidgets.QTableWidgetItem(id_text)
        item_id.setToolTip(template_json_file)
        table.setItem(row, 2, item_id)

        combo = QtWidgets.QComboBox(table)
        combo.addItem("覆盖（默认）", "overwrite")
        combo.addItem("新增（创建新模板）", "add")
        combo.addItem("不导出（跳过）", "skip")
        combo.setCurrentIndex(0)
        table.setCellWidget(row, 3, combo)
        action_combos.append(combo)

    def _apply_filter() -> None:
        q = str(search_edit.text() or "").strip().casefold()
        for row, it in enumerate(items):
            if q == "":
                table.setRowHidden(row, False)
                continue
            name = str(it.get("template_name") or "").casefold()
            table.setRowHidden(row, q not in name)

    search_edit.textChanged.connect(_apply_filter)

    btn_row = QtWidgets.QWidget(dlg)
    btn_layout = QtWidgets.QHBoxLayout(btn_row)
    btn_layout.setContentsMargins(0, 0, 0, 0)
    btn_layout.setSpacing(Sizes.SPACING_SMALL)

    all_overwrite_btn = QtWidgets.QPushButton("全部覆盖", btn_row)
    all_overwrite_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    all_add_btn = QtWidgets.QPushButton("全部新增", btn_row)
    all_add_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    all_skip_btn = QtWidgets.QPushButton("全部不导出", btn_row)
    all_skip_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(all_overwrite_btn)
    btn_layout.addWidget(all_add_btn)
    btn_layout.addWidget(all_skip_btn)
    btn_layout.addStretch(1)

    cancel_btn = QtWidgets.QPushButton("取消", btn_row)
    cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    ok_btn = QtWidgets.QPushButton("继续导出", btn_row)
    ok_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(ok_btn)
    root.addWidget(btn_row)

    def _set_all(action: str) -> None:
        for row, combo in enumerate(action_combos):
            if table.isRowHidden(row):
                continue
            for i in range(combo.count()):
                if str(combo.itemData(i) or "") == action:
                    combo.setCurrentIndex(i)
                    break

    all_overwrite_btn.clicked.connect(lambda: _set_all("overwrite"))
    all_add_btn.clicked.connect(lambda: _set_all("add"))
    all_skip_btn.clicked.connect(lambda: _set_all("skip"))

    ok_btn.clicked.connect(dlg.accept)
    cancel_btn.clicked.connect(dlg.reject)

    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    out: list[dict[str, str]] = []
    for row, it in enumerate(items):
        combo = action_combos[row]
        action = str(combo.currentData() or "overwrite").strip().lower()
        if action not in {"overwrite", "add", "skip"}:
            raise ValueError(f"unexpected action from combobox: {action!r}")
        out.append({"template_json_file": str(it["template_json_file"]), "action": action})
    return out


__all__.append("open_export_center_gil_template_conflicts_dialog")


def open_export_center_gil_instance_conflicts_dialog(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    parent_dialog: object,
    conflict_instances: list[dict[str, object]],
) -> list[dict[str, str]] | None:
    """
    导出中心（GIL）：实体实例同名冲突检查对话框。

    输入 conflict_instances item schema（dict）：
    - instance_json_file: str（绝对路径）
    - instance_name: str
    - existing_instance_id_int: int（可选）

    返回：
    - 用户取消：None
    - 用户确认：list[{"instance_json_file": str, "action": "overwrite"|"add"|"skip"}]
    """
    items: list[dict[str, object]] = []
    for idx, raw in enumerate(list(conflict_instances or [])):
        if not isinstance(raw, dict):
            raise TypeError(f"conflict_instances[{idx}] must be dict")
        instance_json_file = str(raw.get("instance_json_file") or "").strip()
        if instance_json_file == "":
            raise ValueError(f"conflict_instances[{idx}].instance_json_file 不能为空")
        instance_name = str(raw.get("instance_name") or "").strip()
        if instance_name == "":
            raise ValueError(f"conflict_instances[{idx}].instance_name 不能为空")
        existing_id = raw.get("existing_instance_id_int", None)
        if existing_id is not None and not isinstance(existing_id, int):
            raise TypeError(f"conflict_instances[{idx}].existing_instance_id_int must be int or None")
        items.append(
            {
                "instance_json_file": instance_json_file,
                "instance_name": instance_name,
                "existing_instance_id_int": existing_id,
            }
        )

    dlg = QtWidgets.QDialog(parent_dialog)
    dlg.setWindowTitle("资源冲突检查（GIL）")
    dlg.setModal(True)
    dlg.resize(980, 640)
    dlg.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_MAIN}; }}")

    root = QtWidgets.QVBoxLayout(dlg)
    root.setContentsMargins(Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE)
    root.setSpacing(Sizes.SPACING_MEDIUM)

    tip = QtWidgets.QLabel(
        "检测到基础 .gil 已存在同名实体。\n"
        "你可以逐个选择：覆盖（写入同名实体）/ 新增（创建新实体，避免覆盖旧实体）/ 不导出（跳过该实体）。",
        dlg,
    )
    tip.setWordWrap(True)
    tip.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
    root.addWidget(tip)

    search_edit = QtWidgets.QLineEdit(dlg)
    search_edit.setPlaceholderText("搜索实体名（支持模糊匹配）")
    root.addWidget(search_edit)

    table = QtWidgets.QTableWidget(dlg)
    table.setColumnCount(4)
    table.setHorizontalHeaderLabels(["资源类型", "名称", "基础GIL instance_id_int", "处理方式"])
    table.setRowCount(len(items))
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    root.addWidget(table, 1)

    action_combos: list[object] = []
    for row, it in enumerate(items):
        instance_name = str(it["instance_name"])
        instance_json_file = str(it["instance_json_file"])
        existing_id = it.get("existing_instance_id_int", None)

        item_type = QtWidgets.QTableWidgetItem("实体摆放")
        item_type.setForeground(QtCore.Qt.GlobalColor.white)
        item_type.setToolTip(instance_json_file)
        table.setItem(row, 0, item_type)

        item_name = QtWidgets.QTableWidgetItem(instance_name)
        item_name.setToolTip(instance_json_file)
        table.setItem(row, 1, item_name)

        id_text = "" if existing_id is None else str(int(existing_id))
        item_id = QtWidgets.QTableWidgetItem(id_text)
        item_id.setToolTip(instance_json_file)
        table.setItem(row, 2, item_id)

        combo = QtWidgets.QComboBox(table)
        combo.addItem("覆盖（默认）", "overwrite")
        combo.addItem("新增（创建新实体）", "add")
        combo.addItem("不导出（跳过）", "skip")
        combo.setCurrentIndex(0)
        table.setCellWidget(row, 3, combo)
        action_combos.append(combo)

    def _apply_filter() -> None:
        q = str(search_edit.text() or "").strip().casefold()
        for row, it in enumerate(items):
            if q == "":
                table.setRowHidden(row, False)
                continue
            name = str(it.get("instance_name") or "").casefold()
            table.setRowHidden(row, q not in name)

    search_edit.textChanged.connect(_apply_filter)

    btn_row = QtWidgets.QWidget(dlg)
    btn_layout = QtWidgets.QHBoxLayout(btn_row)
    btn_layout.setContentsMargins(0, 0, 0, 0)
    btn_layout.setSpacing(Sizes.SPACING_SMALL)

    all_overwrite_btn = QtWidgets.QPushButton("全部覆盖", btn_row)
    all_overwrite_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    all_add_btn = QtWidgets.QPushButton("全部新增", btn_row)
    all_add_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    all_skip_btn = QtWidgets.QPushButton("全部不导出", btn_row)
    all_skip_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(all_overwrite_btn)
    btn_layout.addWidget(all_add_btn)
    btn_layout.addWidget(all_skip_btn)
    btn_layout.addStretch(1)

    cancel_btn = QtWidgets.QPushButton("取消", btn_row)
    cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    ok_btn = QtWidgets.QPushButton("继续导出", btn_row)
    ok_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(ok_btn)
    root.addWidget(btn_row)

    def _set_all(action: str) -> None:
        for row, combo in enumerate(action_combos):
            if table.isRowHidden(row):
                continue
            for i in range(combo.count()):
                if str(combo.itemData(i) or "") == action:
                    combo.setCurrentIndex(i)
                    break

    all_overwrite_btn.clicked.connect(lambda: _set_all("overwrite"))
    all_add_btn.clicked.connect(lambda: _set_all("add"))
    all_skip_btn.clicked.connect(lambda: _set_all("skip"))

    ok_btn.clicked.connect(dlg.accept)
    cancel_btn.clicked.connect(dlg.reject)

    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    out: list[dict[str, str]] = []
    for row, it in enumerate(items):
        combo = action_combos[row]
        action = str(combo.currentData() or "overwrite").strip().lower()
        if action not in {"overwrite", "add", "skip"}:
            raise ValueError(f"unexpected action from combobox: {action!r}")
        out.append({"instance_json_file": str(it["instance_json_file"]), "action": action})
    return out


__all__.append("open_export_center_gil_instance_conflicts_dialog")
