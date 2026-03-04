from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_ui_records(input_gil: Path) -> List[Any]:
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import dump_gil_to_raw_json_object
    from ugc_file_tools.ui.readable_dump import extract_ui_record_list

    dump = dump_gil_to_raw_json_object(Path(input_gil).resolve())
    return extract_ui_record_list(dump)


def _check(input_gil: Path) -> Dict[str, Any]:
    from ugc_file_tools.ui_patchers.web_ui.web_ui_import_textbox import choose_textbox_record_template
    from ugc_file_tools.ui_patchers.web_ui.web_ui_import_progressbar import choose_progressbar_record_template
    from ugc_file_tools.ui_patchers.web_ui.web_ui_import_item_display import choose_item_display_record_template

    records = _load_ui_records(input_gil)
    textbox = choose_textbox_record_template(records)
    progressbar = choose_progressbar_record_template(records)
    item_display = choose_item_display_record_template(records)

    def _guid(rec: Dict[str, Any] | None) -> int | None:
        if not isinstance(rec, dict):
            return None
        raw = rec.get("501")
        if isinstance(raw, int):
            return int(raw)
        if isinstance(raw, list) and raw and isinstance(raw[0], int):
            return int(raw[0])
        return None

    return {
        "input_gil": str(Path(input_gil).resolve()),
        "ui_record_count": len(records),
        "has_textbox_template": textbox is not None,
        "has_progressbar_template": progressbar is not None,
        "has_item_display_template": item_display is not None,
        "textbox_guid": _guid(textbox),
        "progressbar_guid": _guid(progressbar),
        "item_display_guid": _guid(item_display),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether a .gil contains clonable Web UI templates.")
    parser.add_argument("--input", required=True, help="Input .gil path")
    parser.add_argument("--require-textbox", action="store_true", help="Fail if no textbox template record found")
    parser.add_argument("--require-progressbar", action="store_true", help="Fail if no progressbar template record found")
    parser.add_argument("--require-item-display", action="store_true", help="Fail if no item_display template record found")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root / "private_extensions"))

    report = _check(Path(str(args.input)))
    for k in sorted(report.keys()):
        print(f"{k}: {report.get(k)}")
    if bool(args.require_textbox) and not bool(report.get("has_textbox_template")):
        raise RuntimeError("no textbox template record found")
    if bool(args.require_progressbar) and not bool(report.get("has_progressbar_template")):
        raise RuntimeError("no progressbar template record found")
    if bool(args.require_item_display) and not bool(report.get("has_item_display_template")):
        raise RuntimeError("no item_display template record found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

