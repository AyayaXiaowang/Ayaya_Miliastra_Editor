"""复合节点文件夹管理器 - 负责文件夹的创建、删除和节点移动"""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from engine.utils.logging.logger import log_info, log_error

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
    
    def scan_folders(self) -> None:
        """扫描并收集所有文件夹"""
        self.folders.clear()
        for item in self.composite_library_dir.rglob("*"):
            if item.is_dir() and item.name != "__pycache__":
                relative_path = str(item.relative_to(self.composite_library_dir))
                if relative_path not in self.folders:
                    self.folders.append(relative_path)
    
    def create_folder(self, folder_name: str, parent_folder: str = "") -> bool:
        """创建文件夹
        
        Args:
            folder_name: 文件夹名称
            parent_folder: 父文件夹路径（空字符串表示根目录）
            
        Returns:
            是否成功
        """
        # 构建完整路径
        if parent_folder:
            folder_path = f"{parent_folder}/{folder_name}"
        else:
            folder_path = folder_name
        
        # 检查是否已存在
        if folder_path in self.folders:
            log_error(f"文件夹已存在: {folder_path}")
            return False
        
        # 创建物理文件夹
        physical_path = self.composite_library_dir / folder_path
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
        if folder_path not in self.folders:
            log_error(f"文件夹不存在: {folder_path}")
            return False
        
        # 检查文件夹中是否有复合节点
        if composites_in_folder and not force:
            log_error(f"文件夹不为空，包含 {len(composites_in_folder)} 个复合节点")
            return False
        
        # 删除物理文件夹
        physical_path = self.composite_library_dir / folder_path
        if physical_path.exists():
            import shutil
            shutil.rmtree(physical_path)
        
        # 从列表中移除
        self.folders.remove(folder_path)
        
        log_info(f"删除文件夹: {folder_path}")
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
        
        return target_folder in self.folders
    
    def list_folders(self) -> list[str]:
        """列出所有文件夹
        
        Returns:
            文件夹路径列表
        """
        return self.folders.copy()

