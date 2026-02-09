// compute iframe 提取策略（统一口径）：
// - 优先使用 computeDoc 提取（避免可视预览闪动）
// - 若 compute 提取结果为空：仅在“源码预览 + 当前尺寸”条件下允许回退到可视预览文档提取
//   （用于修复无头/隐藏 iframe 导致的 rect=0 → elements=[] 的极端环境问题）
//
// 说明：
// - 该策略被多个入口复用（扁平化生成 / 导出 bundle / 字号一致性采样 / 分组树刷新）。
// - 本模块只负责“何时允许 fallback + 如何重试”，不负责 applyCanvasSize / ensureComputeReady 等前置动作。
//
// 注意：不要在这里做 try/catch；失败应直接抛出，便于在控制台定位根因。
//
// 返回结构：
// - elementsData：最终提取结果（可能仍为空）
// - usedFallback：是否使用过可视预览文档

export function canFallbackToVisiblePreviewDocument(preview, targetCanvasSizeKey) {
  var p = preview || null;
  if (!p) return false;

  // 仅在源码预览时允许 fallback：避免从“扁平预览/其它变体”提取导致口径漂移。
  if (p.getCurrentPreviewVariant && p.getCurrentPreviewVariant() !== "source") {
    return false;
  }

  // 仅允许当前尺寸 fallback：避免 compute 正在轮询其它尺寸时借用可视预览造成结果错配。
  if (p.getCurrentSelectedCanvasSizeKey && String(targetCanvasSizeKey || "") !== String(p.getCurrentSelectedCanvasSizeKey() || "")) {
    return false;
  }

  return true;
}

export async function extractDisplayElementsDataPreferComputeWithOptionalVisibleFallback(opts) {
  var o = opts || {};
  var extractDisplayElementsData = o.extractDisplayElementsData;
  var computeDoc = o.computeDoc;
  var initialComputeElementsData = o.initialComputeElementsData || null;
  var previewDoc = o.previewDoc || null;
  var allowFallback = !!o.allowFallback;
  var ensurePreviewForFallback = o.ensurePreviewForFallback || null; // async () => Document|null
  var forceEnsurePreviewForFallback = !!o.forceEnsurePreviewForFallback;

  var elementsData = initialComputeElementsData ? initialComputeElementsData : extractDisplayElementsData(computeDoc);
  var usedFallback = false;

  if (!elementsData || !elementsData.elements || elementsData.elements.length > 0) {
    return { elementsData: elementsData, usedFallback: false };
  }

  if (!allowFallback) {
    return { elementsData: elementsData, usedFallback: false };
  }

  if (previewDoc) {
    var fallbackData = extractDisplayElementsData(previewDoc);
    usedFallback = true;
    if (fallbackData) {
      elementsData = fallbackData;
    }
  }

  // 若调用方要求“强制确保可视预览就绪”，则无论 previewDoc fallback 是否已有结果，都再做一次确保 + 重采样，
  // 以尽量消除“可视预览文档尚未稳定/仍是旧 srcdoc”的时序问题。
  if (ensurePreviewForFallback && typeof ensurePreviewForFallback === "function") {
    if (forceEnsurePreviewForFallback || !(elementsData && elementsData.elements && elementsData.elements.length > 0)) {
      var ensuredDoc = await ensurePreviewForFallback();
      if (ensuredDoc) {
        var ensuredData = extractDisplayElementsData(ensuredDoc);
        usedFallback = true;
        if (ensuredData) {
          elementsData = ensuredData;
        }
      }
    }
  }

  return { elementsData: elementsData, usedFallback: usedFallback };
}

