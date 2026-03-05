from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from .file_io import _ensure_directory, _write_text_file


def _write_claude_if_missing(
    directory_path: Path,
    purpose_lines: Sequence[str],
    state_lines: Sequence[str],
    note_lines: Sequence[str],
) -> None:
    claude_file_path = directory_path / "claude.md"
    if claude_file_path.exists():
        return

    lines: List[str] = []
    lines.append("## 目录用途")
    for line in purpose_lines:
        lines.append(f"- {line}")
    lines.append("")

    lines.append("## 当前状态")
    for line in state_lines:
        lines.append(f"- {line}")
    lines.append("")

    lines.append("## 注意事项")
    for line in note_lines:
        lines.append(f"- {line}")
    lines.append("")

    _write_text_file(claude_file_path, "\n".join(lines))


def _ensure_claude_for_directory(directory_path: Path, purpose: str) -> None:
    claude_file_path = directory_path / "claude.md"
    if claude_file_path.exists():
        return
    _write_text_file(
        claude_file_path,
        "\n".join(
            [
                "## 目录用途",
                f"- {purpose}",
                "",
                "## 当前状态",
                "- 当前目录由解析脚本自动创建或补齐。",
                "",
                "## 注意事项",
                "- 不在此文件中记录修改历史，仅保持用途/状态/注意事项的实时描述。",
                "",
            ]
        ),
    )


def _build_package_skeleton(package_root: Path) -> None:
    """
    创建 Graph_Generater 的“项目存档”骨架目录，并为每个目录补齐 claude.md。
    """
    required_directories: List[Path] = [
        package_root,
        package_root / "原始解析",
        package_root / "原始解析" / "pyugc",
        package_root / "原始解析" / "dll",
        package_root / "原始解析" / "数据块",
        package_root / "原始解析" / "数据块" / "decoded_generic",
        package_root / "原始解析" / "数据块" / "decoded_generic" / "keyword_hits",
        package_root / "原始解析" / "数据块" / "decoded_dtype_type3",
        package_root / "原始解析" / "资源条目",
        package_root / "原始解析" / "资源条目" / "section15_unclassified",
        package_root / "元件库",
        package_root / "复合节点库",
        package_root / "实体摆放",
        package_root / "战斗预设",
        package_root / "战斗预设" / "单位状态",
        package_root / "战斗预设" / "技能",
        package_root / "战斗预设" / "投射物",
        package_root / "战斗预设" / "玩家模板",
        package_root / "战斗预设" / "职业",
        package_root / "战斗预设" / "道具",
        package_root / "管理配置",
        package_root / "管理配置" / "UI布局",
        package_root / "管理配置" / "UI控件模板",
        package_root / "管理配置" / "主镜头",
        package_root / "管理配置" / "信号",
        package_root / "管理配置" / "光源",
        package_root / "管理配置" / "关卡变量",
        package_root / "管理配置" / "关卡变量" / "自定义变量",
        package_root / "管理配置" / "关卡变量" / "自定义变量-局内存档变量",
        package_root / "管理配置" / "关卡设置",
        package_root / "管理配置" / "单位标签",
        package_root / "管理配置" / "商店模板",
        package_root / "管理配置" / "外围系统",
        package_root / "管理配置" / "多语言",
        package_root / "管理配置" / "实体布设组",
        package_root / "管理配置" / "局内存档管理",
        package_root / "管理配置" / "扫描标签",
        package_root / "管理配置" / "技能资源",
        package_root / "管理配置" / "护盾",
        package_root / "管理配置" / "结构体定义",
        package_root / "管理配置" / "结构体定义" / "基础结构体",
        package_root / "管理配置" / "结构体定义" / "局内存档结构体",
        package_root / "管理配置" / "聊天频道",
        package_root / "管理配置" / "背景音乐",
        package_root / "管理配置" / "装备数据",
        package_root / "管理配置" / "成长曲线",
        package_root / "管理配置" / "装备栏模板",
        package_root / "管理配置" / "计时器",
        package_root / "管理配置" / "货币背包",
        package_root / "管理配置" / "路径",
        package_root / "管理配置" / "预设点",
        package_root / "节点图",
        package_root / "节点图" / "client",
        package_root / "节点图" / "server",
        package_root / "节点图" / "原始解析",
    ]

    for directory_path in required_directories:
        _ensure_directory(directory_path)

    package_id = package_root.name
    _write_claude_if_missing(
        package_root,
        purpose_lines=[
            f"本目录是 `{package_id}` 项目的项目存档资源根，用于收纳从游戏真实存档解析导出的资源与原始数据。",
        ],
        state_lines=[
            "已创建资源骨架目录；解析导出内容位于 `原始解析/`，按需会进一步归类到各资源子目录。",
        ],
        note_lines=[
            "本项目以“尽可能多解析”为目标，除可结构化内容外，也会保留原始二进制块以便继续逆向。",
            "若后续要把节点图/变量等转换为可执行的 Graph_Generater Python DSL，需要再做语义映射与校验。",
        ],
    )

    _write_claude_if_missing(
        package_root / "原始解析",
        purpose_lines=[f"集中存放对 `{package_id}` 存档的原始 dump、二次解码产物与索引文件。"],
        state_lines=["本目录下内容可重复生成；不保证与 Graph_Generater 的业务 JSON/Python 结构完全一致。"],
        note_lines=["优先以“可追溯”为目标：任何导出的资源都应能回溯到原始 JSON 路径或二进制块索引。"],
    )

    for directory_path in required_directories:
        if directory_path == package_root:
            continue
        if (directory_path / "claude.md").exists():
            continue
        relative_path = directory_path.relative_to(package_root)
        _write_claude_if_missing(
            directory_path,
            purpose_lines=["该目录为项目存档资源骨架的一部分，用于承载对应类别的资源文件。"],
            state_lines=["当前由解析脚本自动创建；资源会逐步落盘到此处或其子目录。"],
            note_lines=["不在此文件中记录修改历史，仅保持用途/状态/注意事项的实时描述。"],
        )




def write_claude_if_missing(
    directory_path: Path,
    purpose_lines: Sequence[str],
    state_lines: Sequence[str],
    note_lines: Sequence[str],
) -> None:
    return _write_claude_if_missing(
        directory_path=Path(directory_path),
        purpose_lines=purpose_lines,
        state_lines=state_lines,
        note_lines=note_lines,
    )

