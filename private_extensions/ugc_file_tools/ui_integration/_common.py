from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def resolve_packages_root_dir(*, workspace_root: Path) -> Path:
    from engine.utils.resource_library_layout import get_packages_root_dir

    resource_library_root = Path(workspace_root) / "assets" / "资源库"
    return get_packages_root_dir(resource_library_root)


def get_selected_package_id(main_window: object) -> str:
    """
    返回“当前操作目标”的项目存档 ID。

    优先级（从高到低）：
    - **仅当当前视图为 PACKAGES**：项目存档页左侧列表当前选中项（预览语义：不必切换为当前也可导出）
    - 其它视图：主窗口 PackageController.current_package_id（全局语义：用于顶部工具栏“导出中心”等入口）
    """
    # 说明：
    # - 项目存档页（PACKAGES）左侧“选中”是预览语义，允许导出非当前存档；
    # - 但在其它视图下，package_library_widget 可能保留上次预览选中（例如 global_view），
    #   若仍优先读取会导致顶部导出入口误判“未选择有效的项目存档”。
    in_packages_view = False
    try:
        from app.models.view_modes import ViewMode

        central_stack = getattr(main_window, "central_stack", None)
        current_index = central_stack.currentIndex() if central_stack is not None else None
        if isinstance(current_index, int) and ViewMode.from_index(int(current_index)) == ViewMode.PACKAGES:
            in_packages_view = True
    except Exception:
        # 缺少 central_stack / ViewMode 或其它异常时，保守认为“不在 PACKAGES 视图”
        in_packages_view = False

    if in_packages_view:
        package_library_widget = getattr(main_window, "package_library_widget", None)
        if package_library_widget is not None:
            selection = getattr(package_library_widget, "get_selection", None)
            if callable(selection):
                sel_obj = selection()
                raw_kind = getattr(sel_obj, "kind", "") if sel_obj is not None else ""
                raw_id = getattr(sel_obj, "id", "") if sel_obj is not None else ""
                # 仅接受 kind="package" 的选择，避免其它协议漂移/特殊视图污染顶部入口。
                if str(raw_kind) == "package" and isinstance(raw_id, str) and raw_id.strip():
                    return raw_id

    package_controller = getattr(main_window, "package_controller", None)
    raw_current = getattr(package_controller, "current_package_id", "") if package_controller is not None else ""
    return raw_current if isinstance(raw_current, str) else ""


@dataclass(frozen=True, slots=True)
class ToolbarProgressWidgetSpec:
    """
    工具栏进度条 Widget 的可参数化配置。

    - kind: 用于缓存/去重的稳定 key（同 kind 必须表达同一类进度条）
    - initial_label: 初始显示文案
    - progress_width: 进度条宽度（像素）
    """

    kind: str
    initial_label: str
    progress_width: int = 180


_PROGRESS_WIDGET_CLASS_CACHE: dict[str, type] = {}


def make_toolbar_progress_widget_cls(
    spec: ToolbarProgressWidgetSpec,
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
) -> type:
    """
    返回稳定的进度条 Widget 类型（避免在回调函数内定义 class 导致 isinstance 失效）。

    注意：不在模块顶层导入 PyQt6；QtCore/QtWidgets/Colors/Sizes 由调用方传入。
    """
    key = str(spec.kind or "").strip()
    if key == "":
        raise ValueError("ToolbarProgressWidgetSpec.kind 不能为空")
    cached = _PROGRESS_WIDGET_CLASS_CACHE.get(key)
    if cached is not None:
        return cached

    label_text = str(spec.initial_label or "").strip() or "准备…"
    progress_width = int(spec.progress_width) if int(spec.progress_width) > 0 else 180

    class _ToolbarProgressWidget(QtWidgets.QWidget):
        def __init__(self, parent: QtWidgets.QWidget) -> None:
            super().__init__(parent)
            layout = QtWidgets.QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(Sizes.SPACING_SMALL)

            self._label = QtWidgets.QLabel(str(label_text), self)
            self._label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            self._label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")

            self._progress = QtWidgets.QProgressBar(self)
            self._progress.setRange(0, 0)  # busy
            self._progress.setValue(0)
            self._progress.setFixedWidth(int(progress_width))
            self._progress.setTextVisible(True)
            self._progress.setFormat("%v/%m")

            layout.addWidget(self._label)
            layout.addWidget(self._progress)

        def set_status(self, *, label: str, current: int, total: int) -> None:
            self._label.setText(str(label or ""))
            if int(total) <= 0:
                self._progress.setRange(0, 0)
                self._progress.setValue(0)
                self._progress.setFormat("…")
            else:
                self._progress.setRange(0, int(total))
                self._progress.setValue(int(current))
                self._progress.setFormat("%v/%m")
            self.setToolTip(f"{label}\n（{int(current)}/{int(total)}）")

    _PROGRESS_WIDGET_CLASS_CACHE[key] = _ToolbarProgressWidget
    return _ToolbarProgressWidget


# ==================== Graph Code 占位符扫描（entity_key/component_key） ====================


@dataclass(frozen=True, slots=True)
class IdRefPlaceholderUsage:
    """
    从 Graph Code（节点图源码）中扫描到的 entity_key/component_key 占位符使用情况。

    说明：
    - 仅扫描 **Python 字符串字面量**（tokenize.STRING），避免将 `owner_entity:` 等代码片段误判为占位符。
    - 约定占位符（与写回阶段一致）：
      - 实体：`entity_key:<实体名>` / `entity:<实体名>`
      - 元件：`component_key:<元件名>` / `component:<元件名>`
    """

    entity_names: frozenset[str]
    component_names: frozenset[str]

    @property
    def is_used(self) -> bool:
        return bool(self.entity_names or self.component_names)


_ID_REF_PLACEHOLDER_CACHE: dict[str, tuple[int, IdRefPlaceholderUsage]] = {}


def _string_literal_prefix(text: str) -> str:
    """
    返回 Python 字符串字面量的前缀（例如 r/f/b/fr/rf...），不包含引号本身。

    tokenize 返回的 STRING token 形如：r"..."、f'...'、三引号字符串（例如 '''...'''）等。
    """
    s = str(text or "")
    i = 0
    while i < len(s) and s[i] not in {"'", '"'}:
        i += 1
    return s[:i].lower()


def _iter_python_string_literals_from_file(*, file_path: Path) -> list[str]:
    """
    读取 Python 文件并返回所有字符串字面量的“真实内容”（已去掉引号/转义）。

    注意：
    - 跳过 f-string（无法用 ast.literal_eval 解析，且占位符不应依赖运行时拼接）。
    """
    import ast
    import tokenize

    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    out: list[str] = []
    with tokenize.open(str(p)) as f:
        for tok in tokenize.generate_tokens(f.readline):
            if tok.type != tokenize.STRING:
                continue
            literal = str(tok.string or "")
            prefix = _string_literal_prefix(literal)
            if "f" in prefix:
                continue
            value = ast.literal_eval(literal)
            if isinstance(value, str):
                out.append(value)
    return out


def scan_id_ref_placeholders_in_graph_code_file(*, graph_code_file: Path) -> IdRefPlaceholderUsage:
    """
    扫描单个节点图源码文件内的 entity/component 占位符，并做缓存（按 mtime_ns）。
    """
    p = Path(graph_code_file).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    cache_key = p.as_posix()
    mtime_ns = int(p.stat().st_mtime_ns)
    cached = _ID_REF_PLACEHOLDER_CACHE.get(cache_key)
    if cached is not None and int(cached[0]) == int(mtime_ns):
        return cached[1]

    entity_names: set[str] = set()
    component_names: set[str] = set()

    for s in _iter_python_string_literals_from_file(file_path=p):
        raw = str(s or "").strip()
        if raw == "":
            continue
        lowered = raw.lower()

        if lowered.startswith("entity_key:"):
            key = raw[len("entity_key:") :].strip()
            if key != "":
                entity_names.add(key)
            continue
        if lowered.startswith("entity:"):
            key = raw[len("entity:") :].strip()
            if key != "":
                entity_names.add(key)
            continue
        if lowered.startswith("component_key:"):
            key = raw[len("component_key:") :].strip()
            if key != "":
                component_names.add(key)
            continue
        if lowered.startswith("component:"):
            key = raw[len("component:") :].strip()
            if key != "":
                component_names.add(key)
            continue

    usage = IdRefPlaceholderUsage(
        entity_names=frozenset(entity_names),
        component_names=frozenset(component_names),
    )
    _ID_REF_PLACEHOLDER_CACHE[cache_key] = (int(mtime_ns), usage)
    return usage


def scan_id_ref_placeholders_in_graph_code_files(*, graph_code_files: list[Path]) -> IdRefPlaceholderUsage:
    """
    扫描一组节点图源码文件，返回合并后的占位符使用集合（去重）。
    """
    entity_names: set[str] = set()
    component_names: set[str] = set()
    for p in list(graph_code_files or []):
        usage = scan_id_ref_placeholders_in_graph_code_file(graph_code_file=Path(p))
        entity_names.update(usage.entity_names)
        component_names.update(usage.component_names)
    return IdRefPlaceholderUsage(
        entity_names=frozenset(entity_names),
        component_names=frozenset(component_names),
    )


def format_missing_id_ref_gil_message(*, subject: str, usage: IdRefPlaceholderUsage) -> str:
    """
    用于 UI：当检测到占位符但未选择参考 `.gil` 时，输出“实体/元件名清单”提示文案。
    """
    subj = str(subject or "").strip() or "节点图"
    if not bool(usage.is_used):
        raise ValueError("usage 为空：不应格式化缺失占位符参考提示")

    def _sorted(xs: frozenset[str]) -> list[str]:
        return sorted([str(x) for x in xs if str(x).strip() != ""], key=lambda t: t.casefold())

    entity_list = _sorted(usage.entity_names)
    component_list = _sorted(usage.component_names)

    lines: list[str] = [
        f"检测到{subj}使用了 entity_key/component_key 占位符，但未选择“占位符参考 GIL”。",
        "本次需要回填的名称如下（按名称匹配）：",
    ]
    if entity_list:
        lines.append(f"实体（entity_key/entity）[{len(entity_list)}]：")
        for name in entity_list:
            lines.append(f"- {name}")
    if component_list:
        lines.append(f"元件（component_key/component）[{len(component_list)}]：")
        for name in component_list:
            lines.append(f"- {name}")
    lines.append("请在右侧选择一个包含以上同名实体/元件的 `.gil` 文件。")
    return "\n".join(lines)

