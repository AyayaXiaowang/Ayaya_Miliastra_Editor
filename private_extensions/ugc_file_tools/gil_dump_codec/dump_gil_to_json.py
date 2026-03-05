from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_dump_json_object


def dump_gil_to_json(gil_file_path: str, json_file_path: str) -> None:
    """
    纯 Python 实现：将 `.gil` 的 payload 解码为“数值键 JSON”（与历史 DLL dump-json 口径兼容）。

    输出 JSON 的顶层仍保持 `{"4": <payload_root>}` 形态（与现有工具链一致）：
    - `<payload_root>` 为 protobuf-like message 的数值键 dict（"1"/"2"/...），
      值为 int/float/str/"<binary_data> .."/dict/list 的组合。
    """
    input_path = Path(gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    dump_object: Dict[str, Any] = load_gil_payload_as_dump_json_object(input_path, max_depth=32, prefer_raw_hex_for_utf8=False)

    output_path = Path(json_file_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dump_object, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = ["dump_gil_to_json"]

