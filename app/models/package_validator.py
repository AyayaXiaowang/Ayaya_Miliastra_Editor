"""存档规范验证器"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, TYPE_CHECKING, Optional, Any

if TYPE_CHECKING:
    from engine.resources.package_interfaces import PackageLike


@dataclass
class ValidationIssue:
    """验证问题"""
    level: str  # "error", "warning", "info"
    category: str  # "level_entity", "ui_controls", "templates", etc.
    message: str
    suggestion: str = ""
    
    def __str__(self) -> str:
        prefix = {
            "error": "❌ 错误",
            "warning": "⚠️ 警告",
            "info": "ℹ️ 提示"
        }.get(self.level, "·")
        
        result = f"{prefix} [{self.category}] {self.message}"
        if self.suggestion:
            result += f"\n   建议：{self.suggestion}"
        return result


class PackageValidator:
    """存档验证器 - 检查存档是否符合UGC规范。

    说明：
        - `package` 接受任意包级视图对象（实现了 `PackageLike` 协议）；
        - 对于关卡实体，优先通过 level_entity.instance_id 反查模板，再退回旧的模板级 level_entity。
    """
    
    def __init__(self, package: "PackageLike"):
        self.package = package
        self.issues: List[ValidationIssue] = []
    
    def validate_all(self) -> List[ValidationIssue]:
        """执行所有验证检查"""
        self.issues = []
        
        self._check_level_entity()
        self._check_ui_controls_location()
        self._check_template_types()
        self._check_level_entity_components()
        
        return self.issues
    
    def _check_level_entity(self) -> None:
        """检查关卡实体的唯一性和存在性"""
        level_entity = getattr(self.package, "level_entity", None)
        # 关卡实体缺失
        if not level_entity:
            self.issues.append(ValidationIssue(
                level="error",
                category="关卡实体",
                message="存档缺少关卡实体",
                suggestion="每个存档必须有且仅有一个关卡实体，用于承载关卡逻辑"
            ))
        else:
            # 在离散资源架构下，level_entity 通常是 InstanceConfig，需要通过模板反推类型。
            entity_type: Optional[str] = None
            template = None
            template_id = getattr(level_entity, "template_id", "") or ""
            if template_id and hasattr(self.package, "get_template"):
                template = self.package.get_template(template_id)  # type: ignore[assignment]
            if template is not None and hasattr(template, "entity_type"):
                entity_type = getattr(template, "entity_type")
            elif hasattr(level_entity, "entity_type"):
                # 兼容旧的模板级 level_entity
                entity_type = getattr(level_entity, "entity_type")

            if entity_type != "关卡":
                display_type = entity_type if entity_type is not None else "未知"
                self.issues.append(ValidationIssue(
                    level="error",
                    category="关卡实体",
                    message=f"关卡实体的类型不正确：{display_type}，应为'关卡'",
                    suggestion="请确保关卡实体的 entity_type 字段设置为'关卡'"
                ))
        
        # 检查templates中是否误添加了关卡类型
        level_templates = [t for t in self.package.templates.values() if t.entity_type == "关卡"]
        if level_templates:
            self.issues.append(ValidationIssue(
                level="error",
                category="关卡实体",
                message=f"元件库中包含{len(level_templates)}个关卡类型的模板，这不符合规范",
                suggestion="关卡实体应该存储在level_entity字段中，而不是templates中。请移除这些模板。"
            ))
    
    def _check_ui_controls_location(self) -> None:
        """检查UI控件是否在正确的位置"""
        # 检查templates中是否误添加了UI控件
        ui_templates = [t for t in self.package.templates.values() if t.entity_type == "UI控件"]
        if ui_templates:
            self.issues.append(ValidationIssue(
                level="warning",
                category="UI控件",
                message=f"元件库中包含{len(ui_templates)}个UI控件类型的模板",
                suggestion="UI控件属于资产类型，不应该在元件库(templates)中。考虑将其移到专门的UI资产管理区域。"
            ))
        
        # 检查UI控件是否被挂载到节点图
        # （这个检查比较复杂，暂时跳过，留作后续优化）
    
    def _check_template_types(self) -> None:
        """检查模板类型的合法性"""
        valid_template_types = {"角色", "物件", "造物", "本地投射物", "玩家"}
        
        for template_id, template in self.package.templates.items():
            if template.entity_type not in valid_template_types:
                self.issues.append(ValidationIssue(
                    level="warning",
                    category="模板类型",
                    message=f"模板'{template.name}'的类型'{template.entity_type}'可能不适合放在元件库中",
                    suggestion=f"元件库应只包含可摆放的实体类型：{', '.join(valid_template_types)}"
                ))
    
    def _check_level_entity_components(self) -> None:
        """检查关卡实体的组件配置"""
        level_entity = getattr(self.package, "level_entity", None)
        if not level_entity:
            return

        # 关卡实体组件通常定义在模板上；实例只引用该模板。
        template = None
        template_id = getattr(level_entity, "template_id", "") or ""
        if template_id and hasattr(self.package, "get_template"):
            template = self.package.get_template(template_id)  # type: ignore[assignment]
        if template is None and hasattr(level_entity, "default_components"):
            template = level_entity  # 兼容旧的模板级 level_entity

        if template is None or not hasattr(template, "default_components"):
            return

        # 关卡实体的可用组件：自定义变量、全局计时器
        valid_components = {"自定义变量", "全局计时器"}

        for comp in getattr(template, "default_components", []):
            component_type = getattr(comp, "component_type", "")
            if component_type not in valid_components:
                self.issues.append(ValidationIssue(
                    level="warning",
                    category="关卡实体",
                    message=f"关卡实体包含组件'{component_type}'，可能不受支持",
                    suggestion=f"关卡实体的可用组件：{', '.join(valid_components)}"
                ))
    
    def get_summary(self) -> str:
        """获取验证摘要"""
        if not self.issues:
            return "✅ 存档符合所有规范要求"
        
        error_count = sum(1 for i in self.issues if i.level == "error")
        warning_count = sum(1 for i in self.issues if i.level == "warning")
        info_count = sum(1 for i in self.issues if i.level == "info")
        
        summary = f"发现 {len(self.issues)} 个问题："
        if error_count > 0:
            summary += f" {error_count} 个错误"
        if warning_count > 0:
            summary += f" {warning_count} 个警告"
        if info_count > 0:
            summary += f" {info_count} 个提示"
        
        return summary


