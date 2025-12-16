from __future__ import annotations

from pathlib import Path
from typing import Iterable, List


def _iter_data_directories(workspace_path: Path) -> Iterable[Path]:
    # 运行期数据目录（约定：只存放可清理的缓存/会话状态，不得包含 Python 源码文件）
    yield workspace_path / "app" / "runtime" / "cache"
    yield workspace_path / "app" / "runtime" / "todo_states"


def _scan_for_python_sources(data_directory: Path) -> List[Path]:
    if not data_directory.exists():
        return []

    forbidden_files: List[Path] = []
    for python_file in data_directory.rglob("*.py"):
        forbidden_files.append(python_file)
    return forbidden_files


def main() -> None:
    workspace_path = Path(__file__).resolve().parent.parent

    all_forbidden_files: List[Path] = []
    for data_directory in _iter_data_directories(workspace_path):
        all_forbidden_files.extend(_scan_for_python_sources(data_directory))

    if all_forbidden_files:
        print("[ERROR] 检测到运行期数据目录中包含 Python 源码文件（会被误认为可导入包/模块）：")
        for forbidden_file in sorted(all_forbidden_files, key=lambda p: p.as_posix()):
            print(f"  - {forbidden_file.as_posix()}")
        raise SystemExit(1)

    print("[OK] 运行期数据目录未发现 Python 源码文件（未被误做成可导入包）")


if __name__ == "__main__":
    main()


