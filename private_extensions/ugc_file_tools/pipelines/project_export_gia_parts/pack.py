from __future__ import annotations

from pathlib import Path

from ugc_file_tools.fs_naming import sanitize_file_stem


def pack_gia_files_to_single(
    *,
    output_gia_files_for_pack: list[Path],
    graphs_dir: Path,
    package_id: str,
    pack_output_gia_file_name: str,
) -> Path:
    """
    pack：合并成单个 .gia（Root.field_1 为 GraphUnit 列表；field_2 为 dependencies）
    """
    raw_name = str(pack_output_gia_file_name or "").strip()
    if raw_name == "":
        raw_name = f"{package_id}_packed_graphs.gia"
    if not raw_name.lower().endswith(".gia"):
        raw_name = raw_name + ".gia"
    if any(sep in raw_name for sep in ["/", "\\\\"]):
        raise ValueError("pack_output_gia_file_name 只能是文件名，不能包含路径分隔符")

    pack_file_name = sanitize_file_stem(str(Path(raw_name).stem)) + ".gia"
    pack_output_gia_file = (Path(graphs_dir).resolve() / pack_file_name).resolve()

    from ugc_file_tools.gia.container import unwrap_gia_container, wrap_gia_container
    from ugc_file_tools.gia.varbase_semantics import decoded_field_map_to_numeric_message
    from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message

    pack_graph_units: list[dict[str, object]] = []
    pack_deps: list[dict[str, object]] = []
    base_file_path_text: str = ""
    base_game_version_text: str = ""

    for p in list(output_gia_files_for_pack):
        if not Path(p).is_file():
            raise FileNotFoundError(str(p))
        proto_bytes = unwrap_gia_container(Path(p), check_header=False)
        fields_map, consumed = decode_message_to_field_map(
            data_bytes=proto_bytes,
            start_offset=0,
            end_offset=len(proto_bytes),
            remaining_depth=16,
        )
        if consumed != len(proto_bytes):
            raise ValueError(f"protobuf 解析未消费完整字节流：consumed={consumed} total={len(proto_bytes)} file={str(p)!r}")
        msg = decoded_field_map_to_numeric_message(fields_map)
        if not isinstance(msg, dict):
            raise TypeError("decoded root message must be dict")

        if base_file_path_text == "":
            fp = msg.get("3")
            if isinstance(fp, str):
                base_file_path_text = str(fp)
        if base_game_version_text == "":
            gv = msg.get("5")
            if isinstance(gv, str):
                base_game_version_text = str(gv)

        main = msg.get("1")
        if isinstance(main, dict):
            pack_graph_units.append(dict(main))
        elif isinstance(main, list):
            for u in list(main):
                if isinstance(u, dict):
                    pack_graph_units.append(dict(u))

        deps_value = msg.get("2")
        if isinstance(deps_value, list):
            for u in list(deps_value):
                if isinstance(u, dict):
                    pack_deps.append(dict(u))
        elif isinstance(deps_value, dict):
            pack_deps.append(dict(deps_value))

    if not pack_graph_units:
        raise ValueError("pack: 未收集到任何 GraphUnit（root.field_1 为空）")

    # deps 去重（按 GraphUnitId: (class, id)）
    dedup_deps: list[dict[str, object]] = []
    seen_dep_ids: set[tuple[int, int]] = set()
    for u in list(pack_deps):
        unit_id = u.get("1") if isinstance(u, dict) else None
        if not isinstance(unit_id, dict):
            continue
        cls = unit_id.get("2")
        rid_id = unit_id.get("4")
        if not isinstance(cls, int) or not isinstance(rid_id, int):
            continue
        key = (int(cls), int(rid_id))
        if key in seen_dep_ids:
            continue
        seen_dep_ids.add(key)
        dedup_deps.append(dict(u))

    def _derive_file_path_from_base(*, base_file_path: str, output_file_name: str) -> str:
        base = str(base_file_path or "").strip()
        out_name = str(output_file_name or "").strip()
        if out_name == "":
            return base
        if base == "":
            return out_name
        marker = "\\\\"
        last = base.rfind(marker)
        if last < 0:
            return base + marker + out_name
        return base[: last + 1] + out_name

    pack_root: dict[str, object] = {
        "1": list(pack_graph_units),
        "2": list(dedup_deps),
        "3": _derive_file_path_from_base(base_file_path=str(base_file_path_text), output_file_name=str(pack_output_gia_file.name)),
        "5": str(base_game_version_text or "6.3.0"),
    }

    out_bytes = wrap_gia_container(encode_message(pack_root))
    pack_output_gia_file.parent.mkdir(parents=True, exist_ok=True)
    pack_output_gia_file.write_bytes(out_bytes)

    return pack_output_gia_file

