import { CANVAS_SIZE_CATALOG } from "../config.js";
import { waitForNextFrame } from "../utils.js";
import {
  extractDisplayElementsData,
  generateFlattenedDivs,
  buildFlattenedInjectionHtml,
  normalizeSizeKeyForCssClass,
  rewritePageSwitchLinksForFlattenedOutput,
  replaceBodyInnerHtml,
} from "../flatten.js";
import { setStatusText } from "./context.js";
import * as preview from "../preview/index.js";

function _safeNumber(n) {
  var x = Number(n);
  if (!isFinite(x)) return 0;
  return x;
}

function _sumStats(diagList, key) {
  var total = 0;
  for (var i = 0; i < diagList.length; i++) {
    var d = diagList[i] || {};
    var s = d.stats || {};
    total += _safeNumber(s[key]);
  }
  return total;
}

function _buildEmptyFlattenFailureText(result, canvasCatalog) {
  var perSize = (result && result.perSize) ? result.perSize : [];
  var diags = [];
  for (var i = 0; i < perSize.length; i++) {
    var d = (perSize[i] && perSize[i].extractDiagnostics) ? perSize[i].extractDiagnostics : null;
    if (d) diags.push(d);
  }

  var totalVisited = _sumStats(diags, "totalVisited");
  var totalEmitted = _sumStats(diags, "totalEmitted");
  var skippedDisplayNone = _sumStats(diags, "skippedDisplayNone");
  var skippedVisHidden = _sumStats(diags, "skippedVisibilityHiddenWithoutUiState");
  var skippedZeroRectNonButton = _sumStats(diags, "skippedZeroRectNonButton");
  var skippedZeroRectBtnNoUnion = _sumStats(diags, "skippedZeroRectButtonNoUnionRect");
  var skippedOutsideCanvas = _sumStats(diags, "skippedOutsideCanvas");
  var skippedNoViewOrCS = _sumStats(diags, "skippedNoViewOrComputedStyle");
  var skippedNoCS = _sumStats(diags, "skippedNoComputedStyle");

  var reasons = [];
  var tips = [];

  // Reason 1: DOM为空（body没有子元素，或遍历没有触发）
  if (totalVisited <= 0) {
    reasons.push("页面的 body 下没有可遍历的元素（或文档尚未就绪），因此提取结果为 0。");
    tips.push("切到“原稿”看看是否能看到任何内容；如果原稿也是空白，优先检查 HTML 是否真的有 body 内容。");
  }

  // Reason 2: 布局尚未稳定（body/canvas 尺寸为 0）
  var allBodyZero = true;
  for (var bi = 0; bi < diags.length; bi++) {
    var br = (diags[bi] && diags[bi].bodyRect) ? diags[bi].bodyRect : null;
    var bw = br ? _safeNumber(br.width) : 0;
    var bh = br ? _safeNumber(br.height) : 0;
    if (bw > 1 && bh > 1) {
      allBodyZero = false;
      break;
    }
  }
  if (diags.length > 0 && allBodyZero) {
    reasons.push("浏览器还没完成排版：compute iframe 的 body 尺寸为 0×0（导致所有元素盒子为 0 或无法相交）。");
    tips.push("等待 1~2 秒后点“扁平分组/刷新”重试；如果每次刷新都稳定为 0×0，说明 compute iframe 没有真正渲染（需要看控制台/网络是否有报错）。");
  }

  // Reason 3: 全部被隐藏
  if (totalVisited > 0 && totalEmitted === 0) {
    var hiddenSkips = skippedDisplayNone + skippedVisHidden;
    if (hiddenSkips > 0 && hiddenSkips >= Math.max(1, Math.floor(totalVisited * 0.9))) {
      reasons.push(
        "页面元素几乎都被隐藏了：扫描到 " +
          String(totalVisited) +
          " 个元素，其中 " +
          String(skippedDisplayNone) +
          " 个是 display:none，" +
          String(skippedVisHidden) +
          " 个是 visibility:hidden（且不属于多状态容器）。"
      );
      tips.push("如果你用的是多状态控件，非默认态请优先用 visibility:hidden（并确保处于 data-ui-state-group 容器内），不要用 display:none。");
    }
  }

  // Reason 4: 全部 0 尺寸
  if (totalVisited > 0 && totalEmitted === 0) {
    var zeroSkips = skippedZeroRectNonButton + skippedZeroRectBtnNoUnion;
    if (zeroSkips > 0 && zeroSkips >= Math.max(1, Math.floor(totalVisited * 0.8))) {
      reasons.push(
        "页面元素盒子尺寸几乎都是 0：被跳过的 0 尺寸元素共 " +
          String(zeroSkips) +
          " 个（其中非按钮 " +
          String(skippedZeroRectNonButton) +
          " 个；显式按钮但无法从子树推导盒子 " +
          String(skippedZeroRectBtnNoUnion) +
          " 个）。"
      );
      tips.push("常见原因是布局尚未稳定，或元素依赖字体/图片加载后才有尺寸。可以先确认原稿模式下是否能看到完整排版。");
    }
  }

  // Reason 5: 全在画布裁剪范围外
  if (totalVisited > 0 && totalEmitted === 0 && skippedOutsideCanvas > 0) {
    if (skippedOutsideCanvas >= Math.max(1, Math.floor(totalVisited * 0.8))) {
      var sampleDiag = diags.length > 0 ? diags[0] : null;
      var cr = sampleDiag ? sampleDiag.canvasRect : null;
      var cs = sampleDiag ? sampleDiag.canvasSize : null;
      var cssInline = sampleDiag && sampleDiag.cssVars ? sampleDiag.cssVars.inline : null;
      reasons.push(
        "页面元素几乎都落在“画布裁剪范围”之外：被跳过的 outside-canvas 元素 " +
          String(skippedOutsideCanvas) +
          " 个。"
      );
      if (cr && cs) {
        reasons.push(
          "当前裁剪框：left=" +
            String(_safeNumber(cr.left)) +
            ", top=" +
            String(_safeNumber(cr.top)) +
            ", width=" +
            String(_safeNumber(cs.width)) +
            ", height=" +
            String(_safeNumber(cs.height)) +
            "。"
        );
      }
      if (cssInline) {
        reasons.push(
          "当前注入的 CSS 变量：--canvas-width=\"" +
            String(cssInline.canvasWidth || "").trim() +
            "\", --canvas-height=\"" +
            String(cssInline.canvasHeight || "").trim() +
            "\"。"
        );
      }
      tips.push("确认页面是不是把内容放在某个容器里（例如 .preview-stage），且容器的坐标不是从 body 左上角开始。必要时检查 --canvas-width/height 是否被正确注入。");
    }
  }

  // Reason 6: compute 文档无法取到 computedStyle（极少见，但要提示）
  if (skippedNoViewOrCS > 0 || skippedNoCS > 0) {
    reasons.push(
      "compute 文档的样式计算不可用：跳过 " +
        String(skippedNoViewOrCS) +
        " 个（无 defaultView/getComputedStyle），" +
        String(skippedNoCS) +
        " 个（computedStyle 为空）。"
    );
    tips.push("这通常意味着 compute iframe 没有正确加载/同源环境异常。请打开控制台看是否有 iframe 相关报错。");
  }

  if (reasons.length <= 0) {
    reasons.push("本次提取流程没有得到任何可用于扁平化的图层，但未命中明确的过滤原因统计（请查看控制台诊断对象）。");
  }

  var lines = [];
  lines.push("未提取到任何可用扁平层，因此无法生成扁平预览与分组树。");
  lines.push("");
  lines.push("本次失败的直接原因（基于实时统计）：");
  for (var ri = 0; ri < reasons.length; ri++) {
    lines.push("- " + String(reasons[ri]));
  }
  lines.push("");
  lines.push("关键数据：");
  lines.push("- 4个尺寸提取元素总数: " + String(result.totalElementsExtracted));
  lines.push("- 有内容的尺寸数: " + String(result.totalAreasWithDivs) + " / " + String(canvasCatalog.length));
  lines.push(
    "- DOM 扫描/产出: visited=" +
      String(totalVisited) +
      ", emitted=" +
      String(totalEmitted) +
      "（emitted=0 即“没有任何元素进入扁平层候选集”）"
  );
  lines.push(
    "- 过滤统计: display:none=" +
      String(skippedDisplayNone) +
      ", visibility:hidden(非多状态)=" +
      String(skippedVisHidden) +
      ", 0尺寸=" +
      String(skippedZeroRectNonButton + skippedZeroRectBtnNoUnion) +
      ", 裁剪范围外(outside-canvas)=" +
      String(skippedOutsideCanvas)
  );
  for (var si = 0; si < perSize.length; si++) {
    var p = perSize[si] || {};
    lines.push(
      "- " +
        String(p.label || p.sizeKey || ("size#" + String(si))) +
        ": elements=" +
        String(p.elementsCount) +
        ", bodySize=" +
        String(p.bodyW) +
        "×" +
        String(p.bodyH)
    );
  }
  if (tips.length > 0) {
    lines.push("");
    lines.push("建议（不需要懂代码）：");
    for (var ti = 0; ti < tips.length; ti++) {
      lines.push("- " + String(tips[ti]));
    }
  }
  lines.push("");
  lines.push("程序员定位：打开控制台查看 window.__wb_last_flatten_empty_diagnostics（包含每个尺寸的过滤统计与画布变量）。");
  return lines.join("\n");
}

async function _extractElementsDataForSize(previewDoc, sourceHtmlText, canvasSizeOption) {
  var trimmed = String(sourceHtmlText || "").trim();
  var elementsData = null;

  if (trimmed) {
    var computeReady = await preview.ensureComputePreviewIsReadyForHtml(trimmed);
    if (computeReady) {
      preview.setComputePreviewCanvasSize(canvasSizeOption);
      var computeDoc = preview.getComputePreviewDocument();
      if (computeDoc) {
        // 关键：compute 预览同样需要应用 canvas size（vw/vh/clamp/--canvas-* 等依赖），否则可能提取到空 elementsData，
        // 从而触发 fallback（会导致可视预览闪回原稿）。
        preview.applyCanvasSizeToPreviewDocument(computeDoc, canvasSizeOption);
        await waitForNextFrame();
        await waitForNextFrame();
        elementsData = extractDisplayElementsData(computeDoc);

        // 经验修复：
        // 在部分环境下，“首次打开网页后第一次选文件”时，compute iframe 虽然已 load，
        // 但布局/字体/样式计算可能还没稳定，导致首轮提取为空，从而显示“扁平化失败（结果为空）”。
        // 等用户切换到别的文件/项目再切回来时，时间足够所以又正常。
        //
        // 这里做一次“额外等待 + 重试提取”，以消除这种首轮时序问题。
        if (!elementsData || !elementsData.elements || elementsData.elements.length <= 0) {
          await waitForNextFrame();
          await waitForNextFrame();
          await waitForNextFrame();
          await waitForNextFrame();
          elementsData = extractDisplayElementsData(computeDoc);
        }
      }
    }
  }

  if (elementsData && elementsData.elements && elementsData.elements.length > 0) {
    return elementsData;
  }

  if (previewDoc) {
    preview.applyCanvasSizeToPreviewDocument(previewDoc, canvasSizeOption);
    await waitForNextFrame();
    await waitForNextFrame();
    var fallbackData = extractDisplayElementsData(previewDoc);
    if (fallbackData && fallbackData.elements && fallbackData.elements.length > 0) {
      return fallbackData;
    }
    if (fallbackData) {
      elementsData = fallbackData;
    }
  }

  if (elementsData) {
    return elementsData;
  }
  return { elements: [], bodySize: { width: 0, height: 0 } };
}

export async function generateFlattenedHtmlFromSourceHtml(sourceHtmlText, uiKeyPrefix) {
  var htmlText = String(sourceHtmlText || "");
  var trimmed = String(htmlText || "").trim();
  if (!trimmed) {
    return "";
  }

  async function _buildFlatAreasFromComputeDoc(computeDoc, htmlTextForOutput, uiKeyPrefixText) {
    var flatAreaList = [];
    var hasAnyDivs = false;
    var totalElementsExtracted = 0;
    var totalAreasWithDivs = 0;
    var perSize = [];
    for (var sizeIndex = 0; sizeIndex < CANVAS_SIZE_CATALOG.length; sizeIndex++) {
      var canvasSizeOption = CANVAS_SIZE_CATALOG[sizeIndex];
      preview.setComputePreviewCanvasSize(canvasSizeOption);
      preview.applyCanvasSizeToPreviewDocument(computeDoc, canvasSizeOption);
      await waitForNextFrame();
      await waitForNextFrame();

      // 注意：这里不传 previewDoc，避免 compute 偶发取空时 fallback 到可视预览导致闪回原稿。
      // 如果 compute 环境真的取不到元素（极少数），那就让该尺寸的 divs 为空，最终整体回退为原稿输出。
      var elementsData = await _extractElementsDataForSize(null, trimmed, canvasSizeOption);
      totalElementsExtracted += (elementsData && elementsData.elements ? elementsData.elements.length : 0);
      var bodyW = elementsData && elementsData.bodySize ? _safeNumber(elementsData.bodySize.width) : 0;
      var bodyH = elementsData && elementsData.bodySize ? _safeNumber(elementsData.bodySize.height) : 0;
      var extractDiagnostics = elementsData && elementsData.diagnostics ? elementsData.diagnostics : null;
      var safeKey = normalizeSizeKeyForCssClass(canvasSizeOption.label);
      var divsHtml = generateFlattenedDivs(elementsData, safeKey, { ui_key_prefix: String(uiKeyPrefixText || "") });
      if (String(divsHtml || "").trim()) {
        hasAnyDivs = true;
        totalAreasWithDivs += 1;
      }
      perSize.push({
        sizeKey: canvasSizeOption.key,
        label: canvasSizeOption.label,
        elementsCount: (elementsData && elementsData.elements) ? elementsData.elements.length : 0,
        bodyW: bodyW,
        bodyH: bodyH,
        extractDiagnostics: extractDiagnostics
      });
      flatAreaList.push({
        safeKey: safeKey,
        sizeKey: canvasSizeOption.key,
        divs: divsHtml,
        width: elementsData.bodySize.width,
        height: elementsData.bodySize.height,
        label: canvasSizeOption.label,
        isDefault: canvasSizeOption.key === preview.getCurrentSelectedCanvasSizeKey(),
      });
    }
    return {
      flatAreaList: flatAreaList,
      hasAnyDivs: hasAnyDivs,
      totalElementsExtracted: totalElementsExtracted,
      totalAreasWithDivs: totalAreasWithDivs,
      perSize: perSize,
    };
  }

  async function _ensureComputeDocReadyOrThrow() {
    // 关键：生成扁平化应尽量只使用 compute iframe，避免切换页面时“先闪原稿再变扁平”。
    // 可视预览只在最终 renderPreview 时一次性切换到目标变体。
    var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(trimmed);
    if (!isComputeReady) {
      throw new Error("compute 预览未就绪（document 为空）：无法生成扁平化输出");
    }
    var computeDoc = preview.getComputePreviewDocument();
    if (!computeDoc || !computeDoc.body) {
      throw new Error("compute 文档为空（无 body）：无法生成扁平化输出");
    }

    // 首次渲染的排版/样式计算可能尚未完全稳定：在开始 4 个尺寸循环前先让一帧，
    // 降低“首轮提取为空”的概率（用户体感：第一次选文件总失败，切换一次又好了）。
    await waitForNextFrame();
    await waitForNextFrame();
    return computeDoc;
  }

  var computeDoc = await _ensureComputeDocReadyOrThrow();

  // 与 Workbench 保持一致：页面切换按钮 href 重写为 *_flattened.html（禁脚本预览不支持动态重写）
  var htmlTextForOutput = rewritePageSwitchLinksForFlattenedOutput(trimmed);

  var r1 = await _buildFlatAreasFromComputeDoc(computeDoc, htmlTextForOutput, uiKeyPrefix);

  // 关键修复：
  // 在部分环境下，“页面刷新后首次扁平化”可能出现 compute iframe 长期提取为 0 的卡死状态。
  // 这里做一次 hard reset（重建 compute iframe + 强制重渲染）后重试一次。
  // - 若第二次仍为 0，则按原逻辑展示失败提示页（避免静默回退让用户误判成功）。
  var result = r1;
  if (!r1.hasAnyDivs && r1.totalElementsExtracted === 0 && preview.resetComputePreviewHard) {
    setStatusText("生成扁平化…（compute 重试）");
    preview.resetComputePreviewHard();
    var computeDoc2 = await _ensureComputeDocReadyOrThrow();
    result = await _buildFlatAreasFromComputeDoc(computeDoc2, htmlTextForOutput, uiKeyPrefix);
  }

  var flattenedHtmlText = "";
  if (!result.hasAnyDivs) {
    // UX：不要静默回退为原稿（用户会误以为扁平化生效但“没变化”）。
    // 这里直接在“扁平化”变体里显示一个明确的失败提示页，让用户一眼看到失败原因。
    setStatusText("扁平化失败：结果为空（已展示失败提示）");
    window.__wb_last_flatten_empty_diagnostics = {
      totalElementsExtracted: result.totalElementsExtracted,
      totalAreasWithDivs: result.totalAreasWithDivs,
      perSize: result.perSize || []
    };
    flattenedHtmlText = preview.buildStatusPlaceholderHtml(
      "扁平化失败（结果为空）",
      _buildEmptyFlattenFailureText(result, CANVAS_SIZE_CATALOG)
    );
  } else {
    var injectedContentHtml = buildFlattenedInjectionHtml(result.flatAreaList);
    // 扁平化预览：彻底替换 body 内容，避免残留原始 DOM（例如页面自身的 preview-stage）
    flattenedHtmlText = replaceBodyInnerHtml(htmlTextForOutput, injectedContentHtml);
  }
  if (!flattenedHtmlText) {
    throw new Error("扁平化失败：找不到 <body></body>，无法替换 body 内容。请确保输入是完整 HTML 文档。");
  }
  return flattenedHtmlText;
}

function _parsePxToNumber(pxText) {
  var raw = String(pxText || "").trim().toLowerCase();
  if (!raw) return null;
  var m = raw.match(/^([0-9]+(?:\.[0-9]+)?)px$/);
  if (!m) return null;
  var n = Number(m[1]);
  if (!isFinite(n) || n <= 0) return null;
  return n;
}

export async function collectUniformTextFontSizeByElementIndexFromComputePreview(sourceHtmlText) {
  var trimmed = String(sourceHtmlText || "").trim();
  if (!trimmed) {
    return {};
  }
  var isComputeReady = await preview.ensureComputePreviewIsReadyForHtml(trimmed);
  if (!isComputeReady) {
    throw new Error("compute iframe 未就绪：无法采样字号一致性");
  }
  var computeDoc = preview.getComputePreviewDocument();
  if (!computeDoc) {
    throw new Error("compute 文档为空：无法采样字号一致性");
  }

  var fontSizeMatrix = []; // sizeIndex -> number[] (by element index)
  for (var sizeIndex = 0; sizeIndex < CANVAS_SIZE_CATALOG.length; sizeIndex++) {
    var canvasSizeOption = CANVAS_SIZE_CATALOG[sizeIndex];
    preview.setComputePreviewCanvasSize(canvasSizeOption);
    preview.applyCanvasSizeToPreviewDocument(computeDoc, canvasSizeOption);
    await waitForNextFrame();
    await waitForNextFrame();
    var elementsData = extractDisplayElementsData(computeDoc);
    var elements = (elementsData && elementsData.elements) ? elementsData.elements : [];
    var row = [];
    for (var ei = 0; ei < elements.length; ei++) {
      var elInfo = elements[ei] || {};
      var styles = elInfo.styles || {};
      row.push(_parsePxToNumber(styles.fontSize || ""));
    }
    fontSizeMatrix.push(row);
  }

  if (!fontSizeMatrix || fontSizeMatrix.length <= 0) {
    return {};
  }

  var map = {};
  var row0 = fontSizeMatrix[0] || [];
  for (var idx = 0; idx < row0.length; idx++) {
    var v0 = row0[idx];
    if (v0 === null) continue;
    var ok = true;
    for (var si = 1; si < fontSizeMatrix.length; si++) {
      var rowX = fontSizeMatrix[si] || [];
      var vx = (idx < rowX.length) ? rowX[idx] : null;
      if (vx === null) {
        ok = false;
        break;
      }
      if (Math.abs(Number(vx) - Number(v0)) > 0.1) {
        ok = false;
        break;
      }
    }
    if (ok) {
      map[String(idx)] = Math.max(1, Math.round(Number(v0)));
    }
  }
  return map;
}

