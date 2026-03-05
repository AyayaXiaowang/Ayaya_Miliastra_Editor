from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import List, Optional

from importlib.machinery import SourceFileLoader

from ..var_type_map import map_server_port_type_text_to_var_type_id_or_raise
from .player_template_bootstrap import create_player_template_inplace, load_seed_from_gil
from .player_templates import (
    add_custom_variable_to_template_inplace,
    copy_template_custom_variable_defs_inplace,
    dump_player_templates_report,
    extract_player_template_group1_container_item_bytes_from_gil,
    list_player_templates,
    load_payload_root,
    patch_player_template_custom_variable_defs_in_gil,
    patch_player_template_custom_variable_group1_item_bytes_in_gil,
    set_template_players_inplace,
    write_back_payload,
)


def _parse_players_1_based(text: str) -> List[int]:
    raw = str(text or "").strip()
    if raw == "":
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip() != ""]
    out: List[int] = []
    for p in parts:
        if not p.isdigit():
            raise ValueError(f"players must be comma-separated integers: {text!r}")
        out.append(int(p))
    return out


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        prog="player_templates_tool",
        description="玩家模板写回工具（.gil）：新建模板/改生效玩家/加自定义变量/导出报告",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_dump = sub.add_parser("dump", help="输出玩家模板报告（JSON）")
    p_dump.add_argument("--input-gil", required=True)

    p_set = sub.add_parser("set-players", help="修改模板生效玩家（1..8，逗号分隔）")
    p_set.add_argument("--input-gil", required=True)
    p_set.add_argument("--output-gil", required=True)
    p_set.add_argument("--template-name", required=True)
    p_set.add_argument("--players", required=True, help="例如: 1 或 2,3,4,5；写 1..8 全部将落成“缺失 field_4”语义")

    p_add = sub.add_parser("add-var", help="给模板添加一条自定义变量定义")
    p_add.add_argument("--input-gil", required=True)
    p_add.add_argument("--output-gil", required=True)
    p_add.add_argument("--template-name", required=True)
    p_add.add_argument("--var-name", required=True)
    p_add.add_argument("--type-code", type=int, required=True, help="例如: 3(整数) 6(字符串) 11(字符串列表) 8(整数列表) 20(配置ID)")
    p_add.add_argument("--default", required=False, help="默认值（当前仅强支持整数/字符串/配置ID；列表建议先留空）")

    p_create = sub.add_parser("create", help="从 seed 克隆结构，在目标存档中创建新玩家模板（含角色编辑条目）")
    p_create.add_argument("--base-gil", required=True, help="要写入的目标存档（可以是空存档）")
    p_create.add_argument("--seed-gil", required=True, help="提供玩家模板段结构的种子存档（推荐使用你给的 简单玩家模板的存档.gil）")
    p_create.add_argument("--output-gil", required=True)
    p_create.add_argument("--base-template-name", required=True, help="seed 中用于克隆的基础模板名（推荐：自定义玩家模版）")
    p_create.add_argument("--new-template-name", required=True)
    p_create.add_argument("--players", required=False, help="例如 1 或 2,3,4,5；不传则表示“全部玩家”（缺失 field_4）")
    p_create.add_argument("--copy-vars-from", required=False, help="从某个模板拷贝变量定义（推荐：自定义变量）")

    p_copy = sub.add_parser("copy-vars", help="从参考 gil 拷贝指定模板的自定义变量定义（覆盖 group1）")
    p_copy.add_argument("--input-gil", required=True, help="目标 .gil（被写回）")
    p_copy.add_argument("--reference-gil", required=True, help="参考 .gil（提供变量定义）")
    p_copy.add_argument("--output-gil", required=True, help="输出 .gil（不覆盖 input）")
    p_copy.add_argument("--src-template-name", required=False, help="参考模板名；不传则要求 reference 仅有一个模板")
    p_copy.add_argument("--dst-template-name", required=False, help="目标模板名；不传则默认同名/或要求 input 仅有一个模板")

    p_apply = sub.add_parser("apply-vars", help="将变量文件(LEVEL_VARIABLES)写入玩家模板自定义变量定义（覆盖 group1）")
    p_apply.add_argument("--input-gil", required=True, help="目标 .gil（被写回）")
    p_apply.add_argument("--output-gil", required=True, help="输出 .gil（不覆盖 input）")
    p_apply.add_argument("--template-name", required=False, help="目标模板名；不传则要求 input 仅有一个玩家模板")
    p_apply.add_argument("--vars-py", required=True, help="变量定义 Python 文件路径（需导出 LEVEL_VARIABLES）")

    args = ap.parse_args(argv)

    if args.cmd == "dump":
        report = dump_player_templates_report(Path(args.input_gil))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    if args.cmd == "set-players":
        in_path = Path(args.input_gil)
        _, root = load_payload_root(in_path)
        players = _parse_players_1_based(args.players)
        report = set_template_players_inplace(root, template_name=args.template_name, players_1_based=players)
        out_path = write_back_payload(base_gil=in_path, payload_root=root, output_gil=Path(args.output_gil))
        print(json.dumps({"output_gil": str(out_path), "report": report}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "add-var":
        in_path = Path(args.input_gil)
        _, root = load_payload_root(in_path)
        default_text = args.default
        default_value = default_text
        if args.type_code in (3, 20):
            if default_text is None or str(default_text).strip() == "":
                default_value = 0
            else:
                default_value = int(str(default_text).strip())
        report = add_custom_variable_to_template_inplace(
            root,
            template_name=args.template_name,
            variable_name=args.var_name,
            type_code=int(args.type_code),
            default_value=default_value,
        )
        out_path = write_back_payload(base_gil=in_path, payload_root=root, output_gil=Path(args.output_gil))
        print(json.dumps({"output_gil": str(out_path), "report": report}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "create":
        seed = load_seed_from_gil(Path(args.seed_gil))
        base_path = Path(args.base_gil)
        _, root = load_payload_root(base_path)
        players_list = _parse_players_1_based(args.players) if args.players else None
        report = create_player_template_inplace(
            root,
            seed=seed,
            base_template_name=args.base_template_name,
            new_template_name=args.new_template_name,
            players_1_based=players_list,
            copy_custom_variable_defs_from_name=args.copy_vars_from,
        )
        out_path = write_back_payload(base_gil=base_path, payload_root=root, output_gil=Path(args.output_gil))
        print(json.dumps({"output_gil": str(out_path), "report": report}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "apply-vars":
        in_path = Path(args.input_gil)

        # 仅用于默认值推断：读取一次结构化列表（不会写回、不影响 wire-level patch 的“保真写回”策略）
        template_name = str(args.template_name or "").strip()
        if template_name == "":
            _, root = load_payload_root(in_path)
            templates = list_player_templates(root)
            if len(templates) != 1:
                names = [t.name for t in templates]
                raise ValueError(f"input 存在多个玩家模板，必须显式指定 --template-name。templates={names!r}")
            template_name = str(templates[0].name)

        vars_py = Path(args.vars_py).resolve()
        if not vars_py.is_file():
            raise FileNotFoundError(str(vars_py))

        # 动态加载变量文件（不要求其处于 python package 内）
        module_name = f"_level_vars_{vars_py.stem}"
        loader = SourceFileLoader(module_name, str(vars_py))
        spec = importlib.util.spec_from_loader(module_name, loader)
        if spec is None:
            raise RuntimeError(f"无法为变量文件构造 module spec：{str(vars_py)!r}")
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)

        level_vars = getattr(mod, "LEVEL_VARIABLES", None)
        if not isinstance(level_vars, list):
            raise TypeError("变量文件必须导出 LEVEL_VARIABLES: list[LevelVariableDefinition]")

        variables: List[tuple[str, int, object]] = []
        for v in level_vars:
            name = getattr(v, "variable_name", None)
            typ = getattr(v, "variable_type", None)
            default_value = getattr(v, "default_value", None)
            if not isinstance(name, str) or name.strip() == "":
                raise TypeError(f"LEVEL_VARIABLES 条目缺少有效 variable_name：{v!r}")
            if not isinstance(typ, str) or typ.strip() == "":
                raise TypeError(f"LEVEL_VARIABLES 条目缺少有效 variable_type：{name!r}")
            type_code = map_server_port_type_text_to_var_type_id_or_raise(str(typ))
            variables.append((str(name).strip(), int(type_code), default_value))

        report = patch_player_template_custom_variable_defs_in_gil(
            input_gil=in_path,
            output_gil=Path(args.output_gil),
            template_name=str(template_name),
            variables=[(n, int(tc), dv) for (n, tc, dv) in variables],
        )
        print(json.dumps({"output_gil": str(report.get("output_gil") or ""), "report": report}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "copy-vars":
        in_path = Path(args.input_gil)
        ref_path = Path(args.reference_gil)

        src_name = str(args.src_template_name or "").strip()
        if src_name == "":
            _, src_root = load_payload_root(ref_path)
            src_templates = list_player_templates(src_root)
            if len(src_templates) != 1:
                names = [t.name for t in src_templates]
                raise ValueError(f"reference 存在多个模板，必须显式指定 --src-template-name。templates={names!r}")
            src_name = str(src_templates[0].name)

        dst_name = str(args.dst_template_name or "").strip()
        if dst_name == "":
            if str(args.src_template_name or "").strip() != "":
                dst_name = str(src_name)
            else:
                _, dst_root = load_payload_root(in_path)
                dst_templates = list_player_templates(dst_root)
                if len(dst_templates) != 1:
                    names = [t.name for t in dst_templates]
                    raise ValueError(f"input 存在多个模板，必须显式指定 --dst-template-name。templates={names!r}")
                dst_name = str(dst_templates[0].name)

        group1_item_bytes = extract_player_template_group1_container_item_bytes_from_gil(
            input_gil=ref_path,
            template_name=str(src_name),
        )
        report = patch_player_template_custom_variable_group1_item_bytes_in_gil(
            input_gil=in_path,
            output_gil=Path(args.output_gil),
            template_name=str(dst_name),
            group1_container_item_bytes=bytes(group1_item_bytes),
        )
        print(json.dumps({"output_gil": str(report.get("output_gil") or ""), "report": report}, ensure_ascii=False, indent=2))
        return

    raise RuntimeError(f"unknown cmd: {args.cmd!r}")


if __name__ == "__main__":
    main()

