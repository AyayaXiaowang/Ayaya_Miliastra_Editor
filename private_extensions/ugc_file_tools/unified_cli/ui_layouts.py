from __future__ import annotations

import argparse
import json
from pathlib import Path

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _load_ui_guid_registry_mapping(path: Path) -> dict[str, int]:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    from ugc_file_tools.ui.guid_registry_format import load_ui_guid_registry_mapping

    return load_ui_guid_registry_mapping(p)


def _command_ui_clone_component_groups_to_library(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers import create_control_group_in_library_from_component_groups

    group_ui_keys_text = str(arguments.group_ui_keys or "").strip()
    group_ui_keys = [s.strip() for s in group_ui_keys_text.split(",") if s.strip() != ""]
    if not group_ui_keys:
        raise ValueError("--group-ui-keys 不能为空，例如: ceshi__btn_exit__group,ceshi__btn_level_select__group")

    registry_path = Path(arguments.ui_guid_registry).resolve()
    mapping = _load_ui_guid_registry_mapping(registry_path)
    group_guids: list[int] = []
    for k in group_ui_keys:
        if k not in mapping:
            raise KeyError(f"ui_guid_registry 中未找到 group_ui_key：{k!r}（registry={str(registry_path)}）")
        group_guids.append(int(mapping[k]))

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = create_control_group_in_library_from_component_groups(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        component_group_guids=group_guids,
        group_name=str(arguments.group_name),
        library_root_guid=int(arguments.library_root_guid),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    created = report.get("created_group") if isinstance(report, dict) else None

    print("=" * 80)
    print("组件组→控件组库（克隆并打组）完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- ui_guid_registry: {str(registry_path)}")
    print(f"- source_group_ui_keys: {group_ui_keys}")
    if isinstance(created, dict):
        print(f"- group_guid: {created.get('guid')}")
        print(f"- group_name: {created.get('name')}")
        print(f"- library_root_guid: {created.get('library_root_guid')}")
        print(f"- cloned_child_total: {len(created.get('child_guids') or [])}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_create_layout(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers import create_layout_in_gil

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    empty_layout = bool(getattr(arguments, "empty_layout", False))
    report = create_layout_in_gil(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        new_layout_name=str(arguments.name),
        base_layout_guid=int(arguments.base_layout_guid) if arguments.base_layout_guid is not None else None,
        empty_layout=bool(empty_layout),
        clone_children=not bool(empty_layout),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    created = report.get("created_layout") if isinstance(report, dict) else None

    print("=" * 80)
    print("布局新增完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    if isinstance(created, dict):
        print(f"- layout_guid: {created.get('guid')}")
        print(f"- name: {created.get('name')}")
        print(f"- empty_layout: {created.get('empty_layout')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_create_control_group(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers import create_control_group_in_library

    child_guids_text = str(arguments.child_guids or "").strip()
    child_guids = [int(part.strip()) for part in child_guids_text.split(",") if part.strip() != ""]
    if not child_guids:
        raise ValueError("child_guids 不能为空，例如: 1073741839,1073741840")

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = create_control_group_in_library(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        library_root_guid=int(arguments.library_root_guid),
        group_name=str(arguments.group_name),
        child_guids=child_guids,
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    created = report.get("created_group") if isinstance(report, dict) else None

    print("=" * 80)
    print("控件组打组完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    if isinstance(created, dict):
        print(f"- group_guid: {created.get('guid')}")
        print(f"- group_name: {created.get('name')}")
        print(f"- library_root_guid: {created.get('library_root_guid')}")
        print(f"- child_guids: {created.get('child_guids')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_place_control_group_template(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers import place_control_group_template_in_layout

    def parse_float_pair_optional(text: str | None) -> tuple[float, float] | None:
        t = str(text or "").strip()
        if t == "":
            return None
        parts = [p.strip() for p in t.split(",")]
        if len(parts) != 2:
            raise ValueError("坐标/尺寸格式必须为 'x,y'")
        return float(parts[0]), float(parts[1])

    pc_pos = parse_float_pair_optional(getattr(arguments, "pc_pos", None))
    pc_size = parse_float_pair_optional(getattr(arguments, "pc_size", None))
    mobile_pos = parse_float_pair_optional(getattr(arguments, "mobile_pos", None))
    mobile_size = parse_float_pair_optional(getattr(arguments, "mobile_size", None))

    if (pc_pos is None) != (pc_size is None):
        raise ValueError("--pc-pos 与 --pc-size 必须同时提供或同时省略")
    if (mobile_pos is None) != (mobile_size is None):
        raise ValueError("--mobile-pos 与 --mobile-size 必须同时提供或同时省略")

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = place_control_group_template_in_layout(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        template_root_guid=int(arguments.template_root_guid),
        layout_guid=int(arguments.layout_guid),
        instance_name=str(arguments.instance_name),
        pc_canvas_position=pc_pos,
        pc_size=pc_size,
        mobile_canvas_position=mobile_pos,
        mobile_size=mobile_size,
        layer=(int(arguments.layer) if arguments.layer is not None else None),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    created = report.get("created_instance") if isinstance(report, dict) else None
    verify = report.get("verify") if isinstance(report, dict) else None

    print("=" * 80)
    print("控件组模板放置完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- template_root_guid: {report.get('template_root_guid')}")
    print(f"- layout_guid: {report.get('layout_guid')}")
    if isinstance(created, dict):
        print(f"- instance_guid: {created.get('guid')}")
        print(f"- instance_name: {created.get('name')}")
        print(f"- instance_children_total: {len(created.get('children_guids') or [])}")
    if isinstance(verify, dict):
        print(f"- verify_ok: {verify.get('instance_exists') and verify.get('instance_parent_ok') and verify.get('instance_children_parent_ok')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_save_control_group_as_template(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers import save_control_group_as_template

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = save_control_group_as_template(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        library_root_guid=int(arguments.library_root_guid),
        group_guid=int(arguments.group_guid),
        template_name=str(arguments.template_name),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("控件组保存为模板完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- group_guid: {report.get('group_guid')}")
    print(f"- template_root_guid: {report.get('template_root_guid')}")
    print(f"- template_name: {report.get('template_name')}")
    print(f"- template_children_guids: {report.get('template_children_guids')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_set_control_layer(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers import set_control_rect_transform_layers

    guids_text = str(arguments.guids or "").strip()
    layers_text = str(arguments.layers or "").strip()
    guids = [int(part.strip()) for part in guids_text.split(",") if part.strip() != ""]
    layers = [int(part.strip()) for part in layers_text.split(",") if part.strip() != ""]
    if not guids:
        raise ValueError("--guids 不能为空，例如: 1073741839,1073741840")
    if len(guids) != len(layers):
        raise ValueError("--guids 与 --layers 个数必须一致")

    layers_by_guid = {int(g): int(l) for g, l in zip(guids, layers, strict=True)}

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = set_control_rect_transform_layers(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        layers_by_guid=layers_by_guid,
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("控件层级写回完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- updated_total: {report.get('updated_total')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_clone_record_from_schema(arguments: argparse.Namespace) -> None:
    from ugc_file_tools.ui_patchers import clone_ui_record_from_schema_library

    def parse_float_pair_optional(text: str | None) -> tuple[float, float] | None:
        t = str(text or "").strip()
        if t == "":
            return None
        parts = [p.strip() for p in t.split(",")]
        if len(parts) != 2:
            raise ValueError("坐标/尺寸格式必须为 'x,y'")
        return float(parts[0]), float(parts[1])

    pc_pos = parse_float_pair_optional(getattr(arguments, "pc_pos", None))
    pc_size = parse_float_pair_optional(getattr(arguments, "pc_size", None))
    mobile_pos = parse_float_pair_optional(getattr(arguments, "mobile_pos", None))
    mobile_size = parse_float_pair_optional(getattr(arguments, "mobile_size", None))

    if (pc_pos is None) != (pc_size is None):
        raise ValueError("--pc-pos 与 --pc-size 必须同时提供或同时省略")
    if (mobile_pos is None) != (mobile_size is None):
        raise ValueError("--mobile-pos 与 --mobile-size 必须同时提供或同时省略")

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = clone_ui_record_from_schema_library(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        schema_id=str(arguments.schema_id),
        parent_guid=int(arguments.parent_guid),
        new_name=(str(arguments.name) if arguments.name is not None else None),
        new_guid=(int(arguments.new_guid) if arguments.new_guid is not None else None),
        pc_canvas_position=pc_pos,
        pc_size=pc_size,
        mobile_canvas_position=mobile_pos,
        mobile_size=mobile_size,
        layer=(int(arguments.layer) if arguments.layer is not None else None),
        register_layout_root_mode=str(arguments.register_layout_root_mode),
        template_id_mode=str(arguments.template_id_mode),
        template_id=(int(arguments.template_id) if arguments.template_id is not None else None),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("schema 克隆写回完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- schema_id: {report.get('schema_id')}")
    print(f"- parent_guid: {report.get('parent_guid')}")
    print(f"- new_guid: {report.get('new_guid')}")
    print(f"- register_layout_root_mode: {report.get('register_layout_root_mode')}")
    meta13 = report.get("meta_blob13_field501")
    if isinstance(meta13, dict):
        print(
            f"- meta_blob13_field501: {meta13.get('before')} -> {meta13.get('after')} (mode={meta13.get('mode')})"
        )
    verify = report.get("verify")
    if isinstance(verify, dict):
        print(f"- verify_ok: {verify.get('ok')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_place_control_from_schemas(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers import place_ui_control_from_schema_library

    def parse_float_pair_optional(text: str | None) -> tuple[float, float] | None:
        t = str(text or "").strip()
        if t == "":
            return None
        parts = [p.strip() for p in t.split(",")]
        if len(parts) != 2:
            raise ValueError("坐标/尺寸格式必须为 'x,y'")
        return float(parts[0]), float(parts[1])

    pc_pos = parse_float_pair_optional(getattr(arguments, "pc_pos", None))
    pc_size = parse_float_pair_optional(getattr(arguments, "pc_size", None))
    mobile_pos = parse_float_pair_optional(getattr(arguments, "mobile_pos", None))
    mobile_size = parse_float_pair_optional(getattr(arguments, "mobile_size", None))

    if (pc_pos is None) != (pc_size is None):
        raise ValueError("--pc-pos 与 --pc-size 必须同时提供或同时省略")
    if (mobile_pos is None) != (mobile_size is None):
        raise ValueError("--mobile-pos 与 --mobile-size 必须同时提供或同时省略")

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)
    report = place_ui_control_from_schema_library(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        template_entry_schema_id=str(arguments.template_entry_schema_id),
        instance_schema_id=str(arguments.instance_schema_id),
        template_parent_guid=int(arguments.template_parent_guid),
        layout_guid=int(arguments.layout_guid),
        template_name=(str(arguments.template_name) if arguments.template_name is not None else None),
        instance_name=(str(arguments.instance_name) if arguments.instance_name is not None else None),
        pc_canvas_position=pc_pos,
        pc_size=pc_size,
        mobile_canvas_position=mobile_pos,
        mobile_size=mobile_size,
        template_id_mode=str(arguments.template_id_mode),
        template_id=(int(arguments.template_id) if arguments.template_id is not None else None),
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    created = report.get("created") if isinstance(report, dict) else None

    print("=" * 80)
    print("schema 放置控件完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    meta13_place = report.get("meta_blob13_field501")
    if isinstance(meta13_place, dict):
        print(f"- meta_blob13_field501: {meta13_place.get('value')} (mode={meta13_place.get('mode')})")
    if isinstance(created, dict):
        print(f"- template_entry_guid: {created.get('template_entry_guid')}")
        print(f"- instance_guid: {created.get('instance_guid')}")
    verify = report.get("verify")
    if isinstance(verify, dict):
        print(f"- verify_ok: {verify.get('ok')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def _command_ui_patch_controls(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers.misc.control_variants import ControlVariantPatch, apply_control_variant_patches_in_gil

    patch_json_path = Path(str(arguments.patch_json_file)).resolve()
    if not patch_json_path.is_file():
        raise FileNotFoundError(str(patch_json_path))

    patch_object = json.loads(patch_json_path.read_text(encoding="utf-8"))
    if isinstance(patch_object, dict):
        patch_list = patch_object.get("patches")
    else:
        patch_list = patch_object

    if not isinstance(patch_list, list) or not patch_list:
        raise ValueError("patch-json 必须是 list[patch]，或 {'patches': list[patch]} 且非空")

    patches: List[ControlVariantPatch] = []
    for item in patch_list:
        if not isinstance(item, dict):
            raise TypeError("patch item must be dict")

        guid_value = item.get("guid")
        if not isinstance(guid_value, int):
            raise ValueError("patch item missing int guid")

        def _parse_optional_float_pair(value: Any) -> Optional[Tuple[float, float]]:
            if value is None:
                return None
            if (
                isinstance(value, (list, tuple))
                and len(value) == 2
                and isinstance(value[0], (int, float))
                and isinstance(value[1], (int, float))
            ):
                return float(value[0]), float(value[1])
            if isinstance(value, dict) and isinstance(value.get("x"), (int, float)) and isinstance(value.get("y"), (int, float)):
                return float(value["x"]), float(value["y"])
            raise ValueError("pair must be [x,y] or {'x':..,'y':..}")

        patches.append(
            ControlVariantPatch(
                guid=int(guid_value),
                new_name=(str(item["name"]) if "name" in item and item.get("name") is not None else None),
                visible=(bool(item["visible"]) if "visible" in item and item.get("visible") is not None else None),
                layer=(int(item["layer"]) if "layer" in item and item.get("layer") is not None else None),
                pc_canvas_position=_parse_optional_float_pair(item.get("pc_pos")),
                pc_size=_parse_optional_float_pair(item.get("pc_size")),
                mobile_canvas_position=_parse_optional_float_pair(item.get("mobile_pos")),
                mobile_size=_parse_optional_float_pair(item.get("mobile_size")),
            )
        )

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)

    report = apply_control_variant_patches_in_gil(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        patches=patches,
        verify_with_dll_dump=bool(arguments.verify),
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("控件属性写回完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- patched: {report.get('patched_total')}/{report.get('requested_patch_total')}")
    verify = report.get("verify")
    if isinstance(verify, dict):
        print(f"- verify_ok: {verify.get('ok')}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def register_ui_layouts_subcommands(ui_subparsers: argparse._SubParsersAction) -> None:
    create_layout_parser = ui_subparsers.add_parser(
        "create-layout",
        help="新建一个界面布局（复制现有布局 root）并写回新 .gil（默认克隆固有 children；可选创建空布局）。",
    )
    create_layout_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    create_layout_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    create_layout_parser.add_argument("--name", dest="name", required=True, help="新布局名称（例如：自定义布局3）")
    create_layout_parser.add_argument(
        "--base-layout-guid",
        dest="base_layout_guid",
        type=int,
        default=None,
        help="可选：复制哪个布局 root 作为模板（不填则自动选择一个“有 children 的布局”作为基底）。",
    )
    create_layout_parser.add_argument(
        "--empty-layout",
        dest="empty_layout",
        action="store_true",
        help="危险：创建空布局（children 为空）。默认不启用：默认会克隆基底布局的固有 children。",
    )
    create_layout_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并检查新布局 GUID 是否存在。",
    )
    create_layout_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    create_layout_parser.set_defaults(entrypoint=_command_ui_create_layout)

    create_control_group_parser = ui_subparsers.add_parser(
        "create-control-group",
        help="在控件组库根下把若干控件打组为一个父节点（组容器）。",
    )
    create_control_group_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    create_control_group_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    create_control_group_parser.add_argument(
        "--library-root-guid",
        dest="library_root_guid",
        type=int,
        default=1073741838,
        help="控件组库根节点 GUID（样本为 1073741838）。",
    )
    create_control_group_parser.add_argument(
        "--group-name",
        dest="group_name",
        required=True,
        help="组名称（例如：组合1）。",
    )
    create_control_group_parser.add_argument(
        "--child-guids",
        dest="child_guids",
        required=True,
        help="要打组的控件 GUID 列表（逗号分隔），例如：1073741839,1073741840",
    )
    create_control_group_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并校验 parent/children 关系是否成立。",
    )
    create_control_group_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    create_control_group_parser.set_defaults(entrypoint=_command_ui_create_control_group)

    clone_component_groups_parser = ui_subparsers.add_parser(
        "clone-component-groups-to-library",
        help=(
            "从布局内“组件组容器”(纯组容器)抽取其 children，克隆到控件组库根下，并一键打组为一个库内控件组。"
            "用于把 Web 导入的按钮等组件写进控件组库（后续可再 save-control-group-as-template）。"
        ),
    )
    clone_component_groups_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    clone_component_groups_parser.add_argument(
        "output_gil_file",
        help="输出 .gil 文件路径（建议不要覆盖原文件）",
    )
    clone_component_groups_parser.add_argument(
        "--ui-guid-registry",
        dest="ui_guid_registry",
        required=True,
        help="UIKey→GUID 注册表路径（ui_guid_registry.json）。",
    )
    clone_component_groups_parser.add_argument(
        "--group-ui-keys",
        dest="group_ui_keys",
        required=True,
        help="要抽取的组件组容器 ui_key 列表（逗号分隔），例如：ceshi__btn_exit__group,ceshi__btn_level_select__group",
    )
    clone_component_groups_parser.add_argument(
        "--library-root-guid",
        dest="library_root_guid",
        type=int,
        default=1073741838,
        help="控件组库根节点 GUID（样本为 1073741838）。",
    )
    clone_component_groups_parser.add_argument(
        "--group-name",
        dest="group_name",
        required=True,
        help="写入控件组库后的组名称（例如：顶部按钮三连）。",
    )
    clone_component_groups_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并校验库内 parent/children 关系。",
    )
    clone_component_groups_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    clone_component_groups_parser.set_defaults(entrypoint=_command_ui_clone_component_groups_to_library)

    place_control_group_template_parser = ui_subparsers.add_parser(
        "place-control-group-template",
        help="将控件组模板(root guid)实例化到某个布局中（克隆模板 children 到组容器实例下）。",
    )
    place_control_group_template_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    place_control_group_template_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    place_control_group_template_parser.add_argument(
        "--template-root-guid",
        dest="template_root_guid",
        type=int,
        required=True,
        help="控件组模板 root GUID（来自 save-control-group-as-template 的 template_root_guid）。",
    )
    place_control_group_template_parser.add_argument(
        "--layout-guid",
        dest="layout_guid",
        type=int,
        required=True,
        help="要放置到的布局 root GUID。",
    )
    place_control_group_template_parser.add_argument(
        "--instance-name",
        dest="instance_name",
        required=True,
        help="实例名称（会写入组容器 record 的 name）。",
    )
    place_control_group_template_parser.add_argument(
        "--pc-pos",
        dest="pc_pos",
        default="",
        help="可选：电脑端画布坐标 x,y（左下角原点）。与 --pc-size 配对。",
    )
    place_control_group_template_parser.add_argument(
        "--pc-size",
        dest="pc_size",
        default="",
        help="可选：电脑端尺寸 w,h。与 --pc-pos 配对。",
    )
    place_control_group_template_parser.add_argument(
        "--mobile-pos",
        dest="mobile_pos",
        default="",
        help="可选：手机端画布坐标 x,y。与 --mobile-size 配对。",
    )
    place_control_group_template_parser.add_argument(
        "--mobile-size",
        dest="mobile_size",
        default="",
        help="可选：手机端尺寸 w,h。与 --mobile-pos 配对。",
    )
    place_control_group_template_parser.add_argument(
        "--layer",
        dest="layer",
        type=int,
        default=None,
        help="可选：写回 RectTransform layer。",
    )
    place_control_group_template_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并校验 instance/children parent 关系。",
    )
    place_control_group_template_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    place_control_group_template_parser.set_defaults(entrypoint=_command_ui_place_control_group_template)

    save_control_group_template_parser = ui_subparsers.add_parser(
        "save-control-group-as-template",
        help="将控件组库内的组容器保存为模板（生成模板 root，并写入互相引用的 meta blob）。",
    )
    save_control_group_template_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    save_control_group_template_parser.add_argument(
        "output_gil_file",
        help="输出 .gil 文件路径（建议不要覆盖原文件）",
    )
    save_control_group_template_parser.add_argument(
        "--library-root-guid",
        dest="library_root_guid",
        type=int,
        default=1073741838,
        help="控件组库根节点 GUID（样本为 1073741838）。",
    )
    save_control_group_template_parser.add_argument(
        "--group-guid",
        dest="group_guid",
        type=int,
        required=True,
        help="要保存为模板的组容器 GUID（例如：1073741842）。",
    )
    save_control_group_template_parser.add_argument(
        "--template-name",
        dest="template_name",
        required=True,
        help="模板名称（样本会把组名也改成该名字，例如：模板组合1）。",
    )
    save_control_group_template_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并校验模板 root/children 是否存在且 parent 正确。",
    )
    save_control_group_template_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    save_control_group_template_parser.set_defaults(entrypoint=_command_ui_save_control_group_as_template)

    set_control_layer_parser = ui_subparsers.add_parser(
        "set-control-layer",
        help="设置 UI 控件的“层级”字段（样本：505[2]/503/13/12/503）。",
    )
    set_control_layer_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    set_control_layer_parser.add_argument(
        "output_gil_file",
        help="输出 .gil 文件路径（建议不要覆盖原文件）",
    )
    set_control_layer_parser.add_argument(
        "--guids",
        dest="guids",
        required=True,
        help="控件 GUID 列表（逗号分隔），例如：1073741839,1073741840",
    )
    set_control_layer_parser.add_argument(
        "--layers",
        dest="layers",
        required=True,
        help="层级列表（逗号分隔，与 --guids 一一对应），例如：998,999",
    )
    set_control_layer_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并校验层级字段是否写入成功。",
    )
    set_control_layer_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    set_control_layer_parser.set_defaults(entrypoint=_command_ui_set_control_layer)

    clone_from_schema_parser = ui_subparsers.add_parser(
        "clone-record-from-schema",
        help="从 ui_schema_library 中按 schema_id 克隆一个 UI record，并插入到指定 parent_guid 下（可选改名/改坐标/改层级/注册到布局表）。",
    )
    clone_from_schema_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    clone_from_schema_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    clone_from_schema_parser.add_argument(
        "--schema-id",
        dest="schema_id",
        required=True,
        help="schema_id（40 位 sha1 hex），来自 ugc_file_tools/ui_schema_library/data/index.json",
    )
    clone_from_schema_parser.add_argument(
        "--parent-guid",
        dest="parent_guid",
        type=int,
        required=True,
        help="插入到哪个父节点（写入 record['504'] 并追加到 parent.children）。",
    )
    clone_from_schema_parser.add_argument(
        "--name",
        dest="name",
        default=None,
        help="可选：覆盖控件名称（写入 505[0]/12/501）。",
    )
    clone_from_schema_parser.add_argument(
        "--new-guid",
        dest="new_guid",
        type=int,
        default=None,
        help="可选：指定新 GUID（不填则自动分配）。",
    )
    clone_from_schema_parser.add_argument(
        "--pc-pos",
        dest="pc_pos",
        default="",
        help="可选：电脑端画布坐标（左下角原点），格式 'x,y'。与 --pc-size 成对使用。",
    )
    clone_from_schema_parser.add_argument(
        "--pc-size",
        dest="pc_size",
        default="",
        help="可选：电脑端尺寸，格式 'w,h'。与 --pc-pos 成对使用。",
    )
    clone_from_schema_parser.add_argument(
        "--mobile-pos",
        dest="mobile_pos",
        default="",
        help="可选：手机端画布坐标（左下角原点），格式 'x,y'。与 --mobile-size 成对使用。",
    )
    clone_from_schema_parser.add_argument(
        "--mobile-size",
        dest="mobile_size",
        default="",
        help="可选：手机端尺寸，格式 'w,h'。与 --mobile-pos 成对使用。",
    )
    clone_from_schema_parser.add_argument(
        "--layer",
        dest="layer",
        type=int,
        default=None,
        help="可选：写回 RectTransform layer 字段（505[2]/503/13/12/503）。",
    )
    clone_from_schema_parser.add_argument(
        "--register-layout-root-mode",
        dest="register_layout_root_mode",
        choices=["none", "append", "prepend"],
        default="none",
        help="可选：将 new_guid 注册到 4/9/501[0]：append=插入到库根前；prepend=插到开头；none=不注册。",
    )
    clone_from_schema_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并检查 new_guid record 是否存在。",
    )
    clone_from_schema_parser.add_argument(
        "--template-id-mode",
        dest="template_id_mode",
        choices=["keep", "auto", "set"],
        default="keep",
        help=(
            "可选：对 record 内的 meta blob（502/*/13 的 field_501(varint)）做重分配："
            "keep=不改；auto=自动分配新值；set=指定。"
            "注意该字段语义随 record 形态变化（可能是 template_root_guid 或 next 指针），仅在你确认语义时使用。"
        ),
    )
    clone_from_schema_parser.add_argument(
        "--template-id",
        dest="template_id",
        type=int,
        default=None,
        help="template_id_mode=set 时使用的 field_501 值（必须不与目标存档已有 GUID 冲突）。",
    )
    clone_from_schema_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    clone_from_schema_parser.set_defaults(entrypoint=_command_ui_clone_record_from_schema)

    place_control_parser = ui_subparsers.add_parser(
        "place-control-from-schemas",
        help=(
            "一键放置控件：克隆“模板库条目 record + 布局实例 record”，并自动分配/对齐 meta_blob13_field501。"
            "（注意：进度条不适用该语义，请改用 progressbars 子命令）"
        ),
    )
    place_control_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    place_control_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    place_control_parser.add_argument(
        "--template-entry-schema-id",
        dest="template_entry_schema_id",
        required=True,
        help="模板库条目的 schema_id（40 位 sha1 hex）。",
    )
    place_control_parser.add_argument(
        "--instance-schema-id",
        dest="instance_schema_id",
        required=True,
        help="布局实例的 schema_id（40 位 sha1 hex）。",
    )
    place_control_parser.add_argument(
        "--template-parent-guid",
        dest="template_parent_guid",
        type=int,
        required=True,
        help="模板库条目要插入到哪个父节点下（通常为控件组库根或某个组容器）。",
    )
    place_control_parser.add_argument(
        "--layout-guid",
        dest="layout_guid",
        type=int,
        required=True,
        help="实例要插入到哪个布局 root GUID 下。",
    )
    place_control_parser.add_argument(
        "--template-name",
        dest="template_name",
        default=None,
        help="可选：覆盖模板库条目名称（写入 505[0]/12/501）。",
    )
    place_control_parser.add_argument(
        "--instance-name",
        dest="instance_name",
        default=None,
        help="可选：覆盖实例名称（写入 505[0]/12/501）。",
    )
    place_control_parser.add_argument(
        "--pc-pos",
        dest="pc_pos",
        default="",
        help="可选：电脑端画布坐标（左下角原点），格式 'x,y'。与 --pc-size 成对使用。",
    )
    place_control_parser.add_argument(
        "--pc-size",
        dest="pc_size",
        default="",
        help="可选：电脑端尺寸，格式 'w,h'。与 --pc-pos 成对使用。",
    )
    place_control_parser.add_argument(
        "--mobile-pos",
        dest="mobile_pos",
        default="",
        help="可选：手机端画布坐标（左下角原点），格式 'x,y'。与 --mobile-size 成对使用。",
    )
    place_control_parser.add_argument(
        "--mobile-size",
        dest="mobile_size",
        default="",
        help="可选：手机端尺寸，格式 'w,h'。与 --mobile-pos 成对使用。",
    )
    place_control_parser.add_argument(
        "--template-id-mode",
        dest="template_id_mode",
        choices=["auto", "set"],
        default="auto",
        help="meta_blob13_field501 分配方式：auto=自动分配新值（默认）；set=指定。",
    )
    place_control_parser.add_argument(
        "--template-id",
        dest="template_id",
        type=int,
        default=None,
        help="template_id_mode=set 时使用的 field_501 值（必须不与目标存档已有 GUID 冲突）。",
    )
    place_control_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并检查新增 GUID 是否存在。",
    )
    place_control_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    place_control_parser.set_defaults(entrypoint=_command_ui_place_control_from_schemas)

    patch_controls_parser = ui_subparsers.add_parser(
        "patch-controls",
        help="按 JSON 批量写回控件属性（名称/可见性/位置大小/层级）。",
    )
    patch_controls_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    patch_controls_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    patch_controls_parser.add_argument(
        "--patch-json",
        dest="patch_json_file",
        required=True,
        help="patch JSON 文件路径：list[patch] 或 {'patches': list[patch]}。每个 patch 支持 guid/name/visible/layer/pc_pos/pc_size/mobile_pos/mobile_size。",
    )
    patch_controls_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump 并检查 patched guid 是否存在。",
    )
    patch_controls_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )
    patch_controls_parser.set_defaults(entrypoint=_command_ui_patch_controls)


