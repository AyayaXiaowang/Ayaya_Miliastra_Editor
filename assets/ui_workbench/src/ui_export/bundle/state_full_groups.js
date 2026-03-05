import { sanitizeIdPart } from "../keys.js";
import { boundsOfWidgets } from "./rect_utils.js";
import { minLayerIndex } from "./layer_order.js";

function _t(text) {
    return String(text || "").trim();
}

function _isInteractiveItemDisplay(widget) {
    if (!widget) return false;
    if (String(widget.widget_type || "") !== "道具展示") return false;
    var settings = widget.settings || null;
    return !!(settings && settings.can_interact === true);
}

function _deepCloneWidget(widget) {
    // 纯 JSON payload：可用 stringify/parse 做深拷贝（浏览器侧兼容，无需 structuredClone）。
    return JSON.parse(JSON.stringify(widget || {}));
}

function _applyUiStateMetaInPlace(widget, groupName, stateName, isDefault) {
    if (!widget) return;
    widget.__ui_state_group = String(groupName || "").trim();
    widget.__ui_state = String(stateName || "").trim();
    widget.__ui_state_default = !!isDefault;
    // 多状态控件初始可见性：默认态 true，其它态 false（写回 GIL 时将由组容器可见性表达）。
    widget.initial_visible = !!isDefault;
}

function _buildUiStateCloneSuffix(groupName, stateName) {
    var g = sanitizeIdPart(groupName) || "state_group";
    var s = sanitizeIdPart(stateName) || "state";
    return "__ui_state__" + g + "__" + s;
}

function _pickDefaultStateKey(stateKeys) {
    // 尽量贴合常用命名：unselected/normal 优先，其它退回排序首个。
    var keys = stateKeys || [];
    if (keys.indexOf("unselected") >= 0) return "unselected";
    if (keys.indexOf("normal") >= 0) return "normal";
    if (keys.indexOf("default") >= 0) return "default";
    if (keys.length <= 0) return "";
    return String(keys.slice().sort()[0] || "");
}

function _updateTemplateBoundsAndOrdering(templates, orderingEntries) {
    var orderingById = {};
    for (var i = 0; i < (orderingEntries ? orderingEntries.length : 0); i++) {
        var e = orderingEntries[i] || {};
        var tid = String(e.template_id || "").trim();
        if (tid) {
            orderingById[tid] = e;
        }
    }
    for (var tIndex = 0; tIndex < (templates ? templates.length : 0); tIndex++) {
        var t0 = templates[tIndex] || {};
        var ws = t0.widgets || [];
        if (!ws || ws.length <= 0) {
            continue;
        }
        var b = boundsOfWidgets(ws);
        t0.group_position = [b.x, b.y];
        t0.group_size = [b.w, b.h];
        var entry = orderingById[String(t0.template_id || "").trim()];
        if (entry) {
            entry.min_layer = minLayerIndex(ws);
        }
    }
}

export function expandUiStateFullGroups(templates, orderingEntries) {
    // 兼容策略：在 full_state_groups 模式下，将 `<state_group>_content` 这类“共享内容组件”
    // 扁平化复制到每个 state 组内，使得状态切换时“底色/边框/文本/图标”等全部随组一起切换。
    //
    // 典型 HTML 结构（关卡按钮）：
    //   rect_level_01 (unselected|selected|disabled)  +  rect_level_01_content (共享)
    //
    // 导出侧约定：
    // - state 组控件已具备 __ui_state_* meta，且 __html_component_key 仅由 state_group+state 生成；
    // - content 组控件没有 state meta，__html_component_key 末 token 以 `_content` 结尾。
    if (!templates || templates.length <= 0) {
        return { templates: templates, orderingEntries: orderingEntries, report: { enabled: true, flattened_groups_total: 0 } };
    }

    // group -> { default_state: string, states: Map(state -> { template, template_priority, component_key }) }
    var stateInfoByGroup = new Map();

    function _ensureGroup(groupName) {
        var g = stateInfoByGroup.get(groupName);
        if (!g) {
            g = { default_state: "", states: new Map() };
            stateInfoByGroup.set(groupName, g);
        }
        return g;
    }

    // pass1: collect state group index (component key + destination template)
    for (var ti = 0; ti < templates.length; ti++) {
        var tpl = templates[ti] || {};
        var tplGroup = _t(tpl.__ui_state_group);
        var tplState = _t(tpl.__ui_state);
        var ws = tpl.widgets || [];
        for (var wi = 0; wi < (ws ? ws.length : 0); wi++) {
            var w = ws[wi] || null;
            if (!w) continue;
            var gName = _t(w.__ui_state_group);
            if (!gName) continue;
            var sName = _t(w.__ui_state) || "state";
            var compKey = _t(w.__html_component_key);
            var gEntry = _ensureGroup(gName);
            if (!!w.__ui_state_default) {
                gEntry.default_state = sName;
            }
            var sEntry = gEntry.states.get(sName);
            if (!sEntry) {
                sEntry = { template: null, template_priority: -1, component_key: "" };
            }
            if (compKey && !sEntry.component_key) {
                sEntry.component_key = compKey;
            }
            // 选择“主要归属模板”：优先 template 自身标注了该 group/state 的模板，其次退回“包含该 state 控件”的模板
            var priority = (tplGroup && tplState && tplGroup === gName && tplState === sName) ? 1 : 0;
            if (sEntry.template === null || priority > sEntry.template_priority) {
                sEntry.template = tpl;
                sEntry.template_priority = priority;
            }
            gEntry.states.set(sName, sEntry);
        }
    }

    if (stateInfoByGroup.size <= 0) {
        return { templates: templates, orderingEntries: orderingEntries, report: { enabled: true, flattened_groups_total: 0 } };
    }

    // pass2: collect content component groups: component_key -> { group_name, refs: [{ template, widget }] }
    var contentGroups = new Map();
    for (var tj = 0; tj < templates.length; tj++) {
        var tpl2 = templates[tj] || {};
        var ws2 = tpl2.widgets || [];
        for (var wj = 0; wj < (ws2 ? ws2.length : 0); wj++) {
            var w2 = ws2[wj] || null;
            if (!w2) continue;
            if (_t(w2.__ui_state_group)) {
                continue;
            }
            var compKey2 = _t(w2.__html_component_key);
            if (!compKey2) continue;
            var parts = compKey2.split("__");
            var last = String(parts && parts.length > 0 ? parts[parts.length - 1] : "").trim();
            if (!last || last.length <= 8) continue;
            if (last.slice(-8) !== "_content") continue;
            var baseGroup = String(last.slice(0, -8) || "").trim();
            if (!baseGroup) continue;
            if (!stateInfoByGroup.has(baseGroup)) continue;

            var entry2 = contentGroups.get(compKey2);
            if (!entry2) {
                entry2 = { group_name: baseGroup, refs: [] };
                contentGroups.set(compKey2, entry2);
            }
            entry2.refs.push({ template: tpl2, widget: w2 });
        }
    }

    if (contentGroups.size <= 0) {
        return { templates: templates, orderingEntries: orderingEntries, report: { enabled: true, flattened_groups_total: 0 } };
    }

    // apply expansion
    var removedWidgetByTemplate = new Map(); // template -> Set(widget)
    var movedWidgetTotal = 0;
    var clonedWidgetTotal = 0;
    var flattenedGroupsTotal = 0;
    var missingStateTemplateTotal = 0;
    var missingStateComponentKeyTotal = 0;
    var skippedInteractiveCloneTotal = 0;

    function _markRemove(srcTemplate, widget) {
        if (!srcTemplate || !widget) return;
        var set0 = removedWidgetByTemplate.get(srcTemplate);
        if (!set0) {
            set0 = new Set();
            removedWidgetByTemplate.set(srcTemplate, set0);
        }
        set0.add(widget);
    }

    contentGroups.forEach(function (contentEntry, contentCompKey) {
        var gName = String(contentEntry && contentEntry.group_name ? contentEntry.group_name : "").trim();
        if (!gName) return;
        var gState = stateInfoByGroup.get(gName);
        if (!gState || !gState.states || gState.states.size <= 0) return;

        // states list
        var stateKeys = [];
        gState.states.forEach(function (_v, stateKey) {
            var s = String(stateKey || "").trim();
            if (s) stateKeys.push(s);
        });
        if (stateKeys.length <= 0) return;

        var defaultState = String(gState.default_state || "").trim();
        if (!defaultState || stateKeys.indexOf(defaultState) < 0) {
            defaultState = _pickDefaultStateKey(stateKeys);
        }
        if (!defaultState) return;

        var defaultStateEntry = gState.states.get(defaultState);
        if (!defaultStateEntry || !defaultStateEntry.template) {
            // 极端兜底：找任意一个 state 的模板作为承载（模板只是导出组织，不影响写回端组件打组）
            defaultStateEntry = gState.states.get(stateKeys[0]);
        }
        var defaultDestTemplate = defaultStateEntry ? defaultStateEntry.template : null;
        if (!defaultDestTemplate) return;

        var defaultComponentKey = String(defaultStateEntry && defaultStateEntry.component_key ? defaultStateEntry.component_key : "").trim();
        if (!defaultComponentKey) {
            // 没有 component_key 无法把内容塞进 state 组（写回端按 __html_component_key 建组容器）
            missingStateComponentKeyTotal += 1;
            return;
        }

        // 先把 content 组控件移入默认态（原件搬迁），再克隆到其它态
        var refs = contentEntry && contentEntry.refs ? contentEntry.refs : [];
        if (!refs || refs.length <= 0) return;

        flattenedGroupsTotal += 1;

        for (var ri = 0; ri < refs.length; ri++) {
            var ref = refs[ri] || null;
            if (!ref || !ref.widget) continue;
            var w0 = ref.widget;

            // --- 默认态：搬迁原件（保留 ui_key/widget_id，最大化 GUID 复用）
            _applyUiStateMetaInPlace(w0, gName, defaultState, true);
            w0.__html_component_key = defaultComponentKey;
            // 若原控件不在默认态模板，则移动（否则只改 meta）
            if (ref.template !== defaultDestTemplate) {
                _markRemove(ref.template, w0);
                if (!defaultDestTemplate.widgets) defaultDestTemplate.widgets = [];
                defaultDestTemplate.widgets.push(w0);
                movedWidgetTotal += 1;
            }

            // --- 其它态：克隆
            for (var si = 0; si < stateKeys.length; si++) {
                var stateKey2 = String(stateKeys[si] || "").trim();
                if (!stateKey2 || stateKey2 === defaultState) continue;
                var stateEntry2 = gState.states.get(stateKey2) || null;
                var destTemplate2 = stateEntry2 && stateEntry2.template ? stateEntry2.template : null;
                var compKey2 = String(stateEntry2 && stateEntry2.component_key ? stateEntry2.component_key : "").trim();

                if (!destTemplate2) {
                    missingStateTemplateTotal += 1;
                    destTemplate2 = defaultDestTemplate;
                }
                if (!compKey2) {
                    missingStateComponentKeyTotal += 1;
                    continue;
                }

                // 交互锚点（can_interact=true）只迁入默认态，不克隆，避免重复键位/重复动作。
                if (_isInteractiveItemDisplay(w0)) {
                    skippedInteractiveCloneTotal += 1;
                    continue;
                }

                var cloned = _deepCloneWidget(w0);
                _applyUiStateMetaInPlace(cloned, gName, stateKey2, false);
                cloned.__html_component_key = compKey2;

                var suffix = _buildUiStateCloneSuffix(gName, stateKey2);
                var baseUiKey = _t(cloned.ui_key) || _t(cloned.widget_id);
                var baseWidgetId = _t(cloned.widget_id) || baseUiKey;
                if (baseUiKey) {
                    cloned.ui_key = baseUiKey + suffix;
                }
                if (baseWidgetId) {
                    cloned.widget_id = baseWidgetId + suffix;
                }

                if (!destTemplate2.widgets) destTemplate2.widgets = [];
                destTemplate2.widgets.push(cloned);
                clonedWidgetTotal += 1;
            }
        }
    });

    // remove moved widgets from their original templates
    if (removedWidgetByTemplate.size > 0) {
        for (var tk = 0; tk < templates.length; tk++) {
            var tpl3 = templates[tk] || {};
            var ws3 = tpl3.widgets || [];
            if (!ws3 || ws3.length <= 0) continue;
            var removeSet = removedWidgetByTemplate.get(tpl3);
            if (!removeSet || removeSet.size <= 0) continue;
            tpl3.widgets = ws3.filter(function (w) { return !removeSet.has(w); });
        }
    }

    // drop empty templates + ordering entries (content-only templates常见会被清空)
    var keptTemplates = [];
    var keptTemplateIdSet = new Set();
    for (var tKeep = 0; tKeep < templates.length; tKeep++) {
        var tObj = templates[tKeep] || {};
        var wsKeep = tObj.widgets || [];
        if (!wsKeep || wsKeep.length <= 0) {
            continue;
        }
        keptTemplates.push(tObj);
        var tidKeep = String(tObj.template_id || "").trim();
        if (tidKeep) {
            keptTemplateIdSet.add(tidKeep);
        }
    }
    var keptOrderingEntries = [];
    for (var oe = 0; oe < (orderingEntries ? orderingEntries.length : 0); oe++) {
        var entry3 = orderingEntries[oe] || {};
        var tid3 = String(entry3.template_id || "").trim();
        if (!tid3 || keptTemplateIdSet.has(tid3)) {
            keptOrderingEntries.push(entry3);
        }
    }

    _updateTemplateBoundsAndOrdering(keptTemplates, keptOrderingEntries);

    return {
        templates: keptTemplates,
        orderingEntries: keptOrderingEntries,
        report: {
            enabled: true,
            flattened_groups_total: Number(flattenedGroupsTotal || 0),
            moved_widgets_total: Number(movedWidgetTotal || 0),
            cloned_widgets_total: Number(clonedWidgetTotal || 0),
            missing_state_template_total: Number(missingStateTemplateTotal || 0),
            missing_state_component_key_total: Number(missingStateComponentKeyTotal || 0),
            skipped_interactive_clone_total: Number(skippedInteractiveCloneTotal || 0)
        }
    };
}

