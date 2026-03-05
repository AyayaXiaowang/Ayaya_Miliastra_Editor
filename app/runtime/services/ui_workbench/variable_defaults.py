from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.resources.auto_custom_variable_registry import (
    load_auto_custom_variable_registry_from_code,
    resolve_owner_refs,
)
from engine.resources.level_variable_registry_provider import REGISTRY_FILENAME

from engine.resources.custom_variable_file_refs import (
    normalize_custom_variable_file_refs,
    serialize_custom_variable_file_refs,
)

from .utils import crc32_hex, read_json, write_json
from app.cli.registry_declaration_editor import replace_auto_custom_variable_default_value


@dataclass(frozen=True, slots=True)
class ImportedVariable:
    scope: str  # "lv" | "ps"
    variable_name: str
    variable_type: str
    default_value: object


def variable_id_for(package_id: str, *, scope: str, variable_name: str) -> str:
    digest = crc32_hex(f"{package_id}:{scope}:{variable_name}")
    return f"ui_{digest}__{package_id}"


def ensure_dict_one_level(value: dict, *, key: str) -> dict:
    out: dict = {}
    for k, v in value.items():
        k2 = str(k)
        if isinstance(v, dict):
            raise ValueError(f"不支持嵌套字典默认值：{key} -> {k2}")
        out[k2] = v
    return out


def infer_variable_type_and_default(value: object, *, key: str) -> tuple[str, object]:
    # 注意：bool 是 int 的子类，必须先判断 bool
    if isinstance(value, bool):
        return "布尔值", bool(value)
    if isinstance(value, int):
        return "整数", int(value)
    if isinstance(value, float):
        return "浮点数", float(value)
    if isinstance(value, str):
        return "字符串", str(value)
    if isinstance(value, dict):
        normalized = ensure_dict_one_level(value, key=key)
        value_types = {type(v) for v in normalized.values()}
        if not normalized:
            return "字符串-字符串字典", {}
        if value_types.issubset({bool}):
            return "字符串-布尔值字典", normalized
        if value_types.issubset({int}) or value_types.issubset({int, bool}):
            if bool in value_types and int in value_types:
                raise ValueError(f"字典默认值 value 类型混合（int/bool），请手动拆分：{key}")
            return "字符串-整数字典", normalized
        if value_types.issubset({float}) or value_types.issubset({int, float}):
            return "字符串-浮点数字典", {k: float(v) for k, v in normalized.items()}
        if value_types.issubset({str}):
            return "字符串-字符串字典", normalized
        raise ValueError(
            f"字典默认值 value 类型不受支持或混合：{key} -> {sorted([t.__name__ for t in value_types])}"
        )
    if isinstance(value, list):
        if len(value) <= 0:
            # 空列表无法推断，默认按字符串列表（最安全的可显示/可编辑类型）
            return "字符串列表", []
        kinds = set(type(x) for x in value)
        # 统一转成 bool/int/float/str 检查
        if kinds.issubset({bool}):
            return "布尔值列表", [bool(x) for x in value]
        if kinds.issubset({int}) or kinds.issubset({int, bool}):
            # 注意：如果 list 里混入 bool，仍按整数列表处理会让 True/False 变 1/0
            # 这里严格：混入 bool 视为混合类型，拒绝自动推断（避免静默改变语义）
            if bool in kinds and int in kinds:
                raise ValueError(f"列表默认值类型混合（int/bool），请手动拆分：{key}")
            return "整数列表", [int(x) for x in value]
        if kinds.issubset({float}) or kinds.issubset({int, float}):
            return "浮点数列表", [float(x) for x in value]
        if kinds.issubset({str}):
            return "字符串列表", [str(x) for x in value]
        raise ValueError(
            f"列表默认值类型不受支持或混合：{key} -> {sorted([t.__name__ for t in kinds])}"
        )

    raise ValueError(f"默认值类型不受支持：{key} -> {type(value)!r}")


def extract_import_items(variable_defaults: dict) -> list[ImportedVariable]:
    items: list[ImportedVariable] = []
    for raw_key, raw_value in variable_defaults.items():
        full_key = str(raw_key or "").strip()
        if not full_key:
            continue
        if full_key.startswith("lv."):
            name = str(full_key[3:]).strip()
            if not name:
                continue
            vtype, dv = infer_variable_type_and_default(raw_value, key=full_key)
            items.append(
                ImportedVariable(
                    scope="lv",
                    variable_name=name,
                    variable_type=vtype,
                    default_value=dv,
                )
            )
            continue
        if full_key.startswith("ps."):
            name = str(full_key[3:]).strip()
            if not name:
                continue
            vtype, dv = infer_variable_type_and_default(raw_value, key=full_key)
            items.append(
                ImportedVariable(
                    scope="ps",
                    variable_name=name,
                    variable_type=vtype,
                    default_value=dv,
                )
            )
            continue
    return items


def write_level_variable_file(
    path: Path,
    *,
    file_id: str,
    file_name: str,
    variables: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from engine.graph.models.package_model import LevelVariableDefinition")
    lines.append("")
    lines.append(f'VARIABLE_FILE_ID = "{file_id}"')
    lines.append(f'VARIABLE_FILE_NAME = "{file_name}"')
    lines.append("")
    lines.append("LEVEL_VARIABLES: list[LevelVariableDefinition] = [")
    for item in variables:
        payload = {
            "variable_id": item.get("variable_id"),
            "variable_name": item.get("variable_name"),
            "variable_type": item.get("variable_type"),
            "default_value": item.get("default_value"),
            "is_global": item.get("is_global", True),
            "description": item.get("description", ""),
            "metadata": item.get("metadata", {}),
        }
        lines.append("    LevelVariableDefinition(")
        lines.append(f"        variable_id={repr(payload['variable_id'])},")
        lines.append(f"        variable_name={repr(payload['variable_name'])},")
        lines.append(f"        variable_type={repr(payload['variable_type'])},")
        lines.append(f"        default_value={repr(payload['default_value'])},")
        lines.append(f"        is_global={repr(payload['is_global'])},")
        lines.append(f"        description={repr(payload['description'])},")
        lines.append(f"        metadata={repr(payload['metadata'])},")
        lines.append("    ),")
    lines.append("]")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def discover_player_templates(package_root: Path) -> list[Path]:
    template_dir = (package_root / "战斗预设" / "玩家模板").resolve()
    if not template_dir.is_dir():
        return []
    return sorted([p for p in template_dir.glob("*.json") if p.is_file()], key=lambda p: p.as_posix())


def get_player_custom_variable_file_ids_from_template(template_json: dict) -> list[str]:
    metadata = template_json.get("metadata")
    if not isinstance(metadata, dict):
        return []
    return normalize_custom_variable_file_refs(metadata.get("custom_variable_file"))


def set_player_custom_variable_file_ids(template_json: dict, file_ids: list[str]) -> None:
    metadata = template_json.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        template_json["metadata"] = metadata
    metadata["custom_variable_file"] = serialize_custom_variable_file_refs(file_ids)


def try_attach_ps_variable_file_to_player_templates(
    *,
    package_root: Path,
    ps_file_id: str,
    report: dict,
) -> None:
    """将 ps 变量文件引用追加到所有玩家模板（若存在），并更新 report 信息。"""
    player_templates = discover_player_templates(package_root)
    updated_templates: list[str] = []
    for tpl_path in player_templates:
        tpl = read_json(tpl_path)
        old_refs = get_player_custom_variable_file_ids_from_template(tpl)
        new_refs = list(old_refs)
        if ps_file_id not in new_refs:
            new_refs.append(ps_file_id)
        if new_refs != old_refs:
            set_player_custom_variable_file_ids(tpl, new_refs)
            write_json(tpl_path, tpl)
            updated_templates.append(tpl_path.name)

    report_ps = report.get("ps")
    if isinstance(report_ps, dict):
        report_ps["player_templates_updated"] = updated_templates
        report_ps["player_templates_total"] = int(len(discover_player_templates(package_root)))
        if not updated_templates and int(len(discover_player_templates(package_root))) <= 0:
            report_ps["note"] = (
                "未找到玩家模板：ps 变量已写入变量文件，但不会出现在 variable_catalog（需要玩家模板引用）"
            )


def apply_variable_defaults_to_registry(
    *,
    workspace_root: Path,
    package_id: str,
    source_rel_path: str,
    variable_defaults: dict,
) -> dict:
    """将前端解析出的 variable_defaults 写回『自定义变量注册表.py』。"""
    if not isinstance(variable_defaults, dict):
        raise ValueError("variable_defaults must be dict")

    pkg = str(package_id or "").strip()
    if not pkg or pkg == "global_view":
        raise ValueError("package_id 无效（必须为具体项目存档）")

    workspace = Path(workspace_root).resolve()
    package_root = (workspace / "assets" / "资源库" / "项目存档" / pkg).resolve()
    registry_path = (package_root / "管理配置" / "关卡变量" / REGISTRY_FILENAME).resolve()
    if not registry_path.is_file():
        raise FileNotFoundError(f"未找到自定义变量注册表文件：{registry_path}")

    declarations = load_auto_custom_variable_registry_from_code(registry_path)
    name_owner_to_decl: dict[tuple[str, str], object] = {}
    for d in list(declarations or []):
        name = str(getattr(d, "variable_name", "") or "").strip()
        if not name:
            continue
        for ref in resolve_owner_refs(d):
            name_owner_to_decl.setdefault((name, ref.lower()), d)

    imported_items = extract_import_items(variable_defaults)
    lv_items = [it for it in imported_items if it.scope == "lv"]
    ps_items = [it for it in imported_items if it.scope == "ps"]

    report: dict[str, object] = {
        "ok": True,
        "package_id": pkg,
        "source_rel_path": str(source_rel_path or ""),
        "input_variable_defaults_total": int(len(variable_defaults)),
        "imported_candidates_total": int(len(imported_items)),
        "imported_lv_total": int(len(lv_items)),
        "imported_ps_total": int(len(ps_items)),
        "lv": {"updated": [], "skipped": []},
        "ps": {"updated": [], "skipped": []},
        "notes": [
            "仅写回 lv.* / ps.* 到 自定义变量注册表.py；不再生成 UI_*_网页默认值.py 变量文件。",
        ],
    }

    def _apply_items(scope: str, items: list[ImportedVariable]) -> None:
        expected_owner = "level" if scope == "lv" else "player"
        updated: list[dict] = []
        skipped: list[dict] = []
        for it in items:
            decl = name_owner_to_decl.get((it.variable_name, expected_owner))
            if decl is None:
                skipped.append({"variable_name": it.variable_name, "reason": "not_in_registry"})
                continue
            decl_type = str(getattr(decl, "variable_type", "") or "").strip()
            if decl_type and decl_type != it.variable_type:
                raise ValueError(
                    f"变量类型冲突：{scope}.{it.variable_name} registry={decl_type!r} imported={it.variable_type!r}"
                )
            variable_id = str(getattr(decl, "variable_id", "") or "").strip()
            if not variable_id:
                raise ValueError(f"{registry_path}: 声明缺少 variable_id：{it.variable_name!r}")
            replace_auto_custom_variable_default_value(
                registry_path=registry_path,
                variable_id=variable_id,
                new_default_value=it.default_value,
            )
            updated.append({"variable_name": it.variable_name, "variable_type": it.variable_type})
        report_block = report.get(scope)
        if isinstance(report_block, dict):
            report_block["updated"] = updated
            report_block["skipped"] = skipped

    _apply_items("lv", lv_items)
    _apply_items("ps", ps_items)
    return report


__all__ = [
    "ImportedVariable",
    "apply_variable_defaults_to_registry",
    "discover_player_templates",
    "extract_import_items",
    "get_player_custom_variable_file_ids_from_template",
    "infer_variable_type_and_default",
    "set_player_custom_variable_file_ids",
    "try_attach_ps_variable_file_to_player_templates",
    "variable_id_for",
    "write_level_variable_file",
]

