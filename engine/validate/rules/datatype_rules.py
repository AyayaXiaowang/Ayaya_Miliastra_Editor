"""数据类型规则定义"""

# 基础数据类型 (基础概念.md:138-153)
BASE_TYPES = {
    "实体": {
        "display_name": "实体",
        "description": "代表了一个运行时的实体",
        "default": 0,
        "default_meaning": "无实际意义，指向了一个不存在的实体",
        "reference": "基础概念.md:145",
    },
    
    "GUID": {
        "display_name": "GUID",
        "description": "实体在场景中布设时的GUID。对于动态创建的实体来说GUID=0",
        "default": 0,
        "reference": "基础概念.md:146",
        "note": "GUID 在引擎内就是数字 ID（也可用字符串包裹数字）表示的标识，纯数字形态是正常的；若编辑器把数字 GUID 当格式错误标红，可在使用处忽略对应的静态检查提示。",
    },
    
    "整数": {
        "display_name": "整数",
        "description": "32位带符号整型数",
        "default": 0,
        "range": (-2147483648, 2147483647),
        "overflow": "超出范围会自动上/下溢出",
        "overflow_example": "2147483648会自动变为-2147483648",
        "reference": "基础概念.md:147",
    },
    
    "布尔值": {
        "display_name": "布尔值",
        "description": "布尔型。只有【是】和【否】两个取值",
        "default": False,
        "values": [True, False],
        "reference": "基础概念.md:148",
    },
    
    "浮点数": {
        "display_name": "浮点数",
        "description": "单精度浮点数",
        "default": 0.0,
        "range": "约±1.5 x 10^−45 至 ±3.4 x 10^38",
        "overflow": "修正为0",
        "overflow_note": "与多数编程语言不同，不使用Inf或NaN，发生溢出时修正为0",
        "reference": "基础概念.md:149",
    },
    
    "字符串": {
        "display_name": "字符串",
        "description": "字符串类型，用于表示文本数据",
        "default": "",
        "max_length_en": 40,  # 英文字符
        "max_length_zh": 13,  # 约13个中文字符
        "note": "最长不能超过40个英文字符（约13个中文字符）",
        "reference": "基础概念.md:150",
    },
    
    "三维向量": {
        "display_name": "三维向量",
        "description": "三维向量类型，每个分量都是一个浮点数",
        "default": (0, 0, 0),
        "component_overflow": "单个分量发生溢出时，按照浮点数的溢出规则处理",
        "reference": "基础概念.md:151",
    },
    
    "元件ID": {
        "display_name": "元件ID",
        "description": "元件的ID，对应一个特定的元件",
        "default": 0,
        "default_meaning": "无实际意义，指向了一个不存在的元件",
        "reference": "基础概念.md:152",
    },
    
    "配置ID": {
        "display_name": "配置ID",
        "description": "通用配置的ID，例如：单位状态的ID、职业的ID等",
        "default": 0,
        "default_meaning": "无实际意义，指向了一个不存在的配置",
        "reference": "基础概念.md:153",
    },
}


# 列表数据类型 (基础概念.md:155-174)
LIST_TYPES = {
    "实体列表": {
        "base_type": "实体",
        "description": "实体列表类型",
        "index_start": 0,  # 基础概念.md:173 "列表的索引从0开始计数"
        "pass_by": "引用",  # 基础概念.md:174 "列表使用【引用传值】的形式进行参数传递"
        "reference": "基础概念.md:160",
    },
    "GUID列表": {
        "base_type": "GUID",
        "index_start": 0,
        "pass_by": "引用",
        "reference": "基础概念.md:161",
    },
    "整数列表": {
        "base_type": "整数",
        "index_start": 0,
        "pass_by": "引用",
        "example": "{1, 3, 5, 7, 9}",  # 基础概念.md:170
        "reference": "基础概念.md:162",
    },
    "布尔值列表": {
        "base_type": "布尔值",
        "index_start": 0,
        "pass_by": "引用",
        "reference": "基础概念.md:163",
    },
    "浮点数列表": {
        "base_type": "浮点数",
        "index_start": 0,
        "pass_by": "引用",
        "reference": "基础概念.md:164",
    },
    "字符串列表": {
        "base_type": "字符串",
        "index_start": 0,
        "pass_by": "引用",
        "reference": "基础概念.md:165",
    },
    "三维向量列表": {
        "base_type": "三维向量",
        "index_start": 0,
        "pass_by": "引用",
        "reference": "基础概念.md:166",
    },
    "元件ID列表": {
        "base_type": "元件ID",
        "index_start": 0,
        "pass_by": "引用",
        "reference": "基础概念.md:167",
    },
    "配置ID列表": {
        "base_type": "配置ID",
        "index_start": 0,
        "pass_by": "引用",
        "reference": "基础概念.md:168",
    },
}


# 类型转换规则 (基础概念.md:176-191)
TYPE_CONVERSIONS = {
    ("整数", "布尔值"): {
        "rule": "0转为否，非0转为是",
        "examples": [
            ("0", "否"),
            ("5", "是"),
        ],
        "reference": "基础概念.md:181",
    },
    
    ("整数", "浮点数"): {
        "rule": "整数转浮点数",
        "examples": [
            ("1", "1.0"),
            ("-2", "-2.0"),
            ("0", "0.0"),
        ],
        "reference": "基础概念.md:182",
    },
    
    ("整数", "字符串"): {
        "rule": "整数转字符串",
        "examples": [
            ("1", '"1"'),
            ("15", '"15"'),
        ],
        "reference": "基础概念.md:183",
    },
    
    ("布尔值", "整数"): {
        "rule": "否转为0，是转为1",
        "examples": [
            ("否", "0"),
            ("是", "1"),
        ],
        "reference": "基础概念.md:186",
    },
    
    ("布尔值", "字符串"): {
        "rule": '返回"是"和"否"',
        "examples": [
            ("否", '"否"'),
            ("是", '"是"'),
        ],
        "reference": "基础概念.md:187",
    },
    
    ("浮点数", "整数"): {
        "rule": "截尾转为整数，与取整节点的截尾功能相同",
        "examples": [
            ("2.5", "2"),
            ("-1.31", "-1"),
            ("0.0", "0"),
        ],
        "reference": "基础概念.md:188",
    },
    
    ("浮点数", "字符串"): {
        "rule": "输出浮点数对应的字符串，至多保留6位有效数字",
        "examples": [
            ("2.5", '"2.5"'),
            ("-1.317524", '"-1.31752"'),
        ],
        "reference": "基础概念.md:189",
    },
    
    ("三维向量", "字符串"): {
        "rule": '返回"(分量1,分量2,分量3)"格式的字符串。每个分量保留1位小数',
        "examples": [
            ("(1.05, 2.3, 3)", '"(1.0, 2.3, 3.0)"'),
        ],
        "reference": "基础概念.md:190",
    },
    
    ("实体", "字符串"): {
        "rule": "输出实体的运行时id",
        "examples": [
            ("某个实体", '"1001"'),
        ],
        "reference": "基础概念.md:184",
    },
    
    ("GUID", "字符串"): {
        "rule": "输出GUID对应的字符串",
        "examples": [
            ("某个实体", '"100001"'),
        ],
        "reference": "基础概念.md:185",
    },
    
    ("阵营", "字符串"): {
        "rule": "返回阵营的id转为的字符串",
        "examples": [
            ("某个实体上的阵营", '"2"'),
        ],
        "reference": "基础概念.md:191",
    },
}


def get_type_default(type_name: str):
    """获取类型的默认值"""
    if type_name in BASE_TYPES:
        return BASE_TYPES[type_name]["default"]
    if type_name in LIST_TYPES:
        return []
    return None


def can_convert_type(from_type: str, to_type: str) -> tuple[bool, str]:
    """检查是否可以进行类型转换
    
    Returns:
        (是否可以转换, 转换规则说明)
    """
    key = (from_type, to_type)
    if key in TYPE_CONVERSIONS:
        conversion = TYPE_CONVERSIONS[key]
        return True, conversion["rule"]
    return False, f"不支持从'{from_type}'到'{to_type}'的类型转换"


def get_type_info(type_name: str) -> dict:
    """获取类型的完整信息"""
    if type_name in BASE_TYPES:
        return BASE_TYPES[type_name]
    if type_name in LIST_TYPES:
        return LIST_TYPES[type_name]
    return {}

