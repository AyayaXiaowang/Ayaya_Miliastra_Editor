from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .context import ValidationContext
from .issue import EngineIssue, ValidationReport
from .pipeline import ValidationPipeline, ValidationRule
from .config import DEFAULT_CONFIG, merge_config, apply_exemptions
from .validation_cache import (
    build_rules_hash,
    load_validation_cache,
    save_validation_cache,
    try_load_cached_issues_for_file,
    update_validation_cache_for_file,
)

# 合并规则模块（仅基于 M2/M3 原子规则与复合节点结构规则，不再依赖旧适配器）
from .rules.code_syntax_rules import (
    NoListDictLiteralRule,
    NoFStringLambdaEnumerateRule,
    MatchCaseLiteralPatternRule,
    NoMethodNestedCallsRule,
    NoInlineIfInCallRule,
    NoInlineArithmeticInRangeRule,
)
from .rules.code_structure_rules import (
    IfBooleanRule,
    NoDirectLogicNotCallInIfRule,
    IfBoolEqualityToConstRule,
    VariadicMinArgsRule,
    GraphVarsDeclarationRule,
    NoLiteralAssignmentRule,
    UnknownNodeCallRule,
    EventHandlerNameRule,
    EventNameRule,
    OnMethodNameRule,
    TypeNameRule,
    SignalParamNamesRule,
    RequiredInputsRule,
    StructNameRequiredRule,
    LocalVarInitialValueRule,
    LocalVarUsageRule,
    NodeCallGameRequiredRule,
)
from .rules.code_quality_rules import (
    LongWireRule,
    EventMultipleFlowOutputsRule,
    PullEvalReevaluationHazardRule,
    UnusedQueryOutputRule,
    UnreachableCodeRule,
)
from .rules.code_port_types_match import PortTypesMatchRule
from .rules.composite_types_nesting import CompositeTypesAndNestingRule
from .rules.node_index import clear_node_index_caches
from engine.nodes.composite_file_policy import is_composite_definition_file

_RULE_CACHE: Dict[Tuple[bool, Tuple[Any, ...]], List[ValidationRule[EngineIssue]]] = {}


def _freeze_config_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze_config_value(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(_freeze_config_value(item) for item in value)
    return value


def _is_composite_file(path: Path) -> bool:
    """判断文件是否应按“复合节点”规则集校验。"""
    return is_composite_definition_file(path)


def _build_rules(config: Dict[str, Any], *, is_composite: bool) -> List[ValidationRule[EngineIssue]]:
    """根据配置构建规则列表，避免在每个文件上重复实例化。"""
    cfg = config or {}
    atomic_enabled = bool(cfg.get("ENABLE_ATOMIC_RULES_M2", True))
    m3_enabled = bool(cfg.get("ENABLE_RULES_M3", True))
    composite_enabled = bool(cfg.get("ENABLE_RULES_M3_COMPOSITE", True))
    signature = (
        atomic_enabled,
        m3_enabled,
        composite_enabled,
        bool(cfg.get("STRICT_ENTITY_INPUTS_WIRE_ONLY", False)),
        _freeze_config_value(cfg.get("ALLOW_METHOD_CALLS", [])),
        _freeze_config_value(cfg.get("ALLOW_METHOD_CALL_NAMES", [])),
        _freeze_config_value(cfg.get("THRESHOLDS", {})),
    )
    cache_key = (is_composite, signature)
    cached_rules = _RULE_CACHE.get(cache_key)
    if cached_rules is not None:
        return cached_rules
    if is_composite:
        if composite_enabled:
            rules = [
                CompositeTypesAndNestingRule(),
                LocalVarInitialValueRule(),
                LocalVarUsageRule(),
                NodeCallGameRequiredRule(),
                NoListDictLiteralRule(),
                MatchCaseLiteralPatternRule(),
            ]
            _RULE_CACHE[cache_key] = rules
            return rules
        _RULE_CACHE[cache_key] = []
        return []

    rules: List[ValidationRule[EngineIssue]] = []
    if atomic_enabled:
        rules.extend(
            [
                NoListDictLiteralRule(),
                MatchCaseLiteralPatternRule(),
                NoFStringLambdaEnumerateRule(),
                NoMethodNestedCallsRule(),
                NoInlineIfInCallRule(),
                NoInlineArithmeticInRangeRule(),
                IfBooleanRule(),
                NoDirectLogicNotCallInIfRule(),
                IfBoolEqualityToConstRule(),
                VariadicMinArgsRule(),
                RequiredInputsRule(),
                GraphVarsDeclarationRule(),
                NoLiteralAssignmentRule(),
                UnknownNodeCallRule(),
                EventHandlerNameRule(),
                EventNameRule(),
                OnMethodNameRule(),
                TypeNameRule(),
                LongWireRule(),
                EventMultipleFlowOutputsRule(),
                PullEvalReevaluationHazardRule(),
                SignalParamNamesRule(),
                StructNameRequiredRule(),
                LocalVarInitialValueRule(),
                LocalVarUsageRule(),
                NodeCallGameRequiredRule(),
            ]
        )
    if m3_enabled:
        rules.extend(
            [
                PortTypesMatchRule(),
                UnusedQueryOutputRule(),
                UnreachableCodeRule(),
            ]
        )
    _RULE_CACHE[cache_key] = rules
    return rules


def validate_files(
    paths: Iterable[Path],
    workspace: Path,
    strict_entity_wire_only: bool = False,
    use_cache: bool = True,
) -> ValidationReport:
    """验证一组节点图文件（类结构 + 复合节点）

    说明：
        - 这是节点图验证的统一底层入口，所有 CLI / UI / runtime 都应通过此函数间接调用验证引擎。
        - 接受任意可迭代的路径序列，内部会先收敛为列表，以便统计与二次遍历时行为一致。
    """
    paths_list = list(paths)
    clear_node_index_caches()
    override = {
        "STRICT_ENTITY_INPUTS_WIRE_ONLY": bool(strict_entity_wire_only),
    }
    config = merge_config(DEFAULT_CONFIG, override)
    issues: List[EngineIssue] = []
    composite_rules = _build_rules(config, is_composite=True)
    standard_rules = _build_rules(config, is_composite=False)
    composite_pipeline = ValidationPipeline(rules=composite_rules)
    standard_pipeline = ValidationPipeline(rules=standard_rules)

    cache_data: Dict[str, Any] = {}
    rules_hash = ""
    if use_cache:
        cache_data = load_validation_cache(workspace)
        rules_hash = build_rules_hash(
            config,
            standard_rules,
            composite_rules,
            workspace=workspace,
        )
    for file_path in paths_list:
        if use_cache and rules_hash:
            cached = try_load_cached_issues_for_file(
                workspace=workspace,
                file_path=file_path,
                cache=cache_data,
                current_rules_hash=rules_hash,
            )
            if cached is not None:
                issues.extend(cached)
                continue
        ctx = ValidationContext(
            workspace_path=workspace,
            file_path=file_path,
            is_composite=_is_composite_file(file_path),
            config=config,
        )
        pipeline = composite_pipeline if ctx.is_composite else standard_pipeline
        produced = pipeline.run(ctx)
        produced = apply_exemptions(produced, ctx, config)
        issues.extend(produced)
        if use_cache and rules_hash:
            update_validation_cache_for_file(
                workspace=workspace,
                file_path=file_path,
                cache=cache_data,
                current_rules_hash=rules_hash,
                issues=produced,
            )
    if use_cache and rules_hash:
        save_validation_cache(workspace, cache_data)

    stats = {
        "files": len(paths_list),
        "errors": len([i for i in issues if i.level == "error"]),
        "warnings": len([i for i in issues if i.level == "warning"]),
    }
    return ValidationReport(issues=issues, stats=stats, config=config)

 