from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.preview_merge.level_select_preview_components_merger import (
    JsonDict,
    TRS,
    Vec3,
    alloc_new_numeric_template_id,
    alloc_stable_def_id_int,
    coerce_def_id_int_from_decoration,
    extract_decorations_list_from_template_obj,
    merge_decorations_keep_world,
    read_json,
    rebuild_templates_index_from_disk,
    write_decorations_list_to_template_obj,
    write_json,
    write_text,
)


@dataclass(frozen=True, slots=True)
class InstanceRef:
    instance_json_file: Path
    instance_id: str
    name: str
    template_id: str
    parent_trs: TRS


def _as_vec3_from_list(value: object, *, default: Vec3) -> Vec3:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        x, y, z = value[0], value[1], value[2]
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and isinstance(z, (int, float)):
            return (float(x), float(y), float(z))
    return tuple(default)


def _read_instance_ref(instance_json_file: Path) -> InstanceRef:
    obj = read_json(Path(instance_json_file))
    instance_id = str(obj.get("instance_id") or "").strip()
    name = str(obj.get("name") or "").strip()
    template_id = str(obj.get("template_id") or "").strip()
    if instance_id == "" or name == "" or template_id == "":
        raise ValueError(f"InstanceConfig 缺少 instance_id/name/template_id：{str(Path(instance_json_file).resolve())}")

    pos = _as_vec3_from_list(obj.get("position"), default=(0.0, 0.0, 0.0))
    rot = _as_vec3_from_list(obj.get("rotation"), default=(0.0, 0.0, 0.0))

    scale: Vec3 = (1.0, 1.0, 1.0)
    if "scale" in obj:
        scale = _as_vec3_from_list(obj.get("scale"), default=scale)
    meta = obj.get("metadata") if isinstance(obj.get("metadata"), Mapping) else {}
    if isinstance(meta, Mapping):
        ugc_scale = meta.get("ugc_scale")
        scale = _as_vec3_from_list(ugc_scale, default=scale)

    return InstanceRef(
        instance_json_file=Path(instance_json_file).resolve(),
        instance_id=str(instance_id),
        name=str(name),
        template_id=str(template_id),
        parent_trs=TRS(pos=pos, rot_deg=rot, scale=scale),
    )


def _load_templates_index_by_id(*, project_root: Path) -> Dict[str, Path]:
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
        tid = str(it.get("template_id") or "").strip()
        output = str(it.get("output") or "").strip()
        if tid == "" or output == "":
            continue
        out[tid] = (Path(project_root).resolve() / output).resolve()
    return out


def _rebuild_instances_index_from_disk(*, project_root: Path) -> List[JsonDict]:
    project = Path(project_root).resolve()
    instances_dir = (project / "实体摆放").resolve()
    out: List[JsonDict] = []
    if not instances_dir.is_dir():
        return out
    for p in sorted(instances_dir.glob("*.json"), key=lambda x: x.as_posix().casefold()):
        if p.name == "instances_index.json":
            continue
        if p.name.startswith("自研_"):
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj, Mapping):
            continue
        iid = str(obj.get("instance_id") or "").strip()
        name = str(obj.get("name") or "").strip()
        tid = str(obj.get("template_id") or "").strip()
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), Mapping) else {}
        entity_type = str(meta.get("entity_type") or "").strip()
        is_level_entity = bool(meta.get("is_level_entity"))
        if iid == "" or name == "" or tid == "" or entity_type == "":
            continue
        rel = str(p.relative_to(project)).replace("\\", "/")
        out.append(
            {
                "instance_id": iid,
                "name": name,
                "template_id": tid,
                "entity_type": entity_type,
                "is_level_entity": bool(is_level_entity),
                "output": rel,
            }
        )
    out.sort(
        key=lambda item: (
            0 if item.get("is_level_entity") else 1,
            str(item.get("name") or ""),
            str(item.get("instance_id") or ""),
        )
    )
    return list(out)


def merge_project_instances_keep_world(
    *,
    project_root: Path,
    include_instance_json_files: Sequence[Path],
    output_template_name: str,
    output_instance_name: str,
    output_instance_id: str,
    dangerous: bool,
) -> Dict[str, Any]:
    """
    合并多个实体摆放实例为一个新实例（keep_world 口径保持装饰物世界变换不变）：
    - 输入：多个 InstanceConfig(JSON)，其引用模板需存在于 元件库/ 且模板包含 decorations。
    - 输出：新模板（合并后的 decorations） + 新实例（引用新模板，transform 取第一个实例）。

    说明：该工具不会删除旧实例/旧模板；仅生成新的。
    """
    project = Path(project_root).resolve()
    templates_dir = (project / "元件库").resolve()
    instances_dir = (project / "实体摆放").resolve()
    if not templates_dir.is_dir():
        raise FileNotFoundError(f"项目存档缺少 元件库/：{str(templates_dir)}")
    if not instances_dir.is_dir():
        raise FileNotFoundError(f"项目存档缺少 实体摆放/：{str(instances_dir)}")

    instance_files = [Path(p).resolve() for p in list(include_instance_json_files or [])]
    if len(instance_files) < 2:
        raise ValueError("include_instance_json_files 至少需要 2 个实例文件")

    refs = [_read_instance_ref(p) for p in instance_files]
    base = refs[0]

    tpl_by_id = _load_templates_index_by_id(project_root=project)
    templates_index_file = (templates_dir / "templates_index.json").resolve()
    templates_index_obj = json.loads(templates_index_file.read_text(encoding="utf-8"))
    if not isinstance(templates_index_obj, list):
        raise ValueError(f"templates_index.json 不是 list：{str(templates_index_file)}")

    # base template obj（用于继承 type_code/entity_config 等）
    base_tpl_path = tpl_by_id.get(str(base.template_id))
    if base_tpl_path is None:
        raise FileNotFoundError(f"未在 templates_index.json 找到 base.template_id 对应模板：{base.template_id!r}")
    base_tpl_obj = read_json(base_tpl_path)

    merged_decos: List[JsonDict] = []
    used_def_ids: set[int] = set()

    for idx, r in enumerate(list(refs)):
        tpl_path = tpl_by_id.get(str(r.template_id))
        if tpl_path is None:
            raise FileNotFoundError(f"未在 templates_index.json 找到实例引用模板：template_id={r.template_id!r} (instance={r.instance_id})")
        tpl_obj = read_json(tpl_path)
        decos = extract_decorations_list_from_template_obj(tpl_obj)
        if not decos:
            continue
        if idx == 0:
            merged_decos = [dict(x) for x in list(decos)]
        else:
            merged_decos = merge_decorations_keep_world(
                decorations_a=list(merged_decos),
                decorations_b=list(decos),
                parent_a=base.parent_trs,
                parent_b=r.parent_trs,
            )

    # def_id 去重（跨多个模板合并时可能碰撞）
    patched = 0
    for i, deco in enumerate(list(merged_decos)):
        did = coerce_def_id_int_from_decoration(deco)
        if did is None:
            continue
        if int(did) in used_def_ids:
            new_id = alloc_stable_def_id_int(
                key_text=f"merge_project_instances:{base.instance_id}:{i}:{did}",
                used=used_def_ids,
            )
            deco["instanceId"] = f"gia_{int(new_id)}"
            sg = deco.get("source_gia")
            if isinstance(sg, dict):
                sg["unit_id_int"] = int(new_id)
            patched += 1
        else:
            used_def_ids.add(int(did))

    # new template id
    new_template_id = alloc_new_numeric_template_id(templates_index=templates_index_obj)
    templates_index_obj.append({"template_id": str(new_template_id)})

    out_tpl_obj: JsonDict = dict(base_tpl_obj)
    out_tpl_obj["template_id"] = str(new_template_id)
    out_tpl_obj["name"] = str(output_template_name).strip()
    out_tpl_obj["description"] = f"由工具合并生成：instances={','.join(r.instance_id for r in refs)}"
    write_decorations_list_to_template_obj(out_tpl_obj, list(merged_decos))

    file_stem = sanitize_file_stem(str(output_template_name))
    out_tpl_path = (templates_dir / f"{file_stem}_{new_template_id}.json").resolve()

    out_inst_obj: JsonDict = {
        "instance_id": str(output_instance_id).strip(),
        "name": str(output_instance_name).strip(),
        "template_id": str(new_template_id),
        "position": [float(base.parent_trs.pos[0]), float(base.parent_trs.pos[1]), float(base.parent_trs.pos[2])],
        "rotation": [float(base.parent_trs.rot_deg[0]), float(base.parent_trs.rot_deg[1]), float(base.parent_trs.rot_deg[2])],
        "scale": [float(base.parent_trs.scale[0]), float(base.parent_trs.scale[1]), float(base.parent_trs.scale[2])],
        "override_variables": [],
        "additional_graphs": [],
        "additional_components": [],
        "metadata": {
            "entity_type": "物件",
            "is_level_entity": False,
            "ugc": {
                "source": "merged_project_instances_keep_world",
                "merged_from_instances": [str(r.instance_id) for r in refs],
            },
        },
        "graph_variable_overrides": {},
    }

    out_inst_stem = sanitize_file_stem(str(output_instance_name))
    out_inst_path = (instances_dir / f"{out_inst_stem}_{sanitize_file_stem(str(output_instance_id))}.json").resolve()

    if bool(dangerous):
        write_json(out_tpl_path, out_tpl_obj)
        write_json(out_inst_path, out_inst_obj)

        # rebuild indices
        templates_index_sorted = rebuild_templates_index_from_disk(project_root=project)
        write_text((templates_dir / "templates_index.json").resolve(), json.dumps(templates_index_sorted, ensure_ascii=False, indent=2) + "\n")
        instances_index_sorted = _rebuild_instances_index_from_disk(project_root=project)
        write_text((instances_dir / "instances_index.json").resolve(), json.dumps(instances_index_sorted, ensure_ascii=False, indent=2) + "\n")

    return {
        "project_root": str(project),
        "dangerous": bool(dangerous),
        "input_instances": [str(p) for p in instance_files],
        "output_template_id": str(new_template_id),
        "output_template_file": str(out_tpl_path),
        "output_instance_id": str(output_instance_id).strip(),
        "output_instance_file": str(out_inst_path),
        "decorations_count": int(len(merged_decos)),
        "def_id_patched": int(patched),
    }


__all__ = ["merge_project_instances_keep_world"]

