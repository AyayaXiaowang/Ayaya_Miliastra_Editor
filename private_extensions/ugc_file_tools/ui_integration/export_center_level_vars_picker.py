from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import json


@dataclass(frozen=True, slots=True)
class LevelCustomVariablePickResult:
    meta_by_id: dict[str, dict[str, str]]
    picked_ids: list[str] | None


def collect_all_level_entity_custom_variable_candidates(
    *,
    workspace_root: Path,
    package_id: str,
) -> LevelCustomVariablePickResult:
    """
    收集“关卡实体自定义变量（全部）”候选（按 LevelVariableDefinition.variable_id）。

    语义：
    - 扫描项目存档的 `实体摆放/*.json`，取 `metadata.is_level_entity=true` 的实例引用到的 `metadata.custom_variable_file`（VARIABLE_FILE_ID）；
    - 从 shared + project 的 `管理配置/关卡变量/自定义变量/**/*.py` 加载变量文件（VARIABLE_FILE_ID + LEVEL_VARIABLES）；
- 仅保留 `owner=="level"` 的变量（owner 缺失会 fail-fast 报错，避免写回阶段误把玩家/第三方变量写入关卡实体）；
    - 返回：
      - meta_by_id：用于 UI 预览/识别表展示（variable_name/type/source）
      - picked_ids：稳定排序后的“全部候选 variable_id”（可能为空列表）
    """
    from importlib.machinery import SourceFileLoader

    from engine.graph.models.package_model import LevelVariableDefinition
    from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs

    ws_root = Path(workspace_root).resolve()
    pkg_id = str(package_id or "").strip()
    if pkg_id == "":
        raise ValueError("package_id 不能为空")

    package_root = (ws_root / "assets" / "资源库" / "项目存档" / pkg_id).resolve()
    shared_root = (ws_root / "assets" / "资源库" / "共享").resolve()

    # 1) 关卡实体绑定的变量文件（VARIABLE_FILE_ID）集合
    allowed_file_ids: set[str] = set()
    instances_dir = (package_root / "实体摆放").resolve()
    if instances_dir.is_dir():
        json_paths = sorted((p for p in instances_dir.rglob("*.json") if p.is_file()), key=lambda p: p.as_posix().casefold())
        for p in json_paths:
            payload = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            meta = payload.get("metadata")
            if not isinstance(meta, dict) or not bool(meta.get("is_level_entity")):
                continue
            refs = normalize_custom_variable_file_refs(meta.get("custom_variable_file"))
            for rid in list(refs or []):
                text = str(rid or "").strip()
                if text != "":
                    allowed_file_ids.add(text)

    # 2) 加载变量文件：shared + project
    def _load_variable_file_payloads_by_file_id(*, base_dir: Path) -> dict[str, list[dict]]:
        base_dir = Path(base_dir).resolve()
        if not base_dir.is_dir():
            return {}
        out: dict[str, list[dict]] = {}
        py_paths = sorted((p for p in base_dir.rglob("*.py") if p.is_file()), key=lambda p: p.as_posix().casefold())
        for py_path in py_paths:
            if "校验" in py_path.stem:
                continue
            module_name = f"code_level_variable_file_{abs(hash(py_path.as_posix()))}"
            module = SourceFileLoader(module_name, str(py_path)).load_module()
            vars_list = getattr(module, "LEVEL_VARIABLES", None)
            if vars_list is None:
                continue
            if not isinstance(vars_list, list):
                raise ValueError(f"LEVEL_VARIABLES 未定义为列表（{py_path}）")

            file_id = getattr(module, "VARIABLE_FILE_ID", None)
            if not isinstance(file_id, str) or str(file_id).strip() == "":
                raise ValueError(f"变量文件缺少 VARIABLE_FILE_ID（{py_path}）")
            file_id_text = str(file_id).strip()
            if file_id_text in out:
                raise ValueError(f"重复的 VARIABLE_FILE_ID：{file_id_text!r}（file={str(py_path)}）")

            payloads: list[dict] = []
            for entry in vars_list:
                if isinstance(entry, LevelVariableDefinition):
                    payload = entry.serialize()
                elif isinstance(entry, dict):
                    payload = dict(entry)
                else:
                    raise ValueError(f"无效的关卡变量条目类型（{py_path}）：{type(entry)!r}")
                if not isinstance(payload, dict):
                    raise TypeError(f"LevelVariableDefinition.serialize() must return dict (file={str(py_path)})")
                payloads.append(payload)
            out[file_id_text] = payloads
        return dict(out)

    shared_custom_dir = (shared_root / "管理配置" / "关卡变量" / "自定义变量").resolve()
    project_custom_dir = (package_root / "管理配置" / "关卡变量" / "自定义变量").resolve()
    payloads_by_file_id: dict[str, list[dict]] = {}
    payloads_by_file_id.update(_load_variable_file_payloads_by_file_id(base_dir=shared_custom_dir))
    project_map = _load_variable_file_payloads_by_file_id(base_dir=project_custom_dir)
    for fid, payloads in project_map.items():
        if fid in payloads_by_file_id:
            raise ValueError(f"变量文件 VARIABLE_FILE_ID 在 shared 与 project 中重复：{fid!r}")
        payloads_by_file_id[str(fid)] = list(payloads)

    # 3) 选择策略
    if not allowed_file_ids:
        stable_level_file_id = f"auto_custom_vars__level__{pkg_id}"
        if stable_level_file_id in payloads_by_file_id:
            allowed_file_ids.add(stable_level_file_id)

    # 4) 构建 candidates（稳定排序：按 variable_name, variable_id）
    candidates: list[tuple[str, str, str, str]] = []
    meta_by_id: dict[str, dict[str, str]] = {}

    if allowed_file_ids:
        # 仅展示/写回：关卡实体绑定的变量文件集合（VARIABLE_FILE_ID）
        file_ids_order = sorted(set(allowed_file_ids), key=lambda t: str(t).casefold())
        for fid in file_ids_order:
            vars_payloads = payloads_by_file_id.get(str(fid))
            if not isinstance(vars_payloads, list):
                continue
            for payload in vars_payloads:
                if not isinstance(payload, dict):
                    continue
                owner = str(payload.get("owner") or "").strip().lower()
                if owner == "":
                    vid = str(payload.get("variable_id") or "").strip()
                    vname = str(payload.get("variable_name") or "").strip()
                    raise ValueError(
                        "关卡实体自定义变量候选缺少 owner（强语义字段）："
                        f"variable_id={vid!r}, variable_name={vname!r}, variable_file_id={fid!r}"
                    )
                if owner != "level":
                    continue
                vid = str(payload.get("variable_id") or "").strip()
                vname = str(payload.get("variable_name") or "").strip()
                vtype = str(payload.get("variable_type") or "").strip()
                if vid == "" or vname == "":
                    continue
                source_text = str(fid)
                candidates.append((vname, vtype, vid, source_text))
                meta_by_id[vid] = {
                    "variable_id": vid,
                    "variable_name": vname,
                    "variable_type": vtype,
                    "source": source_text,
                    "source_file_id": str(fid),
                }
    else:
        # 回退：展示/写回所有 “owner=level 或缺失 owner” 的变量（跨所有变量文件）
        for fid, vars_payloads in payloads_by_file_id.items():
            if not isinstance(vars_payloads, list):
                continue
            for payload in vars_payloads:
                if not isinstance(payload, dict):
                    continue
                owner = str(payload.get("owner") or "").strip().lower()
                if owner == "":
                    vid = str(payload.get("variable_id") or "").strip()
                    vname = str(payload.get("variable_name") or "").strip()
                    raise ValueError(
                        "关卡实体自定义变量候选缺少 owner（强语义字段）："
                        f"variable_id={vid!r}, variable_name={vname!r}, variable_file_id={fid!r}"
                    )
                if owner != "level":
                    continue
                vid = str(payload.get("variable_id") or "").strip()
                vname = str(payload.get("variable_name") or "").strip()
                vtype = str(payload.get("variable_type") or "").strip()
                if vid == "" or vname == "":
                    continue
                source_text = str(fid)
                candidates.append((vname, vtype, vid, source_text))
                meta_by_id[vid] = {
                    "variable_id": vid,
                    "variable_name": vname,
                    "variable_type": vtype,
                    "source": source_text,
                    "source_file_id": str(fid),
                }

    candidates.sort(key=lambda t: (t[0].casefold(), t[2].casefold()))
    picked_ids = [vid for _vname, _vtype, vid, _source in candidates]
    # 去重（保持顺序）
    seen: set[str] = set()
    deduped: list[str] = []
    for vid in picked_ids:
        k = str(vid).casefold()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(str(vid))

    return LevelCustomVariablePickResult(meta_by_id=dict(meta_by_id), picked_ids=list(deduped))


def open_level_custom_variable_picker_dialog(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    parent_dialog: object,
    package_id: str,
    preselected_ids: list[str],
) -> LevelCustomVariablePickResult:
    """
    选择“关卡实体自定义变量”（按 LevelVariableDefinition.variable_id）。

    - 返回 meta_by_id（用于预览展示 variable_name/type/source）
    - 若用户取消，则 picked_ids=None
    """
    from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs
    from engine.resources.level_variable_schema_view import CATEGORY_CUSTOM, LevelVariableSchemaService
    from engine.utils.workspace import (
        get_injected_workspace_root_or_none,
        looks_like_workspace_root,
        resolve_workspace_root,
    )

    pkg_id = str(package_id or "").strip()
    if pkg_id == "":
        raise ValueError("package_id 不能为空")

    injected_root = get_injected_workspace_root_or_none()
    if injected_root is not None and looks_like_workspace_root(injected_root):
        workspace_root = injected_root
    else:
        workspace_root = resolve_workspace_root()

    # 关卡实体绑定的变量文件（VARIABLE_FILE_ID）集合：
    # - 以实体摆放中的关卡实体实例（metadata.is_level_entity=true）的 custom_variable_file 为真源
    # - 若缺失则回退到“自动分配”的稳定 file_id（auto_custom_vars__level__<package_id>），仍能满足主链路需求
    level_entity_variable_file_ids: set[str] = set()
    package_root = (Path(workspace_root) / "assets" / "资源库" / "项目存档" / pkg_id).resolve()
    instances_dir = (package_root / "实体摆放").resolve()
    if instances_dir.is_dir():
        json_paths = sorted(
            [p for p in instances_dir.rglob("*.json") if p.is_file()],
            key=lambda p: p.as_posix().casefold(),
        )
        for p in json_paths:
            payload = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            meta = payload.get("metadata")
            if not isinstance(meta, dict) or not bool(meta.get("is_level_entity")):
                continue
            refs = normalize_custom_variable_file_refs(meta.get("custom_variable_file"))
            for rid in list(refs or []):
                text = str(rid or "").strip()
                if text != "":
                    level_entity_variable_file_ids.add(text)

    svc = LevelVariableSchemaService()
    file_infos = svc.load_all_variable_files(active_package_id=str(pkg_id))

    # 确保选择器“只展示关卡实体变量”：优先按关卡实体绑定的 VARIABLE_FILE_ID 过滤。
    allowed_file_ids: set[str] = set(level_entity_variable_file_ids)
    if not allowed_file_ids:
        stable_level_file_id = f"auto_custom_vars__level__{pkg_id}"
        if stable_level_file_id in file_infos:
            allowed_file_ids.add(stable_level_file_id)
    use_owner_fallback = not bool(allowed_file_ids)

    candidates: list[tuple[str, str, str, str]] = []
    meta_by_id: dict[str, dict[str, str]] = {}
    for file_info in file_infos.values():
        if getattr(file_info, "category", "") != CATEGORY_CUSTOM:
            continue
        fid = str(getattr(file_info, "file_id", "") or "").strip()
        if allowed_file_ids and fid not in allowed_file_ids:
            continue
        for payload in list(getattr(file_info, "variables", []) or []):
            if not isinstance(payload, dict):
                continue
            if use_owner_fallback:
                owner = str(payload.get("owner") or "").strip().lower()
                if owner == "":
                    vid = str(payload.get("variable_id") or "").strip()
                    vname = str(payload.get("variable_name") or "").strip()
                    raise ValueError(
                        "关卡实体自定义变量候选缺少 owner（强语义字段）："
                        f"variable_id={vid!r}, variable_name={vname!r}, variable_file_id={fid!r}"
                    )
                if owner != "level":
                    continue
            vid = str(payload.get("variable_id") or "").strip()
            vname = str(payload.get("variable_name") or "").strip()
            vtype = str(payload.get("variable_type") or "").strip()
            if vid == "" or vname == "":
                continue
            file_name_text = str(getattr(file_info, "file_name", "") or "").strip()
            source_path_text = str(getattr(file_info, "source_path", "") or "").strip()
            source_text = file_name_text or source_path_text or fid
            if fid != "" and fid not in source_text:
                source_text = f"{fid} | {source_text}"
            candidates.append((vname, vtype, vid, source_text))
            meta_by_id[vid] = {
                "variable_id": vid,
                "variable_name": vname,
                "variable_type": vtype,
                "source": source_text,
                "source_file_id": fid,
            }

    candidates.sort(key=lambda t: (t[0].casefold(), t[2].casefold()))

    pick_dialog = QtWidgets.QDialog(parent_dialog)
    pick_dialog.setWindowTitle("选择关卡实体自定义变量")
    pick_dialog.setModal(True)
    pick_dialog.resize(920, 620)
    pick_dialog.setStyleSheet(f"QDialog {{ background-color: {Colors.BG_MAIN}; }}")

    root = QtWidgets.QVBoxLayout(pick_dialog)
    root.setContentsMargins(Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE)
    root.setSpacing(Sizes.SPACING_MEDIUM)

    search_edit = QtWidgets.QLineEdit(pick_dialog)
    search_edit.setPlaceholderText("搜索：变量名 / 类型 / ID / 来源")
    root.addWidget(search_edit)

    tree = QtWidgets.QTreeWidget(pick_dialog)
    tree.setColumnCount(4)
    tree.setHeaderLabels(["变量名", "类型", "ID", "来源"])
    tree.setRootIsDecorated(False)
    tree.setAlternatingRowColors(True)
    tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
    tree.header().setStretchLastSection(True)
    tree.header().setDefaultSectionSize(220)
    root.addWidget(tree, 1)

    preselected = {str(x).casefold() for x in list(preselected_ids) if str(x).strip() != ""}
    for vname, vtype, vid, source_text in candidates:
        item = QtWidgets.QTreeWidgetItem(tree)
        item.setText(0, vname)
        item.setText(1, vtype)
        item.setText(2, vid)
        item.setText(3, source_text)
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, vid)
        item.setFlags(
            item.flags()
            | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            | QtCore.Qt.ItemFlag.ItemIsEnabled
            | QtCore.Qt.ItemFlag.ItemIsSelectable
        )
        item.setCheckState(0, QtCore.Qt.CheckState.Checked if vid.casefold() in preselected else QtCore.Qt.CheckState.Unchecked)

    def _apply_filter() -> None:
        q = str(search_edit.text() or "").strip().casefold()
        for i in range(int(tree.topLevelItemCount())):
            it = tree.topLevelItem(i)
            if it is None:
                continue
            if q == "":
                it.setHidden(False)
                continue
            hay = f"{it.text(0)} {it.text(1)} {it.text(2)} {it.text(3)}".casefold()
            it.setHidden(q not in hay)

    search_edit.textChanged.connect(_apply_filter)

    btn_row = QtWidgets.QWidget(pick_dialog)
    btn_layout = QtWidgets.QHBoxLayout(btn_row)
    btn_layout.setContentsMargins(0, 0, 0, 0)
    btn_layout.setSpacing(Sizes.SPACING_SMALL)

    select_all_btn = QtWidgets.QPushButton("全选(可见)", btn_row)
    select_all_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    select_none_btn = QtWidgets.QPushButton("全不选(可见)", btn_row)
    select_none_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(select_all_btn)
    btn_layout.addWidget(select_none_btn)
    btn_layout.addStretch(1)

    ok_btn = QtWidgets.QPushButton("确定", btn_row)
    ok_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    cancel_btn = QtWidgets.QPushButton("取消", btn_row)
    cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn_layout.addWidget(ok_btn)
    btn_layout.addWidget(cancel_btn)
    root.addWidget(btn_row)

    def _set_visible_check_state(state: object) -> None:
        for i in range(int(tree.topLevelItemCount())):
            it = tree.topLevelItem(i)
            if it is None or it.isHidden():
                continue
            it.setCheckState(0, state)

    select_all_btn.clicked.connect(lambda: _set_visible_check_state(QtCore.Qt.CheckState.Checked))
    select_none_btn.clicked.connect(lambda: _set_visible_check_state(QtCore.Qt.CheckState.Unchecked))
    ok_btn.clicked.connect(pick_dialog.accept)
    cancel_btn.clicked.connect(pick_dialog.reject)

    if pick_dialog.exec() != int(QtWidgets.QDialog.DialogCode.Accepted):
        return LevelCustomVariablePickResult(meta_by_id=dict(meta_by_id), picked_ids=None)

    picked: list[str] = []
    for i in range(int(tree.topLevelItemCount())):
        it = tree.topLevelItem(i)
        if it is None:
            continue
        if it.checkState(0) != QtCore.Qt.CheckState.Checked:
            continue
        vid = str(it.data(0, QtCore.Qt.ItemDataRole.UserRole) or "").strip()
        if vid != "":
            picked.append(vid)

    # 去重（保持顺序）
    seen: set[str] = set()
    deduped: list[str] = []
    for x in picked:
        k = str(x).casefold()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(str(x))

    return LevelCustomVariablePickResult(meta_by_id=dict(meta_by_id), picked_ids=list(deduped))

