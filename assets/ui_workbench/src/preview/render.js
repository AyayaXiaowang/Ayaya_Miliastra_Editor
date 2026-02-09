import { dom } from "../dom_refs.js";
import {
    EMPTY_INPUT_PLACEHOLDER_MARKER,
    PREVIEW_VARIANT_FLATTENED,
    PREVIEW_VARIANT_SOURCE,
    getCanvasSizeByKey
} from "../config.js";
import { state } from "./state.js";
import { applyShadowInspectModeToPreviewDocument } from "./shadow_inspect.js";
import { applyCanvasSizeToPreviewDocument, updatePreviewStageScale } from "./scaling.js";
import { mountPreviewClickInspector, clearCurrentSelection } from "./selection.js";
import { hidePreviewSelectionOverlay } from "./overlays.js";
import { updatePreviewVariantButtonActiveState } from "./ui.js";
import { formatColorTextAsHex } from "./color.js";

var previewIframeElement = dom.previewIframeElement;
var _computeIframeElement = null;

function applyDynamicTextPreviewToHtml(htmlText) {
    // 预览专用：把声明了 data-ui-text 的元素显示为绑定占位符文本，便于检查绑定。
    // 重要：
    // - 只影响“可视预览 iframe”的 srcdoc，不影响 compute iframe（扁平化/导出/校验）。
    // - 只对“无子元素（或仅文本）”的节点生效，避免破坏复杂结构（例如含图标/多段 span 的按钮）。
    var raw = String(htmlText || "");
    if (!raw) {
        return raw;
    }
    if (!window || !window.DOMParser) {
        return raw;
    }
    var parser = new window.DOMParser();
    var parsed = parser.parseFromString(raw, "text/html");
    if (!parsed || !parsed.documentElement) {
        return raw;
    }
    var list = parsed.querySelectorAll ? parsed.querySelectorAll("[data-ui-text]") : [];
    for (var i = 0; i < (list ? list.length : 0); i++) {
        var el = list[i];
        if (!el) continue;
        if (el.children && el.children.length > 0) {
            continue;
        }
        var binding = String(el.getAttribute ? (el.getAttribute("data-ui-text") || "") : "").trim();
        if (!binding) {
            continue;
        }
        el.textContent = binding;
    }
    return parsed.documentElement.outerHTML || raw;
}

function applyDynamicTextPreviewToDocument(targetDocument) {
    // 预览专用（更强）：在已加载完成的 iframe document 上应用动态文本预览，
    // 以便能使用 computedStyle 获取真实文字颜色，并把 `<color=#...>` 标签一并显示出来。
    //
    // 注意：
    // - 这里的 `<color>` 是“字面量显示”（textContent），用于对齐写回 `.gil` 的最终文本内容；
    // - 不改动 DOM 结构：仅对“无子元素（或仅文本）”的节点生效，避免破坏复杂结构。
    if (!targetDocument || !targetDocument.querySelectorAll) {
        return;
    }
    var win = targetDocument.defaultView;
    if (!win || !win.getComputedStyle) {
        return;
    }
    var list = targetDocument.querySelectorAll("[data-ui-text]");
    for (var i = 0; i < (list ? list.length : 0); i++) {
        var el = list[i];
        if (!el) continue;
        if (el.children && el.children.length > 0) {
            continue;
        }
        var binding = String(el.getAttribute ? (el.getAttribute("data-ui-text") || "") : "").trim();
        if (!binding) {
            continue;
        }

        // 若用户已在 data-ui-text 里写了 <color=...>，则保持原样（避免双层包裹）。
        var lower = String(binding || "").toLowerCase();
        var hasColorTag = lower.indexOf("<color") >= 0 || lower.indexOf("</color>") >= 0;
        if (hasColorTag) {
            el.textContent = binding;
            continue;
        }

        var st = win.getComputedStyle(el);
        var colorText = st ? String(st.color || "").trim() : "";
        var colorHex = formatColorTextAsHex(colorText || "");
        if (colorHex) {
            el.textContent = "<color=" + String(colorHex) + ">" + binding + "</color>";
        } else {
            el.textContent = binding;
        }
    }
}

function ensureComputeIframeElement() {
    if (_computeIframeElement) {
        return _computeIframeElement;
    }
    if (!document || !document.body) {
        return null;
    }
    var iframe = document.createElement("iframe");
    iframe.setAttribute("sandbox", "allow-same-origin");
    iframe.setAttribute("aria-hidden", "true");
    iframe.tabIndex = -1;
    iframe.style.position = "fixed";
    iframe.style.left = "0";
    iframe.style.top = "0";
    iframe.style.width = "1600px";
    iframe.style.height = "900px";
    iframe.style.border = "0";
    // 经验值：部分浏览器在“刷新后首轮渲染”时，会对完全透明的 iframe 做更激进的优化，
    // 可能导致内部布局/取样长期为 0（表现为扁平化元素总数=0）。
    // 使用极低但非 0 的 opacity，既保持不可见，也显式要求浏览器进行布局计算。
    iframe.style.opacity = "0.001";
    iframe.style.pointerEvents = "none";
    // NOTE:
    // 这里不要用负 z-index：在部分环境下（尤其是“页面刷新后首次渲染”），
    // 浏览器可能把“完全被遮挡的 iframe”优化掉，导致内部布局/取样长期为 0（扁平化元素总数=0）。
    // compute iframe 本身不可交互且透明（pointer-events:none + opacity:0），放在正常层级即可。
    iframe.style.zIndex = "0";
    document.body.appendChild(iframe);
    _computeIframeElement = iframe;
    return _computeIframeElement;
}

export function resetComputePreviewHard() {
    // 彻底重置 compute iframe：用于修复极端情况下“刷新后 compute 提取长期为 0”的状态卡死。
    // 该函数为 fail-fast：若 DOM 不可用，直接按当前状态返回。
    if (_computeIframeElement && _computeIframeElement.parentNode) {
        _computeIframeElement.parentNode.removeChild(_computeIframeElement);
    }
    _computeIframeElement = null;
    state.computePreviewDocument = null;
    state.computeLastRenderedHtmlText = "";
    // 使任何在途渲染序列失效，避免旧 Promise finalize 覆盖新状态。
    state.computePreviewLoadSequence = (state.computePreviewLoadSequence || 0) + 1;
}

export function setComputePreviewCanvasSize(canvasSizeOption) {
    var iframe = ensureComputeIframeElement();
    if (!iframe || !canvasSizeOption) {
        return;
    }
    iframe.style.width = String(canvasSizeOption.width || 1600) + "px";
    iframe.style.height = String(canvasSizeOption.height || 900) + "px";
    if (state.computePreviewDocument) {
        applyCanvasSizeToPreviewDocument(state.computePreviewDocument, canvasSizeOption);
    }
}

export function normalizeHtmlForSandboxedPreviewSrcDoc(htmlText) {
    var raw = String(htmlText || "");
    if (!raw) {
        return "";
    }

    // 预览 iframe 默认 sandbox 禁用脚本（无 allow-scripts）。
    // 为避免控制台噪音、以及任何可能的“页面自导航/自刷新”，这里强制剔除脚本与 meta refresh。
    var updated = raw;

    // 优先用 DOMParser 做一次“结构化清洗”，避免漏掉：
    // - <svg><script> / 奇怪嵌套
    // - onload/onclick/... 这类内联事件（同样会触发 sandbox 的 blocked script 提示）
    // - href/src="javascript:..."（部分浏览器会尝试执行并报同类提示）
    if (window && window.DOMParser) {
        var parser = new window.DOMParser();
        var parsed = parser.parseFromString(updated, "text/html");
        if (parsed && parsed.documentElement) {
            // Marker: 用于确认 iframe.srcdoc 已真正写入目标文档（避免极端时序下拿到 about:blank 的 contentDocument）。
            // 该 marker 必须在 normalize 阶段稳定注入（作为 canonical HTML 的一部分），以保证缓存/对比口径一致。
            var markerId = "wb-sandbox-marker";

            var scriptList = parsed.querySelectorAll ? parsed.querySelectorAll("script") : [];
            for (var si = 0; si < (scriptList ? scriptList.length : 0); si++) {
                var s = scriptList[si];
                if (s && s.parentNode) {
                    s.parentNode.removeChild(s);
                }
            }

            var metaList = parsed.querySelectorAll ? parsed.querySelectorAll("meta[http-equiv]") : [];
            for (var mi = 0; mi < (metaList ? metaList.length : 0); mi++) {
                var meta = metaList[mi];
                if (!meta) continue;
                var httpEquiv = String(meta.getAttribute ? (meta.getAttribute("http-equiv") || "") : "").trim().toLowerCase();
                if (httpEquiv === "refresh") {
                    if (meta.parentNode) {
                        meta.parentNode.removeChild(meta);
                    }
                }
            }

            var allElements = parsed.querySelectorAll ? parsed.querySelectorAll("*") : [];
            for (var ei = 0; ei < (allElements ? allElements.length : 0); ei++) {
                var el = allElements[ei];
                if (!el || !el.attributes) continue;
                var attrs = el.attributes;
                for (var ai = attrs.length - 1; ai >= 0; ai--) {
                    var attr = attrs[ai];
                    if (!attr) continue;
                    var name = String(attr.name || "").trim().toLowerCase();
                    var value = String(attr.value || "").trim();
                    if (name && name.indexOf("on") === 0) {
                        // onload/onclick/...：sandbox 禁脚本时也会触发 blocked script 控制台提示
                        el.removeAttribute(attr.name);
                        continue;
                    }
                    var loweredValue = value.toLowerCase();
                    if (loweredValue.indexOf("javascript:") === 0) {
                        // 不仅是 href/src：例如 SVG 的 xlink:href 也可能携带 javascript:
                        el.removeAttribute(attr.name);
                        continue;
                    }
                }
            }

            // Ensure marker exists in <head> (or create head if missing).
            if (!parsed.getElementById || !parsed.getElementById(markerId)) {
                var head = parsed.head;
                if (!head && parsed.querySelector) {
                    head = parsed.querySelector("head");
                }
                if (!head && parsed.createElement && parsed.documentElement) {
                    head = parsed.createElement("head");
                    // Put head as first child of html when possible.
                    if (parsed.documentElement.firstChild) {
                        parsed.documentElement.insertBefore(head, parsed.documentElement.firstChild);
                    } else {
                        parsed.documentElement.appendChild(head);
                    }
                }
                if (head && parsed.createElement) {
                    var meta = parsed.createElement("meta");
                    meta.id = markerId;
                    meta.setAttribute("name", "wb-sandbox-marker");
                    meta.setAttribute("content", "1");
                    head.appendChild(meta);
                }
            }

            // serialize: keep as <html>...</html> (doctype 非必需)
            updated = parsed.documentElement.outerHTML || "";
        }
    }

    // <script ...>...</script>
    updated = updated.replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, "");
    // <script ... />
    updated = updated.replace(/<script\b[^>]*\/\s*>/gi, "");
    // 某些不规范 HTML 可能写了 `<script src="...">` 但缺少 `</script>`，上面两条无法移除。
    // 这里做一次兜底：若仍残留 `<script ...>`，则从第一个 `<script` 起丢弃后续内容，
    // 避免 sandbox 控制台持续报错，且避免后续渲染/切换卡住。
    for (var guard = 0; guard < 16; guard++) {
        var lower = updated.toLowerCase();
        var openIndex = lower.indexOf("<script");
        if (openIndex === -1) {
            break;
        }
        var closeIndex = lower.indexOf("</script", openIndex);
        if (closeIndex === -1) {
            updated = updated.slice(0, openIndex);
            break;
        }
        // 若还存在残留开闭标签（理论上不会），直接切掉这段
        var closeEnd = lower.indexOf(">", closeIndex);
        if (closeEnd === -1) {
            updated = updated.slice(0, openIndex);
            break;
        }
        updated = updated.slice(0, openIndex) + updated.slice(closeEnd + 1);
    }

    // <meta http-equiv="refresh" ...>
    updated = updated.replace(/<meta\b[^>]*http-equiv\s*=\s*["']?\s*refresh\s*["']?[^>]*>/gi, "");

    return updated;
}

function removeMetaRefreshTags(targetDocument) {
    if (!targetDocument) {
        return;
    }
    var metaList = targetDocument.querySelectorAll ? targetDocument.querySelectorAll("meta[http-equiv]") : [];
    if (!metaList || metaList.length === 0) {
        return;
    }
    for (var index = 0; index < metaList.length; index++) {
        var meta = metaList[index];
        if (!meta) {
            continue;
        }
        var httpEquiv = String(meta.getAttribute ? (meta.getAttribute("http-equiv") || "") : "");
        if (httpEquiv.toLowerCase() !== "refresh") {
            continue;
        }
        if (meta.parentNode) {
            meta.parentNode.removeChild(meta);
        }
    }
}

function ensurePreviewOverrideStyle(targetDocument) {
    if (!targetDocument || !targetDocument.head) {
        return;
    }

    var styleElementId = "ui-html-workbench-preview-override";
    var existingStyleElement = targetDocument.getElementById(styleElementId);
    if (existingStyleElement) {
        return;
    }

    var styleElement = targetDocument.createElement("style");
    styleElement.id = styleElementId;
    styleElement.textContent = [
        "/* injected by ui_html_workbench: preview-only overrides */",
        "*, *::before, *::after {",
        "  animation: none !important;",
        "  transition: none !important;",
        "  scroll-behavior: auto !important;",
        "}",
        "html {",
        "  padding: 0 !important;",
        "  display: block !important;",
        "  justify-content: initial !important;",
        "  align-items: initial !important;",
        "  overflow: hidden !important;",
        "}",
        "body {",
        "  margin: 0 !important;",
        "  overflow: hidden !important;",
        "}",
        ".canvas-toolbar,",
        ".page-switch-toolbar,",
        "#debug-overlay,",
        "#debug-text-panel,",
        "#selection-overlay,",
        "#selection-box,",
        "#debug-copy-toast,",
        "#debug-reverse-toggle,",
        "#debug-reverse-toggle-label {",
        "  display: none !important;",
        "}"
    ].join("\n");
    targetDocument.head.appendChild(styleElement);
}

export function renderHtmlIntoPreview(htmlText, previewVariant) {
    var normalizedVariant = previewVariant === PREVIEW_VARIANT_FLATTENED ? PREVIEW_VARIANT_FLATTENED : PREVIEW_VARIANT_SOURCE;
    var rawHtmlTextForIframe = String(htmlText || "");
    var htmlTextForIframe = normalizeHtmlForSandboxedPreviewSrcDoc(rawHtmlTextForIframe);
    // 动态文本预览是“纯显示”能力：仅影响可视预览 iframe 的 srcdoc。
    // 它不应改变预览变体（扁平/原稿），也不应影响 compute iframe（扁平化/导出/校验）。
    if (state.isDynamicTextPreviewEnabled) {
        htmlTextForIframe = applyDynamicTextPreviewToHtml(htmlTextForIframe);
    }
    var isEmptyInputPlaceholderHtml = htmlTextForIframe.indexOf(EMPTY_INPUT_PLACEHOLDER_MARKER) !== -1;
    state.currentPreviewVariant = normalizedVariant;
    state.lastRenderedHtmlText = htmlTextForIframe;
    if (normalizedVariant === PREVIEW_VARIANT_SOURCE && !isEmptyInputPlaceholderHtml) {
        state.lastRenderedSourceHtmlText = htmlTextForIframe;
    }
    updatePreviewVariantButtonActiveState(normalizedVariant);

    var expectedSequence = state.previewLoadSequence + 1;
    state.previewLoadSequence = expectedSequence;

    return new Promise(function (resolve) {
        if (!previewIframeElement) {
            resolve(null);
            return;
        }

        var hasResolved = false;
        // 关键：当 iframe srcdoc 发生变化时，部分浏览器可能在 1~数帧内仍返回“旧的 contentDocument”，但 readyState 已是 complete。
        // 若此时直接 finalize，会把点击监听挂在旧 document 上，最终表现为“切换几次页面后点选失效”。
        // 因此：当本次确实更新了 srcdoc 时，必须等待 contentDocument 对象切换（!== previous）后才允许 finalize。
        var previousDocumentAtRenderStart = state.previewDocument || null;
        var shouldWaitForNewDocumentObject = false;

        function tryFinalizeIframeLoadResult(forceFinalize) {
            if (hasResolved) {
                return;
            }
            var iframeDocument = previewIframeElement.contentDocument;
            if (!forceFinalize && shouldWaitForNewDocumentObject && previousDocumentAtRenderStart && iframeDocument === previousDocumentAtRenderStart) {
                return;
            }

            hasResolved = true;
            var isStillCurrent = state.previewLoadSequence === expectedSequence;

            // 被新的渲染请求覆盖：不再更新全局状态，但必须 resolve，避免 await 永久挂起
            if (!isStillCurrent) {
                resolve(iframeDocument || null);
                return;
            }

            state.previewDocument = iframeDocument;
            state.currentSelectedPreviewElement = null;
            state.currentSelectedPreviewGroup = null;
            hidePreviewSelectionOverlay();

            function bindPreviewDocumentOrRetry() {
                // 若 contentDocument 在 finalize 时仍为空（极少数时序/浏览器差异），下一帧再取一次：
                // 避免出现“预览已显示但点选/分组树全失效”的体感问题。
                var doc = state.previewDocument || previewIframeElement.contentDocument;
                if (!doc) {
                    return false;
                }
                state.previewDocument = doc;
                ensurePreviewOverrideStyle(doc);
                removeMetaRefreshTags(doc);
                applyCanvasSizeToPreviewDocument(doc, getCanvasSizeByKey(state.currentSelectedCanvasSizeKey));
                mountPreviewClickInspector(doc);
                applyShadowInspectModeToPreviewDocument(doc);
                if (state.isDynamicTextPreviewEnabled) {
                    applyDynamicTextPreviewToDocument(doc);
                }

                var canvasSizeOption = getCanvasSizeByKey(state.currentSelectedCanvasSizeKey);
                updatePreviewStageScale(canvasSizeOption);
                return true;
            }

            if (!bindPreviewDocumentOrRetry()) {
                window.requestAnimationFrame(function () {
                    // 被新的渲染覆盖时不再绑定，避免旧文档把监听挂到新序列上
                    if (state.previewLoadSequence !== expectedSequence) {
                        return;
                    }
                    bindPreviewDocumentOrRetry();
                });
            }

            resolve(state.previewDocument);
        }

        function onIframeLoad() {
            tryFinalizeIframeLoadResult(false);
        }

        var currentSrcDoc = previewIframeElement.srcdoc;
        if (currentSrcDoc !== htmlTextForIframe) {
            // 先绑定 load，再改 srcdoc：避免“空源码/极快加载”时丢失 load 事件
            previewIframeElement.addEventListener("load", onIframeLoad, { once: true });
            shouldWaitForNewDocumentObject = true;
            previewIframeElement.srcdoc = htmlTextForIframe;

            // 兼容性兜底：
            // 某些浏览器/某些时机下（尤其是多次快速切换 srcdoc），load 事件可能不触发，
            // 会导致 await 永久挂起，表现为“切不回去了/按钮无响应”。
            // 这里用帧轮询 + 超时保证 Promise 必然 resolve。
            var frameCount = 0;
            function pollReady() {
                if (hasResolved) {
                    return;
                }
                var doc = previewIframeElement.contentDocument;
                if (doc && (doc.readyState === "interactive" || doc.readyState === "complete")) {
                    // Require marker to avoid finalizing on about:blank in rare timing windows.
                    if (doc.getElementById && !doc.getElementById("wb-sandbox-marker")) {
                        // continue polling
                    } else {
                    // 若仍是旧 document，继续等（避免监听挂错 document 导致点选失效）
                    if (shouldWaitForNewDocumentObject && previousDocumentAtRenderStart && doc === previousDocumentAtRenderStart) {
                        // continue
                    } else {
                        tryFinalizeIframeLoadResult(false);
                        return;
                    }
                    }
                }
                frameCount += 1;
                if (frameCount >= 90) { // ~1.5s @60fps
                    tryFinalizeIframeLoadResult(true);
                    return;
                }
                window.requestAnimationFrame(pollReady);
            }
            window.requestAnimationFrame(pollReady);
            window.setTimeout(function () {
                tryFinalizeIframeLoadResult(true);
            }, 2500);
            return;
        }

        // srcdoc 未变化时，部分浏览器不会触发 load；下一帧直接复用当前 document
        window.requestAnimationFrame(function () {
            tryFinalizeIframeLoadResult(true);
        });
    });
}

export function renderHtmlIntoComputePreview(htmlText) {
    var rawHtmlTextForIframe = String(htmlText || "");
    var htmlTextForIframe = normalizeHtmlForSandboxedPreviewSrcDoc(rawHtmlTextForIframe);

    var expectedSequence = state.computePreviewLoadSequence + 1;
    state.computePreviewLoadSequence = expectedSequence;
    state.computeLastRenderedHtmlText = htmlTextForIframe;

    return new Promise(function (resolve) {
        var iframe = ensureComputeIframeElement();
        if (!iframe) {
            resolve(null);
            return;
        }

        var hasResolved = false;
        // 与可视预览对齐：避免极端时序下 contentDocument 仍为旧值/为空，
        // 导致 compute 提取得到 0 元素，从而扁平化/分组树全空。
        var previousDocumentAtRenderStart = state.computePreviewDocument || null;
        var shouldWaitForNewDocumentObject = false;

        function tryFinalizeIframeLoadResult(forceFinalize) {
            if (hasResolved) return;
            var iframeDocument = iframe.contentDocument;
            if (!forceFinalize && shouldWaitForNewDocumentObject && previousDocumentAtRenderStart && iframeDocument === previousDocumentAtRenderStart) {
                return;
            }

            var isStillCurrent = state.computePreviewLoadSequence === expectedSequence;
            if (!isStillCurrent) {
                resolve(iframeDocument || null);
                return;
            }

            // bind or retry next frames
            function bindComputeDocumentOrRetry() {
                var doc = iframe.contentDocument;
                if (!doc) {
                    return false;
                }
                state.computePreviewDocument = doc;
                applyCanvasSizeToPreviewDocument(state.computePreviewDocument, getCanvasSizeByKey(state.currentSelectedCanvasSizeKey));
                // 关键：强制触发布局（reflow），确保 bodyRect/元素 rect 可用。
                // 否则在部分刷新时序下可能出现 body.getBoundingClientRect() 为 0，
                // 进而导致 extractDisplayElementsData 全部判定“不在画布范围内”。
                if (state.computePreviewDocument.body) {
                    state.computePreviewDocument.body.getBoundingClientRect();
                    // offsetHeight 读一次作为更强的 reflow 触发（仍无副作用）
                    void state.computePreviewDocument.body.offsetHeight;
                }
                return true;
            }

            if (!bindComputeDocumentOrRetry()) {
                window.requestAnimationFrame(function () {
                    if (state.computePreviewLoadSequence !== expectedSequence) {
                        return;
                    }
                    if (!bindComputeDocumentOrRetry()) {
                        // 最终仍为空：保持 null，交由上层显示失败提示
                        state.computePreviewDocument = null;
                    }
                    hasResolved = true;
                    resolve(state.computePreviewDocument);
                });
                return;
            }

            hasResolved = true;
            resolve(state.computePreviewDocument);
        }

        function onIframeLoad() {
            tryFinalizeIframeLoadResult(false);
        }

        var currentSrcDoc = iframe.srcdoc;
        if (currentSrcDoc !== htmlTextForIframe) {
            iframe.addEventListener("load", onIframeLoad, { once: true });
            shouldWaitForNewDocumentObject = true;
            iframe.srcdoc = htmlTextForIframe;

            var frameCount = 0;
            function pollReady() {
                if (hasResolved) return;
                var doc = iframe.contentDocument;
                if (doc && (doc.readyState === "interactive" || doc.readyState === "complete")) {
                    // Require marker to avoid finalizing on about:blank in rare timing windows.
                    if (!doc.getElementById || doc.getElementById("wb-sandbox-marker")) {
                        tryFinalizeIframeLoadResult(false);
                    }
                }
                frameCount += 1;
                if (frameCount >= 90) {
                    tryFinalizeIframeLoadResult(true);
                    return;
                }
                window.requestAnimationFrame(pollReady);
            }
            window.requestAnimationFrame(pollReady);
            window.setTimeout(function () { tryFinalizeIframeLoadResult(true); }, 2500);
            return;
        }

        window.requestAnimationFrame(function () { tryFinalizeIframeLoadResult(true); });
    });
}

export function buildEmptyInputPlaceholderHtml() {
    return [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '  <meta charset="UTF-8" />',
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
        "  <title>空预览</title>",
        "  <style>",
        "    html, body {",
        "      margin: 0; padding: 0; width: 100%; height: 100%;",
        "      background: #000; color: #e0e0e0;",
        "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;",
        "      overflow: hidden;",
        "    }",
        "    .empty-tip {",
        "      position: absolute; inset: 0;",
        "      display: flex; align-items: center; justify-content: center;",
        "      padding: 48px; box-sizing: border-box;",
        "    }",
        "    .empty-card {",
        "      max-width: 640px;",
        "      border: 1px solid #333;",
        "      border-radius: 10px;",
        "      background: rgba(255,255,255,0.04);",
        "      padding: 16px 18px;",
        "      box-shadow: 0 16px 40px rgba(0,0,0,0.65);",
        "    }",
        "    .empty-card h2 {",
        "      margin: 0 0 8px 0;",
        "      font-size: 16px; font-weight: 700;",
        "      color: #fff;",
        "      letter-spacing: 0.3px;",
        "    }",
        "    .empty-card p {",
        "      margin: 0;",
        "      font-size: 13px;",
        "      color: #a8a8a8;",
        "      line-height: 1.7;",
        "    }",
        "    .empty-card code {",
        "      color: #3794ff;",
        "      font-family: Consolas, 'JetBrains Mono', monospace;",
        "      font-size: 12px;",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
        "  <!-- " + EMPTY_INPUT_PLACEHOLDER_MARKER + " -->",
        "  <div class=\"empty-tip\">",
        "    <div class=\"empty-card\">",
        "      <h2>未输入源码</h2>",
        "      <p>请在左侧粘贴完整 <code>&lt;html&gt;...&lt;/html&gt;</code> 文档后，再点击“生成扁平化”或切换到“扁平模式”。</p>",
        "    </div>",
        "  </div>",
        "</body>",
        "</html>"
    ].join("\n");
}

export function buildStatusPlaceholderHtml(titleText, messageText) {
    var title = String(titleText || "处理中").trim();
    var message = String(messageText || "").trim();
    return [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '  <meta charset="UTF-8" />',
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
        "  <title>" + title + "</title>",
        "  <style>",
        "    html, body {",
        "      margin: 0; padding: 0; width: 100%; height: 100%;",
        "      background: #000; color: #e0e0e0;",
        "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;",
        "      overflow: hidden;",
        "    }",
        "    .status {",
        "      position: absolute; inset: 0;",
        "      display: flex; align-items: center; justify-content: center;",
        "      padding: 48px; box-sizing: border-box;",
        "    }",
        "    .card {",
        "      max-width: 720px;",
        "      border: 1px solid #333;",
        "      border-radius: 10px;",
        "      background: rgba(255,255,255,0.04);",
        "      padding: 16px 18px;",
        "      box-shadow: 0 16px 40px rgba(0,0,0,0.65);",
        "    }",
        "    .card h2 {",
        "      margin: 0 0 8px 0;",
        "      font-size: 16px; font-weight: 700;",
        "      color: #fff;",
        "      letter-spacing: 0.3px;",
        "    }",
        "    .card p {",
        "      margin: 0;",
        "      font-size: 13px;",
        "      color: #a8a8a8;",
        "      line-height: 1.7;",
        "      white-space: pre-wrap;",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
        "  <div class=\"status\">",
        "    <div class=\"card\">",
        "      <h2>" + title + "</h2>",
        "      <p>" + (message ? message : "请稍候…") + "</p>",
        "    </div>",
        "  </div>",
        "</body>",
        "</html>",
    ].join("\n");
}

export function ensurePreviewIsReadyForHtml(htmlText) {
    var previewHtmlText = htmlText || "";
    var normalizedPreviewHtmlText = normalizeHtmlForSandboxedPreviewSrcDoc(previewHtmlText);
    if (!state.previewDocument || state.lastRenderedHtmlText !== normalizedPreviewHtmlText) {
        var expectedRenderSequence = state.previewLoadSequence + 1;
        return renderHtmlIntoPreview(previewHtmlText, PREVIEW_VARIANT_SOURCE).then(function () {
            if (state.previewLoadSequence !== expectedRenderSequence) {
                return false;
            }
            return true;
        });
    }
    applyCanvasSizeToPreviewDocument(state.previewDocument, getCanvasSizeByKey(state.currentSelectedCanvasSizeKey));
    return Promise.resolve(true);
}

export function ensureComputePreviewIsReadyForHtml(htmlText) {
    var previewHtmlText = htmlText || "";
    var normalizedPreviewHtmlText = normalizeHtmlForSandboxedPreviewSrcDoc(previewHtmlText);
    if (!state.computePreviewDocument || state.computeLastRenderedHtmlText !== normalizedPreviewHtmlText) {
        var expectedRenderSequence = state.computePreviewLoadSequence + 1;
        return renderHtmlIntoComputePreview(previewHtmlText).then(function () {
            if (state.computePreviewLoadSequence !== expectedRenderSequence) {
                return false;
            }
            if (!state.computePreviewDocument || !state.computePreviewDocument.body) {
                return false;
            }
            return true;
        });
    }
    if (!state.computePreviewDocument || !state.computePreviewDocument.body) {
        return Promise.resolve(false);
    }
    applyCanvasSizeToPreviewDocument(state.computePreviewDocument, getCanvasSizeByKey(state.currentSelectedCanvasSizeKey));
    return Promise.resolve(true);
}

export function refreshPreviewToRestoreDeletedElements() {
    if (!previewIframeElement) {
        return;
    }

    clearCurrentSelection();

    // 仅刷新 iframe 当前文档：不改动任何“源码/扁平化缓存”，确保删除为纯临时行为
    var expectedSequence = state.previewLoadSequence + 1;
    state.previewLoadSequence = expectedSequence;

    previewIframeElement.addEventListener("load", function () {
        if (state.previewLoadSequence !== expectedSequence) {
            return;
        }
        state.previewDocument = previewIframeElement.contentDocument;
        state.currentSelectedPreviewElement = null;
        state.currentSelectedPreviewGroup = null;
        hidePreviewSelectionOverlay();
        if (state.previewDocument) {
            ensurePreviewOverrideStyle(state.previewDocument);
            removeMetaRefreshTags(state.previewDocument);
            applyCanvasSizeToPreviewDocument(state.previewDocument, getCanvasSizeByKey(state.currentSelectedCanvasSizeKey));
            mountPreviewClickInspector(state.previewDocument);
            applyShadowInspectModeToPreviewDocument(state.previewDocument);
            updatePreviewStageScale(getCanvasSizeByKey(state.currentSelectedCanvasSizeKey));
        }
    }, { once: true });

    if (previewIframeElement.contentWindow && previewIframeElement.contentWindow.location) {
        previewIframeElement.contentWindow.location.reload();
    }
}


