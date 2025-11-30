from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2
from typing import Iterable, List, Dict, Any


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".idea",
    ".vscode",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
    ".venv",
    "venv",
}

EXCLUDE_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".pyd",
}

# “代码文件”快照默认包含的扩展名
CODE_EXTENSIONS = {
    ".py",
    ".pyi",
    ".md",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".txt",
    ".csv",
    ".cfg",
    ".conf",
    ".pyx",
    ".pxd",
}


def compute_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def should_include_file(path: Path, include_binaries: bool) -> bool:
    suffix = path.suffix.lower()
    if suffix in EXCLUDE_FILE_SUFFIXES:
        return False
    if include_binaries:
        return True
    return suffix in CODE_EXTENSIONS


def is_subpath(child: Path, parent: Path) -> bool:
    child_resolved = child.resolve()
    parent_resolved = parent.resolve()
    child_str = str(child_resolved)
    parent_str = str(parent_resolved)
    return child_str == parent_str or child_str.startswith(parent_str + os.sep)


def collect_and_copy(
    root: Path,
    out_dir: Path,
    include_binaries: bool,
) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    total_bytes = 0

    for dirpath, dirnames, filenames in os.walk(root):
        current_dir = Path(dirpath)

        # 跳过输出目录自身（避免把快照再快照）
        if is_subpath(current_dir, out_dir):
            dirnames[:] = []
            continue

        # 排除不参与快照的目录
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE_DIRS]

        for filename in filenames:
            src_path = current_dir / filename
            if not should_include_file(src_path, include_binaries):
                continue

            rel_path = src_path.relative_to(root)
            rel_posix = rel_path.as_posix()

            sha256 = compute_sha256(src_path)
            size = src_path.stat().st_size
            total_bytes += size

            dst_path = out_dir / rel_path
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            copy2(src_path, dst_path)

            files.append(
                {
                    "path": rel_posix,
                    "bytes": size,
                    "sha256": sha256,
                }
            )

    manifest: Dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source_root": str(root.resolve()),
        "output_dir": str(out_dir.resolve()),
        "include_binaries": include_binaries,
        "excluded_dirs": sorted(list(DEFAULT_EXCLUDE_DIRS)),
        "excluded_file_suffixes": sorted(list(EXCLUDE_FILE_SUFFIXES)),
        "included_extensions": "ALL" if include_binaries else sorted(list(CODE_EXTENSIONS)),
        "total_files": len(files),
        "total_bytes": total_bytes,
        "files": files,
    }
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成项目‘改名前’的完整代码快照（含校验清单）。默认仅包含代码/文本类文件，可加 --full 包含二进制资源。"
    )
    parser.add_argument(
        "-o",
        "--out",
        dest="out",
        default="",
        help="输出目录（相对项目根）。默认：docs/snapshots/before_rename_YYYYMMDD_HHMMSS",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="包含全部文件（除默认排除目录与 .pyc/.pyd 等），而不仅是代码/文本类文件。",
    )
    parser.add_argument(
        "--root",
        dest="root",
        default="",
        help="项目根目录（默认取脚本所在 tools 的上级目录）。",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    default_root = script_path.parent.parent
    root = Path(args.root).resolve() if args.root else default_root

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out_rel = Path("docs") / "snapshots" / f"before_rename_{timestamp}"
    out_rel = Path(args.out) if args.out else default_out_rel
    out_dir = (root / out_rel).resolve()

    out_dir.mkdir(parents=True, exist_ok=False)

    manifest = collect_and_copy(root=root, out_dir=out_dir, include_binaries=args.full)

    manifest_path = out_dir / "snapshot_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    file_list_path = out_dir / "FILE_LIST.txt"
    with file_list_path.open("w", encoding="utf-8") as f:
        for item in manifest["files"]:
            f.write(f"{item['sha256']} {item['bytes']} {item['path']}\n")

    readme_path = out_dir / "README.txt"
    with readme_path.open("w", encoding="utf-8") as f:
        f.write(
            "本目录为‘改名前’的代码快照（只读）。\n"
            "包含：\n"
            "- 文件副本（按项目相对路径重建目录）\n"
            "- snapshot_manifest.json（校验与统计）\n"
            "- FILE_LIST.txt（sha256 与字节数清单）\n\n"
            "注意：请勿手工修改此目录内容；如需新快照，请重新运行工具脚本生成新批次。\n"
        )

    print(f"Snapshot created at: {out_dir}")
    print(f"Files: {manifest['total_files']}, Bytes: {manifest['total_bytes']}")


if __name__ == "__main__":
    main()


