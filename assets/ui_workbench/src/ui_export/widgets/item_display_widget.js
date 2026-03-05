import { buildStableHtmlComponentKey, buildStableUiKey } from "../keys.js";
import { applyUiStateMetaToPayload } from "../ui_state.js";
import { inferInitialVisibleFromSource } from "./visibility.js";

export function buildItemDisplayWidget(widgetId, widgetName, rect, zIndex, source, overrides, uiKeyKind) {
    var ariaLabel = source && source.attributes ? (source.attributes.ariaLabel || null) : null;
    var onclickText = source && source.attributes ? (source.attributes.onclick || null) : null;
    var dataDebugLabel = source && source.attributes ? (source.attributes.dataDebugLabel || null) : null;
    var dataInventoryItemId = source && source.attributes ? (source.attributes.dataInventoryItemId || null) : null;
    var dataUiAction = source && source.attributes ? (source.attributes.dataUiAction || null) : null;
    var dataUiActionArgs = source && source.attributes ? (source.attributes.dataUiActionArgs || null) : null;
    var dataUiInteractKey = source && source.attributes ? (source.attributes.dataUiInteractKey || null) : null;
    var dataUiSaveTemplate = source && source.attributes ? (source.attributes.dataUiSaveTemplate || source.attributes.componentOwnerDataUiSaveTemplate || null) : null;
    var overrideSettings = (overrides && overrides.settings) ? overrides.settings : (overrides || null);
    var canInteract = overrideSettings && overrideSettings.can_interact !== undefined ? !!overrideSettings.can_interact : true;
    var displayType = overrideSettings && overrideSettings.display_type ? String(overrideSettings.display_type || "").trim() : "";
    if (!displayType) {
        // 约定：按钮锚点道具展示默认使用“模板道具”，便于稳定走“变量绑定 + 运行时设置配置ID”的工作流。
        displayType = canInteract ? "模板道具" : "玩家当前装备";
    }
    var settings = { can_interact: canInteract, display_type: displayType };
    if (overrideSettings) {
        if (overrideSettings.config_id_variable) {
            settings.config_id_variable = String(overrideSettings.config_id_variable || "").trim();
        }
        if (overrideSettings.quantity_variable) {
            settings.quantity_variable = String(overrideSettings.quantity_variable || "").trim();
        }
        if (overrideSettings.cooldown_seconds_variable) {
            settings.cooldown_seconds_variable = String(overrideSettings.cooldown_seconds_variable || "").trim();
        }
        if (overrideSettings.use_count_variable) {
            settings.use_count_variable = String(overrideSettings.use_count_variable || "").trim();
        }
        if (overrideSettings.use_count_enabled !== undefined) {
            settings.use_count_enabled = !!overrideSettings.use_count_enabled;
        }
        if (overrideSettings.hide_when_empty_count !== undefined) {
            settings.hide_when_empty_count = !!overrideSettings.hide_when_empty_count;
        }
        if (overrideSettings.show_quantity !== undefined) {
            settings.show_quantity = !!overrideSettings.show_quantity;
        }
        if (overrideSettings.hide_when_zero !== undefined) {
            settings.hide_when_zero = !!overrideSettings.hide_when_zero;
        }
        if (overrideSettings.keybind_kbm_code !== undefined) {
            settings.keybind_kbm_code = overrideSettings.keybind_kbm_code;
        }
        if (overrideSettings.keybind_gamepad_code !== undefined) {
            settings.keybind_gamepad_code = overrideSettings.keybind_gamepad_code;
        }
    }
    // 约定：所有可交互按钮锚点都默认绑定到一套“关卡实体变量”，作为占位/可写载体。
    if (settings.can_interact === true) {
        if (!settings.display_type || String(settings.display_type || "").trim() === "" || String(settings.display_type || "").trim() === "玩家当前装备") {
            settings.display_type = "模板道具";
        }
        if (!settings.config_id_variable || String(settings.config_id_variable || "").trim() === "." || String(settings.config_id_variable || "").trim() === "") {
            settings.config_id_variable = "关卡.UI_交互按钮_道具配置ID";
        }
        if (!settings.quantity_variable || String(settings.quantity_variable || "").trim() === "." || String(settings.quantity_variable || "").trim() === "") {
            settings.quantity_variable = "关卡.UI_交互按钮_道具数量";
        }
        if (!settings.cooldown_seconds_variable || String(settings.cooldown_seconds_variable || "").trim() === "." || String(settings.cooldown_seconds_variable || "").trim() === "") {
            settings.cooldown_seconds_variable = "关卡.UI_交互按钮_栏位冷却时间";
        }
    }
    // HTML 侧可用 `data-ui-interact-key="1..14"` 指定按钮按键槽位
    if (dataUiInteractKey !== null && dataUiInteractKey !== undefined) {
        var keyText = String(dataUiInteractKey || "").trim();
        if (keyText && /^[0-9]+$/.test(keyText)) {
            var keyCode = Math.trunc(Number(keyText));
            if (isFinite(keyCode)) {
                if (settings.keybind_kbm_code === undefined) {
                    settings.keybind_kbm_code = keyCode;
                }
                if (settings.keybind_gamepad_code === undefined) {
                    settings.keybind_gamepad_code = keyCode;
                }
            }
        }
    }
    var initialVisible = inferInitialVisibleFromSource(source, true);
    return applyUiStateMetaToPayload({
        ui_key: buildStableUiKey(source, uiKeyKind || "item_display"),
        __html_component_key: buildStableHtmlComponentKey(source),
        // 可选：HTML 标记“该组件组需要沉淀为控件组库自定义模板”（写回/导出阶段使用）。
        // - data-ui-save-template="<模板名>"：使用该名称（并在基底已存在同名模板时复用）
        // - data-ui-save-template="1"/"true"：表示需要沉淀，名称由导出端生成默认名
        __ui_custom_template_name: (dataUiSaveTemplate ? String(dataUiSaveTemplate || "").trim() : ""),
        widget_id: widgetId,
        widget_type: "道具展示",
        widget_name: widgetName,
        position: [Number(rect.left || 0), Number(rect.top || 0)],
        size: [Number(rect.width || 0), Number(rect.height || 0)],
        initial_visible: initialVisible,
        layer_index: Number.isFinite(zIndex) ? Math.trunc(zIndex) : 0,
        is_builtin: false,
        settings: settings,
        _html_button_aria_label: ariaLabel,
        _html_button_onclick: onclickText,
        _html_data_debug_label: dataDebugLabel,
        _html_data_inventory_item_id: dataInventoryItemId,
        // UI 交互动作标注（不绑定实现方式）
        ui_action_key: (dataUiAction ? String(dataUiAction || "").trim() : ""),
        ui_action_args: (dataUiActionArgs ? String(dataUiActionArgs || "").trim() : "")
    }, source);
}

