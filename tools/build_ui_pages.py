from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path
else:
    from _bootstrap import ensure_workspace_root_on_sys_path

# 允许 `python tools/build_ui_pages.py ...` 直接运行
ensure_workspace_root_on_sys_path()

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


@dataclass
class UiPageSpec:
    ui_page_id: str
    html_relative_path: str
    flattened_relative_path: str
    text_binding_relative_path: str


UI_PAGE_SPECS: Dict[str, UiPageSpec] = {
    # 后续可在此按需补充更多页面
    "forge_hero_forge": UiPageSpec(
        ui_page_id="forge_hero_forge",
        html_relative_path="projects/锻刀英雄/ui_mockups/forge_ui_mockup.html",
        flattened_relative_path=(
            "projects/锻刀英雄/ui_mockups/flattened/forge_ui_mockup_flattened.html"
        ),
        text_binding_relative_path=(
            "assets/资源库/管理配置/UI文本绑定/forge_hero_forge_ui_text_bindings.json"
        ),
    ),
}


def _find_workspace_root(current_path: Path) -> Path:
    search_directories = [current_path.parent] + list(current_path.parents)
    for directory in search_directories:
        marker_file = directory / "pyrightconfig.json"
        if marker_file.is_file():
            return directory
    return current_path.parent


def _load_ui_page_spec(ui_page_id: str) -> UiPageSpec:
    if ui_page_id not in UI_PAGE_SPECS:
        raise ValueError(f"不支持的 ui_page_id: {ui_page_id!r}")
    return UI_PAGE_SPECS[ui_page_id]


def _extract_placeholders_from_html(html_text: str) -> List[str]:
    matches = PLACEHOLDER_PATTERN.findall(html_text)
    unique_names: List[str] = []
    seen_names: set[str] = set()
    for name in matches:
        cleaned = name.strip()
        if cleaned and cleaned not in seen_names:
            seen_names.add(cleaned)
            unique_names.append(cleaned)
    return unique_names


def _sync_placeholders_for_page(workspace_path: Path, page_spec: UiPageSpec) -> None:
    html_path = workspace_path / page_spec.html_relative_path
    if not html_path.is_file():
        raise FileNotFoundError(f"找不到原始 HTML 文件: {html_path}")

    html_text = html_path.read_text(encoding="utf-8")
    placeholder_names = _extract_placeholders_from_html(html_text)

    bindings_path = workspace_path / page_spec.text_binding_relative_path
    if not bindings_path.parent.is_dir():
        bindings_path.parent.mkdir(parents=True, exist_ok=True)

    if bindings_path.is_file():
        config_text = bindings_path.read_text(encoding="utf-8")
        config_data = json.loads(config_text)

        existing_bindings_data = config_data.get("bindings")
        if not isinstance(existing_bindings_data, list):
            raise ValueError(f"UI 文本绑定资源 {bindings_path} 的 bindings 字段必须是列表")

        bindings_by_placeholder: Dict[str, Dict[str, Any]] = {}
        for binding in existing_bindings_data:
            placeholder_value = binding.get("placeholder")
            if isinstance(placeholder_value, str) and placeholder_value:
                bindings_by_placeholder[placeholder_value] = binding

        updated_bindings: List[Dict[str, Any]] = list(existing_bindings_data)
        for placeholder_name in placeholder_names:
            if placeholder_name in bindings_by_placeholder:
                continue
            updated_bindings.append(
                {
                    "placeholder": placeholder_name,
                    "label": "",
                    "source": "player",
                    "level_variable_file": "",
                    "variable_name": "",
                    "path": [],
                    "format": "",
                }
            )

        config_data["id"] = config_data.get("id", f"{page_spec.ui_page_id}_ui_text_bindings")
        config_data["ui_page_id"] = config_data.get("ui_page_id", page_spec.ui_page_id)
        config_data["bindings"] = updated_bindings

        bindings_path.write_text(
            json.dumps(config_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已更新 UI 文本绑定资源: {bindings_path}")
        return

    config_data = {
        "id": f"{page_spec.ui_page_id}_ui_text_bindings",
        "ui_page_id": page_spec.ui_page_id,
        "name": page_spec.ui_page_id,
        "description": f"{page_spec.ui_page_id} UI 文本绑定",
        "bindings": [
            {
                "placeholder": placeholder_name,
                "label": "",
                "source": "player",
                "level_variable_file": "",
                "variable_name": "",
                "path": [],
                "format": "",
            }
            for placeholder_name in placeholder_names
        ],
    }

    bindings_path.write_text(
        json.dumps(config_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已创建 UI 文本绑定资源: {bindings_path}")


class UiTextBinding:
    def __init__(
        self,
        placeholder: str,
        source: str,
        level_variable_file_id: str,
        variable_name: str,
        path_segments: List[str],
        text_format: str,
    ) -> None:
        self.placeholder = placeholder
        self.source = source
        self.level_variable_file_id = level_variable_file_id
        self.variable_name = variable_name
        self.path_segments = list(path_segments)
        self.text_format = text_format

    def to_engine_reference(self) -> str:
        if self.source == "player":
            prefix = "ps"
        elif self.source == "level":
            prefix = "lv"
        else:
            raise ValueError(f"不支持的 source 类型: {self.source}")

        if self.path_segments:
            full_path = ".".join(self.path_segments)
            return f"{{1:{prefix}.{self.variable_name}.{full_path}}}"

        return f"{{1:{prefix}.{self.variable_name}}}"


def _build_level_variable_index() -> tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    schema_view = get_default_level_variable_schema_view()
    variable_files = schema_view.get_all_variable_files()

    variable_files_by_id: Dict[str, Any] = variable_files
    variables_by_file_and_name: Dict[str, Dict[str, Any]] = {}

    for file_id, file_info in variable_files_by_id.items():
        variable_by_name: Dict[str, Any] = {}
        for variable_payload in file_info.variables:
            variable_name = variable_payload["variable_name"]
            variable_by_name[variable_name] = variable_payload
        variables_by_file_and_name[file_id] = variable_by_name

    return variable_files_by_id, variables_by_file_and_name


def _load_and_validate_bindings(workspace_path: Path, page_spec: UiPageSpec) -> List[UiTextBinding]:
    bindings_path = workspace_path / page_spec.text_binding_relative_path
    if not bindings_path.is_file():
        raise FileNotFoundError(f"找不到 UI 文本绑定资源: {bindings_path}")

    config_text = bindings_path.read_text(encoding="utf-8")
    config_data = json.loads(config_text)

    bindings_data = config_data.get("bindings")
    if not isinstance(bindings_data, list):
        raise ValueError(f"UI 文本绑定资源 {bindings_path} 的 bindings 字段必须是列表")

    variable_files_by_id, variables_by_file_and_name = _build_level_variable_index()

    effective_bindings: List[UiTextBinding] = []

    for binding_data in bindings_data:
        placeholder_value = binding_data.get("placeholder", "")
        if not isinstance(placeholder_value, str) or not placeholder_value.strip():
            raise ValueError(f"UI 文本绑定 {bindings_path} 中存在占位符为空的绑定项")

        placeholder_name = placeholder_value.strip()

        source_value = binding_data.get("source", "player")
        if source_value not in ("player", "level"):
            raise ValueError(
                f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』的 source={source_value!r} 非 player/level"
            )

        level_variable_file_id_value = binding_data.get("level_variable_file", "")
        variable_name_value = binding_data.get("variable_name", "")
        path_value = binding_data.get("path", [])
        text_format_value = binding_data.get("format", "")

        # 允许尚未补齐变量文件或变量名的占位符，它们在绑定阶段会原样保留为 {{占位符}}。
        if not level_variable_file_id_value or not variable_name_value:
            continue

        if not isinstance(level_variable_file_id_value, str):
            raise ValueError(
                f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』的 level_variable_file 必须是字符串"
            )

        if not isinstance(variable_name_value, str):
            raise ValueError(
                f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』的 variable_name 必须是字符串"
            )

        if not isinstance(path_value, list):
            raise ValueError(
                f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』的 path 必须是字符串列表"
            )

        path_segments: List[str] = []
        for segment in path_value:
            if not isinstance(segment, str):
                raise ValueError(
                    f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』的 path 中存在非字符串段: {segment!r}"
                )
            path_segments.append(segment)

        file_info = variable_files_by_id.get(level_variable_file_id_value)
        if file_info is None:
            raise ValueError(
                f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』引用的变量文件 ID 不存在: {level_variable_file_id_value!r}"
            )

        variables_by_name = variables_by_file_and_name[level_variable_file_id_value]
        variable_payload = variables_by_name.get(variable_name_value)
        if variable_payload is None:
            raise ValueError(
                f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』引用的变量名在文件"
                f" {level_variable_file_id_value!r} 中不存在: {variable_name_value!r}"
            )

        default_value = variable_payload.get("default_value")
        current: Any = default_value

        for segment in path_segments:
            if not isinstance(current, dict):
                raise ValueError(
                    f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』的路径"
                    f" {'.'.join(path_segments)} 在字段 '{segment}' 之前遇到非字典结构"
                )
            if segment not in current:
                raise ValueError(
                    f"UI 文本绑定 {bindings_path} 中占位符『{placeholder_name}』的路径"
                    f" {'.'.join(path_segments)} 中找不到字段: {segment}"
                )
            current = current[segment]

        effective_bindings.append(
            UiTextBinding(
                placeholder=placeholder_name,
                source=source_value,
                level_variable_file_id=level_variable_file_id_value,
                variable_name=variable_name_value,
                path_segments=path_segments,
                text_format=text_format_value if isinstance(text_format_value, str) else "",
            )
        )

    return effective_bindings


def _bind_placeholders_in_html(html_text: str, bindings: List[UiTextBinding]) -> str:
    binding_map: Dict[str, UiTextBinding] = {}
    for binding in bindings:
        if binding.placeholder in binding_map:
            raise ValueError(f"重复的占位符绑定: {binding.placeholder}")
        binding_map[binding.placeholder] = binding

    def replace_match(match: re.Match[str]) -> str:
        placeholder_name = match.group(1).strip()
        if placeholder_name not in binding_map:
            # 尚未配置绑定的占位符保持原样，便于逐步迁移与人工检查。
            return match.group(0)
        binding = binding_map[placeholder_name]
        return binding.to_engine_reference()

    return PLACEHOLDER_PATTERN.sub(replace_match, html_text)


def _run_flatten_for_page(workspace_path: Path, page_spec: UiPageSpec) -> None:
    script_path = (
        workspace_path
        / "projects"
        / "锻刀英雄"
        / "ui_mockups"
        / "html_flatten_converter.py"
    )
    html_path = workspace_path / page_spec.html_relative_path
    flattened_path = workspace_path / page_spec.flattened_relative_path

    if not script_path.is_file():
        raise FileNotFoundError(f"找不到 html_flatten_converter.py 脚本: {script_path}")

    if not html_path.is_file():
        raise FileNotFoundError(f"找不到原始 HTML 文件: {html_path}")

    command = [
        sys.executable,
        "-X",
        "utf8",
        str(script_path),
        str(html_path),
        str(flattened_path),
    ]

    completed_process = subprocess.run(
        command,
        cwd=str(workspace_path),
        check=False,
    )
    if completed_process.returncode != 0:
        raise RuntimeError(
            f"执行 html_flatten_converter.py 失败，返回码: {completed_process.returncode}"
        )


def build_ui_page(ui_page_id: str) -> None:
    current_file = Path(__file__).resolve()
    workspace_path = _find_workspace_root(current_file)

    page_spec = _load_ui_page_spec(ui_page_id)

    print(f"开始构建 UI 页面: {ui_page_id}")
    _run_flatten_for_page(workspace_path, page_spec)
    print("已完成 HTML 扁平化生成。")

    bindings = _load_and_validate_bindings(workspace_path, page_spec)
    print(f"已加载并校验 UI 文本绑定 {len(bindings)} 条。")

    flattened_path = workspace_path / page_spec.flattened_relative_path
    html_text = flattened_path.read_text(encoding="utf-8")
    new_html = _bind_placeholders_in_html(html_text, bindings)
    flattened_path.write_text(new_html, encoding="utf-8")

    print(f"已完成 UI 页面 {ui_page_id} 的扁平化与变量绑定生成。")


def main() -> None:
    arguments = sys.argv[1:]
    if not arguments or len(arguments) < 1:
        print("用法: python -X utf8 -m tools.build_ui_pages <ui_page_id>")
        print("示例: python -X utf8 -m tools.build_ui_pages forge_hero_forge")
        print("占位符同步: python -X utf8 -m tools.build_ui_pages --sync-placeholders forge_hero_forge")
        return

    if arguments[0] == "--sync-placeholders":
        if len(arguments) < 2:
            raise ValueError("使用 --sync-placeholders 时需要提供 ui_page_id")
        ui_page_id_value = arguments[1]

        current_file = Path(__file__).resolve()
        workspace_path = _find_workspace_root(current_file)

        page_spec_value = _load_ui_page_spec(ui_page_id_value)
        _sync_placeholders_for_page(workspace_path, page_spec_value)
        return

    ui_page_id_argument = arguments[0]
    build_ui_page(ui_page_id_argument)


if __name__ == "__main__":
    main()


