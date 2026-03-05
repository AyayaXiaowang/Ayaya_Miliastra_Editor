from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.resources.auto_custom_variable_registry import load_auto_custom_variable_registry_from_code
from engine.resources.auto_custom_variable_registry import normalize_owner_refs

_EXIT_OK = 0
_EXIT_ERROR = 1

_SEPARATOR_WIDTH = 60


@dataclass(frozen=True, slots=True)
class _RegistryError:
    package_id: str
    registry_path: Path
    variable_id: str
    variable_name: str
    variable_type: str
    owner_ref: str
    message: str


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_custom_variable_registry",
        description=(
            "自定义变量注册表校验（静态加载，不执行注册表代码）。\n"
            "目标：提前定位“写回阶段会崩”的问题，例如：\n"
            "- typed dict alias 与 default_value 类型不一致（字符串-整数字典却给中文文本）\n"
            "- default_value 在目标 VarType 下无法解析（int/float 等）\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--package-id",
        default="",
        help="仅校验指定项目存档（默认校验全部项目存档）。",
    )
    return parser.parse_args(list(argv))


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.resolve()


def _project_archives_root() -> Path:
    return (_repo_root() / "assets" / "资源库" / "项目存档").resolve()


def _iter_package_ids(*, only_package_id: str | None) -> list[str]:
    root = _project_archives_root()
    if only_package_id:
        return [str(only_package_id)]
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    out: list[str] = []
    for p in sorted(root.iterdir(), key=lambda x: x.name.casefold()):
        if not p.is_dir():
            continue
        name = str(p.name).strip()
        if not name or name.startswith("_"):
            continue
        out.append(name)
    return out


def _try_load_registry_path(*, package_id: str) -> Path | None:
    pkg_root = (_project_archives_root() / str(package_id)).resolve()
    registry_path = (pkg_root / "管理配置" / "关卡变量" / "自定义变量注册表.py").resolve()
    return registry_path if registry_path.is_file() else None


def _load_instance_and_template_name_indexes(*, package_id: str) -> tuple[dict[str, str], dict[str, str]]:
    pkg_root = (_project_archives_root() / str(package_id)).resolve()
    instances_index = (pkg_root / "实体摆放" / "instances_index.json").resolve()
    templates_index = (pkg_root / "元件库" / "templates_index.json").resolve()

    def _load_index(path: Path, id_key: str) -> dict[str, str]:
        if not path.is_file():
            return {}
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, list):
            return {}
        out: dict[str, str] = {}
        for item in obj:
            if not isinstance(item, dict):
                continue
            rid = str(item.get(id_key) or "").strip()
            name = str(item.get("name") or "").strip()
            if rid and name and rid not in out:
                out[rid] = name
        return out

    return (_load_index(instances_index, "instance_id"), _load_index(templates_index, "template_id"))


def _validate_registry_for_package(*, package_id: str) -> tuple[list[_RegistryError], int]:
    registry_path = _try_load_registry_path(package_id=package_id)
    if registry_path is None:
        return ([], 0)

    # 让“第三方 owner_ref”可以做一点基本校验：owner_ref 是否能在索引里找到。
    instance_name_by_id, template_name_by_id = _load_instance_and_template_name_indexes(package_id=package_id)

    decls = load_auto_custom_variable_registry_from_code(registry_path)

    # 复用写回阶段的 value_message 构造逻辑做“会不会炸”的校验。
    from private_extensions.ugc_file_tools.project_archive_importer.custom_variable_writeback import (
        build_custom_variable_item_from_level_variable_payload,
    )

    errors: list[_RegistryError] = []
    owners_keywords = {"level", "player"}

    for d in decls:
        variable_id = str(d.variable_id or "").strip()
        variable_name = str(d.variable_name or "").strip()
        variable_type = str(d.variable_type or "").strip()

        owner_refs = [str(x).strip() for x in normalize_owner_refs(d.owner)]
        if not owner_refs:
            owner_refs = [""]

        for owner_ref in owner_refs:
            owner_ref2 = str(owner_ref or "").strip()

            # 第三方 owner_ref：尽量提前发现“引用不存在”的情况（这会在写回阶段因为找不到目标而 fail-fast）。
            lower = owner_ref2.lower()
            if lower and lower not in owners_keywords:
                if owner_ref2 not in instance_name_by_id and owner_ref2 not in template_name_by_id:
                    errors.append(
                        _RegistryError(
                            package_id=str(package_id),
                            registry_path=Path(registry_path),
                            variable_id=variable_id,
                            variable_name=variable_name,
                            variable_type=variable_type,
                            owner_ref=owner_ref2,
                            message=(
                                "第三方 owner_ref 未在 instances_index.json/template_index.json 中找到对应条目："
                                f"{owner_ref2!r}"
                            ),
                        )
                    )

            payload: dict[str, Any] = {
                "variable_id": variable_id,
                "variable_name": variable_name,
                "variable_type": variable_type,
                "default_value": d.default_value,
                "owner": owner_ref2,
                "category": str(d.category or ""),
                "description": str(d.description or ""),
                "metadata": (dict(d.metadata) if isinstance(d.metadata, dict) else {}),
            }

            try:
                # 只需要触发构造过程；返回值本身不使用。
                build_custom_variable_item_from_level_variable_payload(payload)
            except Exception as e:
                errors.append(
                    _RegistryError(
                        package_id=str(package_id),
                        registry_path=Path(registry_path),
                        variable_id=variable_id,
                        variable_name=variable_name,
                        variable_type=variable_type,
                        owner_ref=owner_ref2,
                        message=f"{type(e).__name__}: {e}",
                    )
                )

    return (errors, len(decls))


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

    parsed = _parse_args(sys.argv[1:] if argv is None else argv)
    package_id0 = str(getattr(parsed, "package_id", "") or "").strip()
    package_id = package_id0 or None

    package_ids = _iter_package_ids(only_package_id=package_id)

    all_errors: list[_RegistryError] = []
    total_decls = 0
    total_registries = 0

    for pid in package_ids:
        errs, decls_count = _validate_registry_for_package(package_id=str(pid))
        if decls_count > 0:
            total_registries += 1
            total_decls += int(decls_count)
        all_errors.extend(list(errs))

    print("=" * _SEPARATOR_WIDTH)
    print("自定义变量注册表校验")
    print("=" * _SEPARATOR_WIDTH)
    if package_id:
        print(f"package_id: {package_id}")
    print(f"注册表数量: {total_registries}")
    print(f"声明总数: {total_decls}")
    print(f"错误数量: {len(all_errors)}")

    if all_errors:
        print("")
        for i, e in enumerate(all_errors, start=1):
            print(f"[{i}] package={e.package_id} registry={e.registry_path}")
            print(f"    variable_id={e.variable_id!r}")
            print(f"    variable_name={e.variable_name!r}")
            print(f"    variable_type={e.variable_type!r}")
            print(f"    owner_ref={e.owner_ref!r}")
            print(f"    error={e.message}")
        return _EXIT_ERROR

    print("校验通过：未发现会导致写回失败的注册表问题。")
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

