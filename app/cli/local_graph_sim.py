from __future__ import annotations

"""
本地测试入口（CLI）。

目标：
- 将节点图源码编译为可运行类（runtime cache），并用 Mock `GameRuntime` 驱动事件/信号；
- 通过浏览器承载 UI HTML，支持“点击注入 -> 图逻辑执行 -> UI patch 回显”（MVP）。
"""

import argparse
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

if not __package__ and not getattr(sys, "frozen", False):
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m app.cli.local_graph_sim --help\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

from engine.utils.logging.console_sanitizer import install_ascii_safe_print
from engine.utils.logging.logger import log_warn, log_info
from engine.utils.workspace import resolve_workspace_root
from engine.resources.atomic_json import atomic_write_json

from app.runtime.services.local_graph_simulator import build_local_graph_sim_session
from app.runtime.services.local_graph_sim_server import LocalGraphSimServer, LocalGraphSimServerConfig
from app.runtime.services.local_graph_simulator import GraphMountSpec


SAFETY_NOTICE = (
    "【安全声明】小王千星工坊（Ayaya_Miliastra_Editor）仅用于离线教学、代码模拟与节点图研究。"
    "不得将任何脚本、自动化流程或鼠标指令连接至官方《原神》客户端或服务器，"
    "否则可能触发账号封禁、奖励回收等处罚。"
)


def _open_url_or_raise(*, url: str) -> None:
    url_text = str(url or "").strip()
    if not url_text:
        raise ValueError("URL 为空")
    opened = webbrowser.open(url_text, new=2)
    if opened:
        return
    if hasattr(os, "startfile"):
        os.startfile(url_text)  # type: ignore[attr-defined]
        return
    raise RuntimeError(f"无法打开浏览器: {url_text}")


def _parse_kv_list(raw_items: Iterable[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        if "=" not in text:
            raise ValueError(f"参数必须是 key=value 形式: {text!r}")
        key, value = text.split("=", 1)
        k = key.strip()
        v = value.strip()
        if not k:
            raise ValueError(f"参数 key 不能为空: {text!r}")
        if v.lower() in {"true", "false"}:
            out[k] = v.lower() == "true"
            continue
        if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
            out[k] = int(v)
            continue
        out[k] = v
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local_graph_sim",
        description="节点图 + UI 本地测试（信号/交互/显隐回显）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--root",
        dest="workspace_root",
        default="",
        help="工作区根目录（默认：自动推断仓库根目录）",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="启动本地 HTTP server 并打开浏览器预览")
    serve.add_argument("--graph", required=True, help="主图节点图源码文件路径（.py）")
    serve.add_argument("--extra-graph", action="append", default=[], help="额外挂载节点图源码文件路径（.py，可重复）")
    serve.add_argument(
        "--extra-owner",
        action="append",
        default=[],
        help="额外挂载图 owner 实体名（与 --extra-graph 一一对应；可少于图数量，缺省使用 --owner）",
    )
    serve.add_argument("--ui-html", required=True, help="入口页面 UI HTML 源码文件路径（.html）")
    serve.add_argument("--host", default="127.0.0.1", help="监听 host（默认 127.0.0.1）")
    serve.add_argument("--port", type=int, default=0, help="监听端口（默认自动选择）")
    serve.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    serve.add_argument(
        "--ready-file",
        default="",
        help="（供 UI 父进程使用）server 启动后将 {url,port,pid} 写入该 JSON 文件路径；为空则不写。",
    )
    serve.add_argument("--owner", default="自身实体", help="图 owner 实体名称（默认：自身实体）")
    serve.add_argument("--player", default="玩家1", help="UI 点击事件源实体名称（默认：玩家1）")
    serve.add_argument("--present-players", type=int, default=1, help="在场玩家数量（默认 1）")
    serve.add_argument("--auto-signal-id", default="", help="server 启动后自动发送的信号 ID（可选）")
    serve.add_argument("--auto-param", action="append", default=[], help="auto-signal 参数（key=value，可重复）")

    click = subparsers.add_parser("click", help="一次性注入 UI 点击事件并打印 UI patches（不启动 server）")
    click.add_argument("--graph", required=True, help="主图节点图源码文件路径（.py）")
    click.add_argument("--extra-graph", action="append", default=[], help="额外挂载节点图源码文件路径（.py，可重复）")
    click.add_argument(
        "--extra-owner",
        action="append",
        default=[],
        help="额外挂载图 owner 实体名（与 --extra-graph 一一对应；可少于图数量，缺省使用 --owner）",
    )
    click.add_argument("--ui-key", required=True, help="HTML data-ui-key（例如 btn_allow / btn_exit）")
    click.add_argument("--state-group", default="", help="HTML data-ui-state-group（可选）")
    click.add_argument("--state", default="", help="HTML data-ui-state（可选）")
    click.add_argument("--owner", default="自身实体", help="图 owner 实体名称（默认：自身实体）")
    click.add_argument("--player", default="玩家1", help="UI 点击事件源实体名称（默认：玩家1）")
    click.add_argument("--present-players", type=int, default=1, help="在场玩家数量（默认 1）")
    click.add_argument("--dump-state", action="store_true", help="同时输出实体/变量快照（JSON）")

    emit = subparsers.add_parser("emit-signal", help="一次性发送信号并打印 UI patches（不启动 server）")
    emit.add_argument("--graph", required=True, help="主图节点图源码文件路径（.py）")
    emit.add_argument("--extra-graph", action="append", default=[], help="额外挂载节点图源码文件路径（.py，可重复）")
    emit.add_argument(
        "--extra-owner",
        action="append",
        default=[],
        help="额外挂载图 owner 实体名（与 --extra-graph 一一对应；可少于图数量，缺省使用 --owner）",
    )
    emit.add_argument("--signal-id", required=True, help="信号 ID（例如 signal_level_lobby_start_level）")
    emit.add_argument("--param", action="append", default=[], help="信号参数（key=value，可重复）")
    emit.add_argument("--owner", default="自身实体", help="图 owner 实体名称（默认：自身实体）")
    emit.add_argument("--player", default="玩家1", help="UI 点击事件源实体名称（默认：玩家1）")
    emit.add_argument("--present-players", type=int, default=1, help="在场玩家数量（默认 1）")
    emit.add_argument("--dump-state", action="store_true", help="同时输出实体/变量快照（JSON）")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    install_ascii_safe_print()
    log_warn(SAFETY_NOTICE)

    parser = _build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    workspace_root_text = str(getattr(args, "workspace_root", "") or "").strip()
    workspace_root = resolve_workspace_root(workspace_root_text) if workspace_root_text else resolve_workspace_root(start_paths=[Path(__file__).resolve()])

    command = str(getattr(args, "command", "") or "").strip()

    if command == "serve":
        graph_file = Path(str(args.graph)).resolve()
        ui_html = Path(str(args.ui_html)).resolve()
        auto_params = _parse_kv_list(list(args.auto_param or []))
        extra_graphs = [str(x) for x in list(getattr(args, "extra_graph", []) or [])]
        extra_owners = [str(x) for x in list(getattr(args, "extra_owner", []) or [])]
        owner_fallback = str(args.owner)
        extra_mounts: list[GraphMountSpec] = []
        for i, g in enumerate(extra_graphs):
            owner = extra_owners[i] if i < len(extra_owners) and str(extra_owners[i]).strip() else owner_fallback
            extra_mounts.append(GraphMountSpec(graph_code_file=Path(str(g)).resolve(), owner_entity_name=str(owner)))
        cfg = LocalGraphSimServerConfig(
            workspace_root=workspace_root,
            graph_code_file=graph_file,
            ui_html_file=ui_html,
            owner_entity_name=str(args.owner),
            player_entity_name=str(args.player),
            present_player_count=int(args.present_players),
            host=str(args.host),
            port=int(args.port),
            auto_emit_signal_id=str(args.auto_signal_id),
            auto_emit_signal_params=auto_params,
            extra_graph_mounts=extra_mounts,
        )
        server = LocalGraphSimServer(cfg)
        server.start()
        url = server.get_url()
        log_info("[local_sim] server 已启动：{}", url)

        ready_file_text = str(getattr(args, "ready_file", "") or "").strip()
        if ready_file_text:
            ready_file = Path(ready_file_text).resolve()
            atomic_write_json(
                ready_file,
                {
                    "ok": True,
                    "url": str(url),
                    "host": str(cfg.host),
                    "port": int(server.port),
                    "pid": int(os.getpid()),
                    "graph": str(graph_file),
                    "ui_html": str(ui_html),
                },
            )

        if not bool(args.no_open):
            # 默认打开“扁平化预览”（monitor.html 会读取 `?flatten=1` 并自动勾选开关）
            open_url = url.rstrip("/") + "/?flatten=1" if "?" not in url else url
            _open_url_or_raise(url=open_url)
        # 阻塞主线程（后台线程提供 HTTP 服务）
        while True:
            time.sleep(3600.0)

    if command == "click":
        extra_graphs = [str(x) for x in list(getattr(args, "extra_graph", []) or [])]
        extra_owners = [str(x) for x in list(getattr(args, "extra_owner", []) or [])]
        owner_fallback = str(args.owner)
        extra_mounts: list[GraphMountSpec] = []
        for i, g in enumerate(extra_graphs):
            owner = extra_owners[i] if i < len(extra_owners) and str(extra_owners[i]).strip() else owner_fallback
            extra_mounts.append(GraphMountSpec(graph_code_file=Path(str(g)).resolve(), owner_entity_name=str(owner)))
        session = build_local_graph_sim_session(
            workspace_root=workspace_root,
            graph_code_file=Path(str(args.graph)).resolve(),
            owner_entity_name=str(args.owner),
            player_entity_name=str(args.player),
            present_player_count=int(args.present_players),
            extra_graph_mounts=extra_mounts,
        )
        patches = session.trigger_ui_click(
            data_ui_key=str(args.ui_key),
            data_ui_state_group=str(args.state_group),
            data_ui_state=str(args.state),
        )
        if bool(getattr(args, "dump_state", False)):
            print(json_dumps({"patches": patches, "state": _build_state_snapshot(session)}))
        else:
            print(json_dumps(patches))
        return 0

    if command == "emit-signal":
        extra_graphs = [str(x) for x in list(getattr(args, "extra_graph", []) or [])]
        extra_owners = [str(x) for x in list(getattr(args, "extra_owner", []) or [])]
        owner_fallback = str(args.owner)
        extra_mounts: list[GraphMountSpec] = []
        for i, g in enumerate(extra_graphs):
            owner = extra_owners[i] if i < len(extra_owners) and str(extra_owners[i]).strip() else owner_fallback
            extra_mounts.append(GraphMountSpec(graph_code_file=Path(str(g)).resolve(), owner_entity_name=str(owner)))
        session = build_local_graph_sim_session(
            workspace_root=workspace_root,
            graph_code_file=Path(str(args.graph)).resolve(),
            owner_entity_name=str(args.owner),
            player_entity_name=str(args.player),
            present_player_count=int(args.present_players),
            extra_graph_mounts=extra_mounts,
        )
        params = _parse_kv_list(list(args.param or []))
        patches = session.emit_signal(signal_id=str(args.signal_id), params=params)
        if bool(getattr(args, "dump_state", False)):
            print(json_dumps({"patches": patches, "state": _build_state_snapshot(session)}))
        else:
            print(json_dumps(patches))
        return 0

    raise RuntimeError(f"未知 command: {command}")


def json_dumps(obj: object) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


def _build_state_snapshot(session) -> dict[str, Any]:
    game = session.game
    entities: list[dict[str, Any]] = []
    for entity_id, ent in getattr(game, "entities", {}).items():
        entities.append(
            {
                "entity_id": str(entity_id),
                "name": str(getattr(ent, "name", "")),
                "position": list(getattr(ent, "position", [])),
                "rotation": list(getattr(ent, "rotation", [])),
            }
        )
    entities.sort(key=lambda x: (x.get("name", ""), x.get("entity_id", "")))

    attached_graphs: dict[str, list[str]] = {}
    raw_attached = getattr(game, "attached_graphs", None)
    if isinstance(raw_attached, dict):
        for entity_id, graphs in raw_attached.items():
            items: list[str] = []
            if isinstance(graphs, list):
                for inst in graphs:
                    items.append(str(getattr(getattr(inst, "__class__", None), "__name__", "Graph")))
            attached_graphs[str(entity_id)] = items

    mounted_graphs_payload: list[dict[str, Any]] = []
    mounted = getattr(session, "mounted_graphs", None)
    if isinstance(mounted, list) and mounted:
        for g in mounted:
            mounted_graphs_payload.append(
                {
                    "graph_name": str(getattr(g, "graph_name", "")),
                    "graph_type": str(getattr(g, "graph_type", "")),
                    "graph_code_file": str(getattr(g, "graph_code_file", "")),
                    "owner_entity_id": str(getattr(g, "owner_entity_id", "")),
                    "owner_entity_name": str(getattr(g, "owner_entity_name", "")),
                }
            )

    ui_active_groups_by_player = getattr(game, "ui_active_groups_by_player", {}) or {}
    if isinstance(ui_active_groups_by_player, dict):
        ui_active_groups_by_player = {k: sorted(list(v)) for k, v in ui_active_groups_by_player.items()}

    return {
        "entities": entities,
        "custom_variables": getattr(game, "custom_variables", {}),
        "graph_variables": getattr(game, "graph_variables", {}),
        "local_variables": getattr(game, "local_variables", {}),
        "attached_graphs": attached_graphs,
        "mounted_graphs": mounted_graphs_payload,
        "ui_current_layout_by_player": getattr(game, "ui_current_layout_by_player", {}),
        "ui_widget_state_by_player": getattr(game, "ui_widget_state_by_player", {}),
        "ui_active_groups_by_player": ui_active_groups_by_player,
    }


if __name__ == "__main__":
    raise SystemExit(main())

