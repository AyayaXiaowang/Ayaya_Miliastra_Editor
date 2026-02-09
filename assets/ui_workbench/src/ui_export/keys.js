export function sanitizeIdPart(raw) {
    var text = String(raw || "").trim();
    if (!text) {
        return "";
    }
    // 说明：
    // - UI 侧大量使用中文 `data-debug-label`/`data-ui-key`，若 sanitize 只允许 ASCII，
    //   会把中文全部打成 "_" 并最终变空串，导致 ui_key / __html_component_key 退化为 elementIndex（e30 等），
    //   从而出现“不同按钮被误打成同一组 / GUID 复用覆盖”的问题。
    //
    // 因此这里允许中文（CJK Unified Ideographs），保证 key 稳定且可读。
    return text.replace(/[^a-zA-Z0-9\u4e00-\u9fff_\-]+/g, "_").replace(/^_+|_+$/g, "");
}

// 当前一次导出过程使用的“页面前缀”（用于避免跨页面/跨布局 ui_key 冲突）
var _stableUiKeyPrefix = "";

export function setStableUiKeyPrefix(rawPrefix) {
    var prefixText = String(rawPrefix || "").trim();
    if (!prefixText) {
        _stableUiKeyPrefix = "";
        return;
    }
    _stableUiKeyPrefix = sanitizeIdPart(prefixText);
}

function _joinStablePrefix(prefix, key) {
    var p = String(prefix || "").trim();
    var base = String(key || "").trim();
    if (!base) {
        return "";
    }
    if (!p) {
        return base;
    }
    return p + "__" + base;
}

export function buildStableUiKeyBase(source) {
    // 稳定 UIKey 的来源优先级（越靠前越推荐）：
    // 1) data-ui-key：显式声明“逻辑控件 key”（最稳定）
    // 2) element id：HTML 原生 id
    // 3) data-debug-label：Workbench/调试用标签
    // 4) dataLabel：由提取器给的 class/语义画像
    // 5) elementIndex：兜底（可能随 DOM 变化漂移，不建议长期依赖）
    if (!source) {
        return "";
    }
    var attrs = source.attributes || null;
    var explicitKey = attrs ? String(attrs.dataUiKey || "").trim() : "";
    var stateGroup = attrs ? String(attrs.dataUiStateGroup || "").trim() : "";
    var stateKey = attrs ? String(attrs.dataUiState || "").trim() : "";
    // 多状态：允许复用同一个 data-ui-key，通过 data-ui-state 区分为不同稳定 key。
    // 例如：data-ui-key="level_01_bg" + data-ui-state="normal|selected"
    if (stateGroup) {
        var base0 = explicitKey ? sanitizeIdPart(explicitKey) : "";
        if (!base0) {
            base0 = sanitizeIdPart(stateGroup);
        }
        var statePart0 = stateKey ? sanitizeIdPart(stateKey) : "state";
        return (base0 ? (base0 + "__" + statePart0) : statePart0);
    }
    if (explicitKey) {
        return sanitizeIdPart(explicitKey);
    }

    var idPart = source.id ? sanitizeIdPart(source.id) : "";
    if (idPart) {
        return idPart;
    }

    var debugLabel = attrs ? String(attrs.dataDebugLabel || "").trim() : "";
    var labelPart = debugLabel ? sanitizeIdPart(debugLabel) : "";
    if (labelPart) {
        return labelPart;
    }

    var classPart = source.dataLabel ? sanitizeIdPart(source.dataLabel) : "";
    if (classPart) {
        return classPart;
    }

    if (Number.isFinite(source.elementIndex)) {
        return "e" + String(Math.trunc(source.elementIndex));
    }
    return "";
}

export function buildStableUiKey(source, kind) {
    // 需要区分 kind：同一 HTML 元素可能会导出多个 widget（shadow/border/text/...）
    var base = buildStableUiKeyBase(source);
    var kindText = String(kind || "").trim();
    var parts = [];
    if (_stableUiKeyPrefix) {
        parts.push(_stableUiKeyPrefix);
    }
    if (base) {
        parts.push(base);
    }
    if (kindText) {
        parts.push(kindText);
    }
    return parts.filter(function (x) { return !!x; }).join("__");
}

function _buildStableHtmlComponentKeyInternal(source, stablePrefix) {
    // “组件级”稳定 key：只用于“原子组”打组，必须能精确指向同一个 DOM 元素，
    // 严禁依赖 class 画像（dataLabel），否则不同按钮（同 class）会被误合并。
    //
    // 来源优先级（越靠前越推荐）：
    // 1) data-ui-key
    // 2) element id
    // 3) data-debug-label
    // 4) elementIndex（兜底）
    if (!source) {
        return "";
    }
    var prefix = String(stablePrefix || "").trim();
    var attrs = source.attributes || null;
    var explicitKey = attrs ? String(attrs.dataUiKey || "").trim() : "";
    var explicitComponentKey = attrs ? String(attrs.dataUiComponentKey || "").trim() : "";
    var stateGroup = attrs ? String(attrs.dataUiStateGroup || "").trim() : "";
    var stateKey = attrs ? String(attrs.dataUiState || "").trim() : "";

    // 多状态（关键）：若当前元素标注了 data-ui-state-*，必须优先以自身 state 作为组件 key 的一部分，
    // 即使 flatten 阶段给出了 componentOwner 也不应“归属到 owner”。
    // 否则会把不同状态的内容合并进同一个组容器，节点图无法做到“整组切换显隐”。
    if (stateGroup) {
        // 根因修复（多状态整组）：
        // - 写回端的“组件打组”是按 widget.__html_component_key 分组创建组容器（见 ui_patchers/web_ui_import_grouping.py）。
        // - 约定：当处于 data-ui-state-group 作用域内，“一个 state 的所有内容必须落到一个组件组里”，
        //   因此组件组 key 只由 stateGroup + stateKey 决定（不掺入子元素 data-ui-key）。
        var base0 = sanitizeIdPart(stateGroup);
        var statePart0 = stateKey ? sanitizeIdPart(stateKey) : "state";
        var composed = (base0 ? (base0 + "__" + statePart0) : statePart0);
        return _joinStablePrefix(prefix, composed);
    }

    // 可选：用户显式声明“组件组 key”（用于把多个控件强制归到同一个组件组里）。
    // 典型用途：把“选关 + 退出”两个按钮视为同一个可复用控件组模板。
    if (explicitComponentKey) {
        var compKeyPart0 = sanitizeIdPart(explicitComponentKey);
        if (compKeyPart0) {
            return _joinStablePrefix(prefix, compKeyPart0);
        }
    }

    // 若 flatten 阶段提供了 componentOwner，则优先使用（把 span 文本归属到 button 本体）
    if (attrs) {
        var ownerComponentKey = String(attrs.componentOwnerDataUiComponentKey || "").trim();
        if (ownerComponentKey) {
            var ownerCompPart = sanitizeIdPart(ownerComponentKey);
            if (ownerCompPart) {
                return _joinStablePrefix(prefix, ownerCompPart);
            }
        }
        var ownerUiKey = String(attrs.componentOwnerDataUiKey || "").trim();
        if (ownerUiKey) {
            var ownerUiKeyPart = sanitizeIdPart(ownerUiKey);
            return _joinStablePrefix(prefix, ownerUiKeyPart);
        }
        var ownerId = String(attrs.componentOwnerId || "").trim();
        if (ownerId) {
            var ownerIdPart = sanitizeIdPart(ownerId);
            return _joinStablePrefix(prefix, ownerIdPart);
        }
        var ownerDbg = String(attrs.componentOwnerDataDebugLabel || "").trim();
        if (ownerDbg) {
            var ownerDbgPart = sanitizeIdPart(ownerDbg);
            return _joinStablePrefix(prefix, ownerDbgPart);
        }

        // owner 没有显式 key 时，允许用 owner 的 elementIndex 做兜底（仅在“没有任何显式 key”的场景触发）
        var ownerElementIndexText = String(attrs.componentOwnerElementIndex || "").trim();
        if (ownerElementIndexText && /^\d+$/.test(ownerElementIndexText)) {
            var ownerIndexPart = "e" + String(Math.trunc(Number(ownerElementIndexText)));
            return _joinStablePrefix(prefix, ownerIndexPart);
        }
    }
    if (explicitKey) {
        explicitKey = sanitizeIdPart(explicitKey);
        return _joinStablePrefix(prefix, explicitKey);
    }

    var idPart = source.id ? sanitizeIdPart(source.id) : "";
    if (idPart) {
        return _joinStablePrefix(prefix, idPart);
    }

    var debugLabel = attrs ? String(attrs.dataDebugLabel || "").trim() : "";
    var labelPart = debugLabel ? sanitizeIdPart(debugLabel) : "";
    if (labelPart) {
        return _joinStablePrefix(prefix, labelPart);
    }

    if (Number.isFinite(source.elementIndex)) {
        var fallback = "e" + String(Math.trunc(source.elementIndex));
        return _joinStablePrefix(prefix, fallback);
    }
    return "";
}

export function buildStableHtmlComponentKey(source) {
    return _buildStableHtmlComponentKeyInternal(source, _stableUiKeyPrefix);
}

export function buildStableHtmlComponentKeyWithPrefix(source, rawPrefix) {
    // Workbench 侧需要“展示/分组”用到的稳定 key 规则必须与导出侧完全一致，但不应靠修改导出侧的全局前缀来实现。
    // 因此提供一个无副作用的 pure helper：调用者显式传入 prefix。
    var prefix = String(rawPrefix || "").trim();
    var stablePrefix = prefix ? sanitizeIdPart(prefix) : "";
    return _buildStableHtmlComponentKeyInternal(source, stablePrefix);
}

