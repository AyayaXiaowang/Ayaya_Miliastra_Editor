import { sanitizeIdPart } from "./keys.js";
import { inferUiStateMetaFromWidgetList } from "./ui_state.js";
import { ensureUniqueUiKeysInWidgetList } from "./dedupe.js";
import { buildUiControlGroupTemplateFromFlattenedLayers } from "./template_from_layers.js";
import { boundsOfWidgets, rectFromWidget, rectArea, rectCenter, rectContainsPoint, rectIntersectionArea } from "./bundle/rect_utils.js";
import { minLayerIndex } from "./bundle/layer_order.js";
import { ensureUniqueInteractiveKeybindsForPage } from "./bundle/interact_keys.js";
import { collectButtonAnchors, groupWidgetsByAnchors, pickAnchorLabel } from "./bundle/grouping.js";
import { consolidateUiStateTemplates } from "./bundle/state_consolidation.js";
import { expandUiStateFullGroups } from "./bundle/state_full_groups.js";
import { hashTextFNV1a32Hex } from "../utils.js";

var DEFAULT_TEMPLATE_ID_PREFIX = "template_html_import_";
var DEFAULT_LAYOUT_ID_PREFIX = "layout_html_import_";
var DEFAULT_ID_SEED_PREFIX = "ui_bundle_default_id_v1";
var DEFAULT_ID_SEP = "|";

var DETERMINISTIC_TIMESTAMP_ISO = "2000-01-01T00:00:00.000Z";

function _normalizeIdSeedPart(v) {
    return String(v !== undefined ? v : "").trim();
}

function _buildDeterministicId(prefix, seedParts) {
    var parts = Array.isArray(seedParts) ? seedParts : [];
    var normalized = [];
    for (var i = 0; i < parts.length; i++) {
        normalized.push(_normalizeIdSeedPart(parts[i]));
    }
    var seed = normalized.join(DEFAULT_ID_SEP);
    return String(prefix || "") + hashTextFNV1a32Hex(seed);
}

function _buildLayerListHash(layerList) {
    // JS 对象 key 顺序通常保持插入顺序；layerList 由同一条管线构建，JSON.stringify 在同一输入下应稳定。
    return hashTextFNV1a32Hex(JSON.stringify(layerList || []));
}

function nowIsoText(options) {
    var opts = options || {};
    if (opts && opts.deterministic_timestamps === true) {
        return DETERMINISTIC_TIMESTAMP_ISO;
    }
    return new Date().toISOString();
}

function _asIntLayerIndex(raw) {
    var n = Number(raw !== undefined ? raw : 0);
    if (!isFinite(n)) {
        return 0;
    }
    return Math.trunc(n);
}

function _inferLayerKindPriorityFromFlatLayerKeyText(flatLayerKeyText) {
    // format: kind__left__top__width__height__round(z)
    var text = String(flatLayerKeyText || "").trim();
    if (!text) {
        return null;
    }
    var parts = text.split("__");
    if (!parts || parts.length < 6) {
        return null;
    }
    var kind = String(parts[0] || "").trim();
    if (!kind) {
        return null;
    }
    // 越小越靠底；越大越靠顶
    // 注：这里仅用于“同 layer_index 的 tie-break”，不改变原有跨层顺序。
    switch (kind) {
        case "shadow":
            return 0;
        case "border":
            return 1;
        case "element":
            return 2;
        case "button_anchor":
            // 视觉为空但可交互的锚点：通常应在底色之上、文本之下（更接近 element）
            return 2;
        case "text":
            return 3;
        default:
            return 2;
    }
}

function _inferLayerKindPriorityFromWidget(widget) {
    if (!widget) {
        return 2;
    }
    // 优先使用预览绑定的 flat layer key（更贴近 DOM 扁平层 kind）
    var k1 = widget.__flat_layer_key !== undefined ? widget.__flat_layer_key : null;
    var p1 = _inferLayerKindPriorityFromFlatLayerKeyText(k1);
    if (p1 !== null) {
        return p1;
    }
    var k2 = widget.flat_layer_key !== undefined ? widget.flat_layer_key : null;
    var p2 = _inferLayerKindPriorityFromFlatLayerKeyText(k2);
    if (p2 !== null) {
        return p2;
    }

    // 兜底：按控件类型推断大致层级（只作为 tie-break）
    var t = String(widget.widget_type || "").trim();
    if (t === "文本框") return 3;
    if (t === "道具展示") return 2;
    if (t === "进度条") return 2;
    return 2;
}

function _sortWidgetListByLayerIndexStable(widgetList) {
    if (!widgetList || widgetList.length <= 1) {
        return;
    }
    widgetList.sort(function (l, r) {
        var ll = _asIntLayerIndex(l && l.layer_index !== undefined ? l.layer_index : 0);
        var rr = _asIntLayerIndex(r && r.layer_index !== undefined ? r.layer_index : 0);
        if (ll !== rr) {
            return ll - rr;
        }
        var lp = _inferLayerKindPriorityFromWidget(l);
        var rp = _inferLayerKindPriorityFromWidget(r);
        if (lp !== rp) {
            return lp - rp;
        }
        return String(l && l.widget_id ? l.widget_id : "").localeCompare(String(r && r.widget_id ? r.widget_id : ""));
    });
}

function _ensureGlobalUniqueLayerIndexAcrossTemplates(templates) {
    // 需求：任何 layer_index（zIndex）必须全局唯一。
    // 策略：保持“原来的全局叠放顺序”，对所有 widgets 重新分配 layer_index=0..N-1。
    var all = [];
    for (var ti = 0; ti < (templates ? templates.length : 0); ti++) {
        var t0 = templates[ti] || {};
        var ws = t0.widgets || [];
        for (var wi = 0; wi < (ws ? ws.length : 0); wi++) {
            var w0 = ws[wi] || null;
            if (!w0) continue;
            all.push({
                widget: w0,
                oldLayer: _asIntLayerIndex(w0.layer_index),
                kindPri: _inferLayerKindPriorityFromWidget(w0),
                widgetId: String(w0.widget_id || "")
            });
        }
    }
    if (all.length <= 1) {
        return 0;
    }
    all.sort(function (a, b) {
        if (a.oldLayer !== b.oldLayer) {
            return a.oldLayer - b.oldLayer;
        }
        if (a.kindPri !== b.kindPri) {
            return a.kindPri - b.kindPri;
        }
        return String(a.widgetId || "").localeCompare(String(b.widgetId || ""));
    });
    for (var i = 0; i < all.length; i++) {
        all[i].widget.layer_index = i;
    }
    // 每个 template 内也保持按 layer_index 升序（满足后续遮挡/点击顺序假设）
    for (var tj = 0; tj < (templates ? templates.length : 0); tj++) {
        var t1 = templates[tj] || {};
        var ws2 = t1.widgets || [];
        _sortWidgetListByLayerIndexStable(ws2);
    }

    // 保险：断言无重复
    var seen = new Set();
    for (var k = 0; k < all.length; k++) {
        var z = _asIntLayerIndex(all[k].widget.layer_index);
        if (seen.has(z)) {
            throw new Error("layer_index 未能全局唯一化：重复值 " + String(z));
        }
        seen.add(z);
    }
    return all.length;
}

export function buildUiLayoutBundleFromFlattenedLayers(layerList, options) {
    options = options || {};
    var now = nowIsoText(options);

    // 稳定导出（diff 更干净）：
    // - 优先使用上游传入的 `options.source_hash`（来自归一化 HTML 的稳定 hash）
    // - 若缺失，则回退为 layerList 的 JSON hash（同一输入下应稳定）
    var sourceHash = _normalizeIdSeedPart(options.source_hash || "");
    var stableHash = sourceHash || _buildLayerListHash(layerList);

    var uiKeyPrefixForId = _normalizeIdSeedPart(options.ui_key_prefix || "");
    var layoutNameForId = _normalizeIdSeedPart(options.layout_name || "");

    // 1) 先复用既有导出：统一把 DOM 扁平层转成 widgets（保证规则一致）
    var baseTemplateId = String(
        options.template_id
        || _buildDeterministicId(DEFAULT_TEMPLATE_ID_PREFIX, [
            DEFAULT_ID_SEED_PREFIX,
            "template",
            uiKeyPrefixForId,
            layoutNameForId,
            stableHash
        ])
    );
    var baseTemplateName = String(options.template_name || "HTML导入_UI控件组");
    var baseIdPrefix = sanitizeIdPart(options.id_prefix || baseTemplateId) || baseTemplateId;

    var fullResult = buildUiControlGroupTemplateFromFlattenedLayers(layerList, {
        template_id: baseTemplateId,
        template_name: baseTemplateName,
        id_prefix: baseIdPrefix,
        ui_key_prefix: options.ui_key_prefix || "",
        group_width: options.group_width,
        group_height: options.group_height,
        description: options.description,
        // 例外规则：4 分辨率字号一致的文本，允许用 `<size=...>` 精确表达（不限制白名单）
        uniform_text_font_size_by_element_index: options.uniform_text_font_size_by_element_index || null
    });
    var fullTemplate = fullResult && fullResult.template ? fullResult.template : null;
    var warnings = fullResult && fullResult.warnings ? fullResult.warnings : [];
    var allWidgets = fullTemplate && fullTemplate.widgets ? fullTemplate.widgets : [];

    // 2) 组装 UILayout + 多模板
    var layoutName = String(options.layout_name || "HTML导入_界面布局");
    var layoutId = String(
        options.layout_id
        || _buildDeterministicId(DEFAULT_LAYOUT_ID_PREFIX, [
            DEFAULT_ID_SEED_PREFIX,
            "layout",
            uiKeyPrefixForId,
            layoutNameForId || _normalizeIdSeedPart(layoutName),
            stableHash
        ])
    );
    var layoutDescription = String(options.layout_description || "由 ui_html_workbench 导出。");

    var templates = [];
    var usedTemplateIds = new Set();
    var orderingEntries = []; // { min_layer: number, template_id: string }
    var globalUsedUiKeys = new Set();
    var globalUiKeyFixedTotal = 0;

    // 2.1) 按钮打组：以“道具展示”（交互层）作为按钮锚点
    var anchors = collectButtonAnchors(allWidgets);

    // 强制：本页所有可交互按钮必须拥有 1..14 且同页唯一（未指定则按页面顺序自动分配）。
    ensureUniqueInteractiveKeybindsForPage(anchors);

    var groupedResult = groupWidgetsByAnchors(allWidgets, anchors);
    var groupedWidgetIds = groupedResult.groupedWidgetIds;
    var membersByAnchorId = groupedResult.membersByAnchorId;

    function allocateUniqueTemplateId(candidateId) {
        var base = String(candidateId || "");
        if (!base) {
            base = "template_auto";
        }
        var unique = base;
        var counter = 2;
        while (usedTemplateIds.has(unique)) {
            unique = base + "_" + counter;
            counter += 1;
        }
        usedTemplateIds.add(unique);
        return unique;
    }

    // 2.2) 输出按钮组合模板
    for (var aIndex = 0; aIndex < anchors.length; aIndex++) {
        var anchor3 = anchors[aIndex];
        var anchorId3 = String(anchor3.widget_id || "");
        var memberList = membersByAnchorId[anchorId3] || [];
        if (!memberList || memberList.length === 0) {
            continue;
        }

        // 规则：当“按钮由文本 ICON 充当”（锚点道具展示 display_type=模板道具），则该道具展示应在组内最顶部。
        if (memberList.length > 1) {
            var minOtherLayer = null;
            var maxOtherLayer = null;
            for (var mi = 0; mi < memberList.length; mi++) {
                var m = memberList[mi];
                if (!m) {
                    continue;
                }
                if (String(m.widget_id || "") === anchorId3) {
                    continue;
                }
                var mLayer = Number(m.layer_index !== undefined ? m.layer_index : 0);
                if (!isFinite(mLayer)) {
                    mLayer = 0;
                }
                if (minOtherLayer === null || mLayer < minOtherLayer) {
                    minOtherLayer = mLayer;
                }
                if (maxOtherLayer === null || mLayer > maxOtherLayer) {
                    maxOtherLayer = mLayer;
                }
            }

            if (minOtherLayer !== null && maxOtherLayer !== null) {
                var anchorDisplayType = "";
                if (anchor3.settings && anchor3.settings.display_type) {
                    anchorDisplayType = String(anchor3.settings.display_type || "").trim();
                }
                var isIconTextButtonAnchor = (anchorDisplayType === "模板道具");
                if (isIconTextButtonAnchor) {
                    anchor3.layer_index = Math.trunc(maxOtherLayer + 1);
                } else {
                    anchor3.layer_index = Math.max(0, Math.trunc(minOtherLayer - 1));
                }
            }
        }

        var membersSorted = memberList.slice().sort(function (l, r) {
            var ll = Number(l && l.layer_index !== undefined ? l.layer_index : 0);
            var rr = Number(r && r.layer_index !== undefined ? r.layer_index : 0);
            if (!isFinite(ll)) {
                ll = 0;
            }
            if (!isFinite(rr)) {
                rr = 0;
            }
            return ll - rr;
        });

        var labelText = String(pickAnchorLabel(anchor3) || "").trim();
        var labelIdPart = sanitizeIdPart(labelText) || ("btn_" + String(aIndex));
        var rawTemplateId = baseIdPrefix + "_btn_" + labelIdPart;
        var templateId = allocateUniqueTemplateId(rawTemplateId);

        var templateName = layoutName + "_按钮_" + (labelText ? labelText : ("按钮_" + String(aIndex)));
        var bounds = boundsOfWidgets(membersSorted);
        var templatePayload = {
            template_id: templateId,
            template_name: templateName,
            is_combination: true,
            widgets: membersSorted,
            group_position: [bounds.x, bounds.y],
            group_size: [bounds.w, bounds.h],
            supports_layout_visibility_override: true,
            description: "由 ui_html_workbench 导出：按钮已打组（道具展示+底色/阴影/文本等）。",
            created_at: now,
            updated_at: now,
            __html_group_kind: "button"
        };
        var stateMeta = inferUiStateMetaFromWidgetList(membersSorted);
        if (stateMeta) {
            templatePayload.__ui_state_group = stateMeta.group;
            templatePayload.__ui_state = stateMeta.state;
            templatePayload.__ui_state_default = stateMeta.isDefault;
        }
        globalUiKeyFixedTotal += ensureUniqueUiKeysInWidgetList(membersSorted, globalUsedUiKeys);
        templates.push(templatePayload);
        orderingEntries.push({ min_layer: minLayerIndex(membersSorted), template_id: templateId });
    }

    // 2.3) 其余控件：单控件模板
    var singleCounter = 0;
    for (var wi3 = 0; wi3 < allWidgets.length; wi3++) {
        var widget3 = allWidgets[wi3];
        if (!widget3) {
            continue;
        }
        var widgetId3 = String(widget3.widget_id || "");
        if (groupedWidgetIds.has(widgetId3)) {
            continue;
        }
        if (widget3.is_builtin) {
            continue;
        }

        var suffix = ("000" + String(singleCounter)).slice(-3);
        singleCounter += 1;
        var partTemplateId = allocateUniqueTemplateId(baseIdPrefix + "_part_" + suffix);

        var widgetName3 = String(widget3.widget_name || "") || String(widget3.widget_type || "") || partTemplateId;
        var partTemplateName = layoutName + "_" + widgetName3;
        var rect3 = rectFromWidget(widget3);

        globalUiKeyFixedTotal += ensureUniqueUiKeysInWidgetList([widget3], globalUsedUiKeys);
        templates.push({
            template_id: partTemplateId,
            template_name: partTemplateName,
            is_combination: false,
            widgets: [widget3],
            group_position: [rect3.x, rect3.y],
            group_size: [rect3.w, rect3.h],
            supports_layout_visibility_override: true,
            description: "由 ui_html_workbench 导出：单控件模板。",
            created_at: now,
            updated_at: now,
            __html_group_kind: "single"
        });
        orderingEntries.push({ min_layer: minLayerIndex([widget3]), template_id: partTemplateId });
    }

    // 2.35) UI 多状态（可选策略）
    //
    // 默认策略：组件内跨状态合并（最小冗余）
    // - 将“同一组件的多个状态”合并到同一个 template（部分控件会被提升为跨状态共享）。
    //
    // 兼容策略：整态打组（full_state_groups）
    // - 保持每个 state 的控件都留在自己的组件组里，避免跨状态共享控件；
    // - 并将 `<state_group>_content` 这类“共享内容组件”复制进各 state 组内（默认态迁入原件 + 其它态克隆），
    //   让状态切换真正做到“底色/内容整组一起切换”；
    // - 用于规避游戏侧可能存在的“多状态控件切换时层级/底色异常”的渲染问题；
    // - 代价是模板数量增加（同一按钮多个状态会变成多个模板/组件组）。
    var uiStateConsolidationMode = String(options.ui_state_consolidation_mode || "").trim();
    if (!uiStateConsolidationMode) {
        uiStateConsolidationMode = "minimal_redundancy";
    }
    if (uiStateConsolidationMode !== "minimal_redundancy" && uiStateConsolidationMode !== "full_state_groups") {
        throw new Error("ui_state_consolidation_mode 不支持：" + uiStateConsolidationMode);
    }
    if (uiStateConsolidationMode === "minimal_redundancy") {
        var consolidated = consolidateUiStateTemplates(templates, orderingEntries, {
            base_id_prefix: baseIdPrefix,
            layout_name: layoutName,
            now_iso: now,
            allocateUniqueTemplateId: allocateUniqueTemplateId,
            ensureUniqueUiKeysInWidgetList: ensureUniqueUiKeysInWidgetList,
            globalUsedUiKeys: globalUsedUiKeys
        });
        templates = consolidated.templates;
        orderingEntries = consolidated.orderingEntries;
    }
    var uiStateFullGroupsReport = null;
    if (uiStateConsolidationMode === "full_state_groups") {
        var expanded = expandUiStateFullGroups(templates, orderingEntries);
        templates = expanded.templates;
        orderingEntries = expanded.orderingEntries;
        uiStateFullGroupsReport = expanded.report || null;
        if (uiStateFullGroupsReport && Number(uiStateFullGroupsReport.flattened_groups_total || 0) > 0) {
            warnings.push(
                "UI 多状态兼容策略（full_state_groups）：已将 *_content 共享内容复制进各 state 组内，" +
                "用于规避状态切换时的“层级/底色异常”。" +
                " flattened_groups=" + String(uiStateFullGroupsReport.flattened_groups_total || 0) +
                " moved=" + String(uiStateFullGroupsReport.moved_widgets_total || 0) +
                " cloned=" + String(uiStateFullGroupsReport.cloned_widgets_total || 0)
            );
        }
        if (
            uiStateFullGroupsReport &&
            (Number(uiStateFullGroupsReport.missing_state_template_total || 0) > 0 ||
                Number(uiStateFullGroupsReport.missing_state_component_key_total || 0) > 0)
        ) {
            warnings.push(
                "UI 多状态兼容策略（full_state_groups）：发现异常：" +
                " missing_state_template=" + String(uiStateFullGroupsReport.missing_state_template_total || 0) +
                " missing_state_component_key=" + String(uiStateFullGroupsReport.missing_state_component_key_total || 0) +
                "（可能导致部分 content 未能正确归入 state 组）。"
            );
        }
    }

    // 2.36) 强约束：全局 layer_index（zIndex）必须唯一（消除同层级的不确定叠放）
    _ensureGlobalUniqueLayerIndexAcrossTemplates(templates);
    // 同步重算 orderingEntries（min_layer 受 layer_index 影响）
    orderingEntries = (templates || []).map(function (t) {
        var ws = t && t.widgets ? t.widgets : [];
        return { min_layer: minLayerIndex(ws), template_id: String(t && t.template_id ? t.template_id : "") };
    }).filter(function (x) { return !!(x && x.template_id); });

    orderingEntries.sort(function (l, r) {
        var la = Number(l && l.min_layer !== undefined ? l.min_layer : 0);
        var ra = Number(r && r.min_layer !== undefined ? r.min_layer : 0);
        if (!isFinite(la)) {
            la = 0;
        }
        if (!isFinite(ra)) {
            ra = 0;
        }
        if (la !== ra) {
            return la - ra;
        }
        return String(l.template_id || "").localeCompare(String(r.template_id || ""));
    });

    var customGroups = orderingEntries.map(function (item) { return String(item.template_id || ""); }).filter(function (x) { return !!x; });

    // UI 多状态：
    // - 控件级：widget 已通过 ui_state.js 写入 initial_visible（默认态 true，其它态 false）
    // - 因此这里默认不再依赖 UILayout.visibility_overrides 去“模板级隐藏非默认态”，避免迫使作者复制整组模板。
    // - 状态切换由节点图/逻辑层按 ui_key/guid 做显隐切换（可配合主程序生成的 ui_states 映射）。
    var visibilityOverrides = {};

    var layoutPayload = {
        layout_id: layoutId,
        layout_name: layoutName,
        builtin_widgets: [],
        custom_groups: customGroups,
        default_for_player: "所有玩家",
        description: layoutDescription,
        created_at: now,
        updated_at: now,
        visibility_overrides: visibilityOverrides
    };

    // 最终保险：确保跨 templates 的 ui_key 全局唯一（尤其是 state 合并可能引入重复）
    if (templates && templates.length > 0) {
        var finalUsed = new Set();
        var finalFixed = 0;
        for (var ft = 0; ft < templates.length; ft++) {
            var tFix = templates[ft] || {};
            var wsFix = tFix.widgets || [];
            finalFixed += ensureUniqueUiKeysInWidgetList(wsFix, finalUsed);
        }
        globalUiKeyFixedTotal += finalFixed;
    }

    return {
        bundle: {
            bundle_type: "ui_workbench_ui_layout_bundle",
            bundle_version: 1,
            layout: layoutPayload,
            templates: templates,
            canvas_size_key: String(options.canvas_size_key || ""),
            canvas_size_label: String(options.canvas_size_label || ""),
            created_at: now,
            updated_at: now,
            _ui_state_consolidation_mode: String(uiStateConsolidationMode),
            _ui_state_full_groups_report: uiStateFullGroupsReport,
            _ui_key_dedup_fixed_total: Number(globalUiKeyFixedTotal || 0)
        },
        warnings: warnings
    };
}

