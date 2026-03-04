from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


JSON_DUMPS_KWARGS = {"ensure_ascii": False, "separators": (",", ":")}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _as_payload_root(raw_dump: Dict[str, Any]) -> Dict[str, Any]:
    payload_root = raw_dump.get("4")
    if not isinstance(payload_root, dict):
        raise TypeError("dump['4'] payload_root must be dict")
    return payload_root


def _key_sort_tuple(k: Any) -> Tuple[int, str]:
    try:
        return int(str(k)), str(k)
    except Exception:
        return (2**31 - 1), str(k)


def inspect_fields(input_gil: Path) -> None:
    from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object

    raw = dump_gil_to_raw_json_object(Path(input_gil).resolve())
    payload_root = _as_payload_root(raw)

    items: List[Tuple[str, int]] = []
    for k, v in payload_root.items():
        size = len(json.dumps(v, **JSON_DUMPS_KWARGS))
        items.append((str(k), int(size)))

    items.sort(key=lambda kv: _key_sort_tuple(kv[0]))

    print(str(Path(input_gil).resolve()))
    print(f"payload_root fields: {len(items)}")
    for k, size in items:
        print(f"- {k}: approx_json_chars={size}")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect payload_root('4') top-level fields of a .gil.")
    parser.add_argument("--input", required=True, help="Input .gil path")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root / "private_extensions"))

    inspect_fields(Path(args.input))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

