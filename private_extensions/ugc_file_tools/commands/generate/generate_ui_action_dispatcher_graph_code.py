from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    # 统一输出 ISO 时间戳（本地时区无关）；不做 try/except，依赖环境正常。
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 *.ui_actions.json 生成“UI 交互待绑定清单”（JSON 报告）。",
    )
    parser.add_argument(
        "--ui-actions",
        required=True,
        help="输入：app/runtime/cache/ui_artifacts/<package_id>/ui_actions/*.ui_actions.json（运行时缓存；不落资源库）",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="输出报告路径（.json）。推荐放到 ugc_file_tools/out/ 下。",
    )
    return parser.parse_args(argv)


def _ensure_dict(obj: Any, *, name: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise TypeError(f"{name} 必须为 dict")
    return obj


def _ensure_list(obj: Any, *, name: str) -> List[Any]:
    if not isinstance(obj, list):
        raise TypeError(f"{name} 必须为 list")
    return obj


def build_ui_actions_checklist_report(
    *,
    ui_actions_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    ui_actions_payload = json.loads(Path(ui_actions_path).read_text(encoding="utf-8"))
    payload = _ensure_dict(ui_actions_payload, name="ui_actions.json")
    click_actions = _ensure_list(payload.get("click_actions"), name="click_actions")

    entries: List[Dict[str, Any]] = []
    for item in click_actions:
        if not isinstance(item, dict):
            continue
        guid = item.get("guid")
        if not isinstance(guid, int):
            continue
        ui_key = str(item.get("ui_key") or "").strip()
        widget_name = str(item.get("widget_name") or "").strip()
        action_key = str(item.get("action_key") or "").strip()
        action_args = str(item.get("action_args") or "").strip()
        entries.append(
            {
                "guid": int(guid),
                "ui_key": ui_key,
                "widget_name": widget_name,
                "action_key": action_key,
                "action_args": action_args,
            }
        )

    entries.sort(key=lambda x: int(x.get("guid") or 0))

    # ---- stats / todos
    missing_ui_key = [e for e in entries if str(e.get("ui_key") or "") == ""]
    missing_action_key = [e for e in entries if str(e.get("action_key") or "") == ""]

    guid_to_entries: Dict[int, List[Dict[str, Any]]] = {}
    ui_key_to_entries: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        g = int(e["guid"])
        guid_to_entries.setdefault(g, []).append(e)
        k = str(e.get("ui_key") or "")
        if k != "":
            ui_key_to_entries.setdefault(k, []).append(e)

    duplicate_guids = {str(g): v for g, v in guid_to_entries.items() if len(v) >= 2}
    duplicate_ui_keys = {k: v for k, v in ui_key_to_entries.items() if len(v) >= 2}

    report: Dict[str, Any] = {
        "version": 1,
        "generated_at": _now_iso(),
        "source_ui_actions": str(ui_actions_path),
        "output": str(output_path),
        "entries_total": len(entries),
        "entries": entries,
        "stats": {
            "missing_ui_key_total": len(missing_ui_key),
            "missing_action_key_total": len(missing_action_key),
            "duplicate_guid_total": len(duplicate_guids),
            "duplicate_ui_key_total": len(duplicate_ui_keys),
        },
        "todos": {
            # 通常意味着：Workbench 侧未填 data-ui-key / 导出链路未生成 ui_key
            "missing_ui_key": missing_ui_key,
            # 通常意味着：你还没在 HTML 上填 data-ui-action / 或者你想完全在节点图里手写分发
            "missing_action_key": missing_action_key,
        },
        "duplicates": {
            "guid_to_entries": duplicate_guids,
            "ui_key_to_entries": duplicate_ui_keys,
        },
        "note": (
            "这是“待绑定清单”，不生成任何节点图。"
            "推荐在节点图中使用 ui_key: 占位符 + 运行时缓存 ui_guid_registry.json 进行校验/解析，避免硬编码 1073741xxx。"
        ),
    }
    return report


def main(argv: Optional[List[str]] = None) -> None:
    args = _parse_args(argv)
    ui_actions_path = Path(str(args.ui_actions or "")).resolve()
    if not ui_actions_path.is_file():
        raise FileNotFoundError(str(ui_actions_path))

    out_path = Path(str(args.out or "")).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() != ".json":
        raise ValueError(f"--out 必须为 .json 文件：{out_path}")

    report = build_ui_actions_checklist_report(
        ui_actions_path=ui_actions_path,
        output_path=out_path,
    )
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()

