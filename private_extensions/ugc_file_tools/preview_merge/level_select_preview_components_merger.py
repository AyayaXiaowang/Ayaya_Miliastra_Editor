from __future__ import annotations

import ast
import json
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.preview_merge.trs_math import TRS, Mat4, decompose_mat4_to_trs, mat4_from_trs, mat4_inv_trs, mat4_mul


JsonDict = Dict[str, Any]
Vec3 = Tuple[float, float, float]


_COMPONENT_KEY_PREFIX = "component_key:"
_INSTANCE_ID_RE = re.compile(r"^(?:gia_)?(\d+)$", flags=re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LevelPreviewConfig:
    comp_ids_1: List[object]
    comp_ids_2: List[object]
    pos_offset: List[object]
    comp2_offset: List[object]
    rot_1: List[object]
    rot_2: List[object]


def _read_text(path: Path) -> str:
    return Path(path).resolve().read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> JsonDict:
    obj = json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 不是 dict：{str(Path(path).resolve())}")
    return obj


def _write_json(path: Path, obj: JsonDict) -> None:
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _as_vec3(value: object, *, label: str) -> Vec3:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        x, y, z = value[0], value[1], value[2]
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and isinstance(z, (int, float)):
            return (float(x), float(y), float(z))
    raise ValueError(f"{label} 不是 vec3：{value!r}")


def _extract_component_key_name(value: object) -> Optional[str]:
    if isinstance(value, str):
        text = str(value).strip()
        if text.startswith(_COMPONENT_KEY_PREFIX):
            name = text[len(_COMPONENT_KEY_PREFIX) :].strip()
            if name != "":
                return name
    return None


def _parse_graph_variable_defaults(*, graph_code_file: Path) -> Dict[str, object]:
    """
    从 Graph Code 源码中抽取 GraphVariableConfig(name=..., default_value=...) 的 default_value。

    只解析字面量（list/tuple/dict/str/number）；不导入、不执行 Graph Code。
    """
    text = _read_text(Path(graph_code_file))
    tree = ast.parse(text, filename=str(Path(graph_code_file).resolve()))
    out: Dict[str, object] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name):
            continue
        if str(func.id) != "GraphVariableConfig":
            continue

        kw_map: Dict[str, ast.AST] = {}
        for kw in list(node.keywords or []):
            if kw.arg is None:
                continue
            kw_map[str(kw.arg)] = kw.value

        name_node = kw_map.get("name")
        default_node = kw_map.get("default_value")
        if name_node is None or default_node is None:
            continue
        try:
            name_val = ast.literal_eval(name_node)
            default_val = ast.literal_eval(default_node)
        except Exception:
            continue
        if not isinstance(name_val, str):
            continue
        out[str(name_val)] = default_val

    return dict(out)


def load_level_preview_config_from_player_graph(*, player_graph_file: Path) -> LevelPreviewConfig:
    defaults = _parse_graph_variable_defaults(graph_code_file=Path(player_graph_file))

    def _get_list(name: str) -> List[object]:
        v = defaults.get(name)
        if not isinstance(v, list):
            raise ValueError(f"GraphVariableConfig({name!r}) default_value 不是 list：{type(v).__name__}")
        return list(v)

    return LevelPreviewConfig(
        comp_ids_1=_get_list("关卡号到展示元件ID_1"),
        comp_ids_2=_get_list("关卡号到展示元件ID_2"),
        pos_offset=_get_list("关卡号到展示位置偏移"),
        comp2_offset=_get_list("关卡号到第二元件自带偏移"),
        rot_1=_get_list("关卡号到展示旋转_1"),
        rot_2=_get_list("关卡号到展示旋转_2"),
    )


def _extract_decorations_list_from_template_obj(template_obj: Mapping[str, Any]) -> List[JsonDict]:
    meta = template_obj.get("metadata")
    if not isinstance(meta, Mapping):
        return []
    ci = meta.get("common_inspector")
    if not isinstance(ci, Mapping):
        return []
    model = ci.get("model")
    if not isinstance(model, Mapping):
        return []
    decorations = model.get("decorations")
    if isinstance(decorations, list):
        out: List[JsonDict] = []
        for it in list(decorations):
            if isinstance(it, Mapping):
                out.append(dict(it))
        return out
    return []


def _write_decorations_list_to_template_obj(template_obj: JsonDict, decorations: List[JsonDict]) -> None:
    meta = template_obj.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        template_obj["metadata"] = meta
    ci = meta.get("common_inspector")
    if not isinstance(ci, dict):
        ci = {}
        meta["common_inspector"] = ci
    model = ci.get("model")
    if not isinstance(model, dict):
        model = {}
        ci["model"] = model
    model["decorations"] = list(decorations)


def _format_py_literal(value: object) -> str:
    if isinstance(value, str):
        # 双引号风格（对齐 Graph Code 内现有）
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f"\"{escaped}\""
    if isinstance(value, bool):
        return "True" if bool(value) else "False"
    if value is None:
        return "None"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, tuple):
        return "(" + ", ".join(_format_py_literal(x) for x in value) + ")"
    if isinstance(value, list):
        return "[" + ", ".join(_format_py_literal(x) for x in value) + "]"
    if isinstance(value, dict):
        # 仅用于兜底；本工具写回主要写 list item
        items = ", ".join(f"{_format_py_literal(k)}: {_format_py_literal(v)}" for k, v in value.items())
        return "{" + items + "}"
    return repr(value)


def _patch_graph_variable_list_items(
    *,
    graph_code_file: Path,
    variable_name: str,
    replacements_by_level_1based: Mapping[int, object],
) -> Dict[str, Any]:
    """
    以最小文本差异补丁 GraphVariableConfig(name=variable_name) 的 default_value 列表项：
    - 通过行尾 `# <关卡号>` 注释定位具体行（假设每行一个 item）。
    """
    p = Path(graph_code_file).resolve()
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

    # ---- locate GraphVariableConfig block ----
    hit_idx = None
    for i, line in enumerate(lines):
        if f'name="{variable_name}"' in line or f"name='{variable_name}'" in line:
            hit_idx = i
            break
    if hit_idx is None:
        raise ValueError(f"未找到 GraphVariableConfig(name={variable_name!r})：{str(p)}")

    # ---- locate default_value=[ ----
    start_idx = None
    for i in range(hit_idx, min(hit_idx + 200, len(lines))):
        if "default_value" in lines[i] and "[" in lines[i]:
            if "default_value" in lines[i] and "=[" in lines[i].replace(" ", ""):
                start_idx = i
                break
    if start_idx is None:
        raise ValueError(f"未找到 {variable_name!r} 的 default_value=[ 段落：{str(p)}")

    # ---- find end of list: a line containing '],' (same or lower indent) ----
    base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip(" "))
    end_idx = None
    for i in range(start_idx + 1, min(start_idx + 400, len(lines))):
        line = lines[i]
        indent = len(line) - len(line.lstrip(" "))
        if indent <= base_indent and line.lstrip(" ").startswith("],"):
            end_idx = i
            break
    if end_idx is None:
        raise ValueError(f"未找到 {variable_name!r} 的 default_value 列表闭合行(],)：{str(p)}")

    # ---- patch items within [start_idx+1, end_idx) ----
    changed = 0
    for level, new_value in sorted(replacements_by_level_1based.items(), key=lambda kv: int(kv[0])):
        if not isinstance(level, int) or int(level) <= 0:
            raise ValueError(f"invalid level key: {level!r}")
        marker = f"# {int(level)}"
        match_line_idx: Optional[int] = None
        for j in range(start_idx + 1, end_idx):
            if marker in lines[j]:
                match_line_idx = j
                break
        if match_line_idx is None:
            raise ValueError(f"{variable_name!r} default_value 未找到关卡注释 {marker!r}：{str(p)}")

        old_line = lines[match_line_idx]
        indent_prefix = old_line[: len(old_line) - len(old_line.lstrip(" "))]
        # 保留尾部注释（从 marker 开始）
        comment_pos = old_line.find(marker)
        suffix = old_line[comment_pos:].rstrip("\n")
        new_literal = _format_py_literal(new_value)
        new_line = f"{indent_prefix}{new_literal},  {suffix}\n"
        if new_line != old_line:
            lines[match_line_idx] = new_line
            changed += 1

    if changed > 0:
        p.write_text("".join(lines), encoding="utf-8")

    return {"changed_lines": int(changed), "file": str(p), "variable_name": str(variable_name)}


def _coerce_def_id_int_from_decoration(deco: Mapping[str, Any]) -> Optional[int]:
    source_gia = deco.get("source_gia")
    if isinstance(source_gia, Mapping) and isinstance(source_gia.get("unit_id_int"), int):
        return int(source_gia.get("unit_id_int"))
    inst = deco.get("instanceId")
    if isinstance(inst, int):
        return int(inst)
    if isinstance(inst, str):
        m = _INSTANCE_ID_RE.match(str(inst).strip())
        if not m:
            return None
        digits = m.group(1)
        if digits == "" or not digits.isdigit():
            return None
        return int(digits)
    return None


def _alloc_stable_def_id_int(*, key_text: str, used: set[int]) -> int:
    h24 = int(zlib.crc32(str(key_text).encode("utf-8")) & 0x00FFFFFF)
    if h24 == 0:
        h24 = 1
    candidate = int(0x40000000 | int(h24))
    while candidate in used:
        low24 = int(candidate) & 0x00FFFFFF
        low24 = (int(low24) + 1) & 0x00FFFFFF
        if low24 == 0:
            low24 = 1
        candidate = int(0x40000000 | int(low24))
    used.add(int(candidate))
    return int(candidate)


def _ensure_unique_def_ids_for_merged_decorations(
    *,
    decorations: List[JsonDict],
    stable_key_prefix: str,
) -> Dict[str, Any]:
    used: set[int] = set()
    patched = 0
    skipped_missing = 0
    for idx, deco in enumerate(list(decorations)):
        def_id = _coerce_def_id_int_from_decoration(deco)
        if def_id is None:
            skipped_missing += 1
            continue
        if int(def_id) in used:
            new_id = _alloc_stable_def_id_int(key_text=f"{stable_key_prefix}:{idx}:{def_id}", used=used)
            deco["instanceId"] = f"gia_{int(new_id)}"
            source_gia = deco.get("source_gia")
            if isinstance(source_gia, dict):
                source_gia["unit_id_int"] = int(new_id)
            patched += 1
        else:
            used.add(int(def_id))
    return {"patched": int(patched), "skipped_missing_def_id": int(skipped_missing), "total": int(len(decorations))}


def _read_deco_trs(deco: Mapping[str, Any]) -> TRS:
    transform = deco.get("transform")
    if not isinstance(transform, Mapping):
        transform = {}
    pos_map = transform.get("pos")
    rot_map = transform.get("rot")
    scale_map = transform.get("scale")
    pos = (
        float(pos_map.get("x", 0.0)) if isinstance(pos_map, Mapping) else 0.0,
        float(pos_map.get("y", 0.0)) if isinstance(pos_map, Mapping) else 0.0,
        float(pos_map.get("z", 0.0)) if isinstance(pos_map, Mapping) else 0.0,
    )
    rot = (
        float(rot_map.get("x", 0.0)) if isinstance(rot_map, Mapping) else 0.0,
        float(rot_map.get("y", 0.0)) if isinstance(rot_map, Mapping) else 0.0,
        float(rot_map.get("z", 0.0)) if isinstance(rot_map, Mapping) else 0.0,
    )
    scale = (
        float(scale_map.get("x", 1.0)) if isinstance(scale_map, Mapping) else 1.0,
        float(scale_map.get("y", 1.0)) if isinstance(scale_map, Mapping) else 1.0,
        float(scale_map.get("z", 1.0)) if isinstance(scale_map, Mapping) else 1.0,
    )
    return TRS(pos=tuple(pos), rot_deg=tuple(rot), scale=tuple(scale))


def _write_deco_trs(deco: JsonDict, trs: TRS) -> None:
    transform = deco.get("transform")
    if not isinstance(transform, dict):
        transform = {}
        deco["transform"] = transform
    pos_map = transform.get("pos")
    if not isinstance(pos_map, dict):
        pos_map = {}
        transform["pos"] = pos_map
    rot_map = transform.get("rot")
    if not isinstance(rot_map, dict):
        rot_map = {}
        transform["rot"] = rot_map
    scale_map = transform.get("scale")
    if not isinstance(scale_map, dict):
        scale_map = {}
        transform["scale"] = scale_map

    pos_map["x"], pos_map["y"], pos_map["z"] = float(trs.pos[0]), float(trs.pos[1]), float(trs.pos[2])
    rot_map["x"], rot_map["y"], rot_map["z"] = float(trs.rot_deg[0]), float(trs.rot_deg[1]), float(trs.rot_deg[2])
    scale_map["x"], scale_map["y"], scale_map["z"] = float(trs.scale[0]), float(trs.scale[1]), float(trs.scale[2])


def _merge_decorations_keep_world(
    *,
    decorations_a: List[JsonDict],
    decorations_b: List[JsonDict],
    parent_a: TRS,
    parent_b: TRS,
) -> List[JsonDict]:
    """
    keep_world：在 parent_a 坐标系下，合并 parent_b 的装饰物。

    目标：对于 b 的每个装饰物 Lb，生成 Lb' 使得：
      parent_a ∘ Lb' == parent_b ∘ Lb
    即：
      Lb' = inv(parent_a) ∘ parent_b ∘ Lb
    """
    inv_a = mat4_inv_trs(pos=parent_a.pos, rot_deg=parent_a.rot_deg, scale=parent_a.scale)
    mat_b = mat4_from_trs(pos=parent_b.pos, rot_deg=parent_b.rot_deg, scale=parent_b.scale)
    rel = mat4_mul(inv_a, mat_b)

    out: List[JsonDict] = [dict(x) for x in list(decorations_a)]
    for deco in list(decorations_b):
        d2 = dict(deco)
        local = _read_deco_trs(d2)
        local_mat = mat4_from_trs(pos=local.pos, rot_deg=local.rot_deg, scale=local.scale)
        new_mat = mat4_mul(rel, local_mat)
        new_trs = decompose_mat4_to_trs(new_mat)
        _write_deco_trs(d2, new_trs)
        out.append(d2)
    return out


def _load_templates_index_by_name(*, project_root: Path) -> Dict[str, Path]:
    templates_dir = (Path(project_root).resolve() / "元件库").resolve()
    index_file = (templates_dir / "templates_index.json").resolve()
    if not index_file.is_file():
        raise FileNotFoundError(f"缺少 templates_index.json：{str(index_file)}")
    index_obj = json.loads(index_file.read_text(encoding="utf-8"))
    if not isinstance(index_obj, list):
        raise ValueError(f"templates_index.json 不是 list：{str(index_file)}")
    out: Dict[str, Path] = {}
    for it in list(index_obj):
        if not isinstance(it, Mapping):
            continue
        name = str(it.get("name") or "").strip()
        output = str(it.get("output") or "").strip()
        if name == "" or output == "":
            continue
        out[name] = (Path(project_root).resolve() / output).resolve()
    return out


def _alloc_new_numeric_template_id(*, templates_index: Iterable[Mapping[str, Any]]) -> str:
    max_id: Optional[int] = None
    for it in list(templates_index):
        tid = it.get("template_id") if isinstance(it, Mapping) else None
        if isinstance(tid, str) and tid.isdigit():
            v = int(tid)
            if max_id is None or v > max_id:
                max_id = v
    if max_id is None:
        # fallback：使用 1077936000 段位起步（与测试项目已有样本一致）
        return str(1077936000)
    return str(int(max_id) + 1)


def _rebuild_templates_index_from_disk(*, project_root: Path) -> List[JsonDict]:
    project = Path(project_root).resolve()
    templates_dir = (project / "元件库").resolve()
    out: List[JsonDict] = []
    for p in sorted(templates_dir.glob("*.json"), key=lambda x: x.as_posix().casefold()):
        if p.name == "templates_index.json":
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj, Mapping):
            continue
        template_id = str(obj.get("template_id") or "").strip()
        name = str(obj.get("name") or "").strip()
        entity_type = str(obj.get("entity_type") or "").strip() or "物件"
        if template_id == "" or name == "":
            continue
        rel = p.relative_to(project).as_posix()
        out.append(
            {
                "template_id": template_id,
                "name": name,
                "entity_type": entity_type,
                "output": rel,
            }
        )
    out.sort(key=lambda x: (str(x.get("name") or ""), str(x.get("template_id") or "")))
    return list(out)


# ------------------------------------------------------------------ public shared helpers
# 这些 helper 会被 `preview_merge/*` 其它模块复用：对外必须是“非下划线”名字，
# 以满足 `tests/arch/test_ugc_file_tools_import_policy.py` 的 import-policy（禁止跨模块 from-import 私有名）。


def read_text(path: Path) -> str:
    return _read_text(Path(path))


def write_text(path: Path, text: str) -> None:
    _write_text(Path(path), str(text))


def read_json(path: Path) -> JsonDict:
    return _read_json(Path(path))


def write_json(path: Path, obj: JsonDict) -> None:
    _write_json(Path(path), obj)


def extract_decorations_list_from_template_obj(template_obj: Mapping[str, Any]) -> List[JsonDict]:
    return _extract_decorations_list_from_template_obj(template_obj)


def write_decorations_list_to_template_obj(template_obj: JsonDict, decorations: List[JsonDict]) -> None:
    _write_decorations_list_to_template_obj(template_obj, decorations)


def coerce_def_id_int_from_decoration(deco: Mapping[str, Any]) -> Optional[int]:
    return _coerce_def_id_int_from_decoration(deco)


def alloc_stable_def_id_int(*, key_text: str, used: set[int]) -> int:
    return _alloc_stable_def_id_int(key_text=str(key_text), used=used)


def merge_decorations_keep_world(
    *,
    decorations_a: List[JsonDict],
    decorations_b: List[JsonDict],
    parent_a: TRS,
    parent_b: TRS,
) -> List[JsonDict]:
    return _merge_decorations_keep_world(
        decorations_a=decorations_a,
        decorations_b=decorations_b,
        parent_a=parent_a,
        parent_b=parent_b,
    )


def alloc_new_numeric_template_id(*, templates_index: Iterable[Mapping[str, Any]]) -> str:
    return _alloc_new_numeric_template_id(templates_index=templates_index)


def rebuild_templates_index_from_disk(*, project_root: Path) -> List[JsonDict]:
    return _rebuild_templates_index_from_disk(project_root=project_root)


def merge_level_select_preview_components_in_project(
    *,
    project_root: Path,
    player_graph_file: Path,
    executor_graph_file: Path,
    dangerous: bool,
    output_name_suffix: str = "",
) -> Dict[str, Any]:
    """
    对“选关预览”双元件关卡（当前约定：第 4/5/8 关）做合并：
    - 生成新的“单母体展示元件模板”（写入 元件库/）
    - 补丁玩家图 GraphVariables：comp2 置 0；comp1 指向新模板 component_key
    - 补丁执行图：创建第二元件前先判断 comp2_id!=0（避免写回后仍强制创建）
    """
    project = Path(project_root).resolve()
    templates_dir = (project / "元件库").resolve()
    if not templates_dir.is_dir():
        raise FileNotFoundError(f"项目存档缺少 元件库/：{str(templates_dir)}")

    templates_index_file = (templates_dir / "templates_index.json").resolve()
    templates_index_obj = json.loads(templates_index_file.read_text(encoding="utf-8"))
    if not isinstance(templates_index_obj, list):
        raise ValueError(f"templates_index.json 不是 list：{str(templates_index_file)}")

    by_name = _load_templates_index_by_name(project_root=project)
    cfg = load_level_preview_config_from_player_graph(player_graph_file=Path(player_graph_file))

    levels_to_merge: List[int] = []
    for level in range(1, 11):
        v2 = cfg.comp_ids_2[level - 1] if (level - 1) < len(cfg.comp_ids_2) else 0
        if _extract_component_key_name(v2) is not None:
            levels_to_merge.append(int(level))

    if not levels_to_merge:
        return {
            "project_root": str(project),
            "merged_levels": [],
            "generated_templates": [],
            "patched_graphs": [],
            "dangerous": bool(dangerous),
            "reason": "no_levels_with_comp2",
        }

    generated_templates: List[Dict[str, Any]] = []
    comp1_repl: Dict[int, object] = {}
    comp2_repl: Dict[int, object] = {}
    comp2_offset_repl: Dict[int, object] = {}
    rot2_repl: Dict[int, object] = {}

    for level in list(levels_to_merge):
        idx0 = int(level) - 1
        v1 = cfg.comp_ids_1[idx0] if idx0 < len(cfg.comp_ids_1) else 0
        v2 = cfg.comp_ids_2[idx0] if idx0 < len(cfg.comp_ids_2) else 0
        name1 = _extract_component_key_name(v1)
        name2 = _extract_component_key_name(v2)
        if name1 is None or name2 is None:
            continue

        t1_path = by_name.get(str(name1))
        t2_path = by_name.get(str(name2))
        if t1_path is None or t2_path is None:
            raise FileNotFoundError(f"未在 templates_index.json 找到展示元件模板：{name1!r} / {name2!r}")
        t1 = _read_json(Path(t1_path))
        t2 = _read_json(Path(t2_path))

        decos1 = _extract_decorations_list_from_template_obj(t1)
        decos2 = _extract_decorations_list_from_template_obj(t2)

        pos1 = _as_vec3(cfg.pos_offset[idx0], label=f"pos_offset[{level}]")
        pos2 = _as_vec3(cfg.comp2_offset[idx0], label=f"comp2_offset[{level}]")
        rot1 = _as_vec3(cfg.rot_1[idx0], label=f"rot_1[{level}]")
        rot2 = _as_vec3(cfg.rot_2[idx0], label=f"rot_2[{level}]")

        parent1 = TRS(pos=pos1, rot_deg=rot1, scale=(1.0, 1.0, 1.0))
        parent2 = TRS(pos=pos2, rot_deg=rot2, scale=(1.0, 1.0, 1.0))
        merged_decos = _merge_decorations_keep_world(decorations_a=decos1, decorations_b=decos2, parent_a=parent1, parent_b=parent2)

        # def_id 去重（避免写回 root27 时被 scanner 跳过）
        dedup_report = _ensure_unique_def_ids_for_merged_decorations(
            decorations=merged_decos,
            stable_key_prefix=f"level_preview_merge:{level}:{name1}:{name2}",
        )

        base_name = str(name1)
        if base_name.endswith("1") and str(name2).endswith("2") and base_name[:-1] == str(name2)[:-1]:
            out_name = base_name[:-1]
        else:
            out_name = f"{base_name}_合并"
        out_name = str(out_name + (str(output_name_suffix) if str(output_name_suffix) else "")).strip()
        if out_name == "":
            out_name = f"第{int(level)}关展示元件_合并"

        new_template_id = _alloc_new_numeric_template_id(templates_index=templates_index_obj)
        # bump local view (avoid duplicates within this run)
        templates_index_obj.append({"template_id": str(new_template_id)})

        out_obj: JsonDict = dict(t1)
        out_obj["template_id"] = str(new_template_id)
        out_obj["name"] = str(out_name)
        out_obj["description"] = f"由工具合并生成：{name1} + {name2}"

        meta = out_obj.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
            out_obj["metadata"] = meta
        ugc = meta.get("ugc")
        if not isinstance(ugc, dict):
            ugc = {}
            meta["ugc"] = ugc
        ugc["source"] = "merged_level_select_preview_components"
        ugc["merged_from"] = [
            {"template_name": str(name1), "template_file": str(Path(t1_path).resolve())},
            {"template_name": str(name2), "template_file": str(Path(t2_path).resolve())},
        ]

        _write_decorations_list_to_template_obj(out_obj, merged_decos)

        file_stem = sanitize_file_stem(out_name)
        out_path = (templates_dir / f"{file_stem}_{new_template_id}.json").resolve()

        if bool(dangerous):
            _write_json(out_path, out_obj)

        generated_templates.append(
            {
                "level": int(level),
                "output_template_id": str(new_template_id),
                "output_template_name": str(out_name),
                "output_template_file": str(out_path),
                "source_templates": [str(t1_path), str(t2_path)],
                "decorations_count": int(len(merged_decos)),
                "def_id_dedup": dict(dedup_report),
            }
        )

        comp1_repl[int(level)] = f"{_COMPONENT_KEY_PREFIX}{out_name}"
        comp2_repl[int(level)] = 0
        comp2_offset_repl[int(level)] = (0.0, 0.0, 0.0)
        rot2_repl[int(level)] = (0.0, 0.0, 0.0)

    patched_graphs: List[Dict[str, Any]] = []
    if bool(dangerous):
        # update templates_index.json
        templates_index_sorted = _rebuild_templates_index_from_disk(project_root=project)
        _write_text(templates_index_file, json.dumps(templates_index_sorted, ensure_ascii=False, indent=2) + "\n")

        # patch player graph variables
        patched_graphs.append(
            _patch_graph_variable_list_items(
                graph_code_file=Path(player_graph_file),
                variable_name="关卡号到展示元件ID_1",
                replacements_by_level_1based=comp1_repl,
            )
        )
        patched_graphs.append(
            _patch_graph_variable_list_items(
                graph_code_file=Path(player_graph_file),
                variable_name="关卡号到展示元件ID_2",
                replacements_by_level_1based=comp2_repl,
            )
        )
        patched_graphs.append(
            _patch_graph_variable_list_items(
                graph_code_file=Path(player_graph_file),
                variable_name="关卡号到第二元件自带偏移",
                replacements_by_level_1based=comp2_offset_repl,
            )
        )
        patched_graphs.append(
            _patch_graph_variable_list_items(
                graph_code_file=Path(player_graph_file),
                variable_name="关卡号到展示旋转_2",
                replacements_by_level_1based=rot2_repl,
            )
        )

        # patch executor graph: guard create comp2 by comp2_id!=0
        patched_graphs.append(patch_executor_graph_guard_comp2_create(executor_graph_file=Path(executor_graph_file)))

    return {
        "project_root": str(project),
        "merged_levels": list(levels_to_merge),
        "generated_templates": list(generated_templates),
        "patched_graphs": list(patched_graphs),
        "dangerous": bool(dangerous),
    }


def patch_executor_graph_guard_comp2_create(*, executor_graph_file: Path) -> Dict[str, Any]:
    """
    将“固定关卡号判断”补丁为更稳的口径：
    - 读取 comp2_id 后，仅当 comp2_id!=0 才创建第二元件；
    - 允许 player_graph 通过表驱动哪些关卡是双元件（无需在执行图里硬编码关卡号）。

    说明：该补丁应可重复执行（已补丁则 no-op）。
    """
    p = Path(executor_graph_file).resolve()
    text = p.read_text(encoding="utf-8")

    # 目标片段：if (目标关卡 == 4) or (目标关卡 == 5) or (目标关卡 == 8):
    marker = "if (目标关卡 == 4) or (目标关卡 == 5) or (目标关卡 == 8):"
    if marker not in text:
        # 已升级为“表驱动 comp2_id”或其它版本：若已存在 guard 则视为已补丁
        if ("预览元件ID2" in text) and (
            ("if 预览元件ID2 == 0" in text) or ("if 预览元件ID2 == 空元件ID" in text)
        ):
            return {"file": str(p), "changed": False, "reason": "already_patched"}
        raise ValueError(f"未找到预期片段（可能已改过或版本不一致）：{marker!r} file={str(p)}")

    # 在块内插入 guard：读取到 预览元件ID2 后，若为 0 则跳过创建
    lines = text.splitlines(keepends=True)
    changed = False
    for i, line in enumerate(lines):
        if marker in line:
            base_indent = line[: len(line) - len(line.lstrip(" "))]
            # 在该 if 块中寻找 “预览元件ID2: ... = 获取列表对应值”
            for j in range(i + 1, min(i + 60, len(lines))):
                if "预览元件ID2" in lines[j] and "获取列表对应值" in lines[j]:
                    indent2 = lines[j][: len(lines[j]) - len(lines[j].lstrip(" "))]
                    guard_line = f"{indent2}if 预览元件ID2 == 0:\n{indent2}    return\n"
                    # 若已存在 guard，则不重复插入
                    window = "".join(lines[j : min(j + 6, len(lines))])
                    if "if 预览元件ID2 == 0" in window:
                        return {"file": str(p), "changed": False, "reason": "already_patched"}
                    lines.insert(j + 1, guard_line)
                    changed = True
                    break
            break

    if not changed:
        raise ValueError(f"未能在目标 if 块内定位 '预览元件ID2 = 获取列表对应值'：{str(p)}")

    p.write_text("".join(lines), encoding="utf-8")
    return {"file": str(p), "changed": True}


__all__ = [
    "LevelPreviewConfig",
    "load_level_preview_config_from_player_graph",
    "merge_level_select_preview_components_in_project",
    "patch_executor_graph_guard_comp2_create",
]

