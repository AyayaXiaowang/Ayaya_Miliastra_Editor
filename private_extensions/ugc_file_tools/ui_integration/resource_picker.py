from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResourceSelectionItem:
    """资源选择条目（以相对路径为主键）。"""

    source_root: str  # "project" | "shared"
    category: str  # "graphs" | "templates" | "instances" | "player_templates" | "ui_src" | "mgmt_cfg" | "level_entity_vars" | "resource_repo"
    relative_path: str  # relative to the source root directory
    absolute_path: Path

    @property
    def key(self) -> str:
        return f"{self.source_root}:{self.relative_path}"


def _extract_top_level_json_string_field(
    *,
    file_path: Path,
    field_name: str,
    max_chars: int = 200_000,
) -> str | None:
    """
    从 JSON 文件开头快速提取“根对象”的某个字符串字段（例如 `name`）。

    设计动机：
    - `实体摆放/*.json` 可能包含 shape-editor 导出的巨大 payload（例如数万行 objects），
      若为了展示名称而 `json.loads` 整文件会明显卡 UI。

    约束：
    - 不做完整 JSON 校验；只做“足够解析到根对象的 key/value”的扫描；
    - 仅扫描 `max_chars` 字符；未命中返回 None；
    - 仅支持提取根对象里 value 为字符串的字段。
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        return None
    want = str(field_name or "").strip()
    if want == "":
        return None
    limit = int(max_chars) if int(max_chars) > 0 else 200_000

    import json

    stack: list[str] = []
    tl_mode: str | None = None  # "key" | "colon" | "value"
    cur_key: str | None = None

    in_string = False
    escape = False
    raw_buf: list[str] = []

    read_total = 0
    with p.open("r", encoding="utf-8-sig") as f:
        while read_total < limit:
            chunk = f.read(min(8192, limit - read_total))
            if chunk == "":
                break
            read_total += len(chunk)

            for ch in chunk:
                if in_string:
                    if escape:
                        raw_buf.append(ch)
                        escape = False
                        continue
                    if ch == "\\":
                        raw_buf.append(ch)
                        escape = True
                        continue
                    if ch == '"':
                        raw = "".join(raw_buf)
                        raw_buf.clear()
                        in_string = False

                        s = json.loads('"' + raw + '"')
                        if stack == ["{"]:
                            if tl_mode == "key":
                                cur_key = str(s)
                                tl_mode = "colon"
                            elif tl_mode == "value":
                                if cur_key == want:
                                    out = str(s).strip()
                                    return out if out != "" else None
                        continue

                    raw_buf.append(ch)
                    continue

                # not in string
                if stack == ["{"] and tl_mode == "value" and cur_key == want:
                    # root.name 的 value 必须是 string；若遇到其它 token，直接判定为“不可提取”
                    if ch.isspace():
                        continue
                    if ch != '"':
                        return None

                if ch == '"':
                    in_string = True
                    escape = False
                    raw_buf.clear()
                    continue

                if ch == "{":
                    stack.append("{")
                    if stack == ["{"]:
                        tl_mode = "key"
                        cur_key = None
                    continue
                if ch == "[":
                    stack.append("[")
                    continue
                if ch == "}" or ch == "]":
                    if stack:
                        stack.pop()
                    if not stack:
                        return None
                    continue

                if stack == ["{"]:
                    if ch == ":":
                        if tl_mode == "colon":
                            tl_mode = "value"
                        continue
                    if ch == ",":
                        tl_mode = "key"
                        cur_key = None
                        continue

    return None


def _extract_top_level_json_string_fields(
    *,
    file_path: Path,
    max_chars: int = 200_000,
) -> dict[str, str]:
    """
    从 JSON 文件开头快速提取“根对象”的所有「字符串字段」。

    用途：
    - 管理配置 JSON 的“显示名”字段并不总是 `name`（例如 `camera_name/level_name/...`），
      需要提取多个候选字段并做优先级选择；
    - 仍保持“只扫文件开头、不整文件 json.loads”的性能约束。

    约束同 `_extract_top_level_json_string_field`：
    - 不做完整 JSON 校验；
    - 仅扫描 `max_chars` 字符；
    - 仅收集根对象里 value 为字符串的字段。
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        return {}
    limit = int(max_chars) if int(max_chars) > 0 else 200_000

    import json

    stack: list[str] = []
    tl_mode: str | None = None  # "key" | "colon" | "value"
    cur_key: str | None = None

    in_string = False
    escape = False
    raw_buf: list[str] = []

    out: dict[str, str] = {}
    read_total = 0
    with p.open("r", encoding="utf-8-sig") as f:
        while read_total < limit:
            chunk = f.read(min(8192, limit - read_total))
            if chunk == "":
                break
            read_total += len(chunk)

            for ch in chunk:
                if in_string:
                    if escape:
                        raw_buf.append(ch)
                        escape = False
                        continue
                    if ch == "\\":
                        raw_buf.append(ch)
                        escape = True
                        continue
                    if ch == '"':
                        raw = "".join(raw_buf)
                        raw_buf.clear()
                        in_string = False

                        s = json.loads('"' + raw + '"')
                        if stack == ["{"]:
                            if tl_mode == "key":
                                cur_key = str(s)
                                tl_mode = "colon"
                            elif tl_mode == "value":
                                if cur_key is not None:
                                    v = str(s).strip()
                                    if v != "":
                                        out[str(cur_key)] = v
                        continue

                    raw_buf.append(ch)
                    continue

                # not in string
                if ch == '"':
                    in_string = True
                    escape = False
                    raw_buf.clear()
                    continue

                if ch == "{":
                    stack.append("{")
                    if stack == ["{"]:
                        tl_mode = "key"
                        cur_key = None
                    continue
                if ch == "[":
                    stack.append("[")
                    continue
                if ch == "}" or ch == "]":
                    if stack:
                        stack.pop()
                    if not stack:
                        return out
                    continue

                if stack == ["{"]:
                    if ch == ":":
                        if tl_mode == "colon":
                            tl_mode = "value"
                        continue
                    if ch == ",":
                        tl_mode = "key"
                        cur_key = None
                        continue

    return out


def _pick_display_name_from_fields(fields: dict[str, str]) -> str | None:
    if not fields:
        return None

    def _get_case_insensitive(name: str) -> str | None:
        want = str(name or "").strip().casefold()
        if want == "":
            return None
        for k, v in fields.items():
            if str(k or "").casefold() == want:
                vv = str(v or "").strip()
                return vv if vv != "" else None
        return None

    def _get_first(names: list[str]) -> str | None:
        for n in list(names or []):
            v = _get_case_insensitive(str(n))
            if v is not None:
                return v
        return None

    # === 常见“显示名”字段优先级（管理配置 JSON/Python payload 共用） ===
    explicit = _get_first(
        [
            "display_name",
            "displayName",
            "DISPLAY_NAME",
            "title",
            "label",
            # 常见 mgmt_cfg JSON：*_name 优先于 name（name 往往是 id）
            "camera_name",
            "light_name",
            "level_name",
            "save_point_name",
            "template_name",
            "signal_name",
            "struct_name",
            # 关卡变量文件（Python）：模块级常量
            "VARIABLE_FILE_NAME",
            "variable_file_name",
            # 最后兜底：name（部分资源 name=真实名；但更常见是 id）
            "name",
        ]
    )
    if explicit is not None:
        return explicit

    # === 泛化：任意 *_name（排除 name） ===
    for k, v in fields.items():
        kk = str(k or "").strip()
        if kk == "":
            continue
        if kk.casefold() == "name":
            continue
        if kk.casefold().endswith("_name"):
            vv = str(v or "").strip()
            if vv != "":
                return vv

    return None


def _extract_top_level_py_string_fields(*, file_path: Path) -> dict[str, str]:
    """
    从 Python 管理配置文件中提取“模块级字符串信息”，用于资源选择器显示名。

    覆盖常见形态：
    - `VARIABLE_FILE_NAME = "..."`（关卡变量文件）
    - `*_PAYLOAD = {...}` / `*_PAYLOAD: Dict[...] = {...}`（信号/结构体/局内存档模板等）
      仅提取 payload 字典的顶层 str->str 键值（例如 `signal_name/struct_name/save_point_name/...`）。
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        return {}
    text = p.read_text(encoding="utf-8-sig")

    import ast

    mod = ast.parse(text, filename=str(p))
    out: dict[str, str] = {}

    def _collect_assignment(*, target_name: str, value) -> None:
        name = str(target_name or "")
        if name == "":
            return

        # module-level string constants
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            s = str(value.value).strip()
            if s != "":
                out[name] = s
            return

        # payload dict literals
        if name.casefold().endswith("payload") and isinstance(value, ast.Dict):
            for k, v in zip(list(value.keys), list(value.values)):
                if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                    continue
                if not isinstance(v, ast.Constant) or not isinstance(v.value, str):
                    continue
                kk = str(k.value).strip()
                vv = str(v.value).strip()
                if kk != "" and vv != "":
                    out[kk] = vv

    for node in list(getattr(mod, "body", []) or []):
        if isinstance(node, ast.Assign):
            for t in list(getattr(node, "targets", []) or []):
                if isinstance(t, ast.Name):
                    _collect_assignment(target_name=str(t.id), value=node.value)
        elif isinstance(node, ast.AnnAssign):
            t = getattr(node, "target", None)
            if isinstance(t, ast.Name) and node.value is not None:
                _collect_assignment(target_name=str(t.id), value=node.value)

    return out


def get_mgmt_cfg_display_name(*, file_path: Path) -> str | None:
    """
    计算“管理配置文件”的更友好显示名（用于资源选择器）。

    规则：
    - JSON：优先 *_name（如 camera_name/level_name/...），其次 display_name，再兜底 name
    - Python：优先 payload 字典里的 *_name（如 signal_name/struct_name/...），其次 VARIABLE_FILE_NAME/NAME 等
    - 失败则返回 None，由调用方回退到文件名
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        return None

    suffix = str(p.suffix or "").lower()
    if suffix == ".json":
        fields = _extract_top_level_json_string_fields(file_path=p)
        name = _pick_display_name_from_fields(fields)
        return str(name) if isinstance(name, str) and str(name).strip() != "" else None
    if suffix == ".py":
        fields = _extract_top_level_py_string_fields(file_path=p)
        name = _pick_display_name_from_fields(fields)
        return str(name) if isinstance(name, str) and str(name).strip() != "" else None

    return None


def _is_ignored_path_part(part: str) -> bool:
    p = str(part or "")
    if p in {"__pycache__", ".git"}:
        return True
    if p.startswith("."):
        return True
    return False


def _should_ignore_file(file_path: Path) -> bool:
    if not file_path.is_file():
        return True
    name = file_path.name
    if name.startswith("."):
        return True
    if name.startswith("_"):
        return True
    if name.lower() == "claude.md":
        return True
    if file_path.parent.name == "__pycache__":
        return True
    return False


def _scan_graph_code_files(graph_root: Path) -> list[Path]:
    if not graph_root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(graph_root.rglob("*.py"), key=lambda x: x.as_posix().casefold()):
        if _should_ignore_file(p):
            continue
        if "校验" in p.stem:
            continue
        out.append(p)
    return out


def _scan_template_json_files(templates_root: Path) -> list[Path]:
    if not templates_root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(templates_root.rglob("*.json"), key=lambda x: x.as_posix().casefold()):
        if _should_ignore_file(p):
            continue
        # 元件库索引（列表）不是单模板 JSON，避免被当作“模板文件”误选进导出/写回流程
        if p.name == "templates_index.json":
            continue
        # 元件库：允许子目录结构；这里仅做最基础忽略策略
        out.append(p)
    return out


def _scan_instance_json_files(instances_root: Path) -> list[Path]:
    if not instances_root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(instances_root.rglob("*.json"), key=lambda x: x.as_posix().casefold()):
        if _should_ignore_file(p):
            continue
        if p.name == "instances_index.json":
            continue
        # 一些解析辅助 JSON（非 InstanceConfig）
        if p.name.startswith("自研_"):
            continue
        out.append(p)
    return out


def _scan_player_template_json_files(player_templates_root: Path) -> list[Path]:
    """
    扫描“玩家模板（战斗预设）”JSON。

    注意：
    - 目录内可能包含“原始解析/pyugc dump/变量抽取”等辅助 JSON，它们不是可导出的玩家模板资源；
      若误选交给导出工具会 fail-fast，因此在资源选择器侧先行过滤。
    """
    if not player_templates_root.is_dir():
        return []

    out: list[Path] = []
    for p in sorted(player_templates_root.rglob("*.json"), key=lambda x: x.as_posix().casefold()):
        if _should_ignore_file(p):
            continue
        # 索引文件（列表）不是单资源 JSON
        if p.name.lower().endswith("_index.json") or p.name.lower().endswith("index.json"):
            continue
        # 忽略“原始解析”目录下的 pyugc dump / variables 提取等辅助 JSON
        if "原始解析" in p.parts:
            continue
        lower_name = str(p.name).lower()
        if lower_name.endswith(".pyugc.json") or lower_name.endswith(".variables.json"):
            continue
        out.append(p)

    return out


def _scan_all_files(root: Path, *, excluded_top_dirs: set[str]) -> list[Path]:
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(root.rglob("*"), key=lambda x: x.as_posix().casefold()):
        if p.is_dir():
            continue
        # 过滤掉排除目录
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        parts = [str(x) for x in rel.parts]
        if not parts:
            continue
        if parts[0] in excluded_top_dirs:
            continue
        if any(_is_ignored_path_part(part) for part in parts):
            continue
        if _should_ignore_file(p):
            continue
        out.append(p)
    return out


def _scan_management_cfg_files(mgmt_root: Path) -> list[Path]:
    if not mgmt_root.is_dir():
        return []
    # NOTE:
    # - 导出中心的 mgmt_cfg 选择当前只用于“解析信号/结构体的 ID 列表”，并驱动：
    #   - .gia：导出基础信号/基础结构体（局内存档结构体仅用于 .gil 写回，.gia 不导出）
    #   - .gil：写回信号/结构体定义
    # - 因此这里必须 **白名单收敛**：只展示导出/写回链路实际会消费的“代码级定义资源”，
    #   避免把整个 管理配置 目录（UI 工件/导出缓存/校验脚本/项目杂项 JSON）都暴露给用户造成误选。

    allowed_roots = [
        (mgmt_root / "信号").resolve(),
        (mgmt_root / "结构体定义" / "基础结构体").resolve(),
        (mgmt_root / "结构体定义" / "局内存档结构体").resolve(),
    ]

    out: list[Path] = []
    for root in allowed_roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.py"), key=lambda x: x.as_posix().casefold()):
            if _should_ignore_file(p):
                continue
            # 校验脚本属于工具入口，不是“可导出/可写回资源定义”，避免误选。
            if "校验" in str(p.stem):
                continue
            out.append(p)

    # 去重 + 稳定排序（防御：软链接/大小写差异）
    seen: set[str] = set()
    dedup: list[Path] = []
    for p in out:
        k = p.as_posix()
        if k in seen:
            continue
        seen.add(k)
        dedup.append(p)
    dedup.sort(key=lambda x: x.as_posix().casefold())
    return dedup


def _scan_ui_source_files(ui_src_root: Path) -> list[Path]:
    if not ui_src_root.is_dir():
        return []
    out: list[Path] = []
    # 约定：UI源码目录只收录 HTML（每个功能页一个 HTML），不应混入 json/bundle 等其它产物
    patterns = ["*.html", "*.htm"]
    for pat in patterns:
        for p in sorted(ui_src_root.rglob(pat), key=lambda x: x.as_posix().casefold()):
            if not p.is_file():
                continue
            if _should_ignore_file(p):
                continue
            out.append(p)
    # 去重（防御：大小写/软链接导致重复）
    seen: set[str] = set()
    dedup: list[Path] = []
    for p in out:
        k = p.as_posix()
        if k in seen:
            continue
        seen.add(k)
        dedup.append(p)
    dedup.sort(key=lambda x: x.as_posix().casefold())
    return dedup


def build_resource_selection_items(
    *,
    project_root: Path,
    shared_root: Path,
    include_shared: bool,
) -> dict[str, list[ResourceSelectionItem]]:
    """构建默认资源候选列表（按 category 分组）。"""
    result: dict[str, list[ResourceSelectionItem]] = {
        "graphs": [],
        "templates": [],
        "instances": [],
        "player_templates": [],
        "ui_src": [],
        "level_entity_vars": [],
        "mgmt_cfg": [],
        "resource_repo": [],
    }

    def _add_items(source_root: str, base_dir: Path, category: str, files: list[Path]) -> None:
        for f in files:
            try:
                rel = f.relative_to(base_dir).as_posix()
            except ValueError:
                continue
            result[category].append(
                ResourceSelectionItem(
                    source_root=source_root,
                    category=category,
                    relative_path=str(rel),
                    absolute_path=Path(f).resolve(),
                )
            )

    # project
    _add_items("project", project_root, "graphs", _scan_graph_code_files(project_root / "节点图"))
    _add_items("project", project_root, "templates", _scan_template_json_files(project_root / "元件库"))
    _add_items("project", project_root, "instances", _scan_instance_json_files(project_root / "实体摆放"))
    _add_items(
        "project",
        project_root,
        "player_templates",
        _scan_player_template_json_files(project_root / "战斗预设" / "玩家模板"),
    )
    _add_items("project", project_root, "ui_src", _scan_ui_source_files(project_root / "管理配置" / "UI源码"))
    # 关卡实体自定义变量：导出中心 GIL 模式下可选的“自动全量补齐”写回项（非文件列表）。
    # 这里放一个稳定的“虚拟资源条目”作为左侧勾选入口。
    result["level_entity_vars"].append(
        ResourceSelectionItem(
            source_root="project",
            category="level_entity_vars",
            relative_path="关卡实体自定义变量（全部）",
            absolute_path=(Path(project_root).resolve() / "管理配置" / "关卡变量").resolve(),
        )
    )
    _add_items("project", project_root, "mgmt_cfg", _scan_management_cfg_files(project_root / "管理配置"))
    _add_items(
        "project",
        project_root,
        "resource_repo",
        _scan_all_files(project_root, excluded_top_dirs={"节点图", "管理配置", "元件库", "实体摆放"}),
    )

    # shared
    if include_shared:
        _add_items("shared", shared_root, "graphs", _scan_graph_code_files(shared_root / "节点图"))
        _add_items("shared", shared_root, "templates", _scan_template_json_files(shared_root / "元件库"))
        _add_items("shared", shared_root, "instances", _scan_instance_json_files(shared_root / "实体摆放"))
        _add_items(
            "shared",
            shared_root,
            "player_templates",
            _scan_player_template_json_files(shared_root / "战斗预设" / "玩家模板"),
        )
        _add_items("shared", shared_root, "ui_src", _scan_ui_source_files(shared_root / "管理配置" / "UI源码"))
        _add_items("shared", shared_root, "mgmt_cfg", _scan_management_cfg_files(shared_root / "管理配置"))
        _add_items(
            "shared",
            shared_root,
            "resource_repo",
            _scan_all_files(shared_root, excluded_top_dirs={"节点图", "管理配置", "元件库", "实体摆放"}),
        )

    # 稳定排序
    for items in result.values():
        items.sort(key=lambda it: (it.source_root, it.relative_path.casefold()))
    return result


_RESOURCE_PICKER_WIDGET_CLASS_CACHE: dict[str, type] = {}


def make_resource_picker_widget_cls(*, QtCore: object, QtWidgets: object, Colors: object, Sizes: object) -> type:
    """
    返回稳定的“资源选择器”Widget 类型（可嵌入其它对话框复用）。

    约束：
    - 不在模块顶层 import PyQt6；
    - QtCore/QtWidgets/Colors/Sizes 由调用方传入；
    - Widget 内以 `ResourceSelectionItem.key` 作为稳定主键（source_root + relative_path）。
    """
    cache_key = "ResourcePickerWidget"
    cached = _RESOURCE_PICKER_WIDGET_CLASS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    class _ResourcePickerWidget(QtWidgets.QWidget):
        selection_changed = QtCore.pyqtSignal()

        def __init__(
            self,
            parent: QtWidgets.QWidget,
            *,
            catalog: dict[str, list[ResourceSelectionItem]],
            allowed_categories: set[str] | None = None,
            preselected_keys: set[str] | None = None,
            show_remove_button: bool = True,
            show_selected_panel: bool = True,
            count_format: str = "paren",  # "paren" | "plain" | "none"
            show_relative_path_column: bool = True,
        ) -> None:
            super().__init__(parent)
            self._catalog: dict[str, list[ResourceSelectionItem]] = dict(catalog or {})
            self._allowed_categories: set[str] | None = set(allowed_categories) if allowed_categories else None
            self._show_selected_panel: bool = bool(show_selected_panel)
            self._count_format: str = str(count_format or "paren").strip().lower() or "paren"
            self._show_relative_path_column: bool = bool(show_relative_path_column)

            # === key -> item 的稳定映射（用于 prune / 恢复） ===
            items_by_key: dict[str, ResourceSelectionItem] = {}
            for group in self._catalog.values():
                for it in list(group):
                    items_by_key[it.key] = it
            self._items_by_key = items_by_key

            # === 选中态（以 key 为主） ===
            selected_by_key: dict[str, ResourceSelectionItem] = {}
            if preselected_keys:
                wanted = {str(x) for x in set(preselected_keys) if str(x)}
                for k in wanted:
                    it = self._items_by_key.get(k)
                    if it is not None:
                        selected_by_key[k] = it
            self._selected_by_key = selected_by_key

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(Sizes.SPACING_MEDIUM)

            # === 搜索行 ===
            search_row = QtWidgets.QWidget(self)
            search_layout = QtWidgets.QHBoxLayout(search_row)
            search_layout.setContentsMargins(0, 0, 0, 0)
            search_layout.setSpacing(Sizes.SPACING_SMALL)

            self.search_edit = QtWidgets.QLineEdit(search_row)
            self.search_edit.setPlaceholderText("搜索（按名称/路径片段过滤）…")

            self.only_selected_cb = QtWidgets.QCheckBox("只看已选", search_row)
            self.only_selected_cb.setChecked(False)

            self.stats_label = QtWidgets.QLabel("", search_row)
            self.stats_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")

            search_layout.addWidget(self.search_edit, 1)
            search_layout.addWidget(self.only_selected_cb)
            search_layout.addWidget(self.stats_label)
            layout.addWidget(search_row)

            if self._show_selected_panel:
                splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)
                layout.addWidget(splitter, 1)

                self.tree = QtWidgets.QTreeWidget(splitter)
            else:
                self.tree = QtWidgets.QTreeWidget(self)
                layout.addWidget(self.tree, 1)
            if self._show_relative_path_column:
                self.tree.setHeaderLabels(["资源", "来源", "相对路径"])
                self.tree.setColumnWidth(0, 240)
                self.tree.setColumnWidth(1, 80)
                self.tree.setColumnWidth(2, 520)
            else:
                # 导出中心左侧“资源选择”不需要相对路径列；避免冗余信息与视觉噪音。
                self.tree.setHeaderLabels(["资源", "来源"])
                self.tree.setColumnWidth(0, 340)
                self.tree.setColumnWidth(1, 80)
            self.tree.setUniformRowHeights(True)

            self.selected_list: QtWidgets.QListWidget | None = None
            if self._show_selected_panel:
                self.selected_list = QtWidgets.QListWidget(splitter)
                self.selected_list.setMinimumWidth(320)
                splitter.setSizes([620, 300])

            if show_remove_button:
                if self._show_selected_panel:
                    self.remove_btn = QtWidgets.QPushButton("移除选中", self)
                else:
                    self.remove_btn = QtWidgets.QPushButton("清空已选", self)
                self.remove_btn.clicked.connect(self._on_remove_selected)  # handler will branch
                layout.addWidget(self.remove_btn)
            else:
                self.remove_btn = None

            self._ROLE_ITEM = int(QtCore.Qt.ItemDataRole.UserRole) + 10
            self._ROLE_SEARCH_TEXT = int(QtCore.Qt.ItemDataRole.UserRole) + 11
            self._ROLE_NODE_ID = int(QtCore.Qt.ItemDataRole.UserRole) + 12

            # JSON (templates/instances) 的 display_name 缓存：避免 UI 侧重复扫描大文件
            self._json_name_cache_by_abs_path: dict[str, str] = {}
            # 管理配置（mgmt_cfg）显示名缓存：避免重复解析 JSON/Python payload
            self._mgmt_cfg_display_name_cache_by_abs_path: dict[str, str] = {}

            self._refresh_selected_list()
            self._rebuild_tree()
            self._apply_filters()

            self.tree.itemChanged.connect(self._on_tree_item_changed)
            self.search_edit.textChanged.connect(lambda _t: self._apply_filters())
            self.only_selected_cb.toggled.connect(lambda _c: self._apply_filters())

        def get_selected_items(self) -> list[ResourceSelectionItem]:
            return list(self._selected_by_key.values())

        def get_selected_keys(self) -> set[str]:
            return set(self._selected_by_key.keys())

        def clear_selection(self) -> None:
            """清空已选，并刷新 UI。"""
            if not self._selected_by_key:
                return
            self._selected_by_key.clear()
            self._refresh_selected_list()
            self._rebuild_tree()
            self._apply_filters()
            self.selection_changed.emit()

        def remove_keys(self, keys: list[str]) -> int:
            """按 key 移除已选条目（用于外部自定义“已选列表”面板）。返回移除数量。"""
            removed = 0
            for k in list(keys or []):
                kk = str(k or "").strip()
                if not kk:
                    continue
                if kk in self._selected_by_key:
                    self._selected_by_key.pop(kk, None)
                    removed += 1
            if removed > 0:
                self._refresh_selected_list()
                self._rebuild_tree()
                self._apply_filters()
                self.selection_changed.emit()
            return int(removed)

        def set_allowed_categories(self, allowed_categories: set[str] | None, *, prune_selection: bool = True) -> int:
            """切换可选分类，并按需自动裁剪已选条目。返回被裁剪的数量。"""
            self._allowed_categories = set(allowed_categories) if allowed_categories else None
            removed = 0
            if prune_selection:
                removed = self._prune_selection_to_allowed_categories()
            self._refresh_selected_list()
            self._rebuild_tree()
            self._apply_filters()
            if removed > 0:
                self.selection_changed.emit()
            return int(removed)

        def _is_category_allowed(self, category: str) -> bool:
            if self._allowed_categories is None:
                return True
            return str(category or "") in self._allowed_categories

        def _prune_selection_to_allowed_categories(self) -> int:
            if self._allowed_categories is None:
                return 0
            allowed = set(self._allowed_categories)
            to_remove: list[str] = []
            for k, it in self._selected_by_key.items():
                if str(it.category or "") not in allowed:
                    to_remove.append(k)
            for k in to_remove:
                self._selected_by_key.pop(k, None)
            return int(len(to_remove))

        def _set_stats(self) -> None:
            self.stats_label.setText(f"已选：{len(self._selected_by_key)} 项")

        def _refresh_selected_list(self) -> None:
            if self.selected_list is None:
                self._set_stats()
                return
            self.selected_list.clear()
            for k in sorted(self._selected_by_key.keys(), key=lambda t: t.casefold()):
                it = self._selected_by_key[k]
                prefix = "项目" if it.source_root == "project" else "共享"
                display = self._format_item_display_text(it)
                text = f"[{prefix}] {display} — {it.relative_path}"
                item = QtWidgets.QListWidgetItem(text)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, it.key)
                item.setToolTip(str(it.absolute_path))
                self.selected_list.addItem(item)
            self._set_stats()

        def _matches_filter(self, text: str, item: QtWidgets.QTreeWidgetItem) -> bool:
            needle = str(text or "").strip().casefold()
            if needle == "":
                return True
            extra = item.data(0, self._ROLE_SEARCH_TEXT)
            extra_s = str(extra) if isinstance(extra, str) else ""
            if self._show_relative_path_column:
                hay = " ".join([item.text(0), item.text(1), item.text(2), extra_s]).casefold()
            else:
                # 隐藏“相对路径”列时，仍允许按路径片段搜索：依赖 ROLE_SEARCH_TEXT。
                hay = " ".join([item.text(0), item.text(1), extra_s]).casefold()
            return needle in hay

        def _apply_filters(self) -> None:
            needle = str(self.search_edit.text() or "")
            only_selected = bool(self.only_selected_cb.isChecked())

            def _walk(node: QtWidgets.QTreeWidgetItem) -> bool:
                visible_any_child = False
                for i in range(node.childCount()):
                    child = node.child(i)
                    if child is None:
                        continue
                    child_visible = _walk(child)
                    visible_any_child = visible_any_child or child_visible

                payload = node.data(0, self._ROLE_ITEM)
                is_leaf = isinstance(payload, ResourceSelectionItem)
                if is_leaf:
                    key = payload.key
                    if only_selected and key not in self._selected_by_key:
                        node.setHidden(True)
                        return False
                    if not self._matches_filter(needle, node):
                        node.setHidden(True)
                        return False
                    node.setHidden(False)
                    return True

                node.setHidden(not visible_any_child)
                return visible_any_child

            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                if top is None:
                    continue
                _walk(top)

        def _toggle_item_from_checkbox(self, item: QtWidgets.QTreeWidgetItem, checked: bool) -> None:
            payload = item.data(0, self._ROLE_ITEM)
            if not isinstance(payload, ResourceSelectionItem):
                return
            if checked:
                self._selected_by_key[payload.key] = payload
            else:
                self._selected_by_key.pop(payload.key, None)
            self._refresh_selected_list()
            self._apply_filters()
            self.selection_changed.emit()

        def get_item_display_text(self, it: ResourceSelectionItem) -> str:
            """
            返回资源条目的展示文本（用于“已选清单”等外部 UI），与资源树叶子节点口径保持一致。

            约束：
            - 当隐藏“相对路径”列时，若展示名与文件名不同，会显示为 `展示名 (文件名)`，避免用户找不到对应文件。
            """
            return self._format_item_display_text(it)

        def _format_item_display_text(self, it: ResourceSelectionItem) -> str:
            file_name = str(it.relative_path or "").replace("\\", "/").split("/")[-1]
            title = str(file_name)
            cat = str(it.category or "")

            if cat == "mgmt_cfg":
                human = self._get_mgmt_cfg_display_name_cached(Path(it.absolute_path))
                if human != "":
                    title = str(human)
            elif cat in {"templates", "instances", "player_templates"} and str(it.absolute_path.suffix).lower() == ".json":
                human2 = self._get_json_name_cached(Path(it.absolute_path))
                if human2 != "":
                    title = str(human2)

            return title

        def _get_json_name_cached(self, file_path: Path) -> str:
            p = Path(file_path).resolve()
            key = str(p)
            cached = self._json_name_cache_by_abs_path.get(key)
            if cached is not None:
                return str(cached)
            name = _extract_top_level_json_string_field(file_path=p, field_name="name")
            out = str(name or "").strip()
            self._json_name_cache_by_abs_path[key] = out
            return out

        def _get_mgmt_cfg_display_name_cached(self, file_path: Path) -> str:
            p = Path(file_path).resolve()
            key = str(p)
            cached = self._mgmt_cfg_display_name_cache_by_abs_path.get(key)
            if cached is not None:
                return str(cached)
            name = get_mgmt_cfg_display_name(file_path=p)
            out = str(name or "").strip()
            self._mgmt_cfg_display_name_cache_by_abs_path[key] = out
            return out

        def _rebuild_tree(self) -> None:
            class _DirTreeNode:
                __slots__ = ("subdirs", "files", "total", "selected")

                def __init__(self) -> None:
                    self.subdirs: dict[str, _DirTreeNode] = {}
                    self.files: list[ResourceSelectionItem] = []
                    self.total: int = 0
                    self.selected: int = 0

            def _compute_state(*, total: int, selected: int) -> QtCore.Qt.CheckState:
                if total <= 0:
                    return QtCore.Qt.CheckState.Unchecked
                if selected <= 0:
                    return QtCore.Qt.CheckState.Unchecked
                if selected >= total:
                    return QtCore.Qt.CheckState.Checked
                return QtCore.Qt.CheckState.PartiallyChecked

            def _with_count(title: str, count: int) -> str:
                base = str(title or "")
                n = int(count or 0)
                mode = str(getattr(self, "_count_format", "paren") or "paren").strip().lower()
                if mode == "none":
                    return base
                if mode == "plain":
                    return f"{base} {n}"
                # default: parentheses (legacy)
                return f"{base} ({n})"

            def _strip_prefix_for_tree(relative_path: str, prefix: str) -> str:
                rel = str(relative_path or "").replace("\\", "/").strip("/")
                prefix2 = str(prefix or "").replace("\\", "/").strip("/")
                if prefix2 and rel.startswith(prefix2 + "/"):
                    rel = rel[len(prefix2) + 1 :]
                return rel

            def _build_category_node(*, category: str, title: str, items: list[ResourceSelectionItem]) -> QtWidgets.QTreeWidgetItem:
                def _row(col0: str, col1: str, col2: str) -> list[str]:
                    return [col0, col1, col2] if self._show_relative_path_column else [col0, col1]

                root = QtWidgets.QTreeWidgetItem(_row(title, "", ""))
                root.setData(0, self._ROLE_NODE_ID, f"cat:{category}")
                root.setFlags(
                    root.flags()
                    | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                    | QtCore.Qt.ItemFlag.ItemIsAutoTristate
                )
                root.setExpanded(False)

                by_source: dict[str, list[ResourceSelectionItem]] = {"project": [], "shared": []}
                for it in items:
                    by_source.setdefault(it.source_root, []).append(it)

                for source_root in ["project", "shared"]:
                    group = by_source.get(source_root) or []
                    if not group:
                        continue
                    source_text = "项目" if source_root == "project" else "共享"
                    node = QtWidgets.QTreeWidgetItem(_row(_with_count(source_text, len(group)), source_text, ""))
                    node.setData(0, self._ROLE_NODE_ID, f"cat:{category}/src:{source_root}")
                    node.setFlags(
                        node.flags()
                        | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                        | QtCore.Qt.ItemFlag.ItemIsAutoTristate
                    )
                    node.setExpanded(False)

                    if str(category or "") in {"graphs", "templates", "instances", "player_templates", "mgmt_cfg", "ui_src"}:
                        def _to_tree_rel(relative_path: str) -> str:
                            cat = str(category or "")
                            if cat == "graphs":
                                return _strip_prefix_for_tree(relative_path, "节点图")
                            if cat == "templates":
                                return _strip_prefix_for_tree(relative_path, "元件库")
                            if cat == "instances":
                                return _strip_prefix_for_tree(relative_path, "实体摆放")
                            if cat == "player_templates":
                                return _strip_prefix_for_tree(relative_path, "战斗预设/玩家模板")
                            if cat == "ui_src":
                                return _strip_prefix_for_tree(relative_path, "管理配置/UI源码")
                            if cat == "mgmt_cfg":
                                return _strip_prefix_for_tree(relative_path, "管理配置")
                            return str(relative_path or "").replace("\\", "/").strip("/")

                        root_dir = _DirTreeNode()
                        for it in group:
                            rel2 = _to_tree_rel(str(it.relative_path or ""))
                            parts = [p for p in str(rel2).split("/") if p]
                            if not parts:
                                parts = [str(it.relative_path or "").split("/")[-1]]
                            selected = it.key in self._selected_by_key
                            dir_parts = parts[:-1]

                            cur = root_dir
                            cur.total += 1
                            if selected:
                                cur.selected += 1
                            for d in dir_parts:
                                child = cur.subdirs.get(d)
                                if child is None:
                                    child = _DirTreeNode()
                                    cur.subdirs[d] = child
                                cur = child
                                cur.total += 1
                                if selected:
                                    cur.selected += 1
                            cur.files.append(it)

                        def _add_dir_children(
                            *,
                            parent_item: QtWidgets.QTreeWidgetItem,
                            prefix: str,
                            tree_node: _DirTreeNode,
                        ) -> None:
                            for dir_name in sorted(tree_node.subdirs.keys(), key=lambda t: str(t).casefold()):
                                child_tree = tree_node.subdirs[dir_name]
                                dir_rel = f"{prefix}/{dir_name}" if prefix else str(dir_name)
                                folder = QtWidgets.QTreeWidgetItem(_row(str(dir_name), "", dir_rel))
                                folder.setData(0, self._ROLE_NODE_ID, f"cat:{category}/src:{source_root}/dir:{dir_rel}")
                                folder.setData(0, self._ROLE_SEARCH_TEXT, str(dir_rel))
                                if not self._show_relative_path_column:
                                    folder.setToolTip(0, str(dir_rel))
                                folder.setFlags(
                                    folder.flags()
                                    | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                                    | QtCore.Qt.ItemFlag.ItemIsAutoTristate
                                )
                                folder.setExpanded(False)
                                folder.setCheckState(
                                    0,
                                    _compute_state(total=int(child_tree.total), selected=int(child_tree.selected)),
                                )
                                parent_item.addChild(folder)
                                _add_dir_children(parent_item=folder, prefix=dir_rel, tree_node=child_tree)

                            def _file_sort_key(it2: ResourceSelectionItem) -> str:
                                return str(_to_tree_rel(str(it2.relative_path or ""))).casefold()

                            for it2 in sorted(list(tree_node.files), key=_file_sort_key):
                                rel3 = _to_tree_rel(str(it2.relative_path or ""))
                                file_name = (
                                    rel3.split("/")[-1]
                                    if rel3
                                    else str(it2.relative_path or "").split("/")[-1]
                                )
                                leaf_title = self._format_item_display_text(it2)

                                leaf = QtWidgets.QTreeWidgetItem(_row(leaf_title, source_text, it2.relative_path))
                                leaf.setData(0, self._ROLE_ITEM, it2)
                                leaf.setData(0, self._ROLE_SEARCH_TEXT, str(it2.relative_path))
                                if self._show_relative_path_column:
                                    leaf.setToolTip(2, str(it2.absolute_path))
                                else:
                                    leaf.setToolTip(0, f"{it2.relative_path}\n{it2.absolute_path}")
                                leaf.setFlags(leaf.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                                leaf.setCheckState(
                                    0,
                                    QtCore.Qt.CheckState.Checked
                                    if it2.key in self._selected_by_key
                                    else QtCore.Qt.CheckState.Unchecked,
                                )
                                parent_item.addChild(leaf)

                        _add_dir_children(parent_item=node, prefix="", tree_node=root_dir)
                        node.setCheckState(
                            0,
                            _compute_state(total=int(root_dir.total), selected=int(root_dir.selected)),
                        )
                    else:
                        selected_count = 0
                        for it in group:
                            if it.key in self._selected_by_key:
                                selected_count += 1
                            leaf = QtWidgets.QTreeWidgetItem(
                                _row(self._format_item_display_text(it), source_text, it.relative_path)
                            )
                            leaf.setData(0, self._ROLE_ITEM, it)
                            leaf.setData(0, self._ROLE_SEARCH_TEXT, str(it.relative_path))
                            if self._show_relative_path_column:
                                leaf.setToolTip(2, str(it.absolute_path))
                            else:
                                leaf.setToolTip(0, f"{it.relative_path}\n{it.absolute_path}")
                            leaf.setFlags(leaf.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                            leaf.setCheckState(
                                0,
                                QtCore.Qt.CheckState.Checked
                                if it.key in self._selected_by_key
                                else QtCore.Qt.CheckState.Unchecked,
                            )
                            node.addChild(leaf)
                        node.setCheckState(
                            0,
                            _compute_state(total=len(group), selected=int(selected_count)),
                        )
                    root.addChild(node)

                root_selected = sum(1 for it in items if it.key in self._selected_by_key)
                root.setCheckState(
                    0,
                    _compute_state(total=len(items), selected=int(root_selected)),
                )
                return root

            def _category_label(key: str, count: int) -> str:
                mapping = {
                    "graphs": "节点图源码",
                    "templates": "元件（JSON）",
                    "instances": "实体摆放（JSON）",
                    "player_templates": "玩家模板（战斗预设）",
                    "ui_src": "UI源码",
                    "level_entity_vars": "关卡实体自定义变量",
                    # 导出中心当前只消费“信号/结构体定义”这部分管理配置；其余杂项不应出现在候选列表中。
                    "mgmt_cfg": "管理配置（信号/结构体）",
                    "resource_repo": "其它资源文件",
                }
                title = mapping.get(key, key)
                return _with_count(title, int(count))

            enabled_categories = (
                [
                    c
                    for c in ["graphs", "templates", "instances", "player_templates", "ui_src", "level_entity_vars", "mgmt_cfg", "resource_repo"]
                    if self._allowed_categories is None or c in self._allowed_categories
                ]
                if self._allowed_categories is not None
                else ["graphs", "templates", "instances", "player_templates", "ui_src", "level_entity_vars", "mgmt_cfg", "resource_repo"]
            )

            self.tree.setUpdatesEnabled(False)
            self.tree.blockSignals(True)
            self.tree.clear()
            for category in enabled_categories:
                items = list(self._catalog.get(category, []))
                if not items:
                    continue
                self.tree.addTopLevelItem(
                    _build_category_node(
                        category=str(category),
                        title=_category_label(category, len(items)),
                        items=items,
                    )
                )
            self.tree.blockSignals(False)
            self.tree.setUpdatesEnabled(True)

        def get_expanded_node_ids(self) -> set[str]:
            """
            返回当前树中“已展开”的可展开节点集合（稳定 node_id）。

            只记录带有子节点的节点；叶子节点不参与。
            """
            expanded: set[str] = set()
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                if top is None:
                    continue
                stack = [top]
                while stack:
                    node = stack.pop()
                    if node.childCount() > 0:
                        if bool(node.isExpanded()):
                            node_id = node.data(0, self._ROLE_NODE_ID)
                            if isinstance(node_id, str) and str(node_id).strip() != "":
                                expanded.add(str(node_id).strip())
                    for j in range(node.childCount()):
                        c = node.child(j)
                        if c is not None:
                            stack.append(c)
            return expanded

        def set_expanded_node_ids(self, node_ids: set[str] | list[str]) -> None:
            """
            按 node_id 恢复展开状态：命中的节点会 setExpanded(True)。
            """
            wanted = {str(x).strip() for x in (list(node_ids) if node_ids else []) if str(x).strip()}
            if not wanted:
                return
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                if top is None:
                    continue
                stack = [top]
                while stack:
                    node = stack.pop()
                    node_id = node.data(0, self._ROLE_NODE_ID)
                    if isinstance(node_id, str) and str(node_id).strip() in wanted:
                        # 使用 view 侧 expandItem，避免极端情况下“未 attach 到 view 时 setExpanded 不生效”
                        self.tree.expandItem(node)
                    for j in range(node.childCount()):
                        c = node.child(j)
                        if c is not None:
                            stack.append(c)

        def _on_tree_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
            if item is None or column != 0:
                return
            payload = item.data(0, self._ROLE_ITEM)
            if not isinstance(payload, ResourceSelectionItem):
                return
            checked = item.checkState(0) == QtCore.Qt.CheckState.Checked
            self._toggle_item_from_checkbox(item, bool(checked))

        def _on_remove_selected(self) -> None:
            # 没有右侧“已选列表”面板时：按钮语义为“清空已选”
            if self.selected_list is None:
                if not self._selected_by_key:
                    return
                self._selected_by_key.clear()
            else:
                items = self.selected_list.selectedItems()
                if not items:
                    return
                for li in items:
                    key = li.data(QtCore.Qt.ItemDataRole.UserRole)
                    if isinstance(key, str) and key:
                        self._selected_by_key.pop(key, None)

            # 同步树复选框（只对叶子节点生效）
            self.tree.blockSignals(True)
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                if top is None:
                    continue
                stack = [top]
                while stack:
                    node = stack.pop()
                    payload = node.data(0, self._ROLE_ITEM)
                    if isinstance(payload, ResourceSelectionItem):
                        node.setCheckState(
                            0,
                            QtCore.Qt.CheckState.Checked
                            if payload.key in self._selected_by_key
                            else QtCore.Qt.CheckState.Unchecked,
                        )
                    for j in range(node.childCount()):
                        child = node.child(j)
                        if child is not None:
                            stack.append(child)
            self.tree.blockSignals(False)

            self._refresh_selected_list()
            self._apply_filters()
            self.selection_changed.emit()

    _RESOURCE_PICKER_WIDGET_CLASS_CACHE[cache_key] = _ResourcePickerWidget
    return _ResourcePickerWidget


def open_resource_picker_dialog(
    *,
    parent,
    workspace_root: Path,
    package_id: str,
    include_shared: bool = True,
    allowed_categories: set[str] | None = None,
    title: str = "",
    preselected_keys: set[str] | None = None,
) -> list[ResourceSelectionItem]:
    """打开资源选择器对话框并返回已选条目。"""
    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation.theme_manager import Colors, Sizes
    from engine.utils.resource_library_layout import get_shared_root_dir, get_packages_root_dir

    ws_root = Path(workspace_root).resolve()
    resource_library_root = (ws_root / "assets" / "资源库").resolve()
    packages_root = get_packages_root_dir(resource_library_root).resolve()
    shared_root = get_shared_root_dir(resource_library_root).resolve()
    project_root = (packages_root / str(package_id)).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    catalog = build_resource_selection_items(
        project_root=project_root,
        shared_root=shared_root,
        include_shared=bool(include_shared),
    )
    dialog = QtWidgets.QDialog(parent)
    dialog_title = str(title or "").strip() or "选择导出资源（按相对路径）"
    dialog.setWindowTitle(dialog_title)
    dialog.setModal(True)
    dialog.resize(920, 560)

    root_layout = QtWidgets.QVBoxLayout(dialog)
    root_layout.setContentsMargins(
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
    )
    root_layout.setSpacing(Sizes.SPACING_MEDIUM)

    header_lines = [f"项目存档：{package_id}"]
    if dialog_title:
        header_lines.insert(0, dialog_title)
    header = QtWidgets.QLabel("\n".join(header_lines), dialog)
    header.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
    root_layout.addWidget(header)

    PickerWidgetCls = make_resource_picker_widget_cls(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
    )
    picker = PickerWidgetCls(
        dialog,
        catalog=dict(catalog),
        allowed_categories=set(allowed_categories) if isinstance(allowed_categories, set) and allowed_categories else None,
        preselected_keys=set(preselected_keys) if preselected_keys else None,
        show_remove_button=True,
    )
    root_layout.addWidget(picker, 1)

    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok
        | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
        dialog,
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    root_layout.addWidget(buttons)

    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return []

    return list(picker.get_selected_items())

