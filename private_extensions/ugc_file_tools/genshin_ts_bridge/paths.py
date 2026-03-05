from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _find_graph_generater_root(start: Path) -> Path:
    resolved = Path(start).resolve()
    for parent in [resolved, *resolved.parents]:
        if (parent / "engine").is_dir() and (parent / "assets").is_dir():
            return parent
    raise ValueError("无法定位 Graph_Generater 根目录（未找到 engine/ 与 assets/）。")


@dataclass(frozen=True, slots=True)
class GenshinTsBridgePaths:
    graph_generater_root: Path
    genshin_ts_root: Path
    node_editor_pack_root: Path
    gia_proto_path: Path
    node_id_ts_path: Path
    node_pin_records_ts_path: Path
    concrete_map_ts_path: Path


def resolve_paths() -> GenshinTsBridgePaths:
    gg_root = _find_graph_generater_root(Path(__file__))
    snapshot_root = (
        gg_root
        / "private_extensions"
        / "ugc_file_tools"
        / "refs"
        / "genshin_ts"
        / "upstream_snapshot"
    )
    _ = snapshot_root
    genshin_ts_root = gg_root / "private_extensions" / "third_party" / "genshin-ts"
    node_editor_pack_root = (
        genshin_ts_root
        / "src"
        / "thirdparty"
        / "Genshin-Impact-Miliastra-Wonderland-Code-Node-Editor-Pack"
    )
    gia_proto_path = node_editor_pack_root / "protobuf" / "gia.proto"
    node_id_ts_path = node_editor_pack_root / "node_data" / "node_id.ts"
    node_pin_records_ts_path = node_editor_pack_root / "node_data" / "node_pin_records.ts"
    concrete_map_ts_path = node_editor_pack_root / "node_data" / "concrete_map.ts"

    if not genshin_ts_root.is_dir():
        raise FileNotFoundError(str(genshin_ts_root))
    if not node_editor_pack_root.is_dir():
        raise FileNotFoundError(str(node_editor_pack_root))
    if not gia_proto_path.is_file():
        raise FileNotFoundError(str(gia_proto_path))
    if not node_id_ts_path.is_file():
        raise FileNotFoundError(str(node_id_ts_path))
    if not node_pin_records_ts_path.is_file():
        raise FileNotFoundError(str(node_pin_records_ts_path))
    if not concrete_map_ts_path.is_file():
        raise FileNotFoundError(str(concrete_map_ts_path))

    return GenshinTsBridgePaths(
        graph_generater_root=gg_root,
        genshin_ts_root=genshin_ts_root,
        node_editor_pack_root=node_editor_pack_root,
        gia_proto_path=gia_proto_path,
        node_id_ts_path=node_id_ts_path,
        node_pin_records_ts_path=node_pin_records_ts_path,
        concrete_map_ts_path=concrete_map_ts_path,
    )

