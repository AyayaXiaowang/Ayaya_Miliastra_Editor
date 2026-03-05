import { dom } from "../dom_refs.js";
import { getCanvasSizeByKey } from "../config.js";
import { state } from "./state.js";
import { computeCanvasRectFromElement } from "./geometry.js";
import { clearTextAlignInspectorUi, updateInspectorForElement, updateInspectorForGroup } from "./inspector.js";
import {
    hidePreviewSelectionOverlay,
    hideReverseRegionOverlays,
    renderOverlayBoxForCanvasRect,
    updatePreviewSelectionOverlayForElement,
    updatePreviewSelectionOverlayForGroup
} from "./overlays.js";

var inspectorImportantTextAreaElement = dom.inspectorImportantTextAreaElement;
var inspectorDetailsTextAreaElement = dom.inspectorDetailsTextAreaElement;
var previewDragSelectBoxElement = dom.previewDragSelectBoxElement;

function emitSelectionChanged(kind, selectedElement, selectedGroup) {
    var cb = state.onSelectionChanged;
    if (typeof cb !== "function") {
        // 即便没有订阅者，也要暴露测试/诊断用的“最后一次选中信息”：
        // - 便于端到端用例断言“真实点选/列表点击”确实发生
        // - 便于现场排查映射问题（layerKey 是否为空 / 是否命中扁平层）
        var k0 = String(kind || "none");
        var el0 = selectedElement || null;
        var layerKey0 = "";
        if (el0) {
            if (el0.dataset && String(el0.dataset.layerKey || "").trim()) {
                layerKey0 = String(el0.dataset.layerKey || "").trim();
            } else if (el0.getAttribute && String(el0.getAttribute("data-layer-key") || "").trim()) {
                layerKey0 = String(el0.getAttribute("data-layer-key") || "").trim();
            }
        }
        window.__wb_last_preview_selected_layer_key = layerKey0;
        window.__wb_last_preview_selected = { kind: k0, layer_key: layerKey0 };
        return;
    }
    var k = String(kind || "none");
    var el = selectedElement || null;
    var layerKey = "";
    if (el) {
        if (el.dataset && String(el.dataset.layerKey || "").trim()) {
            layerKey = String(el.dataset.layerKey || "").trim();
        } else if (el.getAttribute && String(el.getAttribute("data-layer-key") || "").trim()) {
            layerKey = String(el.getAttribute("data-layer-key") || "").trim();
        }
    }
    // 测试/诊断约定：无论点选来源（画布点击/列表点击），都应写入最后一次选中层 key。
    window.__wb_last_preview_selected_layer_key = layerKey;
    window.__wb_last_preview_selected = { kind: k, layer_key: layerKey };
    cb({
        kind: k,
        element: el,
        group: selectedGroup || null
    });
}

export function clearCurrentSelection() {
    state.currentSelectedPreviewElement = null;
    state.currentSelectedPreviewGroup = null;
    hidePreviewSelectionOverlay();
    if (inspectorImportantTextAreaElement) {
        inspectorImportantTextAreaElement.value = "";
    }
    if (inspectorDetailsTextAreaElement) {
        inspectorDetailsTextAreaElement.value = "";
    }
    clearTextAlignInspectorUi();
    emitSelectionChanged("none", null, null);
}

export function selectPreviewElement(targetElement) {
    // 供外部（Workbench 列表）驱动选中：用于实现“列表 ↔ 画布”双向联动。
    // 兜底：极端情况下 state.previewDocument 可能尚未写回，但 iframe 已就绪。
    // 不要让“列表点击/分组树点击”因为时序差导致无响应。
    if (!state.previewDocument && dom && dom.previewIframeElement && dom.previewIframeElement.contentDocument) {
        state.previewDocument = dom.previewIframeElement.contentDocument;
    }
    if (!state.previewDocument) return;
    if (!targetElement) {
        return;
    }
    // 保护：避免把扁平化画布容器当作真实控件选中
    if (targetElement.classList && targetElement.classList.contains("flat-display-area")) {
        return;
    }

    state.currentSelectedPreviewGroup = null;
    state.currentSelectedPreviewElement = targetElement;
    updateInspectorForElement(state.previewDocument, targetElement);
    updatePreviewSelectionOverlayForElement(state.previewDocument, targetElement);
    emitSelectionChanged("element", targetElement, null);
}

function isEditableTextInputElement(targetElement) {
    if (!targetElement) {
        return false;
    }
    if (targetElement.isContentEditable) {
        return true;
    }
    var tagNameUpper = String(targetElement.tagName || "").toUpperCase();
    if (tagNameUpper === "TEXTAREA") {
        return !targetElement.readOnly && !targetElement.disabled;
    }
    if (tagNameUpper === "INPUT") {
        var inputType = String(targetElement.type || "text").toLowerCase();
        var isTextLikeInput =
            inputType === "text" ||
            inputType === "search" ||
            inputType === "url" ||
            inputType === "tel" ||
            inputType === "email" ||
            inputType === "password" ||
            inputType === "number";
        if (!isTextLikeInput) {
            return false;
        }
        return !targetElement.readOnly && !targetElement.disabled;
    }
    return false;
}

function buildDeletionTargetList(rawSelectedElements) {
    if (!state.previewDocument || !rawSelectedElements || rawSelectedElements.length === 0) {
        return [];
    }

    var uniqueSelectedElements = [];
    var uniqueSelectedElementSet = new Set();
    for (var index = 0; index < rawSelectedElements.length; index++) {
        var element = rawSelectedElements[index];
        if (!element) {
            continue;
        }
        if (uniqueSelectedElementSet.has(element)) {
            continue;
        }
        uniqueSelectedElementSet.add(element);
        uniqueSelectedElements.push(element);
    }

    var deletionTargetList = [];
    for (var candidateIndex = 0; candidateIndex < uniqueSelectedElements.length; candidateIndex++) {
        var candidateElement = uniqueSelectedElements[candidateIndex];
        if (!candidateElement) {
            continue;
        }
        if (candidateElement === state.previewDocument.documentElement || candidateElement === state.previewDocument.body) {
            continue;
        }
        // 保护：扁平化模式的“画布容器”不允许被删（删掉会导致所有扁平层消失）
        if (candidateElement.classList && candidateElement.classList.contains("flat-display-area")) {
            continue;
        }

        var ancestorElement = candidateElement.parentElement;
        var isAncestorAlsoSelected = false;
        while (ancestorElement) {
            if (uniqueSelectedElementSet.has(ancestorElement)) {
                isAncestorAlsoSelected = true;
                break;
            }
            ancestorElement = ancestorElement.parentElement;
        }
        if (!isAncestorAlsoSelected) {
            deletionTargetList.push(candidateElement);
        }
    }

    return deletionTargetList;
}

export function deleteSelectedPreviewElements() {
    if (!state.previewDocument) {
        return;
    }

    var rawSelectedElements = [];
    if (state.currentSelectedPreviewGroup && state.currentSelectedPreviewGroup.length > 0) {
        rawSelectedElements = state.currentSelectedPreviewGroup;
    } else if (state.currentSelectedPreviewElement) {
        rawSelectedElements = [state.currentSelectedPreviewElement];
    }

    var deletionTargetList = buildDeletionTargetList(rawSelectedElements);
    if (!deletionTargetList || deletionTargetList.length === 0) {
        return;
    }

    for (var index = 0; index < deletionTargetList.length; index++) {
        var targetElement = deletionTargetList[index];
        if (!targetElement || !targetElement.parentNode) {
            continue;
        }
        if (targetElement.classList && targetElement.classList.contains("flat-display-area")) {
            continue;
        }
        targetElement.parentNode.removeChild(targetElement);
    }

    // 删除后清空高亮与检查器，并提示“刷新可恢复”
    clearCurrentSelection();
    if (inspectorImportantTextAreaElement) {
        inspectorImportantTextAreaElement.value = "已删除 " + deletionTargetList.length + " 个元素（点击“刷新”可恢复）";
    }
    if (inspectorDetailsTextAreaElement) {
        inspectorDetailsTextAreaElement.value = "说明：删除仅作用于当前预览 iframe 的 DOM，不会改动左侧源码。";
    }
}

export function handleDeleteShortcutKeyDown(event) {
    if (!event) {
        return;
    }
    var keyName = String(event.key || "");
    if (keyName !== "Delete") {
        return;
    }

    var eventTargetDocument = event.target && event.target.ownerDocument ? event.target.ownerDocument : null;
    var activeElement = eventTargetDocument ? eventTargetDocument.activeElement : document.activeElement;
    if (isEditableTextInputElement(activeElement)) {
        return;
    }

    deleteSelectedPreviewElements();
    if (event.preventDefault) {
        event.preventDefault();
    }
    if (event.stopPropagation) {
        event.stopPropagation();
    }
}

export function setReverseRegionModeEnabled(isEnabled) {
    state.isReverseRegionModeEnabled = !!isEnabled;
    if (state.previewDocument && state.currentSelectedPreviewElement) {
        updatePreviewSelectionOverlayForElement(state.previewDocument, state.currentSelectedPreviewElement);
    } else if (state.previewDocument && state.currentSelectedPreviewGroup && state.currentSelectedPreviewGroup.length > 0) {
        updatePreviewSelectionOverlayForGroup(state.previewDocument, state.currentSelectedPreviewGroup);
    } else {
        hideReverseRegionOverlays();
    }

    if (state.previewDocument && state.currentSelectedPreviewGroup && state.currentSelectedPreviewGroup.length > 0) {
        updateInspectorForGroup(state.previewDocument, state.currentSelectedPreviewGroup);
    } else if (state.previewDocument && state.currentSelectedPreviewElement) {
        updateInspectorForElement(state.previewDocument, state.currentSelectedPreviewElement);
    }
}

export function mountPreviewClickInspector(targetDocument) {
    if (!targetDocument) {
        return;
    }

    if (state.previewClickListenerCleanup) {
        state.previewClickListenerCleanup();
        state.previewClickListenerCleanup = null;
    }

    function suppressDefaultPreviewInteraction(event) {
        if (!event) {
            return;
        }
        if (event.preventDefault) {
            event.preventDefault();
        }
        if (event.stopPropagation) {
            event.stopPropagation();
        }
    }

    function isIgnorableClickTarget(element) {
        if (!element) {
            return true;
        }
        if (element === targetDocument.documentElement || element === targetDocument.body) {
            return true;
        }
        if (element.classList) {
            // 扁平化模式：flat-display-area 是“画布容器”，点击空白处会命中它，选中会显示一个巨大框（不利于检查）
            if (element.classList.contains("flat-display-area")) {
                return true;
            }
        }
        return false;
    }

    function resolveSelectionTargetFromEvent(event) {
        if (!event) {
            return null;
        }
        function _isEffectivelyHiddenByStyle(el) {
            // 关键：用户通过“显隐/状态预览”等机制隐藏的层，不应仍能在画布上被点选。
            // 注意：此处不能简单用 pointer-events 过滤，因为扁平层为了“文字优先点击”会主动设置 pointer-events:none，
            // 而我们仍需要通过几何命中测试选中这些可见层。
            if (!el || !targetDocument || !targetDocument.defaultView || !targetDocument.defaultView.getComputedStyle) {
                return false;
            }
            var cs = targetDocument.defaultView.getComputedStyle(el);
            if (!cs) {
                return false;
            }
            if (cs.display === "none") {
                return true;
            }
            if (cs.visibility === "hidden") {
                return true;
            }
            // opacity:0 常用于“仅隐藏预览”（例如状态预览/调试显隐的某些链路）
            var op = Number(cs.opacity);
            if (isFinite(op) && op <= 0.0001) {
                return true;
            }
            return false;
        }
        function _parseZIndexValue(zText) {
            var raw = String(zText || "").trim().toLowerCase();
            if (!raw || raw === "auto") {
                return 0;
            }
            var n = Number(raw);
            if (!isFinite(n)) {
                return 0;
            }
            return Math.trunc(n);
        }

        function _inferFlatKindPriority(el) {
            // 更符合用户心智的点选优先级（而不是单纯按 z）：
            // 文本 > 底色（矩形） > 边框 > 阴影
            // 说明：border/shadow 多为“视觉装饰层”，更希望点到“可读/可交互”的主体。
            if (!el || !el.classList) return -1;
            if (el.classList.contains("flat-text")) return 3;
            // button anchor：视觉可能为空，但属于“可交互主体”的锚点，优先级与主体同级
            if (el.classList.contains("flat-button-anchor")) return 2;
            if (el.classList.contains("flat-element")) return 2;
            if (el.classList.contains("flat-border")) return 1;
            if (el.classList.contains("flat-shadow")) return 0;
            return -1;
        }

        function _pickBestFlatCandidate(candidateList) {
            var list = Array.isArray(candidateList) ? candidateList : [];
            if (!list || list.length === 0) {
                return null;
            }
            var best = null;
            var bestKindP = -1;
            var bestZ = null;
            var bestArea = null;
            for (var i = 0; i < list.length; i++) {
                var el = list[i];
                if (!el || !el.getBoundingClientRect) continue;
                if (isIgnorableClickTarget(el)) continue;
                if (_isEffectivelyHiddenByStyle(el)) continue;
                var kindP = _inferFlatKindPriority(el);
                if (kindP < 0) continue;

                var r = el.getBoundingClientRect();
                if (!r || r.width <= 0 || r.height <= 0) continue;

                var z = 0;
                if (targetDocument.defaultView && targetDocument.defaultView.getComputedStyle) {
                    var cs = targetDocument.defaultView.getComputedStyle(el);
                    if (cs) {
                        z = _parseZIndexValue(cs.zIndex);
                    }
                } else if (el.style && el.style.zIndex !== undefined) {
                    z = _parseZIndexValue(el.style.zIndex);
                }
                var area = Math.max(0, r.width) * Math.max(0, r.height);

                if (best === null) {
                    best = el;
                    bestKindP = kindP;
                    bestZ = z;
                    bestArea = area;
                    continue;
                }
                // 关键：必须先按“最上层（z-index）”决定可点选目标，避免选到被遮挡的底层内容。
                // 否则会出现“视觉上已被其它层盖住（已隐藏/不可见）但仍能点到”的体验问题。
                //
                // 策略：
                // 1) z-index 越大越靠上（优先）
                // 2) 同 z 再用“文本 > 主体 > 边框 > 阴影”细化（更符合心智）
                // 3) 同 z 同类：优先更小的（更精确的）碎片，避免总选到巨大的底层矩形
                if (bestZ === null || z > bestZ) {
                    best = el;
                    bestKindP = kindP;
                    bestZ = z;
                    bestArea = area;
                    continue;
                }
                if (z < bestZ) {
                    continue;
                }
                // z 相等：再比较 kind priority
                if (kindP > bestKindP) {
                    best = el;
                    bestKindP = kindP;
                    bestArea = area;
                    continue;
                }
                if (kindP < bestKindP) {
                    continue;
                }
                // 同 z 同 kind：更小 area 更优
                if (bestArea === null || area < bestArea) {
                    best = el;
                    bestArea = area;
                    continue;
                }
            }
            return best;
        }

        function resolveFlattenedLayerTargetByPoint(clientX, clientY) {
            // NOTE:
            // 扁平化输出为了“点选优先文字层”，会把 .flat-shadow/.flat-border/.flat-element 设为 pointer-events:none。
            // 这会导致 elementsFromPoint 拿不到这些层，从而表现为“扁平模式点不选/检查器不更新”。
            // 这里显式做一次几何命中测试（忽略 pointer-events）来恢复点选能力。
            if (!targetDocument || !targetDocument.querySelectorAll) {
                return null;
            }
            var candidates = targetDocument.querySelectorAll(".flat-text, .flat-element, .flat-border, .flat-shadow, .flat-button-anchor");
            if (!candidates || candidates.length === 0) {
                return null;
            }
            var hitList = [];
            for (var i = 0; i < candidates.length; i++) {
                var el = candidates[i];
                if (!el || !el.getBoundingClientRect) {
                    continue;
                }
                // 保护：不允许选中画布容器
                if (el.classList && el.classList.contains("flat-display-area")) {
                    continue;
                }
                // 若该层被隐藏（display:none / visibility:hidden / opacity:0），则必须跳过
                // 否则会出现“已隐藏但仍能在画布上点击选中”的体验问题。
                if (_isEffectivelyHiddenByStyle(el)) {
                    continue;
                }
                var r = el.getBoundingClientRect();
                if (!r || r.width <= 0 || r.height <= 0) {
                    continue;
                }
                if (clientX < r.left || clientX > r.right || clientY < r.top || clientY > r.bottom) {
                    continue;
                }
                hitList.push(el);
            }
            return _pickBestFlatCandidate(hitList);
        }
        function normalizeTarget(el) {
            if (!el || !el.classList) {
                return el || null;
            }
            // 统一：点击文字时选中外层 .flat-text，避免落在 inner 节点导致“看起来选不中/删不掉”
            if (el.classList.contains("flat-text-inner")) {
                var parentFlatText = el.closest ? el.closest(".flat-text") : null;
                return parentFlatText || el;
            }
            return el;
        }

        var isFlattenedVariant = String(state.currentPreviewVariant || "") === "flattened";
        function _isFlatSelectableLayer(el) {
            if (!el || !el.classList) {
                return false;
            }
            return (
                el.classList.contains("flat-text") ||
                el.classList.contains("flat-element") ||
                el.classList.contains("flat-border") ||
                el.classList.contains("flat-shadow") ||
                el.classList.contains("flat-button-anchor")
            );
        }

        function resolveTargetByViewportPoint(clientX, clientY) {
            var x = Number(clientX || 0);
            var y = Number(clientY || 0);
            if (!isFinite(x) || !isFinite(y)) {
                return null;
            }

            // elementsFromPoint 是首选（更快且命中更精确），但在 pointer-events:none/容器覆盖时可能拿不到 flat 层。
            var list = null;
            if (targetDocument.elementsFromPoint) {
                list = targetDocument.elementsFromPoint(x, y) || [];
            } else {
                list = [];
            }

            if (!list || list.length === 0) {
                return isFlattenedVariant ? resolveFlattenedLayerTargetByPoint(x, y) : null;
            }

            // 先收集一遍 flat-* 命中（包含可能被 pointer-events/容器覆盖影响的情况），统一按相同策略挑选。
            // 这样可以避免“同点叠多层时偶尔选到 border/shadow”的体验问题。
            var flatHitList = [];
            for (var i = 0; i < list.length; i++) {
                var el = normalizeTarget(list[i]);
                if (!el || isIgnorableClickTarget(el)) {
                    continue;
                }
                // 源码/扁平两种模式都适用：被隐藏的元素不允许成为“点击选中”的目标
                if (_isEffectivelyHiddenByStyle(el)) {
                    continue;
                }
                if (el.classList) {
                    if (
                        el.classList.contains("flat-text") ||
                        el.classList.contains("flat-element") ||
                        el.classList.contains("flat-border") ||
                        el.classList.contains("flat-shadow") ||
                        el.classList.contains("flat-button-anchor")
                    ) {
                        flatHitList.push(el);
                        continue;
                    }
                }
                // 扁平模式：不允许选中“非 flat-* 的大容器/布局节点”，避免出现“选中背景删除全没了”
                if (isFlattenedVariant) {
                    continue;
                }
                // 源码模式：次级兜底，返回第一个非容器元素
                return el;
            }

            if (flatHitList.length > 0) {
                var pickedFlat = _pickBestFlatCandidate(flatHitList);
                if (pickedFlat) {
                    return pickedFlat;
                }
            }

            // 兜底：elementsFromPoint 只返回容器时，回退几何命中（忽略 pointer-events）
            return isFlattenedVariant ? resolveFlattenedLayerTargetByPoint(x, y) : null;
        }

        var directTarget = normalizeTarget(event.target);
        if (directTarget && !isIgnorableClickTarget(directTarget)) {
            // 关键修正：
            // - 扁平化预览中，很多 flat 层会设为 pointer-events:none（“文字优先点击”）
            // - 这会让 event.target 落到“底层原始 DOM 容器”（例如某个大 panel/div）
            // - 若此处直接 return，会绕开后续的“按点几何命中挑选 flat-* 层”，导致总是选到大容器
            //
            // 因此：扁平化模式只允许“directTarget 本身就是可选 flat 层”时直返；否则继续走按点命中逻辑。
            if (_isEffectivelyHiddenByStyle(directTarget)) {
                // 被隐藏的层不应成为点选目标（两种模式保持一致）
            } else if (!isFlattenedVariant) {
                return directTarget;
            } else if (_isFlatSelectableLayer(directTarget)) {
                return directTarget;
            }
        }

        // fallback：某些情况下（例如容器覆盖/点击落在透明容器上），event.target 可能是大容器。
        // 用 point 命中找到真正的可选层（优先 flat-*）。
        //
        // 关键兼容点：
        // - 预览 iframe 在父页面通过 CSS transform: scale(...) 缩放显示；
        // - 不同浏览器/不同输入源下，click 事件的 clientX/clientY 可能是“缩放后的坐标”或“未缩放坐标”；
        // - 当扁平层使用 pointer-events:none 时，elementsFromPoint 可能拿不到层。
        // 这里生成一组“候选坐标”，逐个尝试命中，尽可能覆盖这些差异。
        var rawX = Number(event.clientX || 0);
        var rawY = Number(event.clientY || 0);
        var scale = Number(state.currentPreviewScale || 1);
        if (!isFinite(scale) || scale <= 0) {
            scale = 1;
        }

        var usedKeys = new Set();
        var pointList = [];
        function pushPoint(x, y) {
            var px = Number(x);
            var py = Number(y);
            if (!isFinite(px) || !isFinite(py)) {
                return;
            }
            var key = String(Math.round(px)) + "|" + String(Math.round(py));
            if (usedKeys.has(key)) {
                return;
            }
            usedKeys.add(key);
            pointList.push({ x: px, y: py });
        }

        // 1) 直接使用 event.clientX/Y
        pushPoint(rawX, rawY);

        // 2) 按预览缩放比例做一次反算（以及正算），覆盖“坐标是否已缩放”的差异
        if (Math.abs(scale - 1) > 1e-6) {
            pushPoint(rawX / scale, rawY / scale);
            pushPoint(rawX * scale, rawY * scale);
        }

        // 3) 若有 offsetX/offsetY，则把它换算成 viewport 坐标（更贴近真实点击点）
        //    注意：offsetX/offsetY 的参考系是 event.target（不是 normalize 后的 directTarget）。
        var rawEventTarget = event.target;
        var ox = Number(event.offsetX);
        var oy = Number(event.offsetY);
        if (rawEventTarget && rawEventTarget.getBoundingClientRect && isFinite(ox) && isFinite(oy)) {
            var tr = rawEventTarget.getBoundingClientRect();
            if (tr) {
                pushPoint(Number(tr.left) + ox, Number(tr.top) + oy);
                if (Math.abs(scale - 1) > 1e-6) {
                    pushPoint(Number(tr.left) + ox / scale, Number(tr.top) + oy / scale);
                    pushPoint(Number(tr.left) + ox * scale, Number(tr.top) + oy * scale);
                }
            }
        }

        // 4) 兼容极端情况：若某些环境下 event.clientX/Y 意外变成“父页面坐标”，尝试用 iframe rect 做一次转换。
        //    说明：点击事件不跨 iframe 冒泡，理论上不应发生；但这里作为兜底不影响正常路径。
        if (dom && dom.previewIframeElement && dom.previewIframeElement.getBoundingClientRect) {
            var iframeRect = dom.previewIframeElement.getBoundingClientRect();
            if (iframeRect) {
                pushPoint(rawX - Number(iframeRect.left || 0), rawY - Number(iframeRect.top || 0));
                if (Math.abs(scale - 1) > 1e-6) {
                    pushPoint((rawX - Number(iframeRect.left || 0)) / scale, (rawY - Number(iframeRect.top || 0)) / scale);
                    pushPoint((rawX - Number(iframeRect.left || 0)) * scale, (rawY - Number(iframeRect.top || 0)) * scale);
                }
            }
        }

        for (var pi = 0; pi < pointList.length; pi++) {
            var pt = pointList[pi];
            var picked = resolveTargetByViewportPoint(pt.x, pt.y);
            if (picked) {
                return picked;
            }
        }
        return null;
    }

    var clickListener = function (event) {
        if (!event || !event.target) {
            return;
        }
        // 预览用于“检查/选择/删除”，不应触发页面的跳转/默认点击行为，否则可能把 iframe 导航到 404 页面。
        suppressDefaultPreviewInteraction(event);
        if (state.selectionJustCompleted) {
            state.selectionJustCompleted = false;
            return;
        }
        var clickedElement = resolveSelectionTargetFromEvent(event);
        if (!clickedElement) {
            clearCurrentSelection();
            return;
        }

        if (event.shiftKey) {
            toggleShiftSelection(targetDocument, clickedElement);
            return;
        }

        state.currentSelectedPreviewGroup = null;
        state.currentSelectedPreviewElement = clickedElement;
        updateInspectorForElement(targetDocument, clickedElement);
        updatePreviewSelectionOverlayForElement(targetDocument, clickedElement);
        emitSelectionChanged("element", clickedElement, null);
    };

    targetDocument.addEventListener("click", clickListener, true);
    var submitListener = function (event) {
        suppressDefaultPreviewInteraction(event);
    };
    targetDocument.addEventListener("submit", submitListener, true);
    var keyDownListener = function (event) {
        handleDeleteShortcutKeyDown(event);
    };
    targetDocument.addEventListener("keydown", keyDownListener, true);
    state.previewClickListenerCleanup = function () {
        targetDocument.removeEventListener("click", clickListener, true);
        targetDocument.removeEventListener("submit", submitListener, true);
        targetDocument.removeEventListener("keydown", keyDownListener, true);
    };

    mountSelectionDragHandlers(targetDocument);
}

function toggleShiftSelection(targetDocument, clickedElement) {
    if (!targetDocument || !clickedElement) {
        return;
    }

    var nextGroup = [];
    if (state.currentSelectedPreviewGroup && state.currentSelectedPreviewGroup.length > 0) {
        for (var index = 0; index < state.currentSelectedPreviewGroup.length; index++) {
            nextGroup.push(state.currentSelectedPreviewGroup[index]);
        }
    }

    if ((!nextGroup || nextGroup.length === 0) && state.currentSelectedPreviewElement && state.currentSelectedPreviewElement !== clickedElement) {
        nextGroup.push(state.currentSelectedPreviewElement);
    }

    var existingIndex = -1;
    for (var elementIndex = 0; elementIndex < nextGroup.length; elementIndex++) {
        if (nextGroup[elementIndex] === clickedElement) {
            existingIndex = elementIndex;
            break;
        }
    }

    if (existingIndex >= 0) {
        nextGroup.splice(existingIndex, 1);
    } else {
        nextGroup.push(clickedElement);
    }

    state.currentSelectedPreviewElement = null;

    if (nextGroup.length === 0) {
        state.currentSelectedPreviewGroup = null;
        clearCurrentSelection();
        return;
    }

    state.currentSelectedPreviewGroup = nextGroup;
    updateInspectorForGroup(targetDocument, nextGroup);
    updatePreviewSelectionOverlayForGroup(targetDocument, nextGroup);
    emitSelectionChanged("group", null, nextGroup);
}

function updateDragSelectionBoxVisual() {
    if (!previewDragSelectBoxElement || !state.previewDocument || !state.previewDocument.body) {
        return;
    }
    if (!state.isDraggingSelection) {
        previewDragSelectBoxElement.style.display = "none";
        return;
    }

    var left = Math.min(state.selectionStartCanvasX, state.selectionCurrentCanvasX);
    var top = Math.min(state.selectionStartCanvasY, state.selectionCurrentCanvasY);
    var width = Math.abs(state.selectionCurrentCanvasX - state.selectionStartCanvasX);
    var height = Math.abs(state.selectionCurrentCanvasY - state.selectionStartCanvasY);

    renderOverlayBoxForCanvasRect(previewDragSelectBoxElement, { left: left, top: top, width: width, height: height });
}

function isElementVisibleForSelection(targetDocument, element) {
    if (!targetDocument || !element || !element.getBoundingClientRect) {
        return false;
    }
    var rect = element.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
        return false;
    }
    var computedStyle = targetDocument.defaultView.getComputedStyle(element);
    if (!computedStyle) {
        return false;
    }
    if (computedStyle.display === "none" || computedStyle.visibility === "hidden") {
        return false;
    }
    return true;
}

function performGroupSelectionByRect(targetDocument, selectionRectCanvas) {
    if (!targetDocument || !targetDocument.body || !selectionRectCanvas) {
        return [];
    }

    var selectableElementList = [];
    var debugTargetList = targetDocument.querySelectorAll(".debug-target");
    if (debugTargetList && debugTargetList.length > 0) {
        selectableElementList = Array.from(debugTargetList);
    } else {
        selectableElementList = Array.from(targetDocument.body.querySelectorAll("*"));
    }

    var selectedElements = [];
    for (var index = 0; index < selectableElementList.length; index++) {
        var element = selectableElementList[index];
        if (!element || element === targetDocument.body || element === targetDocument.documentElement) {
            continue;
        }
        if (!isElementVisibleForSelection(targetDocument, element)) {
            continue;
        }
        var elementCanvasRect = computeCanvasRectFromElement(targetDocument, element);
        if (!elementCanvasRect) {
            continue;
        }

        var elementLeft = elementCanvasRect.left;
        var elementTop = elementCanvasRect.top;
        var elementRight = elementLeft + elementCanvasRect.width;
        var elementBottom = elementTop + elementCanvasRect.height;

        var selectLeft = selectionRectCanvas.left;
        var selectTop = selectionRectCanvas.top;
        var selectRight = selectLeft + selectionRectCanvas.width;
        var selectBottom = selectTop + selectionRectCanvas.height;

        var isSeparated =
            elementRight < selectLeft ||
            elementLeft > selectRight ||
            elementBottom < selectTop ||
            elementTop > selectBottom;
        if (!isSeparated) {
            selectedElements.push(element);
        }
    }

    return selectedElements;
}

function mountSelectionDragHandlers(targetDocument) {
    if (!targetDocument || !targetDocument.body) {
        return;
    }

    var onMouseDown = function (event) {
        if (!event || event.button !== 0) {
            return;
        }
        state.isMouseDownForSelection = true;
        state.isDraggingSelection = false;
        state.selectionJustCompleted = false;

        var bodyRect = targetDocument.body.getBoundingClientRect();
        state.selectionStartCanvasX = event.clientX - bodyRect.left;
        state.selectionStartCanvasY = event.clientY - bodyRect.top;
        state.selectionCurrentCanvasX = state.selectionStartCanvasX;
        state.selectionCurrentCanvasY = state.selectionStartCanvasY;
    };

    var onMouseMove = function (event) {
        if (!state.isMouseDownForSelection) {
            return;
        }
        if (!event) {
            return;
        }
        var bodyRect = targetDocument.body.getBoundingClientRect();
        state.selectionCurrentCanvasX = event.clientX - bodyRect.left;
        state.selectionCurrentCanvasY = event.clientY - bodyRect.top;

        if (!state.isDraggingSelection) {
            var dx = Math.abs(state.selectionCurrentCanvasX - state.selectionStartCanvasX);
            var dy = Math.abs(state.selectionCurrentCanvasY - state.selectionStartCanvasY);
            if (dx < state.selectionDragThreshold && dy < state.selectionDragThreshold) {
                return;
            }
            state.isDraggingSelection = true;
        }

        updateDragSelectionBoxVisual();
    };

    var onMouseUp = function () {
        if (!state.isMouseDownForSelection) {
            return;
        }
        state.isMouseDownForSelection = false;

        if (!state.isDraggingSelection) {
            updateDragSelectionBoxVisual();
            return;
        }

        state.isDraggingSelection = false;
        updateDragSelectionBoxVisual();

        var left = Math.min(state.selectionStartCanvasX, state.selectionCurrentCanvasX);
        var top = Math.min(state.selectionStartCanvasY, state.selectionCurrentCanvasY);
        var width = Math.abs(state.selectionCurrentCanvasX - state.selectionStartCanvasX);
        var height = Math.abs(state.selectionCurrentCanvasY - state.selectionStartCanvasY);

        var selected = performGroupSelectionByRect(targetDocument, { left: left, top: top, width: width, height: height });
        if (selected.length === 0) {
            clearCurrentSelection();
            state.selectionJustCompleted = true;
            return;
        }

        state.currentSelectedPreviewElement = null;
        state.currentSelectedPreviewGroup = selected;
        updateInspectorForGroup(targetDocument, selected);
        updatePreviewSelectionOverlayForGroup(targetDocument, selected);
        emitSelectionChanged("group", null, selected);
        state.selectionJustCompleted = true;
    };

    targetDocument.addEventListener("mousedown", onMouseDown, true);
    targetDocument.addEventListener("mousemove", onMouseMove, true);
    targetDocument.addEventListener("mouseup", onMouseUp, true);

    // 在换页面/重新挂载时清理
    var previousCleanup = state.previewClickListenerCleanup;
    state.previewClickListenerCleanup = function () {
        if (previousCleanup) {
            previousCleanup();
        }
        targetDocument.removeEventListener("mousedown", onMouseDown, true);
        targetDocument.removeEventListener("mousemove", onMouseMove, true);
        targetDocument.removeEventListener("mouseup", onMouseUp, true);
    };
}


