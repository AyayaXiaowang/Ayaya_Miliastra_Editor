from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class UiVariableDefaultsExtractionResult:
    html_path: Path
    raw_defaults: dict[str, Any]
    split_defaults: dict[str, dict[str, Any]]
    split_defaults_string_values: dict[str, dict[str, str]]


class _DefaultsAttrParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.defaults_text: str | None = None
        self.tag_name: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.defaults_text is not None:
            return
        for k, v in attrs:
            if str(k).strip().lower() == "data-ui-variable-defaults":
                if v is None:
                    self.defaults_text = ""
                else:
                    self.defaults_text = str(v)
                self.tag_name = str(tag)
                return


def _stringify_json_leaf(value: Any) -> str:
    # 目标：生成“UI 展示友好、类型不敏感”的字符串版本，避免运行期字典 value 混型。
    # 注意：不吞异常；遇到无法序列化的对象直接抛错，便于作者修正默认值来源。
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    # 对 list/dict：保持 JSON 结构（写成 compact json 字符串）
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _stringify_dict_values_shallow(source: dict[str, Any]) -> dict[str, str]:
    return {str(k): _stringify_json_leaf(v) for k, v in source.items()}


def extract_ui_variable_defaults_from_html(html_path: Path) -> UiVariableDefaultsExtractionResult:
    html_path = Path(html_path).resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML 文件不存在：{html_path}")

    text = html_path.read_text(encoding="utf-8")
    parser = _DefaultsAttrParser()
    parser.feed(text)

    if parser.defaults_text is None:
        raise ValueError(
            "未找到 data-ui-variable-defaults 属性。"
            "请在页面根节点（例如 .screen-container）声明 data-ui-variable-defaults='{\"lv.xxx\": {...}}'。"
        )

    raw = json.loads(parser.defaults_text)
    if not isinstance(raw, dict):
        raise ValueError(
            "data-ui-variable-defaults 必须是 JSON object（字典）。"
            f"当前解析类型：{type(raw).__name__}"
        )

    split: dict[str, dict[str, Any]] = {}
    split_str: dict[str, dict[str, str]] = {}
    for full_key, payload in raw.items():
        key_text = str(full_key or "").strip()
        if not key_text:
            continue
        if not isinstance(payload, dict):
            raise ValueError(
                "data-ui-variable-defaults 顶层每个 value 必须是 JSON object（字典）。"
                f"当前 key={key_text!r} 的类型为 {type(payload).__name__}"
            )

        # 约定：lv.xxx -> 写回为自定义变量 `xxx`
        scope, sep, rest = key_text.partition(".")
        if sep != "." or not rest:
            raise ValueError(
                "data-ui-variable-defaults 顶层 key 必须为 'lv.xxx' / 'ps.xxx' 形式。"
                f"当前 key={key_text!r}"
            )
        var_name = rest.strip()
        if not var_name:
            raise ValueError(f"data-ui-variable-defaults 顶层 key 缺少变量名：{key_text!r}")

        # 保留 scope 仅用于诊断；实际写回时通常只需 var_name
        split[var_name] = dict(payload)
        split_str[var_name] = _stringify_dict_values_shallow(payload)

    return UiVariableDefaultsExtractionResult(
        html_path=html_path,
        raw_defaults=raw,
        split_defaults=split,
        split_defaults_string_values=split_str,
    )


def try_extract_ui_variable_defaults_from_html(html_path: Path) -> UiVariableDefaultsExtractionResult | None:
    """尝试从 HTML 抽取 data-ui-variable-defaults。

    - 若页面未声明该属性：返回 None（用于批量扫描 UI源码 目录）
    - 若声明但格式非法：直接抛错（fail-fast）
    """
    html_path = Path(html_path).resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML 文件不存在：{html_path}")

    text = html_path.read_text(encoding="utf-8")
    parser = _DefaultsAttrParser()
    parser.feed(text)
    if parser.defaults_text is None:
        return None
    return extract_ui_variable_defaults_from_html(html_path)


def write_ui_variable_defaults_json_outputs(
    *,
    result: UiVariableDefaultsExtractionResult,
    out_dir: Path,
    name_prefix: str = "",
) -> tuple[Path, Path, Path]:
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = result.html_path.stem
    prefix = str(name_prefix or "").strip()
    base = f"{prefix}{stem}.ui_variable_defaults"

    raw_path = out_dir / f"{base}.raw.json"
    split_raw_path = out_dir / f"{base}.split.raw.json"
    split_string_path = out_dir / f"{base}.split.strings.json"

    raw_path.write_text(json.dumps(result.raw_defaults, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    split_raw_path.write_text(
        json.dumps(result.split_defaults, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    split_string_path.write_text(
        json.dumps(result.split_defaults_string_values, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return raw_path, split_raw_path, split_string_path

