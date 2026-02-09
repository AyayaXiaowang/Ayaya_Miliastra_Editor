"""复合节点文件夹管理器 - 负责文件夹的创建、删除和节点移动"""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from engine.utils.logging.logger import log_info, log_error
from engine.utils.path_utils import normalize_slash

if TYPE_CHECKING:
    from engine.nodes.advanced_node_features import CompositeNodeConfig


class CompositeFolderManager:
    """复合节点文件夹管理器
    
    职责：
    - 创建和删除文件夹
    - 移动复合节点到指定文件夹
    - 维护文件夹列表
    """
    
    def __init__(self, composite_library_dir: Path):
        """初始化文件夹管理器
        
        Args:
            composite_library_dir: 复合节点库目录
        """
        self.composite_library_dir = composite_library_dir
        self.folders: list[str] = []

    def _is_path_inside_composite_library(self, physical_path: Path) -> bool:
        """判断物理路径是否位于复合节点库根目录之下（包含子目录）。

        注意：这里使用 resolve(strict=False) 以规避 '..' 片段并跟随已存在的软链接/目录联接，
        防止通过 junction/symlink 将操作逃逸到库外目录。
        """
        resolved_base = self.composite_library_dir.resolve(strict=False)
        resolved_physical = physical_path.resolve(strict=False)
        if hasattr(resolved_physical, "is_relative_to"):
            return bool(resolved_physical.is_relative_to(resolved_base))
        base_parts = resolved_base.parts
        physical_parts = resolved_physical.parts
        if len(physical_parts) < len(base_parts):
            return False
        return physical_parts[: len(base_parts)] == base_parts

    def _try_normalize_relative_folder_path(
        self,
        folder_path: str,
        *,
        allow_empty: bool,
    ) -> str | None:
        """将用户输入/外部传入的文件夹路径归一化为相对路径（使用 '/' 分隔）。

        规则：
        - 仅允许相对路径（禁止绝对路径、UNC、盘符注入）
        - 禁止任何 '.' / '..' 片段（阻断路径穿越）
        - 统一将 '\\' 转换为 '/'
        - 去除首尾空白与首尾 '/'
        """
        raw_text = str(folder_path or "").strip()
        if not raw_text:
            return "" if allow_empty else None

        normalized_text = normalize_slash(raw_text)
        if "\x00" in normalized_text:
            return None
        # 绝对路径/UNC（例如 "/a", "\\\\server\\share" -> "//server/share"）
        if normalized_text.startswith("/"):
            return None
        # Windows 盘符注入/协议注入（例如 "C:/", "C:\\", "file:..."）
        if ":" in normalized_text:
            return None

        normalized_text = normalized_text.strip("/")
        if not normalized_text:
            return "" if allow_empty else None

        parts = [part for part in normalized_text.split("/") if part]
        if not parts:
            return "" if allow_empty else None
        for part in parts:
            if part in (".", ".."):
                return None
        return "/".join(parts)

    def _is_valid_folder_name_segment(self, folder_name: str) -> bool:
        """验证 folder_name 作为“单级文件夹名”是否合法（不能包含路径分隔符等）。"""
        name_text = str(folder_name or "").strip()
        if not name_text:
            return False
        if "\x00" in name_text:
            return False
        if name_text in (".", ".."):
            return False
        if "/" in name_text or "\\" in name_text:
            return False
        if ":" in name_text:
            return False
        return True

    def _try_build_safe_folder_path(self, folder_name: str, parent_folder: str) -> str | None:
        """基于父路径与新建名称构建安全的相对 folder_path（返回统一的 'a/b' 格式）。"""
        if not self._is_valid_folder_name_segment(folder_name):
            return None
        folder_name_segment = str(folder_name or "").strip()
        normalized_parent = self._try_normalize_relative_folder_path(parent_folder, allow_empty=True)
        if normalized_parent is None:
            return None
        combined_path = (
            f"{normalized_parent}/{folder_name_segment}" if normalized_parent else folder_name_segment
        )
        normalized_combined = self._try_normalize_relative_folder_path(combined_path, allow_empty=False)
        if normalized_combined is None:
            return None
        candidate_physical = self.composite_library_dir / normalized_combined
        if not self._is_path_inside_composite_library(candidate_physical):
            return None
        return normalized_combined
    
    def scan_folders(self) -> None:
        """扫描并收集所有文件夹"""
        self.folders.clear()
        for item in self.composite_library_dir.rglob("*"):
            if item.is_dir() and item.name != "__pycache__":
                if not self._is_path_inside_composite_library(item):
                    # 可能是 symlink/junction 指向库外：不纳入可操作列表，避免后续写入/删除逃逸
                    continue
                relative_path = item.relative_to(self.composite_library_dir).as_posix()
                normalized = self._try_normalize_relative_folder_path(relative_path, allow_empty=False)
                if normalized is None:
                    continue
                if normalized not in self.folders:
                    self.folders.append(normalized)
    
    def create_folder(self, folder_name: str, parent_folder: str = "") -> bool:
        """创建文件夹
        
        Args:
            folder_name: 文件夹名称
            parent_folder: 父文件夹路径（空字符串表示根目录）
            
        Returns:
            是否成功
        """
        folder_path = self._try_build_safe_folder_path(folder_name, parent_folder)
        if folder_path is None:
            log_error(f"非法文件夹路径：parent='{parent_folder}', name='{folder_name}'")
            return False
        
        # 检查是否已存在
        if folder_path in self.folders:
            log_error(f"文件夹已存在: {folder_path}")
            return False
        
        # 创建物理文件夹
        physical_path = self.composite_library_dir / folder_path
        if not self._is_path_inside_composite_library(physical_path):
            log_error(f"拒绝创建库外目录: {folder_path}")
            return False
        physical_path.mkdir(parents=True, exist_ok=True)
        
        # 添加到文件夹列表
        self.folders.append(folder_path)
        
        log_info(f"创建文件夹: {folder_path}")
        return True
    
    def delete_folder(
        self, 
        folder_path: str, 
        composites_in_folder: list[CompositeNodeConfig],
        force: bool = False
    ) -> bool:
        """删除文件夹
        
        Args:
            folder_path: 文件夹路径
            composites_in_folder: 文件夹中的复合节点列表
            force: 是否强制删除（包含复合节点的文件夹）
            
        Returns:
            是否成功
        """
        normalized_folder_path = self._try_normalize_relative_folder_path(folder_path, allow_empty=False)
        if normalized_folder_path is None:
            log_error(f"非法文件夹路径: {folder_path}")
            return False
        if normalized_folder_path not in self.folders:
            log_error(f"文件夹不存在: {folder_path}")
            return False
        
        # 检查文件夹中是否有复合节点
        if composites_in_folder and not force:
            log_error(f"文件夹不为空，包含 {len(composites_in_folder)} 个复合节点")
            return False
        
        # 删除物理文件夹
        physical_path = self.composite_library_dir / normalized_folder_path
        if not self._is_path_inside_composite_library(physical_path):
            log_error(f"拒绝删除库外目录: {normalized_folder_path}")
            return False
        if physical_path.exists():
            import shutil
            shutil.rmtree(physical_path)
        
        # 从列表中移除
        self.folders.remove(normalized_folder_path)
        
        log_info(f"删除文件夹: {normalized_folder_path}")
        return True
    
    def validate_target_folder(self, target_folder: str) -> bool:
        """验证目标文件夹是否存在
        
        Args:
            target_folder: 目标文件夹路径（空字符串表示根目录）
            
        Returns:
            是否有效
        """
        # 空字符串表示根目录，总是有效
        if not target_folder:
            return True

        normalized = self._try_normalize_relative_folder_path(target_folder, allow_empty=False)
        if normalized is None:
            return False
        return normalized in self.folders
    
    def list_folders(self) -> list[str]:
        """列出所有文件夹
        
        Returns:
            文件夹路径列表
        """
        return self.folders.copy()

