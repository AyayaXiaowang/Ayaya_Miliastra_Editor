"""
局内存档数据量计算模块

基于引擎实测数据，提供各字段类型的数据量计算能力。

数据量上限：10000 点

测量基准数据（引擎实测）：

结构体开销规律：
- 1个整数的结构体 = 63
- 2个整数的结构体 = 90
- 3个整数的结构体 = 117
- 每增加1个整数字段，增加27点
- 因此：结构体基础开销 = 36，整数字段开销 = 27

单值字段开销与结构体总开销：
- 整数：字段 27，结构体 = 36 + 27 = 63
- 布尔值：字段 15，结构体 = 36 + 15 = 51
- 浮点数：字段 19，结构体 = 36 + 19 = 55
- 字符串：字段 1519，结构体 = 36 + 1519 = 1555
- 三维向量：字段 39，结构体 = 36 + 39 = 75
- GUID：字段 21，结构体 = 36 + 21 = 57
- 配置ID/元件ID/阵营ID：字段 22，结构体 = 36 + 22 = 58

列表字段开销规律：
- 长度0的整数列表结构体 = 51 → 空列表字段开销 = 15
- 长度0的字符串列表结构体 = 51 → 空列表字段开销 = 15（与类型无关！）
- 长度1的整数列表结构体 = 69 → 列表字段 = 15 + 1×18 = 33
- 长度2的整数列表结构体 = 87 → 列表字段 = 15 + 2×18 = 51
- 长度10的整数列表结构体 = 231 → 列表字段 = 15 + 10×18 = 195

列表字段公式：列表基础(15) + N × 元素开销

各类型元素开销与列表10字段开销：
- 整数元素：18，列表10字段 = 15 + 10×18 = 195
- 布尔值元素：3，列表10字段 = 15 + 10×3 = 45
- 浮点数元素：7.5，列表10字段 = 15 + 10×7.5 = 90
- 字符串元素：1504.6，列表10字段 = 15 + 10×1504.6 = 15061
- 三维向量元素：25.5，列表10字段 = 15 + 10×25.5 = 270
- GUID/实体元素：9，列表10字段 = 15 + 10×9 = 105
- 配置ID/元件ID/阵营元素：9，列表10字段 = 15 + 10×9 = 105

注意：单值字段和列表字段是不同的数据结构！
- 单值整数字段 = 27，单值整数结构体 = 36 + 27 = 63
- 长度1整数列表字段 = 15 + 1×18 = 33，长度1整数列表结构体 = 36 + 33 = 69
- 差异：长度1列表比单值多 6 点开销

计算公式：
- 单个结构体实例开销 = 结构体基础(36) + sum(各字段开销)
- 单值字段开销 = 对应类型的单值开销
- 列表字段开销 = 列表基础(15) + N × 元素开销
- 条目总开销 = max_length × 单实例开销
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Optional


# 数据量上限
DATA_COST_LIMIT: int = 10000

# 结构体基础开销（每个结构体实例的固定开销）
STRUCT_BASE_COST: float = 36.0

# 列表字段基础开销（空列表的字段开销，与元素类型无关）
LIST_FIELD_BASE_COST: float = 15.0


@dataclass(frozen=True)
class FieldCostSpec:
    """单个字段类型的数据量规格"""
    single_field_cost: float  # 单值字段的开销
    element_cost: float       # 列表中每个元素的开销

    @property
    def list10_field_cost(self) -> float:
        """长度10列表字段的开销"""
        return LIST_FIELD_BASE_COST + 10 * self.element_cost

    def calculate_single_field_cost(self) -> float:
        """计算单值字段的开销"""
        return self.single_field_cost

    def calculate_list_field_cost(self, length: int) -> float:
        """计算列表字段的开销
        
        Args:
            length: 列表长度，0 表示空列表
            
        Returns:
            列表字段数据量开销（浮点数）
        """
        # 列表字段开销 = 列表基础(15) + N × 元素开销
        return LIST_FIELD_BASE_COST + length * self.element_cost


# ============================================================================
# 字段类型数据量规格表（基于引擎实测数据）
# 注意：这里的开销是字段开销，不包含结构体基础开销(36)
# 列表字段开销 = 列表基础(15) + N × 元素开销
# ============================================================================

# 基础类型
# 单值字段开销 = 结构体开销 - 36
# 元素开销 = (列表10结构体开销 - 36 - 15) / 10
FIELD_COST_INTEGER = FieldCostSpec(single_field_cost=27, element_cost=18)      # 列表10: 15+180=195
FIELD_COST_BOOLEAN = FieldCostSpec(single_field_cost=15, element_cost=3)       # 列表10: 15+30=45
FIELD_COST_FLOAT = FieldCostSpec(single_field_cost=19, element_cost=7.5)       # 列表10: 15+75=90
FIELD_COST_STRING = FieldCostSpec(single_field_cost=1519, element_cost=1504.6) # 列表10: 15+15046=15061
FIELD_COST_VECTOR3 = FieldCostSpec(single_field_cost=39, element_cost=25.5)    # 列表10: 15+255=270
FIELD_COST_GUID = FieldCostSpec(single_field_cost=21, element_cost=9)          # 列表10: 15+90=105

# ID类型（配置ID、元件ID、阵营ID 开销相同）
FIELD_COST_CONFIG_ID = FieldCostSpec(single_field_cost=22, element_cost=9)     # 列表10: 15+90=105
FIELD_COST_COMPONENT_ID = FieldCostSpec(single_field_cost=22, element_cost=9)
FIELD_COST_FACTION_ID = FieldCostSpec(single_field_cost=22, element_cost=9)

# 实体类型（使用 GUID 相同的开销）
FIELD_COST_ENTITY = FieldCostSpec(single_field_cost=21, element_cost=9)


# ============================================================================
# 兼容旧API：TypeCostSpec（包含结构体基础开销的完整结构体开销）
# ============================================================================

@dataclass(frozen=True)
class TypeCostSpec:
    """单个类型的数据量规格（包含结构体基础开销，用于兼容）"""
    single_cost: float  # 单值字段结构体的总开销
    list10_cost: float  # 包含长度10列表字段的结构体总开销

    @property
    def element_cost(self) -> float:
        """每个元素的开销"""
        # 列表10结构体 = 36 + 15 + 10*元素开销
        # 所以元素开销 = (列表10结构体 - 36 - 15) / 10
        return (self.list10_cost - STRUCT_BASE_COST - LIST_FIELD_BASE_COST) / 10.0

    def calculate_cost(self, length: int) -> float:
        """计算指定长度的数据量开销（结构体总开销）
        
        Args:
            length: 元素数量，0 表示空列表，>=1 表示有元素的列表
            
        Returns:
            结构体总数据量开销（浮点数）
        """
        if length <= 0:
            # 空列表结构体 = 36 + 15 = 51
            return STRUCT_BASE_COST + LIST_FIELD_BASE_COST
        # 列表结构体 = 36 + 15 + N * 元素开销
        return STRUCT_BASE_COST + LIST_FIELD_BASE_COST + length * self.element_cost


# 兼容旧API的类型规格（包含结构体基础开销36）
TYPE_COST_INTEGER = TypeCostSpec(single_cost=63, list10_cost=231)
TYPE_COST_BOOLEAN = TypeCostSpec(single_cost=51, list10_cost=81)
TYPE_COST_FLOAT = TypeCostSpec(single_cost=55, list10_cost=126)
TYPE_COST_STRING = TypeCostSpec(single_cost=1555, list10_cost=15097)
TYPE_COST_VECTOR3 = TypeCostSpec(single_cost=75, list10_cost=306)
TYPE_COST_GUID = TypeCostSpec(single_cost=57, list10_cost=141)
TYPE_COST_CONFIG_ID = TypeCostSpec(single_cost=58, list10_cost=141)
TYPE_COST_COMPONENT_ID = TypeCostSpec(single_cost=58, list10_cost=141)
TYPE_COST_FACTION_ID = TypeCostSpec(single_cost=58, list10_cost=141)
TYPE_COST_ENTITY = TypeCostSpec(single_cost=57, list10_cost=141)


# ============================================================================
# 中文类型名到字段规格的映射
# ============================================================================

# 单值类型字段映射
SINGLE_FIELD_COST_MAP: Dict[str, FieldCostSpec] = {
    "整数": FIELD_COST_INTEGER,
    "布尔值": FIELD_COST_BOOLEAN,
    "浮点数": FIELD_COST_FLOAT,
    "字符串": FIELD_COST_STRING,
    "三维向量": FIELD_COST_VECTOR3,
    "GUID": FIELD_COST_GUID,
    "配置ID": FIELD_COST_CONFIG_ID,
    "元件ID": FIELD_COST_COMPONENT_ID,
    "阵营": FIELD_COST_FACTION_ID,
    "实体": FIELD_COST_ENTITY,
}

# 列表类型字段映射（列表类型名 -> 元素类型的字段规格）
LIST_FIELD_COST_MAP: Dict[str, FieldCostSpec] = {
    "整数列表": FIELD_COST_INTEGER,
    "布尔值列表": FIELD_COST_BOOLEAN,
    "浮点数列表": FIELD_COST_FLOAT,
    "字符串列表": FIELD_COST_STRING,
    "三维向量列表": FIELD_COST_VECTOR3,
    "GUID列表": FIELD_COST_GUID,
    "配置ID列表": FIELD_COST_CONFIG_ID,
    "元件ID列表": FIELD_COST_COMPONENT_ID,
    "阵营列表": FIELD_COST_FACTION_ID,
    "实体列表": FIELD_COST_ENTITY,
}

# 兼容旧API的映射
SINGLE_TYPE_COST_MAP: Dict[str, TypeCostSpec] = {
    "整数": TYPE_COST_INTEGER,
    "布尔值": TYPE_COST_BOOLEAN,
    "浮点数": TYPE_COST_FLOAT,
    "字符串": TYPE_COST_STRING,
    "三维向量": TYPE_COST_VECTOR3,
    "GUID": TYPE_COST_GUID,
    "配置ID": TYPE_COST_CONFIG_ID,
    "元件ID": TYPE_COST_COMPONENT_ID,
    "阵营": TYPE_COST_FACTION_ID,
    "实体": TYPE_COST_ENTITY,
}

LIST_TYPE_COST_MAP: Dict[str, TypeCostSpec] = {
    "整数列表": TYPE_COST_INTEGER,
    "布尔值列表": TYPE_COST_BOOLEAN,
    "浮点数列表": TYPE_COST_FLOAT,
    "字符串列表": TYPE_COST_STRING,
    "三维向量列表": TYPE_COST_VECTOR3,
    "GUID列表": TYPE_COST_GUID,
    "配置ID列表": TYPE_COST_CONFIG_ID,
    "元件ID列表": TYPE_COST_COMPONENT_ID,
    "阵营列表": TYPE_COST_FACTION_ID,
    "实体列表": TYPE_COST_ENTITY,
}


def is_list_type(param_type: str) -> bool:
    """判断是否为列表类型"""
    return param_type in LIST_FIELD_COST_MAP or param_type.endswith("列表")


def get_field_cost_spec(param_type: str) -> Optional[FieldCostSpec]:
    """获取字段类型的数据量规格
    
    Args:
        param_type: 参数类型名（中文）
        
    Returns:
        字段类型的数据量规格，如果类型不支持则返回 None
    """
    # 先检查单值类型
    if param_type in SINGLE_FIELD_COST_MAP:
        return SINGLE_FIELD_COST_MAP[param_type]
    
    # 再检查列表类型
    if param_type in LIST_FIELD_COST_MAP:
        return LIST_FIELD_COST_MAP[param_type]
    
    return None


def get_type_cost_spec(param_type: str) -> Optional[TypeCostSpec]:
    """获取类型的数据量规格（兼容旧API，包含结构体基础开销）
    
    Args:
        param_type: 参数类型名（中文）
        
    Returns:
        类型的数据量规格，如果类型不支持则返回 None
    """
    if param_type in SINGLE_TYPE_COST_MAP:
        return SINGLE_TYPE_COST_MAP[param_type]
    if param_type in LIST_TYPE_COST_MAP:
        return LIST_TYPE_COST_MAP[param_type]
    return None


def calculate_field_cost(param_type: str, length: Optional[int] = None) -> float:
    """计算单个字段的数据量开销（不包含结构体基础开销）
    
    Args:
        param_type: 参数类型名（中文）
        length: 列表长度（仅对列表类型有效），None 表示单值类型
        
    Returns:
        字段数据量开销（浮点数）
        
    Raises:
        ValueError: 如果类型不支持数据量计算
    """
    # 检查是否为列表类型
    if param_type in LIST_FIELD_COST_MAP:
        spec = LIST_FIELD_COST_MAP[param_type]
        effective_length = length if length is not None else 0
        return spec.calculate_list_field_cost(effective_length)
    
    # 检查是否为单值类型
    if param_type in SINGLE_FIELD_COST_MAP:
        spec = SINGLE_FIELD_COST_MAP[param_type]
        return spec.calculate_single_field_cost()
    
    raise ValueError(f"不支持的类型: {param_type}")


def calculate_struct_instance_cost(struct_payload: Dict) -> Tuple[float, Dict[str, float]]:
    """计算单个结构体实例的数据量开销
    
    Args:
        struct_payload: 结构体定义（包含 'value' 字段列表）
        
    Returns:
        (单实例总开销, {字段名: 字段开销})
    """
    # 结构体基础开销
    instance_cost = STRUCT_BASE_COST
    field_costs: Dict[str, float] = {}
    
    value_list = struct_payload.get("value", [])
    if not isinstance(value_list, list):
        return instance_cost, {}
    
    for field_def in value_list:
        if not isinstance(field_def, dict):
            continue
        
        field_key = field_def.get("key", "")
        param_type = field_def.get("param_type", "")
        
        if not param_type:
            continue
        
        # 获取列表长度（如果有）
        length: Optional[int] = None
        if is_list_type(param_type):
            length_value = field_def.get("lenth")  # 注意：字段名是 lenth 不是 length
            if isinstance(length_value, int):
                length = length_value
            else:
                length = 1  # 默认长度为1
        
        # 计算字段开销
        field_cost = calculate_field_cost(param_type, length)
        
        field_costs[field_key] = field_cost
        instance_cost += field_cost
    
    return instance_cost, field_costs


def calculate_struct_cost(
    struct_payload: Dict,
    instance_count: int = 1,
) -> Tuple[float, Dict[str, float]]:
    """计算结构体的数据量开销（包含多实例）
    
    Args:
        struct_payload: 结构体定义（包含 'value' 字段列表）
        instance_count: 结构体实例数量（对应 max_length）
        
    Returns:
        (总开销, {字段名: 字段开销 * instance_count})
    """
    instance_cost, field_costs = calculate_struct_instance_cost(struct_payload)
    
    # 总开销 = 单实例开销 × 实例数量
    total_cost = instance_cost * instance_count
    
    # 字段开销也乘以实例数量
    scaled_field_costs = {key: cost * instance_count for key, cost in field_costs.items()}
    
    return total_cost, scaled_field_costs


def calculate_template_total_cost(
    entries: list,
    struct_definitions: Dict[str, Dict],
) -> Tuple[float, Dict[str, float], list]:
    """计算局内存档模板的总数据量
    
    Args:
        entries: 模板的条目列表 [{"struct_id": str, "max_length": int}, ...]
        struct_definitions: 结构体定义字典 {struct_id: struct_payload}
        
    Returns:
        (总开销, {条目index: 条目开销}, 错误列表)
    """
    total_cost = 0.0
    entry_costs: Dict[str, float] = {}
    errors: list = []
    
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        
        struct_id = entry.get("struct_id", "")
        max_length = entry.get("max_length", 1)
        entry_index = entry.get("index", "")
        
        if not struct_id:
            continue
        
        if not isinstance(max_length, int):
            max_length = 1
        
        # 查找结构体定义
        struct_payload = struct_definitions.get(struct_id)
        if struct_payload is None:
            errors.append(f"条目 {entry_index}: 结构体 {struct_id} 未找到")
            continue
        
        # 计算该条目的数据量
        entry_cost, _ = calculate_struct_cost(struct_payload, max_length)
        
        entry_key = str(entry_index) if entry_index else struct_id
        entry_costs[entry_key] = entry_cost
        total_cost += entry_cost
    
    return total_cost, entry_costs, errors


def format_cost_display(cost: float, limit: int = DATA_COST_LIMIT) -> str:
    """格式化数据量显示
    
    Args:
        cost: 数据量
        limit: 上限
        
    Returns:
        格式化的显示字符串，如 "1234 / 10000 (12.3%)"
    """
    percentage = (cost / limit) * 100 if limit > 0 else 0
    return f"{int(cost)} / {limit} ({percentage:.1f}%)"


def check_cost_limit(cost: float, limit: int = DATA_COST_LIMIT) -> Tuple[bool, str]:
    """检查数据量是否超出上限
    
    Args:
        cost: 数据量
        limit: 上限
        
    Returns:
        (是否超限, 错误消息)
    """
    if cost > limit:
        percentage = (cost / limit) * 100
        return True, f"数据量 {int(cost)} 超出上限 {limit} ({percentage:.1f}%)"
    return False, ""


# ============================================================================
# 调试与测试支持
# ============================================================================

def print_type_cost_table() -> None:
    """打印类型数据量对照表"""
    print("=" * 90)
    print("局内存档数据量对照表")
    print("=" * 90)
    print(f"结构体基础开销: {STRUCT_BASE_COST}")
    print(f"列表字段基础开销: {LIST_FIELD_BASE_COST}（空列表字段的固定开销，与元素类型无关）")
    print()
    print(f"{'类型':<15} {'单值字段':<10} {'元素开销':<10} {'列表10字段':<12} {'单值结构体':<12} {'列表10结构体':<12}")
    print("-" * 90)
    
    for type_name, spec in SINGLE_FIELD_COST_MAP.items():
        single_field = spec.single_field_cost
        element = spec.element_cost
        list10_field = spec.list10_field_cost
        single_struct = STRUCT_BASE_COST + single_field
        list10_struct = STRUCT_BASE_COST + list10_field
        print(f"{type_name:<15} {single_field:<10.0f} {element:<10.1f} {list10_field:<12.0f} {single_struct:<12.0f} {list10_struct:<12.0f}")
    
    print()
    print("计算公式:")
    print("  - 单结构体实例 = 结构体基础(36) + sum(字段开销)")
    print("  - 单值字段开销 = 对应类型的单值开销")
    print("  - 列表字段(N) = 列表基础(15) + N × 元素开销")
    print("  - 空列表结构体 = 36 + 15 = 51（与元素类型无关）")
    print("  - 条目总开销 = max_length × 单结构体实例开销")
    print(f"数据量上限: {DATA_COST_LIMIT}")


if __name__ == "__main__":
    print_type_cost_table()
    
    print()
    print("=" * 90)
    print("验证：列表字段开销 = 列表基础(15) + N × 元素开销")
    print("=" * 90)
    
    # 验证用户提供的新数据
    list_test_cases = [
        ("整数列表", 0, 51),    # 36 + 15 + 0×18 = 51（空列表）
        ("字符串列表", 0, 51),  # 36 + 15 + 0×元素 = 51（空列表，与类型无关）
        ("整数列表", 1, 69),    # 36 + 15 + 1×18 = 69
        ("整数列表", 2, 87),    # 36 + 15 + 2×18 = 87
        ("整数列表", 10, 231),  # 36 + 15 + 10×18 = 231
        ("布尔值列表", 10, 81), # 36 + 15 + 10×3 = 81
    ]
    
    print(f"{'类型':<15} {'长度':<6} {'期望结构体':<12} {'计算结构体':<12} {'状态':<6}")
    print("-" * 70)
    
    for type_name, length, expected_struct in list_test_cases:
        field_cost = calculate_field_cost(type_name, length)
        calculated_struct = STRUCT_BASE_COST + field_cost
        diff = abs(calculated_struct - expected_struct)
        status = "✓" if diff < 0.5 else "✗"
        print(f"{type_name:<15} {length:<6} {expected_struct:<12} {calculated_struct:<12.2f} {status}")
    
    print()
    print("=" * 90)
    print("验证：单值字段结构体开销 = 结构体基础(36) + 单值字段开销")
    print("=" * 90)
    
    single_test_cases = [
        ("整数", 63),           # 36 + 27 = 63
        ("布尔值", 51),         # 36 + 15 = 51
        ("浮点数", 55),         # 36 + 19 = 55
        ("字符串", 1555),       # 36 + 1519 = 1555
        ("三维向量", 75),       # 36 + 39 = 75
        ("GUID", 57),          # 36 + 21 = 57
        ("配置ID", 58),         # 36 + 22 = 58
    ]
    
    print(f"{'类型':<15} {'期望结构体':<12} {'计算结构体':<12} {'状态':<6}")
    print("-" * 55)
    
    for type_name, expected_struct in single_test_cases:
        field_cost = calculate_field_cost(type_name)
        calculated_struct = STRUCT_BASE_COST + field_cost
        diff = abs(calculated_struct - expected_struct)
        status = "✓" if diff < 0.1 else "✗"
        print(f"{type_name:<15} {expected_struct:<12} {calculated_struct:<12.2f} {status}")
    
    print()
    print("=" * 90)
    print("验证：多整数字段结构体")
    print("=" * 90)
    
    int_field_cost = calculate_field_cost("整数")
    print(f"整数单值字段开销: {int_field_cost}")
    print(f"1个整数结构体: {STRUCT_BASE_COST} + 1×{int_field_cost} = {STRUCT_BASE_COST + 1*int_field_cost} (期望: 63)")
    print(f"2个整数结构体: {STRUCT_BASE_COST} + 2×{int_field_cost} = {STRUCT_BASE_COST + 2*int_field_cost} (期望: 90)")
    print(f"3个整数结构体: {STRUCT_BASE_COST} + 3×{int_field_cost} = {STRUCT_BASE_COST + 3*int_field_cost} (期望: 117)")
    
    print()
    print("=" * 90)
    print("重要发现：单值字段 ≠ 长度1的列表字段")
    print("=" * 90)
    
    int_single = calculate_field_cost("整数")
    int_list1 = calculate_field_cost("整数列表", 1)
    print(f"单值整数字段: {int_single} → 结构体: {STRUCT_BASE_COST + int_single}")
    print(f"长度1整数列表字段: {int_list1} → 结构体: {STRUCT_BASE_COST + int_list1}")
    print(f"差异: {int_list1 - int_single} 点")
    
    print()
    print("=" * 90)
    print("结论：使用列表比单个存储更划算")
    print("=" * 90)
    
    print("\n示例：存储10个整数")
    single_struct = STRUCT_BASE_COST + calculate_field_cost("整数")
    ten_singles = 10 * single_struct
    list_struct = STRUCT_BASE_COST + calculate_field_cost("整数列表", 10)
    saved = ten_singles - list_struct
    print(f"  10个单独的整数结构体: 10 × {single_struct} = {ten_singles}")
    print(f"  1个包含10元素整数列表的结构体: {list_struct}")
    print(f"  节省: {saved} 点 ({saved/ten_singles*100:.1f}%)")

