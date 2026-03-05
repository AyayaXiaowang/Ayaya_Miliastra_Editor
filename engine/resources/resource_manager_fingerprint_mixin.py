from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from engine.configs.resource_types import ResourceType
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir


class ResourceManagerFingerprintMixin:
    """ResourceManager 的资源库指纹与变更检测相关方法。"""

    def _compute_directory_fingerprint(
        self,
        target_dir: Path,
        pattern: str,
        *,
        recursive: bool,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> str:
        """统计指定目录的文件数量与最新修改时间。"""
        file_count, latest_mtime = self._scan_dirs_for_fingerprint(
            [target_dir],
            pattern=pattern,
            recursive=bool(recursive),
            should_abort=should_abort,
        )
        return f"{target_dir.name}:{int(file_count)}:{round(float(latest_mtime), 3)}"

    def _compute_multi_directory_fingerprint(
        self,
        label: str,
        directories: List[Path],
        pattern: str,
        *,
        recursive: bool,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> str:
        """统计多个目录的文件数量与最新修改时间，并合并为一个指纹片段。"""
        file_count, latest_mtime = self._scan_dirs_for_fingerprint(
            list(directories),
            pattern=pattern,
            recursive=bool(recursive),
            should_abort=should_abort,
        )
        return f"{label}:{int(file_count)}:{round(float(latest_mtime), 3)}"

    @staticmethod
    def _scan_dirs_for_fingerprint(
        directories: List[Path],
        *,
        pattern: str,
        recursive: bool,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> tuple[int, float]:
        """使用 os.scandir 遍历目录，统计文件数量与最新 mtime（用于指纹计算）。

        说明：
        - 仅支持 `*.py` / `*.json` 这类简单后缀模式（与当前指纹调用点一致）。
        - 不引入跨线程共享缓存，保持低风险。
        """
        suffix = str(pattern or "").strip()
        if suffix.startswith("*."):
            suffix = suffix[1:]  # "*.py" -> ".py"
        if not suffix.startswith("."):
            # 非后缀模式：回退为 0（当前调用点不依赖该分支）
            return 0, 0.0

        file_count = 0
        latest_mtime = 0.0
        for root in directories:
            if should_abort is not None and should_abort():
                break
            if not root.exists() or not root.is_dir():
                continue

            stack: list[str] = [str(root)]
            while stack:
                if should_abort is not None and should_abort():
                    stack.clear()
                    break
                current_dir = stack.pop()
                if not os.path.isdir(current_dir):
                    continue
                with os.scandir(current_dir) as entries:
                    for entry in entries:
                        if should_abort is not None and should_abort():
                            break
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:
                                stack.append(entry.path)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        if not entry.name.endswith(suffix):
                            continue
                        if not os.path.exists(entry.path):
                            continue
                        stat_result = entry.stat(follow_symlinks=False)
                        file_count += 1
                        mtime = float(stat_result.st_mtime)
                        if mtime > latest_mtime:
                            latest_mtime = mtime

        return int(file_count), float(latest_mtime)

    def compute_resource_library_fingerprint(
        self,
        *,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> str:
        """计算当前资源库的指纹（覆盖全部资源目录）。"""
        if should_abort is not None and should_abort():
            return str(self._resource_library_fingerprint or "")

        base_fingerprint = self._resource_index_builder.compute_resources_fingerprint(should_abort=should_abort)
        if should_abort is not None and should_abort():
            return str(self._resource_library_fingerprint or "")

        # 复合节点库指纹：与资源索引保持一致，同样按“共享 + 当前项目存档”作用域计算。
        composite_roots: list[Path] = []
        shared_root = get_shared_root_dir(self.resource_library_dir)
        if shared_root.exists() and shared_root.is_dir():
            composite_roots.append(shared_root)
        if self._active_package_id:
            package_root = get_packages_root_dir(self.resource_library_dir) / str(self._active_package_id)
            if package_root.exists() and package_root.is_dir():
                composite_roots.append(package_root)

        composite_dirs = [root / "复合节点库" for root in composite_roots]
        composite_fingerprint = self._compute_multi_directory_fingerprint(
            "复合节点库",
            composite_dirs,
            "*.py",
            recursive=True,
            should_abort=should_abort,
        )
        if should_abort is not None and should_abort():
            return str(self._resource_library_fingerprint or "")

        return "|".join(
            [
                base_fingerprint,
                composite_fingerprint,
            ]
        )

    def compute_resource_library_fingerprint_for_auto_refresh(
        self,
        *,
        trigger_directory: Path | None,
        baseline_fingerprint: str,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> str:
        """用于文件监控/自动刷新确认阶段的指纹计算（允许按触发目录做增量）。

        设计目标：
        - **高收益**：directoryChanged 高频触发时，只重算命中的资源子树/类型，避免全库扫盘；
        - **低风险**：未知路径/无法判定时回退全量；周期性复核（trigger_directory=None）始终全量；
        - 该方法仅用于“确认是否需要刷新”的比较，不用于更新指纹基线（基线仍应由刷新链路全量更新）。
        """
        baseline_text = str(baseline_fingerprint or "")
        if should_abort is not None and should_abort():
            return baseline_text
        if trigger_directory is None:
            return self.compute_resource_library_fingerprint(should_abort=should_abort)
        if not baseline_text:
            return self.compute_resource_library_fingerprint(should_abort=should_abort)

        trigger_resolved = trigger_directory.resolve()
        trigger_parts = trigger_resolved.parts

        affected_types: set[ResourceType] = set()
        for resource_type in ResourceType:
            for base_dir in self._resource_index_builder._get_resource_directories(resource_type):
                base_parts = base_dir.resolve().parts
                if trigger_parts[: len(base_parts)] == base_parts or base_parts[: len(trigger_parts)] == trigger_parts:
                    affected_types.add(resource_type)
                    break

        composite_dirs = self._get_composite_node_library_directories()
        composite_affected = False
        for base_dir in composite_dirs:
            base_parts = base_dir.resolve().parts
            if trigger_parts[: len(base_parts)] == base_parts or base_parts[: len(trigger_parts)] == trigger_parts:
                composite_affected = True
                break

        if not affected_types and not composite_affected:
            # 触发目录不在已知资源子树内：回退全量以降低漏刷新风险。
            return self.compute_resource_library_fingerprint(should_abort=should_abort)

        segments = [seg for seg in baseline_text.split("|") if seg]
        if not segments:
            return self.compute_resource_library_fingerprint(should_abort=should_abort)

        # 始终用当前作用域重写 SCOPE 片段，避免存档切换导致的指纹段漂移。
        scope_label = str(getattr(self, "_active_package_id", None) or "shared_only").strip() or "shared_only"
        scope_segment = f"SCOPE:{scope_label}:0"
        if segments[0].startswith("SCOPE:"):
            segments[0] = scope_segment
        else:
            segments.insert(0, scope_segment)

        replacements: dict[str, str] = {}
        for resource_type in affected_types:
            if should_abort is not None and should_abort():
                break
            count, latest_mtime = self._resource_index_builder._compute_resource_type_fingerprint_stats(
                resource_type,
                should_abort=should_abort,
            )
            replacements[resource_type.name] = (
                f"{resource_type.name}:{int(count)}:{round(float(latest_mtime), 3)}"
            )
        if composite_affected and (should_abort is None or not should_abort()):
            count, latest_mtime = self._compute_composite_node_library_fingerprint_stats(
                should_abort=should_abort
            )
            replacements["复合节点库"] = f"复合节点库:{int(count)}:{round(float(latest_mtime), 3)}"

        # 若 baseline 中缺少任何待替换段，为避免生成“混合指纹”导致漏判，回退全量。
        baseline_labels = {seg.split(":", 1)[0] for seg in segments if seg}
        for label in replacements.keys():
            if label not in baseline_labels:
                return self.compute_resource_library_fingerprint(should_abort=should_abort)

        for idx, seg in enumerate(segments):
            label = seg.split(":", 1)[0]
            replacement = replacements.get(label)
            if replacement is not None:
                segments[idx] = replacement

        return "|".join(segments)

    def _get_composite_node_library_directories(self) -> list[Path]:
        """复合节点库目录列表（按“共享 + 当前项目存档”作用域）。"""
        roots: list[Path] = []
        shared_root = get_shared_root_dir(self.resource_library_dir)
        if shared_root.exists() and shared_root.is_dir():
            roots.append(shared_root)
        active_package_id = str(getattr(self, "_active_package_id", "") or "").strip()
        if active_package_id:
            package_root = get_packages_root_dir(self.resource_library_dir) / active_package_id
            if package_root.exists() and package_root.is_dir():
                roots.append(package_root)
        return [(root / "复合节点库") for root in roots]

    def _compute_composite_node_library_fingerprint_stats(
        self,
        *,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> tuple[int, float]:
        """计算复合节点库的 (file_count, latest_mtime)。"""
        composite_dirs = self._get_composite_node_library_directories()
        file_count, latest_mtime = self._scan_dirs_for_fingerprint(
            composite_dirs,
            pattern="*.py",
            recursive=True,
            should_abort=should_abort,
        )
        return int(file_count), float(latest_mtime)

    def get_resource_library_fingerprint(self) -> str:
        """获取最近一次记录的资源库指纹。"""
        return self._resource_library_fingerprint

    def set_resource_library_fingerprint(self, fingerprint: str) -> None:
        """直接设置当前资源库指纹记录（用于外部已计算的结果）。"""
        self._resource_library_fingerprint = fingerprint
        self._fingerprint_invalidated = False

    def invalidate_fingerprint(self) -> None:
        """标记指纹为脏，延迟到下次需要时再重新计算。

        用于 save_resource 等高频操作，避免每次保存都触发完整的指纹计算。
        """
        self._fingerprint_invalidated = True

    def refresh_resource_library_fingerprint_if_invalidated(self) -> bool:
        """仅在“指纹被内部写盘标记为脏”时刷新资源库指纹基线。

        设计动机：
        - `save_resource/delete_resource` 会调用 `invalidate_fingerprint()`，表示“资源库变化来自进程内写盘”；
        - 保存链条/刷新链条中经常需要把这类内部变更同步到基线，避免后续误判为外部修改；
        - 该方法**不会**用于吞掉真实外部变更：只有在脏标记为 True 时才会刷新并返回 True。

        Returns:
            True：本次确实刷新了基线；False：基线保持不变。
        """
        if not self._fingerprint_invalidated:
            return False
        self.refresh_resource_library_fingerprint()
        return True

    def refresh_resource_library_fingerprint(self) -> str:
        """重新计算并更新资源库指纹记录。"""
        latest_fingerprint = self.compute_resource_library_fingerprint()
        self._resource_library_fingerprint = latest_fingerprint
        self._fingerprint_invalidated = False
        return latest_fingerprint

    def has_resource_library_changed(self) -> bool:
        """检测资源库是否相较于记录指纹发生变更。

        如果指纹已被标记为脏（由 save_resource 等操作触发），
        则先刷新指纹基线再比较，避免因自身保存操作导致误判。
        """
        if self._fingerprint_invalidated:
            self.refresh_resource_library_fingerprint()
            return False  # 脏标记意味着是自身保存导致的变化，不是外部修改
        latest_fingerprint = self.compute_resource_library_fingerprint()
        return latest_fingerprint != self._resource_library_fingerprint




