from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from engine.utils.resource_library_layout import get_packages_root_dir

from .export_gia import _build_decorations_report
from .settings import ShapeEditorSettings


JsonDict = Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="microseconds")


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path) -> JsonDict:
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 必须是 object：{str(path)!r}")
    return obj


def _write_json(path: Path, obj: JsonDict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_shape_editor_ref_images_dir(*, project_root: Path) -> Path:
    """
    shape-editor 的参考图落盘目录（用于“项目级持久化”）。

    约束：
    - 不落在 `实体摆放/`：该目录应只包含实体 JSON，避免资源索引告警。
    - 落在 `管理配置/`：与项目存档管理类元数据更契合。
    """
    cfg_dir = _ensure_dir(Path(project_root).resolve() / "管理配置")
    return _ensure_dir((cfg_dir / "shape_editor_ref_images").resolve())


def _guess_image_ext_from_mime(mime: str) -> str:
    m = str(mime or "").strip().lower()
    if m == "image/png":
        return ".png"
    if m in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if m == "image/webp":
        return ".webp"
    if m == "image/gif":
        return ".gif"
    return ".bin"


def _normalize_src_url_to_stable_path(src: str) -> str:
    """
    将 URL 归一化为“稳定的 path”（不包含 host/port），避免本地端口变化导致引用失效。
    """
    s = str(src or "").strip()
    if s == "":
        return ""
    # data url：保持原样（后续会落盘并替换为稳定 path）
    if s.startswith("data:"):
        return s
    parts = urlsplit(s)
    if parts.scheme in {"http", "https"} and str(parts.path or "").startswith("/"):
        return str(parts.path or "")
    # already stable path
    if s.startswith("/"):
        return s
    # relative path：强制转为 root-absolute（与静态服务根一致）
    return "/" + s.replace("\\", "/").lstrip("/")


def _persist_reference_images_in_canvas_payload(
    *,
    workspace_root: Path,
    project_root: Path,
    canvas_payload: JsonDict,
) -> list[JsonDict]:
    """
    将 payload 内的参考图（type=image 且 isReference=True）落盘到项目存档，并把 obj.src 替换为稳定 path。

    前端会把图片 src 放在 obj.src：
    - 新上传/规整后的参考图：data:image/...;base64,...
    - 已持久化过的参考图：/assets/.../shape_editor_ref_images/ref_xxx.png
    - 也可能是 http://127.0.0.1:port/...（需要剥离 host/port）
    """
    objects = canvas_payload.get("objects")
    if not isinstance(objects, list):
        return []

    ref_dir = _get_shape_editor_ref_images_dir(project_root=project_root)
    ws_root = Path(workspace_root).resolve()

    results: list[JsonDict] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        is_ref = obj.get("isReference")
        if not isinstance(is_ref, bool) or not is_ref:
            continue
        t = str(obj.get("type") or "").strip().lower()
        if t != "image":
            continue

        src0 = str(obj.get("src") or "").strip()
        src = _normalize_src_url_to_stable_path(src0)
        if not src:
            continue

        saved_sha1 = ""
        saved_mime = ""
        stored = False

        if src.startswith("data:image/") and ";base64," in src:
            header, b64 = src.split(",", 1)
            mime = header[5:].split(";", 1)[0].strip().lower()
            data = base64.b64decode(str(b64 or "").strip())
            sha1 = hashlib.sha1(data).hexdigest()
            ext = _guess_image_ext_from_mime(mime)
            out_file = (ref_dir / f"ref_{sha1}{ext}").resolve()
            if not out_file.is_file():
                out_file.write_bytes(data)
            rel = out_file.relative_to(ws_root)
            src = "/" + rel.as_posix()
            saved_sha1 = sha1
            saved_mime = mime
            stored = True

        # update payload in-place (so the saved project JSON stays small & stable)
        obj["src"] = str(src)
        obj["src_kind"] = "project_file" if stored else "path"
        if saved_sha1:
            obj["src_sha1"] = str(saved_sha1)
        if saved_mime:
            obj["src_mime"] = str(saved_mime)

        obj_id = str(obj.get("id") or "").strip()
        results.append(
            {
                "id": obj_id,
                "src": str(src),
                "stored": bool(stored),
                "sha1": str(saved_sha1),
                "mime": str(saved_mime),
            }
        )

    return results


def resolve_project_root(*, resource_library_dir: Path, package_id: str) -> Path:
    package_id_text = str(package_id or "").strip()
    if package_id_text == "" or package_id_text == "global_view":
        raise ValueError("必须在“具体项目存档”上下文落盘（global_view 不支持）")
    return (get_packages_root_dir(Path(resource_library_dir).resolve()) / package_id_text).resolve()


def _get_shape_editor_project_state_file(*, project_root: Path) -> Path:
    """
    形状编辑器的“项目级状态”（例如最近打开的实体摆放 rel_path）。

    注意：
    - 不落在 `实体摆放/`，避免污染实体目录（该目录应只包含实体 JSON）。
    - 落在 `管理配置/`，与“项目存档的管理类元数据”更契合。
    """
    cfg_dir = _ensure_dir(Path(project_root).resolve() / "管理配置")
    return (cfg_dir / "shape_editor_state.json").resolve()


def load_shape_editor_project_state(
    *,
    resource_library_dir: Path,
    package_id: str,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    state_file = _get_shape_editor_project_state_file(project_root=project_root)
    if not state_file.is_file():
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "last_opened_rel_path": "",
        }

    obj = _read_json(state_file)
    rel = str(obj.get("last_opened_rel_path") or "").strip().replace("\\", "/")
    if rel == "":
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "last_opened_rel_path": "",
        }

    placements_dir = (project_root / "实体摆放").resolve()
    p = (project_root / rel).resolve()
    if placements_dir not in p.parents:
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "last_opened_rel_path": "",
        }
    if p.suffix.lower() != ".json":
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "last_opened_rel_path": "",
        }
    if not p.is_file():
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "last_opened_rel_path": "",
        }

    return {
        "ok": True,
        "has_data": True,
        "project_root": str(project_root),
        "state_file": str(state_file),
        "last_opened_rel_path": str(rel),
        "placement_file": str(p),
    }


def save_shape_editor_project_state(
    *,
    resource_library_dir: Path,
    package_id: str,
    last_opened_rel_path: str | None,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    state_file = _get_shape_editor_project_state_file(project_root=project_root)

    rel = str(last_opened_rel_path or "").strip().replace("\\", "/")
    if rel:
        placements_dir = (project_root / "实体摆放").resolve()
        p = (project_root / rel).resolve()
        if placements_dir not in p.parents:
            raise ValueError("非法 rel_path：不在 实体摆放 目录下")
        if p.suffix.lower() != ".json":
            raise ValueError("rel_path 必须是 .json")
        if not p.is_file():
            raise FileNotFoundError(str(p))

    payload: JsonDict = {
        "last_opened_rel_path": rel,
        "updated_at": _utc_now_iso(),
    }
    _write_json(state_file, payload)
    return {
        "ok": True,
        "project_root": str(project_root),
        "state_file": str(state_file),
        "last_opened_rel_path": rel,
    }


def _get_shape_editor_pixel_workbench_dir(*, project_root: Path) -> Path:
    """
    shape-editor 像素工作台（PerfectPixel）项目级持久化目录：
    - state.json：工作台会话（素材列表/参数/选中项）
    - px_<sha1>.png：每张素材当前“标准化像素矩阵”（含改色结果）
    """
    cfg_dir = _ensure_dir(Path(project_root).resolve() / "管理配置")
    return _ensure_dir((cfg_dir / "shape_editor_pixel_workbench").resolve())


def _get_shape_editor_pixel_workbench_state_file(*, project_root: Path) -> Path:
    return (_get_shape_editor_pixel_workbench_dir(project_root=project_root) / "state.json").resolve()


def _persist_pixel_workbench_matrices_in_state(
    *,
    workspace_root: Path,
    project_root: Path,
    state_payload: JsonDict,
) -> list[JsonDict]:
    assets = state_payload.get("assets")
    if not isinstance(assets, list):
        return []

    out_dir = _get_shape_editor_pixel_workbench_dir(project_root=project_root)
    ws_root = Path(workspace_root).resolve()

    results: list[JsonDict] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        src0 = str(asset.get("matrix_src") or "").strip()
        src = _normalize_src_url_to_stable_path(src0)
        if src == "":
            continue

        saved_sha1 = ""
        saved_mime = ""
        stored = False

        if src.startswith("data:image/") and ";base64," in src:
            header, b64 = src.split(",", 1)
            mime = header[5:].split(";", 1)[0].strip().lower()
            data = base64.b64decode(str(b64 or "").strip())
            sha1 = hashlib.sha1(data).hexdigest()
            ext = _guess_image_ext_from_mime(mime)
            out_file = (out_dir / f"px_{sha1}{ext}").resolve()
            if not out_file.is_file():
                out_file.write_bytes(data)
            rel = out_file.relative_to(ws_root)
            src = "/" + rel.as_posix()
            saved_sha1 = sha1
            saved_mime = mime
            stored = True

        # update payload in-place (so the saved project JSON stays small & stable)
        asset["matrix_src"] = str(src)
        asset["matrix_src_kind"] = "project_file" if stored else "path"
        if saved_sha1:
            asset["matrix_sha1"] = str(saved_sha1)
        if saved_mime:
            asset["matrix_mime"] = str(saved_mime)

        asset_id = str(asset.get("id") or "").strip()
        results.append(
            {
                "id": asset_id,
                "matrix_src": str(src),
                "stored": bool(stored),
                "sha1": str(saved_sha1),
                "mime": str(saved_mime),
            }
        )
    return results


def load_shape_editor_pixel_workbench_state(
    *,
    resource_library_dir: Path,
    package_id: str,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    state_file = _get_shape_editor_pixel_workbench_state_file(project_root=project_root)
    if not state_file.is_file():
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "state": {},
        }

    obj = _read_json(state_file)
    assets = obj.get("assets")
    if not isinstance(assets, list) or len(assets) == 0:
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "state": {},
        }

    # normalize any accidental http://127.0.0.1:port/... to stable path (in-memory only)
    for a in assets:
        if not isinstance(a, dict):
            continue
        src0 = str(a.get("matrix_src") or "").strip()
        if src0:
            a["matrix_src"] = _normalize_src_url_to_stable_path(src0)

    return {
        "ok": True,
        "has_data": True,
        "project_root": str(project_root),
        "state_file": str(state_file),
        "state": obj,
    }


def save_shape_editor_pixel_workbench_state(
    *,
    workspace_root: Path,
    resource_library_dir: Path,
    package_id: str,
    state_payload: JsonDict,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    state_file = _get_shape_editor_pixel_workbench_state_file(project_root=project_root)

    assets = state_payload.get("assets")
    if not isinstance(assets, list) or len(assets) == 0:
        if state_file.is_file():
            state_file.unlink()
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "state": {},
            "stored_matrices": [],
        }

    # drop empty items (best-effort) to avoid writing junk
    state_payload["assets"] = [
        a
        for a in assets
        if isinstance(a, dict) and str(a.get("id") or "").strip() and str(a.get("matrix_src") or "").strip()
    ]
    if len(state_payload["assets"]) == 0:
        if state_file.is_file():
            state_file.unlink()
        return {
            "ok": True,
            "has_data": False,
            "project_root": str(project_root),
            "state_file": str(state_file),
            "state": {},
            "stored_matrices": [],
        }

    stored = _persist_pixel_workbench_matrices_in_state(
        workspace_root=Path(workspace_root).resolve(),
        project_root=project_root,
        state_payload=state_payload,
    )

    state_payload["updated_at"] = _utc_now_iso()
    _write_json(state_file, state_payload)
    return {
        "ok": True,
        "has_data": True,
        "project_root": str(project_root),
        "state_file": str(state_file),
        "state": state_payload,
        "stored_matrices": stored,
    }


def _build_empty_template(*, template_id: str, name: str) -> JsonDict:
    return {
        "template_id": str(template_id),
        "name": str(name),
        "entity_type": "物件",
        "description": "shape-editor 画布载体：用于挂载装饰物组并承载网页画布数据（项目级持久化）。",
        "default_graphs": [],
        "default_components": [],
        "entity_config": {
            "render": {"model_name": "空模型", "visible": True},
        },
        "metadata": {
            "object_model_name": "空模型",
            "shape_editor": {"kind": "canvas_carrier"},
        },
        "graph_variable_overrides": {},
        "updated_at": _utc_now_iso(),
    }


def _build_canvas_instance(
    *,
    instance_id: str,
    name: str,
    template_id: str,
    canvas_payload: JsonDict,
    decorations_report: JsonDict,
) -> JsonDict:
    # 将 decorations_report 转为 common_inspector.model.decorations（与现有“装饰物编辑器”口径兼容）
    decorations_list: List[JsonDict] = []
    for deco in list(decorations_report.get("decorations") or []):
        if not isinstance(deco, dict):
            continue
        d_name = str(deco.get("name") or "").strip()
        tid = int(deco.get("template_id") or 0)
        pos = deco.get("pos")
        scale = deco.get("scale")
        yaw = deco.get("yaw_deg")
        rot = deco.get("rot_deg")
        if not isinstance(pos, list) or len(pos) != 3:
            continue
        if not isinstance(scale, list) or len(scale) != 3:
            continue
        yaw_f = float(yaw) if isinstance(yaw, (int, float)) else 0.0
        if isinstance(rot, list) and len(rot) == 3 and all(isinstance(v, (int, float)) for v in rot):
            rx, ry, rz = float(rot[0]), float(rot[1]), float(rot[2])
        else:
            rx, ry, rz = 0.0, float(yaw_f), 0.0
        decorations_list.append(
            {
                "instanceId": f"shape_{len(decorations_list)+1}",
                "displayName": d_name or "装饰物",
                "isVisible": True,
                "assetId": int(tid),
                "parentId": "GI_RootNode",
                "transform": {
                    "pos": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
                    "rot": {"x": float(rx), "y": float(ry), "z": float(rz)},
                    "scale": {"x": float(scale[0]), "y": float(scale[1]), "z": float(scale[2])},
                    "isLocked": False,
                },
                "physics": {
                    "enableCollision": False,
                    "isClimbable": False,
                    "showPreview": False,
                },
            }
        )

    return {
        "instance_id": str(instance_id),
        "name": str(name),
        "template_id": str(template_id),
        "position": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "override_variables": [],
        "additional_graphs": [],
        "additional_components": [],
        "metadata": {
            "entity_type": "物件",
            "shape_editor": {
                "kind": "canvas_instance",
                "canvas_payload": canvas_payload,
            },
            "common_inspector": {
                "model": {
                    "decorations": decorations_list,
                }
            },
        },
        "graph_variable_overrides": {},
        "updated_at": _utc_now_iso(),
    }


def ensure_canvas_persisted_in_project(
    *,
    workspace_root: Path,
    resource_library_dir: Path,
    package_id: str,
    canvas_payload: JsonDict,
    settings_obj: ShapeEditorSettings,
    target_rel_path: str | None = None,
    bump_export_seq: bool = False,
    instance_name_override: str | None = None,
    instance_id_override: str | None = None,
) -> dict:
    """
    将当前画布写入到“当前项目存档”的实体摆放与元件库中：
    - 写入（或更新）一个空模板（元件库）
    - 写入（或更新）一个实体摆放实例（承载 decorations + 原始 canvas payload）
    """
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    templates_dir = _ensure_dir(project_root / "元件库")
    placements_dir = _ensure_dir(project_root / "实体摆放")

    # 历史遗留：实体摆放目录不应包含 registry 文件（会触发资源索引告警）。
    legacy_registry = (placements_dir / "shape_editor_registry.json").resolve()
    if legacy_registry.is_file():
        legacy_registry.unlink()

    template_id = f"shape_editor_empty__{package_id}"
    default_instance_id = f"shape_editor_canvas__{package_id}"

    template_file = (templates_dir / "shape_editor_empty_template.json").resolve()
    if template_file.is_file():
        template_obj = _read_json(template_file)
        template_obj["template_id"] = template_id
        template_obj["updated_at"] = _utc_now_iso()
    else:
        template_obj = _build_empty_template(template_id=template_id, name="拼贴画空实体（画布载体）")
    _write_json(template_file, template_obj)

    canvas = canvas_payload.get("canvas")
    if not isinstance(canvas, dict):
        raise ValueError("payload.canvas 必须是 object")
    objects = canvas_payload.get("objects")
    if not isinstance(objects, list):
        raise ValueError("payload.objects 必须是 list")

    # 参考图持久化：将 data url 自动落为项目内文件，并把 payload 内的 src 替换为稳定 path。
    reference_images = _persist_reference_images_in_canvas_payload(
        workspace_root=Path(workspace_root).resolve(),
        project_root=project_root,
        canvas_payload=canvas_payload,
    )
    decorations_report = _build_decorations_report(
        canvas_width=float(canvas.get("width") or 0.0),
        canvas_height=float(canvas.get("height") or 0.0),
        objects=[obj for obj in objects if isinstance(obj, dict)],
        settings_obj=settings_obj,
    )

    # Resolve target placement file (default: shape_editor_canvas_instance.json).
    rel_text = str(target_rel_path or "").strip().replace("\\", "/")
    if rel_text == "":
        placement_file = (placements_dir / "shape_editor_canvas_instance.json").resolve()
    else:
        p = (project_root / rel_text).resolve()
        if placements_dir not in p.parents:
            raise ValueError("非法 target_rel_path：不在 实体摆放 目录下")
        if p.suffix.lower() != ".json":
            raise ValueError("target_rel_path 必须是 .json")
        placement_file = p

    export_seq_counter = 0
    instance_name = str(instance_name_override or "").strip() or "拼贴画画布"
    instance_id = str(instance_id_override or "").strip() or default_instance_id
    if placement_file.is_file():
        prev = _read_json(placement_file)
        instance_name = str(prev.get("name") or instance_name)
        instance_id = str(prev.get("instance_id") or instance_id)
        meta = prev.get("metadata") if isinstance(prev.get("metadata"), dict) else {}
        se = meta.get("shape_editor") if isinstance(meta.get("shape_editor"), dict) else {}
        raw_seq = se.get("export_seq_counter", 0)
        export_seq_counter = int(raw_seq) if isinstance(raw_seq, int) and not isinstance(raw_seq, bool) else 0

    if bump_export_seq:
        export_seq_counter += 1

    instance_obj = _build_canvas_instance(
        instance_id=instance_id,
        name=instance_name,
        template_id=template_id,
        canvas_payload=canvas_payload,
        decorations_report=decorations_report,
    )
    # Persist export seq counter for stable naming across sessions.
    meta2 = instance_obj.get("metadata")
    if isinstance(meta2, dict):
        se2 = meta2.get("shape_editor")
        if isinstance(se2, dict):
            se2["export_seq_counter"] = int(export_seq_counter)
    _write_json(placement_file, instance_obj)

    return {
        "ok": True,
        "project_root": str(project_root),
        "template_file": str(template_file),
        "placement_file": str(placement_file),
        "rel_path": str((Path("实体摆放") / placement_file.name)).replace("\\", "/"),
        "template_id": template_id,
        "instance_id": instance_id,
        "decorations_count": int(len(decorations_report.get("decorations") or [])),
        "instance_name": str(instance_name),
        "export_seq": int(export_seq_counter),
        "reference_images": reference_images,
    }


def load_canvas_payload_from_project(
    *,
    resource_library_dir: Path,
    package_id: str,
    target_rel_path: str | None = None,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    placements_dir = (project_root / "实体摆放").resolve()
    rel_text = str(target_rel_path or "").strip().replace("\\", "/")
    if rel_text == "":
        placement_file = (placements_dir / "shape_editor_canvas_instance.json").resolve()
    else:
        p = (project_root / rel_text).resolve()
        if placements_dir not in p.parents:
            raise ValueError("非法 target_rel_path：不在 实体摆放 目录下")
        placement_file = p
    if not placement_file.is_file():
        return {
            "ok": True,
            "has_data": False,
            "placement_file": str(placement_file),
            "canvas_payload": None,
        }
    obj = _read_json(placement_file)
    meta = obj.get("metadata")
    if not isinstance(meta, dict):
        return {"ok": True, "has_data": False, "placement_file": str(placement_file), "canvas_payload": None}
    se = meta.get("shape_editor")
    if not isinstance(se, dict):
        return {"ok": True, "has_data": False, "placement_file": str(placement_file), "canvas_payload": None}
    payload = se.get("canvas_payload")
    if not isinstance(payload, dict):
        return {"ok": True, "has_data": False, "placement_file": str(placement_file), "canvas_payload": None}
    return {
        "ok": True,
        "has_data": True,
        "placement_file": str(placement_file),
        "canvas_payload": payload,
    }


def _safe_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return float(default)


def _infer_canvas_payload_from_decorations(
    *,
    decorations: list[dict[str, Any]],
    settings_obj: ShapeEditorSettings,
    canvas_size: Tuple[int, int] = (1600, 900),
) -> JsonDict:
    """
    兜底：当实体摆放里没有 shape_editor.canvas_payload 时，
    尝试把 common_inspector.model.decorations 反推出一个“可编辑”的 canvas payload。

    注意：这是 best-effort，仅保证“能在网页上看到并继续编辑/导出”，不追求 100% 还原历史编辑状态。
    """
    cw, ch = int(canvas_size[0]), int(canvas_size[1])
    units_per_px = float(settings_obj.units_per_100px) / 100.0
    if units_per_px <= 0:
        units_per_px = 0.01

    # invert: template_id -> color/profile
    tid_to_profile: dict[int, tuple[str, JsonDict]] = {}
    for color, prof in settings_obj.baseline_profiles_by_color.items():
        if not isinstance(prof, dict):
            continue
        tid = prof.get("template_id")
        if isinstance(tid, int) and not isinstance(tid, bool) and int(tid) > 0:
            tid_to_profile[int(tid)] = (str(color), prof)

    objects: list[JsonDict] = []
    for deco in decorations:
        if not isinstance(deco, dict):
            continue
        tid = deco.get("assetId")
        if not isinstance(tid, int) or isinstance(tid, bool):
            continue
        color, prof = tid_to_profile.get(int(tid), ("#888888", {}))
        shape_kind = str(prof.get("shape_kind") or "rect").strip().lower()
        if shape_kind not in {"rect", "circle"}:
            shape_kind = "rect"

        base_scale = prof.get("base_scale") if isinstance(prof.get("base_scale"), dict) else {}
        base_sx = _safe_float(base_scale.get("x"), 1.0)
        base_sy = _safe_float(base_scale.get("y"), 1.0)
        base_sz = _safe_float(base_scale.get("z"), 1.0)

        pivot = str(prof.get("pivot") or "center").strip().lower()
        if pivot not in {"center", "bottom_center"}:
            pivot = "center"

        # decorations use world pos/scale
        tf = deco.get("transform") if isinstance(deco.get("transform"), dict) else {}
        pos = tf.get("pos") if isinstance(tf.get("pos"), dict) else {}
        scale = tf.get("scale") if isinstance(tf.get("scale"), dict) else {}
        rot = tf.get("rot") if isinstance(tf.get("rot"), dict) else {}

        wx = _safe_float(pos.get("x"), 0.0)
        wy = _safe_float(pos.get("y"), 0.0)
        # reverse mapping: px from world (X/Y 平面)
        ax = wx / units_per_px + cw / 2.0
        ay = ch / 2.0 - (wy / units_per_px)

        sx = _safe_float(scale.get("x"), base_sx)
        sy = _safe_float(scale.get("y"), base_sy)
        sz = _safe_float(scale.get("z"), base_sz)

        # reverse axis mapping by profile:
        thin_th = float(settings_obj.thin_axis_threshold)
        upright_th = float(settings_obj.upright_y_axis_threshold)
        is_upright_y = (abs(base_sz) <= thin_th) and (abs(base_sy) > upright_th)
        width_px = (sx / base_sx) * 100.0 if base_sx != 0 else 100.0
        height_px = ((sy / base_sy) * 100.0 if base_sy != 0 else 100.0) if is_upright_y else ((sz / base_sz) * 100.0 if base_sz != 0 else 100.0)

        yaw_deg = _safe_float(rot.get("y"), 0.0)

        left = float(ax) - float(width_px) / 2.0
        top = float(ay) - (float(height_px) if pivot == "bottom_center" else float(height_px) / 2.0)

        objects.append(
            {
                "type": shape_kind,
                "label": str(deco.get("displayName") or "").strip() or str(color),
                "color": str(color),
                "left": int(round(left)),
                "top": int(round(top)),
                "width": int(round(width_px)),
                "height": int(round(height_px)),
                "angle": int(round(float(-yaw_deg))),  # 近似回推（与 yaw_sign=-1 口径对齐）
                "pivot": pivot,
                "anchor": {"x": int(round(ax)), "y": int(round(ay))},
                "isReference": False,
                "isLocked": False,
            }
        )

    return {
        "meta": {"tool": "shape_editor_project_infer", "mode": "inferred_from_decorations"},
        "canvas": {"width": int(cw), "height": int(ch)},
        "objects": objects,
    }


def list_project_entity_placements(
    *,
    resource_library_dir: Path,
    package_id: str,
    settings_obj: ShapeEditorSettings,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    placements_dir = (project_root / "实体摆放").resolve()
    if not placements_dir.is_dir():
        return {"ok": True, "placements": [], "placements_dir": str(placements_dir)}

    placements: list[JsonDict] = []
    for f in sorted(list(placements_dir.glob("*.json")), key=lambda p: p.name.casefold()):
        if not f.is_file():
            continue
        # `instances_index.json` 是 ugc_file_tools 生成的索引（JSON list），不是实体摆放资源本体。
        # 若将其当作实体读取，会因 `_read_json()` 约束（必须是 object）而崩溃。
        if f.name == "instances_index.json":
            continue
        # internal bookkeeping file (historical): should never appear in entity list
        if f.name == "shape_editor_registry.json":
            # 历史遗留：该文件不应出现在“实体摆放”目录中，会触发资源索引告警；这里直接清理。
            f.unlink()
            continue
        obj = _read_json(f)
        name = str(obj.get("name") or f.stem).strip()
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        se = meta.get("shape_editor") if isinstance(meta.get("shape_editor"), dict) else {}
        has_canvas_payload = isinstance(se.get("canvas_payload"), dict)

        ci = meta.get("common_inspector") if isinstance(meta.get("common_inspector"), dict) else {}
        model = ci.get("model") if isinstance(ci.get("model"), dict) else {}
        decorations = model.get("decorations")
        deco_count = len(decorations) if isinstance(decorations, list) else 0

        rel_path = str(Path("实体摆放") / f.name)
        placements.append(
            {
                "rel_path": rel_path.replace("\\", "/"),
                "file_name": f.name,
                "name": name,
                "instance_id": str(obj.get("instance_id") or "").strip(),
                "template_id": str(obj.get("template_id") or "").strip(),
                "has_canvas_payload": bool(has_canvas_payload),
                "decorations_count": int(deco_count),
                "updated_at": str(obj.get("updated_at") or "").strip(),
            }
        )

    return {"ok": True, "placements_dir": str(placements_dir), "placements": placements}


def read_project_entity_placement(
    *,
    resource_library_dir: Path,
    package_id: str,
    rel_path: str,
    settings_obj: ShapeEditorSettings,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    placements_dir = (project_root / "实体摆放").resolve()
    rel_text = str(rel_path or "").strip().replace("\\", "/")
    if not rel_text:
        raise ValueError("rel_path 不能为空")
    p = (project_root / rel_text).resolve()
    if placements_dir not in p.parents:
        raise ValueError("非法 rel_path：不在 实体摆放 目录下")
    if not p.is_file():
        raise FileNotFoundError(str(p))

    obj = _read_json(p)
    meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    se = meta.get("shape_editor") if isinstance(meta.get("shape_editor"), dict) else {}
    payload = se.get("canvas_payload")
    has_payload = isinstance(payload, dict)

    if not has_payload:
        ci = meta.get("common_inspector") if isinstance(meta.get("common_inspector"), dict) else {}
        model = ci.get("model") if isinstance(ci.get("model"), dict) else {}
        decorations = model.get("decorations")
        if isinstance(decorations, list) and decorations:
            payload = _infer_canvas_payload_from_decorations(decorations=decorations, settings_obj=settings_obj)
            has_payload = True

    return {
        "ok": True,
        "rel_path": rel_text,
        "file_path": str(p),
        "data": obj,
        "has_canvas_payload": bool(has_payload),
        "canvas_payload": payload if has_payload else None,
    }


def delete_shape_editor_entity_placement(
    *,
    resource_library_dir: Path,
    package_id: str,
    rel_path: str,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    placements_dir = (project_root / "实体摆放").resolve()
    rel_text = str(rel_path or "").strip().replace("\\", "/")
    if not rel_text:
        raise ValueError("rel_path 不能为空")
    p = (project_root / rel_text).resolve()
    if placements_dir not in p.parents:
        raise ValueError("非法 rel_path：不在 实体摆放 目录下")
    if not p.is_file():
        raise FileNotFoundError(str(p))

    obj = _read_json(p)
    meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    se = meta.get("shape_editor") if isinstance(meta.get("shape_editor"), dict) else {}
    if not se:
        raise ValueError("仅允许删除 shape-editor 创建的实体（metadata.shape_editor 缺失）")

    p.unlink()
    return {"ok": True, "deleted": True, "rel_path": rel_text, "file_path": str(p)}


def rename_shape_editor_entity_placement(
    *,
    resource_library_dir: Path,
    package_id: str,
    rel_path: str,
    new_name: str,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    placements_dir = (project_root / "实体摆放").resolve()
    rel_text = str(rel_path or "").strip().replace("\\", "/")
    if not rel_text:
        raise ValueError("rel_path 不能为空")
    p = (project_root / rel_text).resolve()
    if placements_dir not in p.parents:
        raise ValueError("非法 rel_path：不在 实体摆放 目录下")
    if not p.is_file():
        raise FileNotFoundError(str(p))

    name_text = str(new_name or "").strip()
    if name_text == "":
        raise ValueError("实体名称不能为空")

    obj = _read_json(p)
    meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    se = meta.get("shape_editor") if isinstance(meta.get("shape_editor"), dict) else {}
    if not se:
        raise ValueError("仅允许重命名 shape-editor 创建的实体（metadata.shape_editor 缺失）")

    obj["name"] = name_text
    obj["updated_at"] = _utc_now_iso()
    _write_json(p, obj)
    return {"ok": True, "renamed": True, "rel_path": rel_text, "file_path": str(p), "name": name_text}


def duplicate_shape_editor_entity_placement(
    *,
    resource_library_dir: Path,
    package_id: str,
    rel_path: str,
) -> dict:
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    placements_dir = (project_root / "实体摆放").resolve()
    rel_text = str(rel_path or "").strip().replace("\\", "/")
    if not rel_text:
        raise ValueError("rel_path 不能为空")
    src_file = (project_root / rel_text).resolve()
    if placements_dir not in src_file.parents:
        raise ValueError("非法 rel_path：不在 实体摆放 目录下")
    if not src_file.is_file():
        raise FileNotFoundError(str(src_file))

    obj = _read_json(src_file)
    meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    se = meta.get("shape_editor") if isinstance(meta.get("shape_editor"), dict) else {}
    if not se:
        raise ValueError("仅允许复制 shape-editor 创建的实体（metadata.shape_editor 缺失）")

    next_seq = _compute_next_entity_seq(placements_dir=placements_dir)
    dst_file = (placements_dir / f"shape_editor_entity_{next_seq:03d}.json").resolve()

    # Update identity fields for the new instance.
    old_name = str(obj.get("name") or "").strip()
    new_name = (old_name or "拼贴画画布") + " 副本"
    obj["name"] = new_name
    obj["instance_id"] = f"shape_editor_entity__{str(package_id).strip()}__{next_seq}"
    obj["updated_at"] = _utc_now_iso()

    # Refresh shape-editor metadata (keep existing canvas payload & decorations).
    meta2 = obj.get("metadata")
    if not isinstance(meta2, dict):
        meta2 = {}
        obj["metadata"] = meta2
    se2 = meta2.get("shape_editor")
    if not isinstance(se2, dict):
        se2 = {}
        meta2["shape_editor"] = se2
    se2["entity_seq"] = int(next_seq)
    se2["export_seq_counter"] = 0
    se2["copied_from_rel_path"] = str(rel_text)

    _write_json(dst_file, obj)
    return {
        "ok": True,
        "duplicated": True,
        "source_rel_path": rel_text,
        "source_file_path": str(src_file),
        "rel_path": str((Path("实体摆放") / dst_file.name)).replace("\\", "/"),
        "file_path": str(dst_file),
        "instance_id": str(obj.get("instance_id") or "").strip(),
        "name": str(new_name),
        "entity_seq": int(next_seq),
    }

def _extract_seq_from_entity_file_name(name: str) -> int | None:
    """
    从 `shape_editor_entity_003.json` 提取 3。
    """
    text = str(name or "").strip()
    if not text.lower().endswith(".json"):
        return None
    stem = text[:-5]
    prefix = "shape_editor_entity_"
    if not stem.lower().startswith(prefix):
        return None
    tail = stem[len(prefix) :]
    if tail == "" or not tail.isdigit():
        return None
    return int(tail)


def _compute_next_entity_seq(*, placements_dir: Path) -> int:
    """
    通过扫描 `实体摆放/shape_editor_entity_*.json` 推导下一个序号。

    设计目的：让 `实体摆放/` 目录只包含实体 JSON，不再需要额外 registry 文件。
    """
    max_seq = 0
    for f in Path(placements_dir).glob("shape_editor_entity_*.json"):
        if not f.is_file():
            continue
        seq = _extract_seq_from_entity_file_name(f.name)
        if seq is None:
            continue
        if seq > max_seq:
            max_seq = seq
    return int(max_seq + 1)


def create_blank_entity_in_project(
    *,
    workspace_root: Path,
    resource_library_dir: Path,
    package_id: str,
    settings_obj: ShapeEditorSettings,
    instance_name: str | None = None,
) -> dict:
    """
    新建一个空白实体（实体摆放实例），用于承载独立的一套画布与装饰物组。
    """
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    templates_dir = _ensure_dir(project_root / "元件库")
    placements_dir = _ensure_dir(project_root / "实体摆放")

    # Ensure carrier template exists (shared within project).
    template_id = f"shape_editor_empty__{package_id}"
    template_file = (templates_dir / "shape_editor_empty_template.json").resolve()
    if template_file.is_file():
        template_obj = _read_json(template_file)
        template_obj["template_id"] = template_id
        template_obj["updated_at"] = _utc_now_iso()
    else:
        template_obj = _build_empty_template(template_id=template_id, name="拼贴画空实体（画布载体）")
    _write_json(template_file, template_obj)

    next_seq = _compute_next_entity_seq(placements_dir=placements_dir)

    name_text = str(instance_name or "").strip() or "拼贴画画布"
    instance_id = f"shape_editor_entity__{package_id}__{next_seq}"
    file_name = f"shape_editor_entity_{next_seq:03d}.json"
    placement_file = (placements_dir / file_name).resolve()

    empty_payload: JsonDict = {
        "meta": {"tool": "qx-shape-editor", "mode": "blank_entity"},
        "canvas": {"width": 1600, "height": 900},
        "objects": [],
    }
    decorations_report = _build_decorations_report(
        canvas_width=float(empty_payload["canvas"]["width"]),
        canvas_height=float(empty_payload["canvas"]["height"]),
        objects=[],
        settings_obj=settings_obj,
    )
    instance_obj = _build_canvas_instance(
        instance_id=instance_id,
        name=name_text,
        template_id=template_id,
        canvas_payload=empty_payload,
        decorations_report=decorations_report,
    )
    meta = instance_obj.get("metadata")
    if isinstance(meta, dict):
        se = meta.get("shape_editor")
        if isinstance(se, dict):
            se["entity_seq"] = int(next_seq)
            se["export_seq_counter"] = 0
    _write_json(placement_file, instance_obj)

    return {
        "ok": True,
        "project_root": str(project_root),
        "template_file": str(template_file),
        "placement_file": str(placement_file),
        "rel_path": str((Path("实体摆放") / placement_file.name)).replace("\\", "/"),
        "template_id": str(template_id),
        "instance_id": str(instance_id),
        "instance_name": str(name_text),
        "entity_seq": int(next_seq),
    }


def save_as_new_entity_in_project(
    *,
    workspace_root: Path,
    resource_library_dir: Path,
    package_id: str,
    settings_obj: ShapeEditorSettings,
    canvas_payload: JsonDict,
    instance_name: str | None = None,
) -> dict:
    """
    将一份画布（通常来自“选中组/多选导出”）另存为一个新的实体摆放实例。
    """
    project_root = resolve_project_root(resource_library_dir=resource_library_dir, package_id=package_id)
    placements_dir = _ensure_dir(project_root / "实体摆放")

    next_seq = _compute_next_entity_seq(placements_dir=placements_dir)

    file_name = f"shape_editor_entity_{next_seq:03d}.json"
    rel_path = str((Path("实体摆放") / file_name)).replace("\\", "/")
    inst_id = f"shape_editor_entity__{package_id}__{next_seq}"
    name_text = str(instance_name or "").strip() or "拼贴画画布"

    saved = ensure_canvas_persisted_in_project(
        workspace_root=workspace_root,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        canvas_payload=canvas_payload,
        settings_obj=settings_obj,
        target_rel_path=rel_path,
        bump_export_seq=False,
        instance_name_override=name_text,
        instance_id_override=inst_id,
    )
    saved["entity_seq"] = int(next_seq)
    return saved

