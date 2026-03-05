from __future__ import annotations

import argparse
import io
import sys

from engine.resources.level_variable_schema_service import LevelVariableSchemaService

_SEPARATOR_WIDTH = 60


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_level_variables",
        description="关卡变量 Schema 载入校验（会触发引擎侧 fail-fast 规则）。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--package-id",
        default="",
        help="仅校验指定项目存档（默认校验共享+全部项目存档）。",
    )
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

    parsed = _parse_args(sys.argv[1:] if argv is None else argv)
    package_id = str(getattr(parsed, "package_id", "") or "").strip() or None

    service = LevelVariableSchemaService()
    variable_files = service.load_all_variable_files(active_package_id=package_id)
    variables_count = sum(len(info.variables) for info in variable_files.values())

    print("=" * _SEPARATOR_WIDTH)
    print("关卡变量 Schema 载入校验")
    print("=" * _SEPARATOR_WIDTH)
    if package_id:
        print(f"package_id: {package_id}")
    print(f"变量文件数量: {len(variable_files)}")
    print(f"变量总数量: {variables_count}")
    print("校验通过（schema 已成功载入，且规则未触发错误）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

