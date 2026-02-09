import { sanitizeIdPart } from "../keys.js";
import { boundsOfWidgets } from "./rect_utils.js";
import { minLayerIndex } from "./layer_order.js";

function _collectWidgetsFromTemplateList(templateList) {
    var merged = [];
    for (var i = 0; i < (templateList ? templateList.length : 0); i++) {
        var tp = templateList[i] || {};
        var ws = tp.widgets || [];
        for (var j = 0; j < (ws ? ws.length : 0); j++) {
            var w = ws[j];
            if (w) {
                merged.push(w);
            }
        }
    }
    // 组内控件按 layer_index 升序，保证遮挡/点击顺序稳定
    merged.sort(function (l, r) {
        var ll = Number(l && l.layer_index !== undefined ? l.layer_index : 0);
        var rr = Number(r && r.layer_index !== undefined ? r.layer_index : 0);
        if (!isFinite(ll)) ll = 0;
        if (!isFinite(rr)) rr = 0;
        if (ll !== rr) {
            return ll - rr;
        }
        return String(l && l.widget_id ? l.widget_id : "").localeCompare(String(r && r.widget_id ? r.widget_id : ""));
    });
    return merged;
}

function _pickButtonAnchorWidgetFromTemplate(template) {
    var t0 = template || {};
    var ws = t0.widgets || [];
    for (var i = 0; i < ws.length; i++) {
        var w = ws[i] || null;
        if (!w) continue;
        if (String(w.widget_type || "") !== "道具展示") continue;
        var settings = w.settings || null;
        // 约定：按钮锚点道具展示通常 can_interact=true
        if (settings && settings.can_interact === false) continue;
        return w;
    }
    // fallback：仍找第一个道具展示
    for (var j = 0; j < ws.length; j++) {
        var w2 = ws[j] || null;
        if (w2 && String(w2.widget_type || "") === "道具展示") return w2;
    }
    return null;
}

function _pickUiStateIdentityKeyFromTemplate(template) {
    var t0 = template || {};
    var kind = String(t0.__html_group_kind || "").trim();
    if (kind === "button") {
        var anchor = _pickButtonAnchorWidgetFromTemplate(t0);
        if (anchor) {
            var settings = anchor.settings || null;
            if (settings && settings.keybind_kbm_code !== undefined && settings.keybind_kbm_code !== null) {
                var code = Math.trunc(Number(settings.keybind_kbm_code));
                if (isFinite(code) && code > 0) {
                    return "button_keybind_" + String(code);
                }
            }
            var uk = String(anchor.ui_key || "").trim();
            if (uk) {
                return "button_ui_key_" + uk;
            }
        }
    }
    // generic fallback：尽量用 template_id（稳定，且不误合并不同组件）
    var tid = String(t0.template_id || "").trim();
    return tid ? ("template_id_" + tid) : "";
}

function _buildUiStateIndexByIdentity(templates) {
    // group -> identity -> stateKey -> { templates: [], isDefault: bool }
    var byGroup = new Map();
    for (var tIndex = 0; tIndex < (templates ? templates.length : 0); tIndex++) {
        var t0 = templates[tIndex] || {};
        var group0 = String(t0.__ui_state_group || "").trim();
        if (!group0) continue;
        var state0 = String(t0.__ui_state || "").trim();
        var identity0 = String(_pickUiStateIdentityKeyFromTemplate(t0) || "").trim();
        if (!identity0) continue;

        var byIdentity = byGroup.get(group0);
        if (!byIdentity) {
            byIdentity = new Map();
            byGroup.set(group0, byIdentity);
        }
        var byState = byIdentity.get(identity0);
        if (!byState) {
            byState = new Map();
            byIdentity.set(identity0, byState);
        }
        var entry = byState.get(state0);
        if (!entry) {
            entry = { templates: [], isDefault: false };
            byState.set(state0, entry);
        }
        entry.templates.push(t0);
        if (!!t0.__ui_state_default) {
            entry.isDefault = true;
        }
    }
    return byGroup;
}

function _stableStringify(obj) {
    if (obj === null || obj === undefined) return String(obj);
    if (typeof obj !== "object") return JSON.stringify(obj);
    if (Array.isArray(obj)) {
        return "[" + obj.map(function (x) { return _stableStringify(x); }).join(",") + "]";
    }
    var keys = Object.keys(obj).sort();
    var parts = [];
    for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        parts.push(JSON.stringify(k) + ":" + _stableStringify(obj[k]));
    }
    return "{" + parts.join(",") + "}";
}

function _widgetSignatureForStateDedupe(widget) {
    var w = widget || {};
    // 仅用于“跨状态合并时去掉完全相同的控件”，忽略 ui_key/widget_id/状态字段/初始可见性差异
    return _stableStringify({
        widget_type: String(w.widget_type || ""),
        widget_name: String(w.widget_name || ""),
        position: w.position || null,
        size: w.size || null,
        layer_index: Number(w.layer_index !== undefined ? w.layer_index : 0),
        is_builtin: !!w.is_builtin,
        settings: w.settings || null,
        ui_action_key: String(w.ui_action_key || ""),
        ui_action_args: String(w.ui_action_args || "")
    });
}

function _stripUiStateMetaInPlace(widget) {
    if (!widget) return;
    if (widget.__ui_state_group !== undefined) delete widget.__ui_state_group;
    if (widget.__ui_state !== undefined) delete widget.__ui_state;
    if (widget.__ui_state_default !== undefined) delete widget.__ui_state_default;
}

export function consolidateUiStateTemplates(templates, orderingEntries, options) {
    var opts = options || {};
    var baseIdPrefix = String(opts.base_id_prefix || "");
    var layoutName = String(opts.layout_name || "");
    var now = String(opts.now_iso || "");
    var allocateUniqueTemplateId = opts.allocateUniqueTemplateId;
    var ensureUniqueUiKeysInWidgetList = opts.ensureUniqueUiKeysInWidgetList;
    var globalUsedUiKeys = opts.globalUsedUiKeys;

    // 新策略（最小冗余）：
    // - 旧版“整态打组”会把同一状态的内容合成一个 template，并依赖 UILayout.visibility_overrides 做初始隐藏；
    // - 但导出 widget 已具备 initial_visible（默认态 true，其它态 false），因此不必抬升到 template 粒度；
    // - 更糟的是：整态打组会迫使“仅颜色变化”也复制整组模板，节点图侧难以维护。
    //
    // 因此这里改为：优先做“组件内跨状态合并”（把多个状态的 widgets 合并到同一 template），状态切换由控件显隐完成。
    var indexByGroup = _buildUiStateIndexByIdentity(templates || []);
    if (indexByGroup.size <= 0) {
        return { templates: templates, orderingEntries: orderingEntries };
    }
    if (typeof allocateUniqueTemplateId !== "function") {
        throw new Error("allocateUniqueTemplateId 缺失");
    }
    if (typeof ensureUniqueUiKeysInWidgetList !== "function") {
        throw new Error("ensureUniqueUiKeysInWidgetList 缺失");
    }

    var consumedTemplateIdSet = new Set();
    var stateTemplatesToAppend = [];
    var stateOrderingEntriesToAppend = [];

    indexByGroup.forEach(function (byIdentity, groupName) {
        var groupText = String(groupName || "").trim();
        if (!groupText || !byIdentity) return;

        byIdentity.forEach(function (byState, identityKey) {
            if (!byState || byState.size < 2) {
                return;
            }

            // 仅当 identityKey 不是 template_id fallback（即能确认为“同一组件”）才合并。
            // 目前最可靠的是：按钮按键槽位（keybind）或按钮锚点 ui_key。
            var identityText = String(identityKey || "").trim();
            var isReliableIdentity = identityText.indexOf("button_keybind_") === 0 || identityText.indexOf("button_ui_key_") === 0;
            if (!isReliableIdentity) {
                return;
            }

            // 收集要合并的旧模板
            var allTemplateList = [];
            byState.forEach(function (entry, stateKey) {
                var tplList = entry && entry.templates ? entry.templates : [];
                for (var i = 0; i < tplList.length; i++) {
                    var tOld = tplList[i] || {};
                    if (tOld.template_id) {
                        consumedTemplateIdSet.add(String(tOld.template_id));
                    }
                    allTemplateList.push(tOld);
                }
            });
            if (allTemplateList.length <= 0) return;

            var mergedWidgets = _collectWidgetsFromTemplateList(allTemplateList);
            if (mergedWidgets.length <= 0) return;

            // 去掉“跨状态完全一致”的控件（常见于作者把整套 DOM 复制到每个 state）
            var sigSeen = new Map(); // sig -> widget
            var deduped = [];
            for (var wi = 0; wi < mergedWidgets.length; wi++) {
                var w = mergedWidgets[wi] || null;
                if (!w) continue;
                var sig = _widgetSignatureForStateDedupe(w);
                var exist = sigSeen.get(sig) || null;
                if (exist) {
                    // 保留第一个，把它升级为“跨状态共享”：去掉状态 meta，并确保初始可见
                    _stripUiStateMetaInPlace(exist);
                    exist.initial_visible = true;
                    continue;
                }
                sigSeen.set(sig, w);
                deduped.push(w);
            }
            mergedWidgets = deduped;

            if (globalUsedUiKeys) {
                ensureUniqueUiKeysInWidgetList(mergedWidgets, globalUsedUiKeys);
            }
            var bounds = boundsOfWidgets(mergedWidgets);

            var groupIdPart = sanitizeIdPart(groupText) || "state_group";
            var identityIdPart = sanitizeIdPart(identityText) || "component";
            var rawTemplateId = baseIdPrefix + "_state_group_" + groupIdPart + "_" + identityIdPart;
            var mergedTemplateId = allocateUniqueTemplateId(rawTemplateId);

            var mergedTemplateName = layoutName + "_状态组_" + groupText;

            stateTemplatesToAppend.push({
                template_id: mergedTemplateId,
                template_name: mergedTemplateName,
                is_combination: true,
                widgets: mergedWidgets,
                group_position: [bounds.x, bounds.y],
                group_size: [bounds.w, bounds.h],
                supports_layout_visibility_override: true,
                description: "由 ui_html_workbench 导出：多状态控件已做“组件内合并”（同一组件的多个状态合并到同一模板，靠控件 initial_visible/显隐切换表达状态）。",
                created_at: now,
                updated_at: now,
                __html_group_kind: "state_group_merged",
                __ui_state_group: groupText
            });
            stateOrderingEntriesToAppend.push({ min_layer: minLayerIndex(mergedWidgets), template_id: mergedTemplateId });
        });
    });

    var filteredTemplates = (templates || []).filter(function (t) {
        var tid = t && t.template_id ? String(t.template_id || "") : "";
        return tid && !consumedTemplateIdSet.has(tid);
    });
    var filteredOrdering = (orderingEntries || []).filter(function (item) {
        var tid = item && item.template_id ? String(item.template_id || "") : "";
        return tid && !consumedTemplateIdSet.has(tid);
    });

    for (var st = 0; st < stateTemplatesToAppend.length; st++) {
        filteredTemplates.push(stateTemplatesToAppend[st]);
    }
    for (var so = 0; so < stateOrderingEntriesToAppend.length; so++) {
        filteredOrdering.push(stateOrderingEntriesToAppend[so]);
    }

    return { templates: filteredTemplates, orderingEntries: filteredOrdering };
}

