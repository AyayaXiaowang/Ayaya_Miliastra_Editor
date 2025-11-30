from __future__ import annotations

from typing import Any, Dict, List


# 引擎默认配置（可被 CLI/调用方覆盖）
DEFAULT_CONFIG: Dict[str, Any] = {
    "STRICT_ENTITY_INPUTS_WIRE_ONLY": False,
    # M2：原子规则开关（默认开启）
    "ENABLE_ATOMIC_RULES_M2": True,
    # M3：原子规则（类型匹配/未使用输出/不可达/复合节点等）默认开启
    "ENABLE_RULES_M3": True,
    "ENABLE_RULES_M3_COMPOSITE": True,
    # 规则白名单（方法调用）——用于允许少量运行时 API（如事件注册）
    # 1) 基于完整链路名匹配：如 "self.game.register_event_handler"
    # 2) 基于方法名匹配：如 "register_event_handler"
    "ALLOW_METHOD_CALLS": [
        "self.game.register_event_handler",
    ],
    "ALLOW_METHOD_CALL_NAMES": [
        "register_event_handler",
    ],
    "THRESHOLDS": {
        # “事件源实体”长连线：同一方法内使用次数阈值（严格模式可降低）
        "LONG_WIRE_USAGE_MAX": 2,
        # “事件源实体”长连线：大致跨度阈值（以源码行距衡量）
        "LONG_WIRE_LINE_SPAN_MIN": 50,
    },
    # 误报豁免（引擎层过滤）：按 error_code + 条件
    "EXEMPTIONS": [
        # 示例：若未来需要在复合节点下豁免特定结构问题，可配置如下：
        # {"code": "STRUCT_COMPOSITE_LEGACY", "when": {"is_composite": True}},
    ],
}


def merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """浅合并配置（dict of dict）。"""
    result: Dict[str, Any] = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            nv = dict(result[k])
            nv.update(v)
            result[k] = nv
        else:
            result[k] = v
    return result


def _match_condition(issue: Any, ctx: Any, cond: Dict[str, Any]) -> bool:
    """简单条件匹配：支持 is_composite、message_contains、message_contains_any。"""
    if "is_composite" in cond:
        if bool(cond["is_composite"]) != bool(getattr(ctx, "is_composite", False)):
            return False
    msg = getattr(issue, "message", "") or ""
    if "message_contains" in cond:
        if cond["message_contains"] not in msg:
            return False
    if "message_contains_any" in cond:
        arr = cond["message_contains_any"]
        if not any(s in msg for s in arr):
            return False
    return True


def apply_exemptions(issues: List[Any], ctx: Any, config: Dict[str, Any]) -> List[Any]:
    """根据配置过滤需要豁免的问题。"""
    rules = config.get("EXEMPTIONS", [])
    if not rules:
        return issues

    filtered: List[Any] = []
    for iss in issues:
        code = getattr(iss, "code", None)
        exempted = False
        for rule in rules:
            if rule.get("code") == code:
                if _match_condition(iss, ctx, rule.get("when", {})):
                    exempted = True
                    break
        if not exempted:
            filtered.append(iss)
    return filtered


