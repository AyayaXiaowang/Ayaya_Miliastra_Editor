from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import try_find_graph_generater_root
from ugc_file_tools.signal_writeback.writer import add_signals_to_gil


@dataclass(frozen=True, slots=True)
class SignalsImportOptions:
    param_build_mode: str  # "semantic" | "template"
    include_signal_ids: list[str] | None = None  # 可选：仅导入指定 SIGNAL_ID（作用域仍为 共享+项目）
    duplicate_name_policy: str = "error"  # "error" | "keep_first" | "keep_last"
    # 当 base `.gil` 没有任何信号且选择 0x6000/0x6080 口径时，是否写入“占位无参信号”（常见名：新建的没有参数的信号）。
    # - True：写入该占位信号 entry（旧行为）
    # - False：不写入 entry，但预留其应占用的 node_def_id/端口块（更干净的导出产物）
    emit_reserved_placeholder_signal: bool = False


def _resolve_graph_generater_root(project_archive_path: Path) -> Path:
    project_path = Path(project_archive_path).resolve()
    found = try_find_graph_generater_root(start_path=project_path)
    if found is not None:
        return found

    # fallback：从 ugc_file_tools 位置向上/同级探测（见 repo_paths.try_find_graph_generater_root）
    default = try_find_graph_generater_root()
    if default is not None:
        return default

    raise FileNotFoundError(
        "无法定位 Graph_Generater 根目录（需要包含 engine/assets；通常包含 app/plugins）："
        f"project_archive={str(project_path)!r}"
    )


def _iter_code_signal_definition_py_files(*, root_dir: Path) -> List[Path]:
    base_dir = (Path(root_dir) / "管理配置" / "信号").resolve()
    if not base_dir.is_dir():
        return []
    py_paths: List[Path] = []
    for p in sorted(base_dir.rglob("*.py"), key=lambda x: x.as_posix()):
        if not p.is_file():
            continue
        if "校验" in p.stem:
            continue
        py_paths.append(p.resolve())
    return py_paths


def _load_signal_payload_from_py(py_path: Path) -> Tuple[str, Dict[str, Any]]:
    p = Path(py_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    module_name = f"ugc_signal_def_{abs(hash(p.as_posix()))}"
    loader = SourceFileLoader(module_name, str(p))
    module = loader.load_module()

    signal_id_value = getattr(module, "SIGNAL_ID", None)
    payload_value = getattr(module, "SIGNAL_PAYLOAD", None)

    if not isinstance(signal_id_value, str) or signal_id_value.strip() == "":
        raise ValueError(f"{str(p)} 缺少有效的 SIGNAL_ID（期望非空 str）")
    if not isinstance(payload_value, dict):
        raise ValueError(f"{str(p)} 缺少有效的 SIGNAL_PAYLOAD（期望 dict）")

    signal_id = str(signal_id_value).strip()
    payload = dict(payload_value)
    return signal_id, payload


def _merge_signal_payloads_with_shared_scope(
    *,
    shared_root: Path,
    project_root: Path,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """
    对齐 Graph_Generater 的 DefinitionSchemaView：
    - 资源根：共享根 + 当前项目根
    - 同一资源根内重复 ID：保留先出现的那一份（稳定排序）
    - 跨根覆盖：项目根覆盖共享根同 ID 定义

    Returns:
        (payloads_by_id, source_by_id)
    """
    results: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, str] = {}

    def load_root(root: Path) -> Dict[str, Tuple[Dict[str, Any], str]]:
        seen: Dict[str, Tuple[Dict[str, Any], str]] = {}
        for py_path in _iter_code_signal_definition_py_files(root_dir=root):
            signal_id, payload = _load_signal_payload_from_py(py_path)
            if signal_id in seen:
                continue
            seen[signal_id] = (dict(payload), str(py_path))
        return seen

    shared_map = load_root(Path(shared_root))
    project_map = load_root(Path(project_root))

    # 共享先写入
    for sid, (payload, src) in shared_map.items():
        results[str(sid)] = dict(payload)
        sources[str(sid)] = str(src)

    # 项目覆盖共享
    for sid, (payload, src) in project_map.items():
        results[str(sid)] = dict(payload)
        sources[str(sid)] = str(src)

    return results, sources


def _safe_text(value: object) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _build_signals_spec_from_code_payloads(
    *,
    payloads_by_id: Mapping[str, Mapping[str, Any]],
    sources_by_id: Mapping[str, str],
    duplicate_name_policy: str,
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    """
    将 Graph_Generater 代码级 SIGNAL_PAYLOAD 转换为 ugc_file_tools.signal_writeback 所需的 spec.json：
    {
      "signals": [
        {"signal_name": "...", "params": [{"param_name": "...", "type": "..."}]}
      ]
    }
    """
    policy = str(duplicate_name_policy or "").strip().lower() or "error"
    if policy not in {"error", "keep_first", "keep_last"}:
        raise ValueError(f"unsupported duplicate_name_policy: {duplicate_name_policy!r}")

    signals_spec: List[Dict[str, Any]] = []
    seen_names: Dict[str, Dict[str, Any]] = {}
    duplicate_name_resolutions: List[Dict[str, Any]] = []

    for signal_id in payloads_by_id.keys():
        payload = payloads_by_id.get(signal_id)
        if not isinstance(payload, Mapping):
            continue

        signal_name = _safe_text(payload.get("signal_name"))
        if not signal_name:
            src = str(sources_by_id.get(signal_id) or "")
            raise ValueError(f"信号定义缺少 signal_name：signal_id={signal_id}（source={src}）")

        # Gil 侧以 signal_name 作为“信号选择/展示”的主键；同名默认报错。
        if signal_name in seen_names:
            prev = seen_names.get(signal_name) or {}
            prev_id = str(prev.get("signal_id") or "")
            src1 = str(sources_by_id.get(prev_id) or "")
            src2 = str(sources_by_id.get(signal_id) or "")
            if policy == "error":
                raise ValueError(
                    "检测到同名信号定义，无法稳定导入到 .gil："
                    f"signal_name={signal_name!r}，signal_id={prev_id!r}({src1}) vs {signal_id!r}({src2})"
                )
            if policy == "keep_first":
                duplicate_name_resolutions.append(
                    {
                        "signal_name": str(signal_name),
                        "kept_signal_id": str(prev_id),
                        "dropped_signal_id": str(signal_id),
                        "kept_source": str(src1),
                        "dropped_source": str(src2),
                        "strategy": "keep_first",
                    }
                )
                continue

        params_value = payload.get("parameters") or []
        if not isinstance(params_value, list):
            src = str(sources_by_id.get(signal_id) or "")
            raise TypeError(f"信号定义 parameters 必须为 list：signal_id={signal_id}（source={src}）")

        params_spec: List[Dict[str, Any]] = []
        for idx, entry in enumerate(params_value):
            if not isinstance(entry, Mapping):
                continue
            param_name = _safe_text(entry.get("name"))
            param_type = _safe_text(entry.get("parameter_type"))
            if not param_name or not param_type:
                src = str(sources_by_id.get(signal_id) or "")
                raise ValueError(
                    f"信号参数缺少 name/parameter_type：signal_id={signal_id}.parameters[{idx}]（source={src}）"
                )
            params_spec.append(
                {
                    "param_name": str(param_name),
                    # 交给 signal_writeback 侧按 Graph_Generater type_registry 解析（并禁止字典）
                    "type": str(param_type),
                }
            )

        if signal_name in seen_names and policy == "keep_last":
            prev2 = seen_names.get(signal_name) or {}
            prev_id2 = str(prev2.get("signal_id") or "")
            prev_src = str(sources_by_id.get(prev_id2) or "")
            cur_src = str(sources_by_id.get(signal_id) or "")
            replace_index = int(prev2.get("index") or 0)
            signals_spec[replace_index] = {"signal_name": str(signal_name), "params": params_spec}
            seen_names[signal_name] = {"signal_id": str(signal_id), "index": int(replace_index)}
            duplicate_name_resolutions.append(
                {
                    "signal_name": str(signal_name),
                    "kept_signal_id": str(signal_id),
                    "dropped_signal_id": str(prev_id2),
                    "kept_source": str(cur_src),
                    "dropped_source": str(prev_src),
                    "strategy": "keep_last",
                }
            )
            continue

        signals_spec.append({"signal_name": str(signal_name), "params": params_spec})
        seen_names[signal_name] = {"signal_id": str(signal_id), "index": int(len(signals_spec) - 1)}

    return {"signals": signals_spec}, duplicate_name_resolutions


def import_signals_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_gil_file_path: Optional[Path],
    bootstrap_template_gil_file_path: Optional[Path],
    options: SignalsImportOptions,
) -> Dict[str, Any]:
    project_path = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    if not project_path.is_dir():
        raise FileNotFoundError(str(project_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    mode = str(options.param_build_mode or "").strip().lower()
    if mode not in {"semantic", "template"}:
        raise ValueError(f"unsupported param_build_mode: {mode!r}")

    template_path: Optional[Path] = None
    if template_gil_file_path is not None:
        resolved = Path(template_gil_file_path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(str(resolved))
        if resolved.suffix.lower() != ".gil":
            raise ValueError("template_gil 不是 .gil 文件")
        template_path = resolved

    if bootstrap_template_gil_file_path is not None:
        bootstrap_path = Path(bootstrap_template_gil_file_path).resolve()
        if not bootstrap_path.is_file():
            raise FileNotFoundError(str(bootstrap_path))
    else:
        bootstrap_path = None

    gg_root = _resolve_graph_generater_root(project_path)
    resource_library_root = gg_root / "assets" / "资源库"
    shared_root = resource_library_root / "共享"
    if not shared_root.is_dir():
        raise FileNotFoundError(str(shared_root))

    payloads_by_id, sources_by_id = _merge_signal_payloads_with_shared_scope(
        shared_root=shared_root,
        project_root=project_path,
    )

    wanted_ids = [str(x or "").strip() for x in list(getattr(options, "include_signal_ids", None) or [])]
    wanted_ids = [x for x in wanted_ids if x]
    wanted_ids = list(dict.fromkeys(wanted_ids))
    if wanted_ids:
        wanted = set(wanted_ids)
        existing = set(payloads_by_id.keys())
        missing = sorted(list(wanted - existing), key=lambda t: t.casefold())
        if missing:
            raise ValueError(f"选择的信号不存在于当前作用域（共享+项目）：{missing}")
        payloads_by_id = {k: dict(payloads_by_id[k]) for k in wanted_ids}
        sources_by_id = {k: str(sources_by_id.get(k) or "") for k in payloads_by_id.keys()}

    duplicate_name_policy = str(getattr(options, "duplicate_name_policy", "error") or "").strip().lower() or "error"
    if duplicate_name_policy not in {"error", "keep_first", "keep_last"}:
        raise ValueError(f"unsupported duplicate_name_policy: {duplicate_name_policy!r}")
    if wanted_ids and duplicate_name_policy == "error":
        # 精确按 signal_id 选择时，优先保证可导入：若同名，按用户给出的 id 顺序保留第一个。
        duplicate_name_policy = "keep_first"

    spec_object, duplicate_name_resolutions = _build_signals_spec_from_code_payloads(
        payloads_by_id=payloads_by_id,
        sources_by_id=sources_by_id,
        duplicate_name_policy=str(duplicate_name_policy),
    )

    signals_value = spec_object.get("signals")
    if not isinstance(signals_value, list):
        raise TypeError("signals spec must be list")

    # 空：不写回，直接返回摘要（保持 import 链可组合）
    if not signals_value:
        return {
            "project_archive": str(project_path),
            "input_gil": str(input_path),
            "output_gil": str(resolve_output_file_path_in_out_dir(Path(output_gil_file_path))),
            "param_build_mode": mode,
            "graph_generater_root": str(gg_root),
            "shared_root": str(shared_root),
            "signals_count_in_scope": 0,
            "signals_spec_json": "",
            "added_signals": [],
            "duplicate_name_policy": str(duplicate_name_policy),
            "duplicate_name_resolutions": list(duplicate_name_resolutions),
        }

    spec_path = resolve_output_file_path_in_out_dir(Path(f"{project_path.name}.signals.import.spec.json"))
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec_object, ensure_ascii=False, indent=2), encoding="utf-8")

    result = add_signals_to_gil(
        input_gil_file_path=input_path,
        output_gil_file_path=Path(output_gil_file_path),
        template_gil_file_path=template_path,
        bootstrap_template_gil_file_path=bootstrap_path,
        spec_json_path=spec_path,
        param_build_mode=mode,
        emit_reserved_placeholder_signal=bool(getattr(options, "emit_reserved_placeholder_signal", False)),
    )

    return {
        "project_archive": str(project_path),
        "input_gil": str(input_path),
        "output_gil": str(result.get("output_gil") or ""),
        "param_build_mode": mode,
        "template_gil": str(template_path) if template_path is not None else "",
        "bootstrap_template_gil": str(bootstrap_path) if bootstrap_path is not None else "",
        "graph_generater_root": str(gg_root),
        "shared_root": str(shared_root),
        "signals_count_in_scope": len(signals_value),
        "signals_spec_json": str(spec_path),
        "added_signals": list(result.get("added_signals") or []),
        "duplicate_name_policy": str(duplicate_name_policy),
        "duplicate_name_resolutions": list(duplicate_name_resolutions),
    }


def collect_signal_payloads_by_id_in_scope(
    *,
    project_archive_path: Path,
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """
    收集“共享根 + 当前项目存档根”作用域内的信号定义（代码级 SIGNAL_PAYLOAD）。

    用途：
    - 供写回编排层（pipeline）按 signal_name 反查 SIGNAL_ID，自动补齐“节点图 → 信号写回”的依赖闭包，
      避免依赖 GraphModel 是否携带隐藏字段 `__signal_id`。
    """
    project_path = Path(project_archive_path).resolve()
    if not project_path.is_dir():
        raise FileNotFoundError(str(project_path))

    gg_root = _resolve_graph_generater_root(project_path)
    resource_library_root = gg_root / "assets" / "资源库"
    shared_root = resource_library_root / "共享"
    if not shared_root.is_dir():
        raise FileNotFoundError(str(shared_root))

    payloads_by_id, sources_by_id = _merge_signal_payloads_with_shared_scope(
        shared_root=shared_root,
        project_root=project_path,
    )
    return dict(payloads_by_id), dict(sources_by_id)

