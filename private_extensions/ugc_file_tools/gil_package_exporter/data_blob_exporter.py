from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .file_io import _ensure_directory, _write_json_file, _write_text_file
from .models import DataBlobRecord
from .object_scanners import _collect_data_blobs


def _export_data_blobs_from_pyugc_object(
    *,
    pyugc_object: Any,
    output_package_root: Path,
) -> Tuple[List[DataBlobRecord], int]:
    data_blob_entries = _collect_data_blobs(pyugc_object)
    binary_blob_directory = output_package_root / "原始解析" / "数据块"
    _ensure_directory(binary_blob_directory)
    binary_blob_index: List[DataBlobRecord] = []

    seen_sha1_to_stem: Dict[str, str] = {}

    for blob_index, (json_path, key_name, base64_text) in enumerate(data_blob_entries, start=1):
        blob_bytes = base64.b64decode(base64_text)
        if len(blob_bytes) == 0:
            continue

        sha1_hex = hashlib.sha1(blob_bytes).hexdigest()
        existing_stem = seen_sha1_to_stem.get(sha1_hex)
        if existing_stem is None:
            file_stem = f"blob_{blob_index:04d}_{len(blob_bytes)}_{sha1_hex[:12]}"
            seen_sha1_to_stem[sha1_hex] = file_stem

            (binary_blob_directory / f"{file_stem}.bin").write_bytes(blob_bytes)
            _write_text_file(binary_blob_directory / f"{file_stem}.path.txt", json_path)
        else:
            file_stem = existing_stem

        binary_blob_index.append(
            DataBlobRecord(
                blob_index=blob_index,
                json_path=json_path,
                key_name=key_name,
                byte_size=len(blob_bytes),
                sha1_hex=sha1_hex,
                file_stem=file_stem,
            )
        )

    _write_json_file(
        output_package_root / "原始解析" / "数据块" / "index.json",
        [record.__dict__ for record in binary_blob_index],
    )

    unique_files = len(seen_sha1_to_stem)
    return binary_blob_index, unique_files


