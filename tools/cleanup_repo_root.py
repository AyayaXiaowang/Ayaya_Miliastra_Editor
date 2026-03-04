from __future__ import annotations

import dataclasses
import datetime as dt
import filecmp
import re
import shutil
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class MovePlan:
    source: Path
    dest: Path


@dataclasses.dataclass(frozen=True)
class CleanupResult:
    moved: tuple[MovePlan, ...]
    deleted: tuple[Path, ...]
    kept: tuple[Path, ...]
    artifact_root: Path


_KEEP_DIR_NAMES = frozenset(
    {
        ".git",
        ".github",
        ".cursor",
        "app",
        "engine",
        "plugins",
        "assets",
        "docs",
        "tests",
        "tools",
        "projects",
        "release",
        "private_extensions",
    }
)

_DELETE_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache"})

_MOVE_DIR_PATTERNS = (
    re.compile(r".*__report$"),
    re.compile(r".*__report_.*$"),
    re.compile(r".*_report$"),
    re.compile(r"^out$"),
    re.compile(r"^\.migration_logs$"),
    re.compile(r"^ui_guid_registry_history$"),
    re.compile(r"^probe_.*__dump$"),
    re.compile(r"^_tmp_.*$"),
)

_MOVE_FILE_PATTERNS = (
    re.compile(r"^_tmp_.*"),
    re.compile(r"^\.tmp_.*"),
    re.compile(r"^__tmp_.*"),
    re.compile(r"^base_scan_.*\.json$"),
    re.compile(r"^diff_.*\.json$"),
    re.compile(r"^export_scan_output_.*\.json$"),
    re.compile(r"^inspect_signals_.*\.(index|issues)\.json$"),
    re.compile(r"^gil_payload_diff_.*\.(summary\.md|report\.json)$"),
    re.compile(r"^gia_vs_gil_.*\.(server\.)?json$"),
    re.compile(r"^calib_.*\.json$"),
    re.compile(r"^empty_base_.*\.json$"),
    re.compile(r"^exported_.*\.json$"),
    re.compile(r"^lamp_instances_.*\.json$"),
    re.compile(r"^ref_one_.*\.json$"),
    re.compile(r"^node\d+_.*\.json$"),
    re.compile(r"^probe_.*\.json$"),
    re.compile(r"^tmp_selection_.*\.json$"),
    re.compile(r"^server_.*\.graph_model\.json$"),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _is_match(name: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.fullmatch(name) for p in patterns)


def _same_text_file(a: Path, b: Path) -> bool:
    try:
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def _plan_for_entry(entry: Path, artifact_root: Path) -> tuple[str, MovePlan | None]:
    name = entry.name
    if entry.is_dir():
        if name in _KEEP_DIR_NAMES:
            return ("keep", None)
        if name in _DELETE_DIR_NAMES:
            return ("delete", None)
        if _is_match(name, _MOVE_DIR_PATTERNS) or name.endswith("_report"):
            dest = artifact_root / "moved_dirs" / name
            return ("move", MovePlan(entry, dest))
        if name.startswith("direct_") and name.endswith("__report"):
            dest = artifact_root / "moved_dirs" / name
            return ("move", MovePlan(entry, dest))
        if name.startswith("probe_") and ("__report" in name or name.endswith("__dump")):
            dest = artifact_root / "moved_dirs" / name
            return ("move", MovePlan(entry, dest))
        if name.startswith("ui_route_diff_") and name.endswith("__report"):
            dest = artifact_root / "moved_dirs" / name
            return ("move", MovePlan(entry, dest))
        return ("keep", None)

    if name == "claude.md":
        upper = entry.with_name("CLAUDE.md")
        if upper.exists() and _same_text_file(entry, upper):
            return ("delete", None)
        dest = artifact_root / "quarantine_files" / name
        return ("move", MovePlan(entry, dest))

    if name == "WRITE_TEST.md":
        return ("delete", None)

    if _is_match(name, _MOVE_FILE_PATTERNS):
        dest = artifact_root / "moved_files" / name
        return ("move", MovePlan(entry, dest))

    return ("keep", None)


def _move(plan: MovePlan) -> None:
    if plan.dest.exists():
        raise FileExistsError(f"destination exists: {plan.dest}")
    _ensure_dir(plan.dest.parent)
    shutil.move(str(plan.source), str(plan.dest))


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def _write_text_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    _ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def _ensure_tmp_claude(tmp_dir: Path) -> None:
    content = "\n".join(
        [
            "# tmp（临时产物与任务清单）",
            "",
            "## 目录用途",
            "",
            "- 存放一次性/可清理的临时产物、对比报告、隔离区（quarantine）与任务清单。",
            "- `agent_todos/`：任务清单落盘目录（用于多步任务的可追溯执行）。",
            "",
            "## 当前状态",
            "",
            "- 本目录可能包含调试/脚本运行生成的一次性产物；默认可清理。",
            "",
            "## 注意事项",
            "",
            "- 需要长期保存的诊断证据链应写入 `docs/diagnostics/`。",
            "- 本文件仅描述“目录用途 / 当前状态 / 注意事项”，不记录修改历史。",
            "",
        ]
    )
    _write_text_if_missing(tmp_dir / "CLAUDE.md", content)

    agent_todos = tmp_dir / "agent_todos"
    agent_todos_content = "\n".join(
        [
            "# tmp/agent_todos（任务清单落盘）",
            "",
            "## 目录用途",
            "",
            "- 存放代理/脚本执行任务的可勾选清单（便于回溯与复现）。",
            "",
            "## 当前状态",
            "",
            "- 本目录可为空；由任务触发创建与更新。",
            "",
            "## 注意事项",
            "",
            "- 清单应包含：目标/非目标、约束、验收标准与可执行命令。",
            "- 本文件仅描述“目录用途 / 当前状态 / 注意事项”，不记录修改历史。",
            "",
        ]
    )
    _write_text_if_missing(agent_todos / "CLAUDE.md", agent_todos_content)


def _write_root_cleanup_todo(tmp_dir: Path, stamp: str) -> Path:
    todo_path = tmp_dir / "agent_todos" / f"repo_root_cleanup_{stamp}.md"
    content = "\n".join(
        [
            "# 仓库根目录清理任务",
            "",
            "## 目标",
            "",
            "- 清理仓库根目录的一次性调试产物/缓存/报告目录，使根目录只保留长期入口与配置文件。",
            "",
            "## 非目标",
            "",
            "- 不删除源码与文档主目录（如 `app/engine/plugins/assets/docs/tests/tools`）。",
            "- 不触碰 `.git/` 与 `.cursor/`。",
            "",
            "## 约束",
            "",
            "- 不使用 git 命令判断 tracked/untracked（仅按规则识别临时产物）。",
            "- 失败必须显式抛出（不静默跳过、不中途吞错）。",
            "",
            "## 验收标准",
            "",
            "- 根目录中不再出现 `*_report/`、`out/`、`__pycache__/`、`.pytest_cache/` 以及 `_tmp_*` 等临时条目。",
            "- 所有被移动的条目集中到 `tmp/artifacts/<run_stamp>/` 下可追溯存放。",
            "- `docs/diagnostics/repo_root_cleanup.md` 记录本次清理的 moved/deleted/kept 清单与 artifact 路径。",
            "",
        ]
    )
    _ensure_dir(todo_path.parent)
    todo_path.write_text(content, encoding="utf-8")
    return todo_path


def _write_report(report_path: Path, result: CleanupResult) -> None:
    def fmt(p: Path) -> str:
        try:
            return p.relative_to(_repo_root()).as_posix()
        except ValueError:
            return p.as_posix()

    lines: list[str] = []
    lines.extend(["# 仓库根目录清理报告", ""])
    lines.extend([f"- 运行时间(UTC)：`{result.artifact_root.name}`", ""])
    lines.extend([f"- 归档目录：`{fmt(result.artifact_root)}`", ""])

    lines.extend(["## 删除（缓存/可再生）", ""])
    if result.deleted:
        lines.extend([f"- `{fmt(p)}`" for p in result.deleted])
    else:
        lines.append("- （无）")
    lines.append("")

    lines.extend(["## 移动（一次性产物归档到 tmp/）", ""])
    if result.moved:
        for mp in result.moved:
            lines.append(f"- `{fmt(mp.source)}` -> `{fmt(mp.dest)}`")
    else:
        lines.append("- （无）")
    lines.append("")

    lines.extend(["## 保留（疑似长期入口/未匹配规则）", ""])
    if result.kept:
        lines.extend([f"- `{fmt(p)}`" for p in result.kept])
    else:
        lines.append("- （无）")
    lines.append("")

    _ensure_dir(report_path.parent)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def cleanup_repo_root(*, repo_root: Path, artifact_root: Path) -> CleanupResult:
    moved: list[MovePlan] = []
    deleted: list[Path] = []
    kept: list[Path] = []

    for entry in sorted(repo_root.iterdir(), key=lambda p: p.name.lower()):
        action, plan = _plan_for_entry(entry, artifact_root)
        if action == "keep":
            kept.append(entry)
            continue
        if action == "delete":
            _delete_path(entry)
            deleted.append(entry)
            continue
        if action == "move" and plan is not None:
            _move(plan)
            moved.append(plan)
            continue
        raise RuntimeError(f"unexpected plan for: {entry} ({action}, {plan})")

    return CleanupResult(
        moved=tuple(moved),
        deleted=tuple(deleted),
        kept=tuple(kept),
        artifact_root=artifact_root,
    )


def main() -> int:
    repo_root = _repo_root()
    stamp = _utc_stamp()
    artifact_root = repo_root / "tmp" / "artifacts" / f"repo_root_cleanup_{stamp}"

    _ensure_tmp_claude(repo_root / "tmp")
    todo_path = _write_root_cleanup_todo(repo_root / "tmp", stamp)

    result = cleanup_repo_root(repo_root=repo_root, artifact_root=artifact_root)
    _write_report(repo_root / "docs" / "diagnostics" / "repo_root_cleanup.md", result)

    print(f"artifact_root={artifact_root}")
    print(f"todo={todo_path}")
    print(f"moved={len(result.moved)} deleted={len(result.deleted)} kept={len(result.kept)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

