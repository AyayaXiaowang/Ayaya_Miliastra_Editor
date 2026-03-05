"""PackageIndexManager：项目创建/复制/克隆相关职责拆分。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.resources.resource_manager import ResourceManager

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.resources.atomic_json import atomic_write_json
from engine.utils.name_utils import generate_unique_name


class PackageIndexCloneMixin:
    # 类型检查用：mixin 依赖最终组合类（PackageIndexManager）提供的字段与方法。
    # 运行时这些成员由其它 mixin / manager 组合提供，这里仅用于消除静态类型检查噪音。
    if TYPE_CHECKING:
        _packages_root_dir: Path
        resource_manager: "ResourceManager"

        TEMPLATE_PACKAGE_DIRNAME: str
        _CLONE_IGNORE_PATTERNS: tuple[str, ...]

        def _sanitize_package_filename(self, name: str) -> str: ...

        @staticmethod
        def _is_path_under(root_dir: Path, file_path: Path) -> bool: ...

        @staticmethod
        def _resolve_instance_dir(package_root_dir: Path) -> Path: ...

    @staticmethod
    def _write_text_if_not_exists(file_path: Path, content: str) -> None:
        if file_path.exists():
            return
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def _ensure_dir_with_docs(self, dir_path: Path, *, purpose: str) -> None:
        """确保项目存档内目录存在，并写入 claude.md + 示例.md（仅当文件不存在时）。

        注意：示例文件使用 .md，避免被资源索引/代码 Schema 误扫描为真实资源。
        """
        dir_path.mkdir(parents=True, exist_ok=True)

        self._write_text_if_not_exists(
            dir_path / "claude.md",
            "\n".join(
                [
                    "## 目录用途",
                    purpose.strip(),
                    "",
                    "## 当前状态",
                    "新建目录骨架（空目录 + 示例文件），用于指导放置资源与便于版本管理跟踪目录结构。",
                    "",
                    "## 注意事项",
                    "- 本目录下的 `示例.md` 为占位说明文件，不会被资源系统扫描为资源。",
                    "- 请将真实资源文件放在本目录下的正确子目录中（如 .json/.py），并保持 ID 唯一。",
                    "",
                    "---",
                    "注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。",
                    "",
                ]
            ),
        )
        self._write_text_if_not_exists(
            dir_path / "示例.md",
            "\n".join(
                [
                    "## 示例文件（占位）",
                    "",
                    "该文件用于：",
                    "- 避免空目录在版本管理中丢失",
                    "- 提示该目录应放置的资源类型与基本约定",
                    "",
                    "你可以删除本文件；也可以保留作为团队约定说明。",
                    "",
                ]
            ),
        )

    @staticmethod
    def _create_directory_junction(link_dir: Path, *, target_dir: Path) -> None:
        """创建目录 Junction（Windows）或目录符号链接（非 Windows）。

        约定：本项目的“共享文档”默认使用 Junction，以避免 Windows 下创建 symlink 需要额外权限。
        """
        if link_dir.exists():
            # 若目标已存在但不是“链接类目录”，直接报错，避免用户误以为已完成零复制共享。
            if os.name == "nt":
                if not link_dir.is_dir():
                    raise ValueError(f"创建 Junction 失败：目标路径已存在且不是目录：{link_dir}")

                def _is_windows_reparse_point(path: Path) -> bool:
                    import ctypes
                    from ctypes import wintypes

                    FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
                    INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

                    get_attrs = ctypes.windll.kernel32.GetFileAttributesW
                    get_attrs.argtypes = [wintypes.LPCWSTR]
                    get_attrs.restype = wintypes.DWORD

                    attrs = int(get_attrs(str(path)))
                    if attrs == INVALID_FILE_ATTRIBUTES:
                        return False
                    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)

                if not _is_windows_reparse_point(link_dir):
                    raise ValueError(
                        "创建 Junction 失败：目标目录已存在但不是 Junction/符号链接：\n"
                        f"- 路径: {link_dir}\n"
                        "请先删除或改名该目录，再重试。"
                    )
            return
        link_dir.parent.mkdir(parents=True, exist_ok=True)
        target_dir.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            # 重要：不要用 cmd/mklink 直接创建 —— cmd 在 Unicode 路径下经常因 codepage 导致参数解析失败。
            # 这里统一调用 PowerShell 的 New-Item -ItemType Junction，支持中文路径且无需管理员权限。
            pwsh_exe = shutil.which("pwsh")
            if pwsh_exe:
                # -CommandWithArgs 会把后续参数填充到 $args，避免 -Command “吞掉后续参数”的行为
                subprocess.run(
                    [
                        pwsh_exe,
                        "-NoProfile",
                        "-NonInteractive",
                        "-CommandWithArgs",
                        "New-Item -ItemType Junction -Path $args[0] -Target $args[1] | Out-Null",
                        str(link_dir),
                        str(target_dir),
                    ],
                    check=True,
                )
                return

            powershell_exe = shutil.which("powershell") or shutil.which("powershell.exe")
            if powershell_exe:
                link_text = str(link_dir).replace("'", "''")
                target_text = str(target_dir).replace("'", "''")
                command = (
                    f"New-Item -ItemType Junction -Path '{link_text}' -Target '{target_text}' | Out-Null"
                )
                subprocess.run(
                    [
                        powershell_exe,
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        command,
                    ],
                    check=True,
                )
                return

            raise ValueError("创建 Junction 失败：未找到 PowerShell 可执行文件（pwsh/powershell）。")
            return

        link_dir.symlink_to(target_dir, target_is_directory=True)

    def _ensure_shared_docs_link_for_package(self, package_root_dir: Path) -> None:
        """确保项目存档内存在指向共享文档根的 Junction：

        - <package_root>/文档/ 目录用于存放项目特有说明；
        - <package_root>/文档/共享文档 作为 Junction 指向 assets/资源库/共享/文档，实现零复制共享。
        """
        docs_dir = package_root_dir / "文档"
        self._ensure_dir_with_docs(docs_dir, purpose="项目文档目录（项目特有说明 + 共享文档入口）。")

        shared_docs_root = self._packages_root_dir.parent / "共享" / "文档"
        link_dir = docs_dir / "共享文档"
        self._create_directory_junction(link_dir, target_dir=shared_docs_root)

    def ensure_shared_docs_link(self, package_id: str) -> None:
        """为指定项目存档补齐共享文档 Junction（用于存量项目的一键修复/补齐）。"""
        package_id_text = str(package_id or "").strip()
        if not package_id_text:
            raise ValueError("package_id 不能为空")
        package_root_dir = self._packages_root_dir / package_id_text
        if not package_root_dir.exists() or not package_root_dir.is_dir():
            raise ValueError(f"未找到项目存档目录：{package_root_dir}")
        self._ensure_shared_docs_link_for_package(package_root_dir)

    def ensure_shared_docs_links_for_all_packages(self) -> int:
        """为所有项目存档补齐共享文档 Junction，返回处理的项目数量。"""
        packages_root = self._packages_root_dir
        if not packages_root.exists() or not packages_root.is_dir():
            return 0
        count = 0
        for package_dir in sorted([path for path in packages_root.iterdir() if path.is_dir()], key=lambda p: p.name.casefold()):
            self._ensure_shared_docs_link_for_package(package_dir)
            count += 1
        return count

    def ensure_package_directory_structure(self, package_id: str) -> None:
        """为指定项目存档补齐“目录骨架”（仅创建缺失目录，不复制模板文件）。

        背景：
        - 新建项目存档使用“复制示例项目模板”的方式，因此天然具备完整目录结构；
        - 导入/解析型流程（例如从 .gil 解析导入）通常只会创建“有文件落盘的目录”，会导致空目录缺失；
        - 目录缺失会影响 UI 文件夹树展示、团队约定与后续资源落点（例如节点图分类目录）。

        设计：
        - 以 `assets/资源库/项目存档/示例项目模板/` 的目录层级作为结构真源；
        - 将模板中的目录结构镜像到目标项目存档中（仅创建目录，不拷贝任何资源文件）。

        注意：
        - 会跳过 `__pycache__` 等运行期产物目录；
        - 会跳过 `文档/共享文档`（Junction/符号链接），避免破坏“零复制共享”语义。
        """
        package_id_text = str(package_id or "").strip()
        if not package_id_text:
            raise ValueError("package_id 不能为空")

        package_root_dir = self._packages_root_dir / package_id_text
        if not package_root_dir.exists() or not package_root_dir.is_dir():
            raise ValueError(f"未找到项目存档目录：{package_root_dir}")

        template_root_dir = self._packages_root_dir / self.TEMPLATE_PACKAGE_DIRNAME
        if not template_root_dir.exists() or not template_root_dir.is_dir():
            # 兜底：模板缺失时，至少补齐常用资源根目录与节点图分类目录
            self._ensure_node_graph_category_dirs_for_package(package_root_dir)
            (package_root_dir / "复合节点库").mkdir(parents=True, exist_ok=True)
            (package_root_dir / "文档").mkdir(parents=True, exist_ok=True)
            for resource_type in ResourceType:
                if resource_type == ResourceType.GRAPH:
                    continue
                (package_root_dir / resource_type.value).mkdir(parents=True, exist_ok=True)
            return

        ignore_dirnames = {"__pycache__", "共享文档"}
        template_root_resolved = template_root_dir.resolve()
        package_root_resolved = package_root_dir.resolve()

        for dirpath, dirnames, _filenames in os.walk(template_root_resolved):
            dirnames[:] = [name for name in dirnames if name not in ignore_dirnames]
            current_dir = Path(dirpath)
            rel_dir = current_dir.relative_to(template_root_resolved)
            if str(rel_dir) == ".":
                continue
            if any(part in ignore_dirnames for part in rel_dir.parts):
                continue

            target_dir = package_root_resolved / rel_dir
            target_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_new_package_directory_skeleton(self, package_root_dir: Path) -> None:
        """为“新建项目存档”创建完整目录骨架，并在每个目录下写入示例文件。"""
        # 1) 包根目录文档
        package_id = package_root_dir.name
        self._ensure_dir_with_docs(
            package_root_dir,
            purpose=f"项目存档根目录（package_id=`{package_id}`），用于承载该项目存档独占资源。",
        )

        # 1.1) 文档目录：项目特有文档 + 共享文档入口
        self._ensure_shared_docs_link_for_package(package_root_dir)

        # 2) 基于 ResourceType 枚举创建标准资源目录
        self._ensure_dir_with_docs(
            package_root_dir / "战斗预设",
            purpose="战斗预设资源根目录（按玩家模板/职业/技能等进一步分层）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置",
            purpose="管理配置资源根目录（按计时器/关卡变量/结构体定义等进一步分层）。",
        )

        for resource_type in ResourceType:
            if resource_type == ResourceType.GRAPH:
                continue
            if resource_type in {
                ResourceType.UI_LAYOUT,
                ResourceType.UI_WIDGET_TEMPLATE,
                ResourceType.UI_PAGE,
            }:
                # UI 派生物不落资源库：目录骨架不再创建
                continue
            self._ensure_dir_with_docs(
                package_root_dir / resource_type.value,
                purpose=f"存放资源类型：{resource_type.value}。",
            )

        # 3) 节点图目录需要 server/client 结构
        self._ensure_dir_with_docs(
            package_root_dir / "节点图",
            purpose="节点图资源根目录（按 server/client 进一步分层）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "server",
            purpose="服务器节点图目录（放置 Graph Code .py；节点图脚本内自带 workspace bootstrap + app.runtime prelude 导入）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "client",
            purpose="客户端节点图目录（放置 Graph Code .py；节点图脚本内自带 workspace bootstrap + app.runtime prelude 导入）。",
        )

        # 3.1) 节点图分类目录骨架（目录结构约定）
        # server：固定四类目录
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "server" / "实体节点图",
            purpose="服务器节点图：实体节点图（默认归类目录；未明确分类的 server 节点图放这里）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "server" / "状态节点图",
            purpose="服务器节点图：状态节点图（单位状态/状态机等相关逻辑）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "server" / "职业节点图",
            purpose="服务器节点图：职业节点图（职业/天赋/职业相关逻辑）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "server" / "道具节点图",
            purpose="服务器节点图：道具节点图（道具/装备/背包相关逻辑）。",
        )

        # client：固定三类目录
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "client" / "布尔过滤器节点图",
            purpose="客户端节点图：布尔过滤器节点图（返回布尔值，用于本地筛选/显隐条件等）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "client" / "整数过滤器节点图",
            purpose="客户端节点图：整数过滤器节点图（返回整数，用于本地筛选/排序/评分等）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "节点图" / "client" / "技能节点图",
            purpose="客户端节点图：技能节点图（客户端技能/表现/本地调度）。",
        )

        # 4) 额外约定目录：当前工程存在但不在 ResourceType 枚举中的管理子目录
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置" / "UI源码",
            purpose="管理配置：UI源码（HTML/CSS）。约定：一个 HTML 对应一个功能页；HTML 为真源，UI 派生物统一写入运行时缓存。",
        )

        # 5) 关卡变量与结构体定义的常用子目录骨架
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置" / "关卡变量" / "自定义变量",
            purpose="管理配置：关卡变量（自定义变量，代码资源 .py）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置" / "关卡变量" / "自定义变量-局内存档变量",
            purpose="管理配置：关卡变量（局内存档变量，代码资源 .py）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置" / "结构体定义" / "基础结构体",
            purpose="管理配置：结构体定义（基础结构体，代码资源 .py）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置" / "结构体定义" / "局内存档结构体",
            purpose="管理配置：结构体定义（局内存档结构体，代码资源 .py）。",
        )

        # 6) 装备数据常用子目录
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置" / "装备数据" / "标签",
            purpose="管理配置：装备数据（标签分类）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置" / "装备数据" / "类型",
            purpose="管理配置：装备数据（类型分类）。",
        )
        self._ensure_dir_with_docs(
            package_root_dir / "管理配置" / "装备数据" / "词条",
            purpose="管理配置：装备数据（词条分类）。",
        )

    def _copy_graph_prelude_files_to_new_package(self, package_root_dir: Path) -> None:
        """旧逻辑遗留：曾用于为新项目存档拷贝节点图前导文件。

        当前节点图代码已迁移为“workspace bootstrap + app.runtime.engine.graph_prelude_*”，
        不再依赖项目目录内的额外前导文件，因此该步骤不再需要。
        """
        _ = package_root_dir
        return

    @staticmethod
    def _ensure_node_graph_category_dirs_for_package(package_root_dir: Path) -> None:
        """确保项目存档的节点图目录包含固定分类目录（用于新建项目后的兜底补齐）。"""
        server_root = package_root_dir / "节点图" / "server"
        client_root = package_root_dir / "节点图" / "client"
        server_root.mkdir(parents=True, exist_ok=True)
        client_root.mkdir(parents=True, exist_ok=True)

        for dirname in ("实体节点图", "状态节点图", "职业节点图", "道具节点图"):
            (server_root / dirname).mkdir(parents=True, exist_ok=True)
        for dirname in ("布尔过滤器节点图", "整数过滤器节点图", "技能节点图"):
            (client_root / dirname).mkdir(parents=True, exist_ok=True)

    @classmethod
    def _collect_id_values_from_json_obj(
        cls,
        obj,
        *,
        current_key: str | None = None,
        depth: int = 0,
        results: set[str],
    ) -> None:
        """从 JSON 结构中收集“疑似资源 ID”的字符串值。

        约定：仅从 ID 字段收集（`id` / `*_id` / `resource_id` / `preset_id` / `config_id`），
        避免把 `name/description` 等业务文本误当成 ID。
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_text = str(key) if key is not None else ""
                cls._collect_id_values_from_json_obj(
                    value,
                    current_key=key_text,
                    depth=depth + 1,
                    results=results,
                )
            return

        if isinstance(obj, list):
            for item in obj:
                cls._collect_id_values_from_json_obj(
                    item,
                    current_key=current_key,
                    depth=depth,
                    results=results,
                )
            return

        if not isinstance(obj, str):
            return

        value_text = obj.strip()
        if not value_text:
            return

        if not current_key:
            return

        key_lower = current_key.lower()
        if key_lower == "name" or key_lower.endswith("_name") or key_lower == "description":
            return

        # 注意：JSON 内部经常出现“子对象的 id”（如 UI layout 内部 widget 的 id），
        # 这类不是资源 ID，也不应参与克隆时的 ID 改写。因此：
        # - 仅在“顶层对象”（depth==1）收集 `id/resource_id/preset_id/config_id`
        # - 对明确的 `*_id` 字段（引用或资源 ID）允许在任意深度收集
        if (key_lower == "id" and depth == 1) or (key_lower.endswith("_id")) or (
            key_lower in {"resource_id", "preset_id", "config_id"} and depth == 1
        ):
            results.add(value_text)
            return

    @staticmethod
    def _is_safe_clone_id(text: str) -> bool:
        """用于克隆 ID 改写的保守过滤：

        - 排除纯数字（例如 UI 子控件 id=0/1/2），避免误替换 Python 代码中的数字字面量
        - 排除过短字符串，避免误伤常量/占位符
        """
        cleaned = str(text or "").strip()
        if not cleaned:
            return False
        if cleaned.isdigit():
            return False
        if len(cleaned) < 3:
            return False
        return True

    def _collect_template_ids_for_clone(self, template_root_dir: Path) -> List[str]:
        """扫描模板目录，收集需要在克隆时改写的 ID 集合。"""
        id_values: set[str] = set()

        # 1) JSON 资源（元件库/实体摆放/战斗预设/管理配置等）
        for json_file in template_root_dir.rglob("*.json"):
            with open(json_file, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            self._collect_id_values_from_json_obj(data, current_key=None, results=id_values)

        # 2) 节点图 graph_id（docstring）
        graphs_dir = template_root_dir / "节点图"
        if graphs_dir.exists() and graphs_dir.is_dir():
            for py_file in graphs_dir.rglob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                if "校验" in py_file.stem:
                    continue
                meta = load_graph_metadata_from_file(py_file)
                if meta.graph_id:
                    id_values.add(str(meta.graph_id).strip())

        # 3) 复合节点 composite_id（docstring）
        composites_dir = template_root_dir / "复合节点库"
        if composites_dir.exists() and composites_dir.is_dir():
            for py_file in composites_dir.rglob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                if "校验" in py_file.stem:
                    continue
                meta = load_graph_metadata_from_file(py_file)
                if meta.composite_id:
                    id_values.add(str(meta.composite_id).strip())

        # 4) 管理配置中的代码资源（信号/结构体/关卡变量/局内存档模板等）
        management_dir = template_root_dir / "管理配置"
        if management_dir.exists() and management_dir.is_dir():
            constant_patterns = [
                r"^\s*SIGNAL_ID\s*=\s*['\"]([^'\"]+)['\"]\s*$",
                r"^\s*STRUCT_ID\s*=\s*['\"]([^'\"]+)['\"]\s*$",
                r"^\s*VARIABLE_FILE_ID\s*=\s*['\"]([^'\"]+)['\"]\s*$",
                r"^\s*SAVE_POINT_ID\s*=\s*['\"]([^'\"]+)['\"]\s*$",
            ]
            compiled = [re.compile(p, flags=re.MULTILINE) for p in constant_patterns]
            variable_id_pattern = re.compile(r"\bvariable_id\s*=\s*['\"]([^'\"]+)['\"]")

            for py_file in management_dir.rglob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                if "校验" in py_file.stem:
                    continue
                code = py_file.read_text(encoding="utf-8")
                for pattern in compiled:
                    for match in pattern.finditer(code):
                        value_text = str(match.group(1) or "").strip()
                        if value_text:
                            id_values.add(value_text)
                for match in variable_id_pattern.finditer(code):
                    value_text = str(match.group(1) or "").strip()
                    if value_text:
                        id_values.add(value_text)

        # 稳定排序：先替换长字符串，避免“短 ID 是长 ID 子串”时的误替换
        filtered = [text for text in id_values if self._is_safe_clone_id(text)]
        return sorted(filtered, key=lambda text: len(text), reverse=True)

    @staticmethod
    def _collect_signal_ids_for_clone(template_root_dir: Path) -> set[str]:
        """收集模板内的 SIGNAL_ID 集合。

        设计目标：
        - 新建存档时，信号定义（`管理配置/信号/*.py`）不再作为“项目私有资源”复制一份，
          避免出现“新建一个项目就多一份信号文件”的目录膨胀。
        - 因此，克隆时也不应对这些 SIGNAL_ID 做后缀化改写；否则新项目内的图/模板引用会被
          改写为 `xxx__<package>`，但项目内又不存在对应信号定义文件，造成引用断裂。
        """
        signals_dir = template_root_dir / "管理配置" / "信号"
        if not signals_dir.exists() or not signals_dir.is_dir():
            return set()

        signal_id_pattern = re.compile(
            r"^\s*SIGNAL_ID\s*=\s*['\"]([^'\"]+)['\"]\s*$",
            flags=re.MULTILINE,
        )

        results: set[str] = set()
        for py_file in signals_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if "校验" in py_file.stem:
                continue
            code = py_file.read_text(encoding="utf-8")
            match = signal_id_pattern.search(code)
            if not match:
                continue
            value_text = str(match.group(1) or "").strip()
            if value_text:
                results.add(value_text)
        return results

    @staticmethod
    def _remove_signal_definitions_from_cloned_package(package_root_dir: Path) -> None:
        """从新建项目中移除模板自带的信号定义文件（仅移除 .py）。"""
        signals_dir = package_root_dir / "管理配置" / "信号"
        if not signals_dir.exists() or not signals_dir.is_dir():
            return

        for py_path in signals_dir.rglob("*.py"):
            if py_path.is_file():
                py_path.unlink()

        for cache_dir in signals_dir.rglob("__pycache__"):
            if cache_dir.is_dir():
                shutil.rmtree(cache_dir)

    @classmethod
    def _rewrite_json_obj_ids(cls, obj, *, current_key: str | None, id_map: Dict[str, str]):
        if isinstance(obj, dict):
            return {
                key: cls._rewrite_json_obj_ids(value, current_key=str(key) if key is not None else None, id_map=id_map)
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [cls._rewrite_json_obj_ids(item, current_key=current_key, id_map=id_map) for item in obj]
        if isinstance(obj, str):
            key_lower = (current_key or "").lower()
            if key_lower == "name" or key_lower.endswith("_name") or key_lower == "description":
                return obj
            return id_map.get(obj, obj)
        return obj

    def _rewrite_ids_in_cloned_package(self, package_root_dir: Path, *, id_map: Dict[str, str]) -> None:
        """将克隆后的项目存档目录内的资源 ID 按映射改写。"""
        # 1) JSON
        for json_file in package_root_dir.rglob("*.json"):
            with open(json_file, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            rewritten = self._rewrite_json_obj_ids(data, current_key=None, id_map=id_map)
            atomic_write_json(json_file, rewritten, ensure_ascii=False, indent=2)

        # 2) Python（struct 定义文件：仅改 STRUCT_ID；其余 py 按“引号内字符串 + 元数据行”改写）
        struct_dir = package_root_dir / "管理配置" / "结构体定义"

        struct_id_pattern = re.compile(
            r"^(?P<prefix>\s*STRUCT_ID\s*=\s*)(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)\s*$",
            flags=re.MULTILINE,
        )

        def _rewrite_docstring_id_lines(text: str) -> str:
            # 仅处理 docstring 顶部常见的 `graph_id:` / `composite_id:` 行，避免全局 replace 误伤
            lines = text.splitlines()
            new_lines: list[str] = []
            for line in lines:
                stripped = line.strip()
                lowered = stripped.lower()
                if lowered.startswith("graph_id:"):
                    raw_value = stripped.split(":", 1)[1].strip()
                    new_value = id_map.get(raw_value, raw_value)
                    prefix = line[: line.lower().find("graph_id:")]
                    new_lines.append(f"{prefix}graph_id: {new_value}")
                    continue
                if lowered.startswith("composite_id:"):
                    raw_value = stripped.split(":", 1)[1].strip()
                    new_value = id_map.get(raw_value, raw_value)
                    prefix = line[: line.lower().find("composite_id:")]
                    new_lines.append(f"{prefix}composite_id: {new_value}")
                    continue
                new_lines.append(line)
            return "\n".join(new_lines)

        for py_file in package_root_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if "校验" in py_file.stem:
                continue
            if py_file.parent.name == "__pycache__":
                continue

            code = py_file.read_text(encoding="utf-8")

            is_struct_definition = self._is_path_under(struct_dir, py_file)

            if is_struct_definition:

                def _replace_struct_id(match: re.Match[str]) -> str:
                    old_value = str(match.group("value") or "")
                    new_value = id_map.get(old_value, old_value)
                    return f"{match.group('prefix')}{match.group('quote')}{new_value}{match.group('quote')}"

                rewritten_code = struct_id_pattern.sub(_replace_struct_id, code, count=1)
                if rewritten_code != code:
                    py_file.write_text(rewritten_code, encoding="utf-8")
                continue

            # 非结构体定义文件：
            # - 先改写 docstring 顶部的 graph_id/composite_id 行（无引号）
            # - 再仅替换引号内的字符串字面量，避免误替换 Python 数字字面量（例如 sys.path.insert(0, ...)）
            rewritten_code = _rewrite_docstring_id_lines(code)
            for old_id in sorted(id_map.keys(), key=lambda text: len(text), reverse=True):
                new_id = id_map[old_id]
                rewritten_code = rewritten_code.replace(f"'{old_id}'", f"'{new_id}'")
                rewritten_code = rewritten_code.replace(f"\"{old_id}\"", f"\"{new_id}\"")
            if rewritten_code != code:
                py_file.write_text(rewritten_code, encoding="utf-8")

        # 3) 清理 __pycache__
        for cache_dir in package_root_dir.rglob("__pycache__"):
            if cache_dir.is_dir():
                shutil.rmtree(cache_dir)

    def _rewrite_package_root_docs(self, package_root_dir: Path, *, package_display_name: str) -> None:
        """为新建项目写入/覆盖根目录 claude.md（避免把模板说明复制过去）。"""
        claude_file = package_root_dir / "claude.md"
        text = "\n".join(
            [
                "## 目录用途",
                f"项目存档根目录（项目：{package_display_name}）。用于承载该项目的元件/实体摆放/节点图/战斗预设/管理配置等资源。",
                "",
                "## 当前状态",
                "该项目由“示例项目模板”复制创建；资源 ID 已做处理以避免与模板或其他项目冲突。",
                "",
                "## 注意事项",
                "- 建议关卡实体文件命名为 `<项目名>_关卡实体.json`，便于资源结构约定一致（不作为项目显示名真源）。",
                "- 共享文档：`文档/共享文档` 为 Junction，指向 `assets/资源库/共享/文档`（零复制共享）。",
                "- 共享根 `assets/资源库/共享/` 用于放置公共资源（所有存档可见）；修改共享资源会影响所有项目，请谨慎管理。",
                "",
                "---",
                "注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。",
                "",
            ]
        )
        claude_file.write_text(text, encoding="utf-8")

    def _rewrite_cloned_package_root_docs(
        self,
        package_root_dir: Path,
        *,
        package_display_name: str,
        source_package_id: str,
    ) -> None:
        """为“复制项目存档”写入/覆盖根目录 claude.md。

        注意：复制项目存档会保留资源 ID 与引用关系（允许跨项目重复 ID，资源索引按作用域隔离）。
        """
        claude_file = package_root_dir / "claude.md"
        text = "\n".join(
            [
                "## 目录用途",
                f"项目存档根目录（项目：{package_display_name}）。用于承载该项目的元件/实体摆放/节点图/战斗预设/管理配置等资源。",
                "",
                "## 当前状态",
                f"该项目由项目存档“{source_package_id}”复制创建；资源 ID 保持不变（允许跨项目重复 ID，资源索引按作用域隔离）。",
                "",
                "## 注意事项",
                "- 建议关卡实体文件命名为 `<项目名>_关卡实体.json`，便于资源结构约定一致（不作为项目显示名真源）。",
                "- 共享文档：`文档/共享文档` 为 Junction，指向 `assets/资源库/共享/文档`（零复制共享）。",
                "- 复制项目后，GUID 等全局标识可能与源项目重复；如需在同一工作流中并行使用多个项目，建议通过校验工具检查并按需调整。",
                "- 共享根 `assets/资源库/共享/` 用于放置公共资源（所有存档可见）；修改共享资源会影响所有项目，请谨慎管理。",
                "",
                "---",
                "注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。",
                "",
            ]
        )
        claude_file.write_text(text, encoding="utf-8")

    def _rename_level_entity_file(self, package_root_dir: Path, *, package_display_name: str) -> None:
        instances_dir = self._resolve_instance_dir(package_root_dir)
        if not instances_dir.exists() or not instances_dir.is_dir():
            return
        candidates = sorted(instances_dir.glob("*_关卡实体.json"), key=lambda path: path.name.casefold())
        if not candidates:
            return
        level_entity_file = candidates[0]
        target_file = instances_dir / f"{package_display_name}_关卡实体.json"
        if target_file.resolve() == level_entity_file.resolve():
            return
        if target_file.exists():
            raise ValueError(f"重命名关卡实体失败：目标文件已存在：{target_file}")
        level_entity_file.rename(target_file)

    def create_package(self, name: str, description: str = "") -> str:
        """创建新存档。

        Args:
            name: 存档名称
            description: 存档描述（目录模式下不落盘，仅为接口兼容）

        Returns:
            存档ID
        """
        _ = description

        # 目录即存档：新建项目采用“复制示例项目模板并改名”的方式。
        sanitized_display_name = self._sanitize_package_filename(str(name or ""))
        if not sanitized_display_name:
            sanitized_display_name = "新项目"

        existing_names = [path.name for path in self._packages_root_dir.iterdir() if path.is_dir()]
        package_dirname = generate_unique_name(
            sanitized_display_name,
            existing_names,
            separator="_",
            start_index=2,
        )
        package_root_dir = self._packages_root_dir / package_dirname

        template_root_dir = self._packages_root_dir / self.TEMPLATE_PACKAGE_DIRNAME
        if not template_root_dir.exists() or not template_root_dir.is_dir():
            raise ValueError(
                f"创建存档失败：未找到示例项目模板目录：{template_root_dir}。"
                f"请先确保资源库中存在 '{self.TEMPLATE_PACKAGE_DIRNAME}' 项目存档目录。"
            )

        shutil.copytree(
            template_root_dir,
            package_root_dir,
            ignore=shutil.ignore_patterns(*self._CLONE_IGNORE_PATTERNS),
        )

        # 目录结构兜底：确保新建项目自带 server/client 分类目录
        self._ensure_node_graph_category_dirs_for_package(package_root_dir)

        # 模板自带的信号定义不再随项目复制：避免“新建一个项目就多一份信号文件”。
        self._remove_signal_definitions_from_cloned_package(package_root_dir)

        # 复制后：对模板中的资源 ID 做后缀化处理，避免与模板/其它项目冲突。
        template_ids = self._collect_template_ids_for_clone(template_root_dir)
        template_signal_ids = self._collect_signal_ids_for_clone(template_root_dir)
        filtered_ids = [old_id for old_id in template_ids if old_id not in template_signal_ids]
        id_map = {old_id: f"{old_id}__{package_dirname}" for old_id in filtered_ids}
        self._rewrite_ids_in_cloned_package(package_root_dir, id_map=id_map)

        # 更新项目文档与关卡实体文件名（保持目录/约定命名一致）
        self._rewrite_package_root_docs(package_root_dir, package_display_name=package_dirname)
        self._rename_level_entity_file(package_root_dir, package_display_name=package_dirname)
        self._ensure_shared_docs_link_for_package(package_root_dir)

        # 新建项目完成：重建索引以便 UI/校验立刻可见
        self.resource_manager.rebuild_index()
        return package_dirname

    def clone_package(self, source_package_id: str, name: str) -> str:
        """复制一个现有项目存档为新的项目存档目录。

        设计约定：
        - 复制采用目录级 copytree，保留资源 ID 与引用关系；
        - 允许跨项目重复 ID，资源索引按“共享根 + 当前项目存档根”作用域隔离；
        - 复制完成后会更新根目录 claude.md 与关卡实体文件名（保持目录/约定命名一致）。
        """
        source_id_text = str(source_package_id or "").strip()
        if not source_id_text:
            raise ValueError("source_package_id 不能为空")

        source_root_dir = self._packages_root_dir / source_id_text
        if not source_root_dir.exists() or not source_root_dir.is_dir():
            raise ValueError(f"复制存档失败：源存档目录不存在：{source_root_dir}")

        sanitized_display_name = self._sanitize_package_filename(str(name or ""))
        if not sanitized_display_name:
            sanitized_display_name = f"{source_id_text}_副本"

        existing_names = [path.name for path in self._packages_root_dir.iterdir() if path.is_dir()]
        target_dirname = generate_unique_name(
            sanitized_display_name,
            existing_names,
            separator="_",
            start_index=2,
        )
        target_root_dir = self._packages_root_dir / target_dirname

        shutil.copytree(
            source_root_dir,
            target_root_dir,
            ignore=shutil.ignore_patterns(*self._CLONE_IGNORE_PATTERNS),
        )

        # 目录结构兜底：确保复制出的项目也符合目录规范
        self._ensure_node_graph_category_dirs_for_package(target_root_dir)

        # 更新项目文档与关卡实体文件名（保持目录/约定命名一致）
        self._rewrite_cloned_package_root_docs(
            target_root_dir,
            package_display_name=target_dirname,
            source_package_id=source_id_text,
        )
        self._rename_level_entity_file(target_root_dir, package_display_name=target_dirname)
        self._ensure_shared_docs_link_for_package(target_root_dir)

        # 复制完成：刷新索引（保持与 create_package 一致，确保 UI 立刻可见）
        self.resource_manager.rebuild_index()
        return target_dirname



