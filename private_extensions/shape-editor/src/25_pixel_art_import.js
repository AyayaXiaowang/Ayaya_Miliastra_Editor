// 像素图导入（PerfectPixel）：
// - 选图 -> 后端 PerfectPixel 标准像素矩阵 -> 规整到 RECT_COLORS -> 合并为矩形 -> 生成新实体并导出 .gia
//
// 注意：本目录使用“多脚本按顺序加载”（非 ES Module），本文件仅定义函数，不在顶层触发任何副作用。

let _pxInputFileName = '';
let _pxInputDataUrl = '';
let _pxRefinedDataUrl = '';
let _pxRefinedW = 0;
let _pxRefinedH = 0;
let _pxLastRefineSig = '';
let _pxQuantizedBgColor = '';
let _pxMatrixCacheKey = '';
let _pxMatrixCache = null;
let _pxIgnoreMaskKey = '';
let _pxIgnoreMask = null; // Uint8Array(w*h), 1=ignore
let _pxIgnoreMaskBgIdx = -1;

// preview canvas state (px-preview is a <canvas>)
let _pxPreviewCtx = null;
let _pxPreviewW = 0;
let _pxPreviewH = 0;
let _pxPreviewIgnoreMask = null; // Uint8Array(w*h) or null
let _pxKeepMask = null; // Uint8Array(w*h), 1=keep even if bg ignored (user-painted)

// preview view state (CSS zoom/pan; zoom is relative to "fit")
const _PX_PREVIEW_ZOOM_MIN = 0.5;
const _PX_PREVIEW_ZOOM_MAX = 20.0;
let _pxPreviewZoom = 1.0;
let _pxPreviewPanX = 0;
let _pxPreviewPanY = 0;
let _pxPreviewFitScale = 1.0; // last computed fit scale (for UI status)
let _pxPreviewPanning = null; // { pointerId, startX, startY, panX0, panY0 }
let _pxPreviewViewUiSetupDone = false;

// pixel edit state (operates on matrixInfo.idxArr before merging to rects)
let _pxEditEnabled = false;
let _pxEditBrushSize = 1; // square side length in pixels (1=single pixel)
let _pxEditAllowBlank = false; // allow painting on transparent / ignored bg (grow new pixels)
let _pxEditTool = 'brush'; // 'brush' | 'trash' (trash paints transparent/blank)
let _pxEditColor = '';
let _pxEditHistory = []; // stack of { kind, ... }
let _pxEditStroke = null; // { changes: Map(pos->prevIdx), targetIdx, w, h, pointerId }
let _pxOriginalMatrixKey = '';
let _pxOriginalIdxArr = null; // Uint16Array copy
let _pxOriginalCounts = null; // number[] copy
let _pxOriginalBgIdx = -1;
let _pxOriginalIgnoreMask = null; // Uint8Array(w*h), 1=bg (based on original idxArr)
let _pxPixelEditPanelSetupDone = false;
let _pxWorkbenchUiSetupDone = false;
let _pxMidViewMode = 'canvas'; // 'canvas' | 'pixel'

// ------------------------------------------------------------ multi assets (batch import)
let _pxAssets = []; // [{ id, file, fileName, inputDataUrl, refinedDataUrl, refinedW, refinedH, lastRefineSig, status, error, ...sessionState }]
let _pxSelectedAssetId = '';
let _pxAutoRefineRunning = false;
let _pxAutoRefineCancel = false;
let _pxAutoRefineProcessedCount = 0;

// ------------------------------------------------------------ project persistence (pixel workbench state)
let _pxPersistTimerId = 0;
let _pxPersistRunning = false;
let _pxPersistQueued = false;
let _pxPersistLastReason = '';

// color snapping (palette) caches
let _pxRectPaletteRgb = null; // [{r,g,b}]
let _pxRectPaletteLab = null; // [[L,a,b]]
const _pxRgbKeyToPaletteIdx = new Map(); // key(int24) -> idx
const _pxRgbKeyToLab = new Map(); // key(int24) -> [L,a,b]

function _pxResetMatrixAndPreviewCaches() {
    _pxQuantizedBgColor = '';
    _pxMatrixCacheKey = '';
    _pxMatrixCache = null;
    _pxIgnoreMaskKey = '';
    _pxIgnoreMask = null;
    _pxIgnoreMaskBgIdx = -1;

    _pxPreviewCtx = null;
    _pxPreviewW = 0;
    _pxPreviewH = 0;
    _pxPreviewIgnoreMask = null;
    _pxKeepMask = null;
    _pxPreviewZoom = 1.0;
    _pxPreviewPanX = 0;
    _pxPreviewPanY = 0;
    _pxPreviewFitScale = 1.0;
    _pxPreviewPanning = null;

    _pxEditEnabled = false;
    _pxEditHistory = [];
    _pxEditStroke = null;
    _pxOriginalMatrixKey = '';
    _pxOriginalIdxArr = null;
    _pxOriginalCounts = null;
    _pxOriginalBgIdx = -1;
    _pxOriginalIgnoreMask = null;
}

function _pxEl(id) {
    return document.getElementById(String(id || ''));
}

function _pxYieldToUi() {
    return new Promise((resolve) => {
        requestAnimationFrame(() => resolve());
    });
}

function _pxNewAssetId() {
    return `px_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function _pxReadFileAsDataUrl(file) {
    const f = file;
    return new Promise((resolve) => {
        if (!f) {
            resolve('');
            return;
        }
        const reader = new FileReader();
        reader.onload = (ev) => resolve(String(ev && ev.target ? ev.target.result : '') || '');
        reader.onerror = () => resolve('');
        reader.readAsDataURL(f);
    });
}

function _pxCreateAssetFromFile(file) {
    const f = file;
    const name = f ? String(f.name || '').trim() : '';
    const rel = (f && typeof f.webkitRelativePath === 'string') ? String(f.webkitRelativePath || '').trim() : '';
    return {
        id: _pxNewAssetId(),
        file: f || null,
        fileName: name,
        relPath: rel,
        inputDataUrl: '',
        refinedDataUrl: '',
        refinedW: 0,
        refinedH: 0,
        lastRefineSig: '',
        status: 'pending', // pending|reading|refining|ready|error
        error: '',
        // project persistence (pixel workbench)
        persistedMatrixSrc: '', // stable /assets/... path written into project
        matrixDirty: false,
        // session state (per asset)
        quantizedBgColor: '',
        matrixCacheKey: '',
        matrixCache: null,
        ignoreMaskKey: '',
        ignoreMask: null,
        ignoreMaskBgIdx: -1,
        keepMask: null, // Uint8Array(w*h), 1=keep (user-painted)
        originalMatrixKey: '',
        originalIdxArr: null,
        originalCounts: null,
        originalBgIdx: -1,
        originalIgnoreMask: null,
        editHistory: [],
        generatedRelPath: '',
    };
}

function _pxGetSelectedAsset() {
    if (!_pxSelectedAssetId) return null;
    const list = Array.isArray(_pxAssets) ? _pxAssets : [];
    return list.find(it => it && it.id === _pxSelectedAssetId) || null;
}

function _pxCaptureCurrentSessionIntoAsset(asset) {
    if (!asset) return;
    asset.fileName = String(_pxInputFileName || asset.fileName || '').trim();
    asset.inputDataUrl = String(_pxInputDataUrl || asset.inputDataUrl || '').trim();
    asset.refinedDataUrl = String(_pxRefinedDataUrl || asset.refinedDataUrl || '').trim();
    asset.refinedW = Math.max(0, Math.round(Number(_pxRefinedW || asset.refinedW || 0)));
    asset.refinedH = Math.max(0, Math.round(Number(_pxRefinedH || asset.refinedH || 0)));
    asset.lastRefineSig = String(_pxLastRefineSig || asset.lastRefineSig || '').trim();

    asset.quantizedBgColor = String(_pxQuantizedBgColor || '').trim();
    asset.matrixCacheKey = String(_pxMatrixCacheKey || '').trim();
    asset.matrixCache = _pxMatrixCache || null;
    asset.ignoreMaskKey = String(_pxIgnoreMaskKey || '').trim();
    asset.ignoreMask = _pxIgnoreMask || null;
    asset.ignoreMaskBgIdx = Number.isFinite(Number(_pxIgnoreMaskBgIdx)) ? Number(_pxIgnoreMaskBgIdx) : -1;
    asset.keepMask = _pxKeepMask || null;

    asset.originalMatrixKey = String(_pxOriginalMatrixKey || '').trim();
    asset.originalIdxArr = _pxOriginalIdxArr || null;
    asset.originalCounts = _pxOriginalCounts || null;
    asset.originalBgIdx = Number.isFinite(Number(_pxOriginalBgIdx)) ? Number(_pxOriginalBgIdx) : -1;
    asset.originalIgnoreMask = _pxOriginalIgnoreMask || null;
    asset.editHistory = Array.isArray(_pxEditHistory) ? _pxEditHistory : [];
}

function _pxApplyAssetToCurrentSession(asset) {
    const a = asset;
    _pxInputFileName = String(a && a.fileName ? a.fileName : '').trim();
    _pxInputDataUrl = String(a && a.inputDataUrl ? a.inputDataUrl : '').trim();
    _pxRefinedDataUrl = String(a && a.refinedDataUrl ? a.refinedDataUrl : '').trim();
    _pxRefinedW = Math.max(0, Math.round(Number(a && a.refinedW ? a.refinedW : 0)));
    _pxRefinedH = Math.max(0, Math.round(Number(a && a.refinedH ? a.refinedH : 0)));
    _pxLastRefineSig = String(a && a.lastRefineSig ? a.lastRefineSig : '').trim();

    _pxQuantizedBgColor = String(a && a.quantizedBgColor ? a.quantizedBgColor : '').trim();
    _pxMatrixCacheKey = String(a && a.matrixCacheKey ? a.matrixCacheKey : '').trim();
    _pxMatrixCache = a ? (a.matrixCache || null) : null;
    _pxIgnoreMaskKey = String(a && a.ignoreMaskKey ? a.ignoreMaskKey : '').trim();
    _pxIgnoreMask = a ? (a.ignoreMask || null) : null;
    _pxIgnoreMaskBgIdx = Number.isFinite(Number(a && a.ignoreMaskBgIdx)) ? Number(a.ignoreMaskBgIdx) : -1;
    _pxKeepMask = a ? (a.keepMask || null) : null;

    _pxOriginalMatrixKey = String(a && a.originalMatrixKey ? a.originalMatrixKey : '').trim();
    _pxOriginalIdxArr = a ? (a.originalIdxArr || null) : null;
    _pxOriginalCounts = a ? (a.originalCounts || null) : null;
    _pxOriginalBgIdx = Number.isFinite(Number(a && a.originalBgIdx)) ? Number(a.originalBgIdx) : -1;
    _pxOriginalIgnoreMask = a ? (a.originalIgnoreMask || null) : null;
    _pxEditHistory = a && Array.isArray(a.editHistory) ? a.editHistory : [];
    _pxEditStroke = null;
}

function _pxSetAssetStatus(asset, status, errorText) {
    const a = asset;
    if (!a) return;
    a.status = String(status || '').trim() || 'pending';
    a.error = String(errorText || '').trim();
}

function _pxRenderAssetList() {
    const container = _pxEl('px-asset-list');
    const statusEl = _pxEl('px-asset-status');
    if (!container) return;

    const items = Array.isArray(_pxAssets) ? _pxAssets : [];
    const total = items.length;
    const readyCount = items.filter(it => it && it.status === 'ready').length;
    const workCount = items.filter(it => it && (it.status === 'reading' || it.status === 'refining')).length;
    const errCount = items.filter(it => it && it.status === 'error').length;
    const text = total <= 0 ? '0' : `${readyCount}/${total}` + (workCount ? ` · 处理中${workCount}` : '') + (errCount ? ` · 失败${errCount}` : '');
    if (statusEl) statusEl.textContent = text;

    container.innerHTML = '';
    if (total <= 0) {
        const empty = document.createElement('div');
        empty.style.color = 'var(--muted)';
        empty.style.fontSize = '12px';
        empty.textContent = '（未导入图片）';
        container.appendChild(empty);
        return;
    }

    items.forEach((it) => {
        if (!it) return;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'px-asset-item' + (it.id === _pxSelectedAssetId ? ' selected' : '');
        btn.onclick = () => Promise.resolve().then(() => _pxSelectAssetById(it.id));

        const thumb = document.createElement('div');
        thumb.className = 'px-asset-thumb';
        if (it.refinedDataUrl) {
            const img = document.createElement('img');
            img.src = String(it.refinedDataUrl);
            img.alt = 'thumb';
            thumb.appendChild(img);
        } else {
            thumb.textContent = it.status === 'error' ? '×' : '…';
            thumb.style.color = it.status === 'error' ? 'rgba(255,99,99,0.95)' : 'var(--muted)';
            thumb.style.fontWeight = '800';
        }
        btn.appendChild(thumb);

        const info = document.createElement('div');
        info.className = 'px-asset-info';
        const title = document.createElement('div');
        title.className = 'px-asset-title';
        title.textContent = String(it.fileName || '(unnamed)').trim() || '(unnamed)';
        info.appendChild(title);
        const sub = document.createElement('div');
        sub.className = 'px-asset-sub';
        if (it.status === 'ready') {
            sub.textContent = it.refinedW > 0 && it.refinedH > 0 ? `已标准像素化：${it.refinedW}×${it.refinedH}` : '已标准像素化';
        } else if (it.status === 'refining') {
            sub.textContent = '标准像素化中…';
        } else if (it.status === 'reading') {
            sub.textContent = '读取中…';
        } else if (it.status === 'error') {
            sub.textContent = it.error ? `失败：${it.error}` : '失败';
        } else {
            const rel = String(it.relPath || '').trim();
            sub.textContent = rel ? `等待处理… (${rel})` : '等待处理…';
        }
        info.appendChild(sub);
        btn.appendChild(info);

        const badge = document.createElement('div');
        badge.className = 'px-asset-badge';
        if (it.status === 'ready') {
            badge.classList.add('ready');
            badge.textContent = '可改色';
        } else if (it.status === 'error') {
            badge.classList.add('error');
            badge.textContent = '失败';
        } else if (it.status === 'reading' || it.status === 'refining') {
            badge.classList.add('work');
            badge.textContent = '处理中';
        } else {
            badge.textContent = '待处理';
        }
        btn.appendChild(badge);

        container.appendChild(btn);
    });
}

function _pxMarkSelectedAssetMatrixDirty(reason) {
    const cur = _pxGetSelectedAsset();
    if (!cur) return;
    cur.matrixDirty = true;
}

function _pxBuildMatrixPngDataUrlFromMatrixInfo(matrixInfo) {
    const info = matrixInfo;
    if (!info) return '';
    const w = Math.max(0, Math.round(Number(info.w || 0)));
    const h = Math.max(0, Math.round(Number(info.h || 0)));
    const idxArr = info.idxArr;
    const palette = Array.isArray(info.palette) ? info.palette : [];
    const transparentIdx = Number(info.transparentIdx);
    if (w <= 0 || h <= 0 || !(idxArr instanceof Uint16Array)) return '';

    const off = document.createElement('canvas');
    off.width = w;
    off.height = h;
    const ctx = off.getContext('2d', { willReadFrequently: true });
    if (!ctx) return '';
    ctx.imageSmoothingEnabled = false;
    const imgData = ctx.createImageData(w, h);
    const data = imgData.data;

    for (let i = 0; i < w * h; i++) {
        const idx = Number(idxArr[i]);
        const o = i * 4;
        if (idx === transparentIdx) {
            data[o + 3] = 0;
            continue;
        }
        const color = String(palette[idx] || '').trim();
        if (!color) {
            data[o + 3] = 0;
            continue;
        }
        const rgb = hexToRgb(color);
        data[o] = Number(rgb.r) & 255;
        data[o + 1] = Number(rgb.g) & 255;
        data[o + 2] = Number(rgb.b) & 255;
        data[o + 3] = 255;
    }

    ctx.putImageData(imgData, 0, 0);
    return String(off.toDataURL('image/png') || '');
}

function _pxMaskHasAny(mask) {
    const m = (mask instanceof Uint8Array) ? mask : null;
    if (!m || m.length === 0) return false;
    for (let i = 0; i < m.length; i++) {
        if (m[i]) return true;
    }
    return false;
}

function _pxIsProbablyBase64Text(text) {
    const s = String(text || '').trim();
    if (!s) return false;
    if (s.length % 4 !== 0) return false;
    // Strict-ish: only base64 chars + optional "=" padding.
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(s)) return false;
    const pad = s.endsWith('==') ? 2 : (s.endsWith('=') ? 1 : 0);
    // "=" must only appear at the end
    if (pad > 0 && s.slice(0, -pad).includes('=')) return false;
    return true;
}

function _pxBytesToBase64(bytes) {
    const b = (bytes instanceof Uint8Array) ? bytes : null;
    if (!b || b.length === 0) return '';
    // Chunk to avoid "Maximum call stack size exceeded"
    const CHUNK = 8192;
    let bin = '';
    for (let i = 0; i < b.length; i += CHUNK) {
        const sub = b.subarray(i, i + CHUNK);
        bin += String.fromCharCode.apply(null, sub);
    }
    return btoa(bin);
}

function _pxBase64ToBytes(b64) {
    const s = String(b64 || '').trim();
    if (!s) return new Uint8Array(0);
    const bin = atob(s);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
        out[i] = bin.charCodeAt(i) & 255;
    }
    return out;
}

function _pxPackKeepMaskToBitsetB64(mask) {
    const m = (mask instanceof Uint8Array) ? mask : null;
    if (!m || m.length === 0) return '';
    const n = m.length;
    const bytes = new Uint8Array((n + 7) >> 3);
    for (let i = 0; i < n; i++) {
        if (m[i]) {
            bytes[i >> 3] |= (1 << (i & 7));
        }
    }
    return _pxBytesToBase64(bytes);
}

function _pxUnpackKeepMaskFromBitsetB64(b64, expectedLen) {
    const n = Math.max(0, Math.round(Number(expectedLen || 0)));
    if (n <= 0) return null;
    const s = String(b64 || '').trim();
    if (!_pxIsProbablyBase64Text(s)) return null;
    const bytes = _pxBase64ToBytes(s);
    const need = (n + 7) >> 3;
    if (bytes.length < need) return null;
    const out = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
        out[i] = (bytes[i >> 3] >> (i & 7)) & 1;
    }
    return out;
}

function _pxBuildPixelWorkbenchStatePayloadForProject() {
    const opts = _pxGetOptionsFromUi();
    const items = Array.isArray(_pxAssets) ? _pxAssets : [];
    const assets = [];

    for (let i = 0; i < items.length; i++) {
        const a = items[i];
        if (!a) continue;
        if (String(a.status || '') !== 'ready') continue;
        const id = String(a.id || '').trim();
        if (!id) continue;

        // Prefer stable path if not dirty; otherwise persist current matrix (edited) as PNG.
        let matrixSrc = '';
        const stable = String(a.persistedMatrixSrc || '').trim();
        const dirty = a.matrixDirty === true || !stable;
        if (!dirty && stable) {
            matrixSrc = stable;
        } else {
            const info = a.matrixCache;
            if (info && info.idxArr instanceof Uint16Array) {
                matrixSrc = _pxBuildMatrixPngDataUrlFromMatrixInfo(info);
            } else {
                matrixSrc = String(a.refinedDataUrl || '').trim();
            }
        }
        if (!matrixSrc) continue;

        const refinedW = Math.max(0, Math.round(Number(a.refinedW || 0)));
        const refinedH = Math.max(0, Math.round(Number(a.refinedH || 0)));
        const out = {
            id: id,
            file_name: String(a.fileName || '').trim(),
            refined_w: refinedW,
            refined_h: refinedH,
            matrix_src: String(matrixSrc),
            generated_rel_path: String(a.generatedRelPath || '').trim(),
        };

        const keepMask = a.keepMask;
        const n = refinedW > 0 && refinedH > 0 ? refinedW * refinedH : 0;
        if (keepMask instanceof Uint8Array && n > 0 && keepMask.length === n && _pxMaskHasAny(keepMask)) {
            out.keep_mask_kind = 'bitset_b64_v1';
            out.keep_mask_w = refinedW;
            out.keep_mask_h = refinedH;
            out.keep_mask_b64 = _pxPackKeepMaskToBitsetB64(keepMask);
        }

        assets.push(out);
    }

    return {
        schema: 'shape_editor_pixel_workbench_v1',
        selected_asset_id: String(_pxSelectedAssetId || '').trim(),
        options: {
            cell_size_px: Number(opts.cellSizePx || 12),
            refine_intensity: Number(opts.refineIntensity || 0),
            sample_method: String(opts.sampleMethod || 'center'),
            fix_square: !!opts.fixSquare,
            ignore_bg: !!opts.ignoreBg,
            generate_mode: String(opts.generateMode || 'merge_rects'),
        },
        assets: assets,
    };
}

function _pxApplyPixelWorkbenchOptionsFromProject(options) {
    const o = options && typeof options === 'object' ? options : {};
    const cellEl = _pxEl('px-cell-size');
    const refineEl = _pxEl('px-refine-intensity');
    const sampleEl = _pxEl('px-sample-method');
    const fixEl = _pxEl('px-fix-square');
    const ignoreEl = _pxEl('px-ignore-bg');
    const genModeEl = _pxEl('px-generate-mode');

    const cell = Math.max(1, Math.min(400, Math.round(Number(o.cell_size_px || 12))));
    const refine = Math.max(0, Math.min(0.5, Number(o.refine_intensity || 0.30)));
    const sample = String(o.sample_method || 'center').trim() || 'center';
    const fixSquare = !!o.fix_square;
    const ignoreBg = !!o.ignore_bg;
    const genMode0 = String(o.generate_mode || 'merge_rects').trim() || 'merge_rects';
    const genMode = (genMode0 === 'pixel_points') ? 'pixel_points' : 'merge_rects';

    if (cellEl) cellEl.value = String(cell);
    if (refineEl) refineEl.value = String(refine);
    if (sampleEl) sampleEl.value = String(sample);
    if (fixEl) fixEl.checked = fixSquare;
    if (ignoreEl) ignoreEl.checked = ignoreBg;
    if (genModeEl) genModeEl.value = genMode;
}

function _pxSchedulePersistPixelWorkbenchState(reason) {
    const r = String(reason || '').trim();
    _pxPersistLastReason = r;
    if (_pxPersistTimerId) {
        clearTimeout(_pxPersistTimerId);
        _pxPersistTimerId = 0;
    }
    _pxPersistTimerId = window.setTimeout(() => {
        _pxPersistTimerId = 0;
        if (_pxPersistRunning) {
            _pxPersistQueued = true;
            return;
        }
        _pxPersistRunning = true;
        Promise.resolve()
            .then(() => _pxPersistPixelWorkbenchStateNow(_pxPersistLastReason))
            .finally(() => {
                _pxPersistRunning = false;
                if (_pxPersistQueued) {
                    _pxPersistQueued = false;
                    _pxSchedulePersistPixelWorkbenchState('queued');
                }
            });
    }, 900);
}

async function _pxPersistPixelWorkbenchStateNow(reason) {
    const r = String(reason || '').trim() || '-';

    if (_pxEditStroke) {
        await _pxCommitPaintStroke();
    }
    const cur = _pxGetSelectedAsset();
    if (cur) {
        _pxCaptureCurrentSessionIntoAsset(cur);
    }

    const payload = _pxBuildPixelWorkbenchStatePayloadForProject();
    const body = JSON.stringify(payload);
    const resp = await fetch('/api/shape_editor/pixel_workbench_state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body
    });
    const text = await resp.text();
    if (!resp.ok) {
        toastToUi('error', `像素工作台保存失败（HTTP ${resp.status}）`, 2600);
        logToUi('ERROR', `像素工作台保存失败（HTTP ${resp.status}） reason=${r}`);
        logToUi('ERROR', text);
        return;
    }
    const obj = JSON.parse(text);
    if (!obj || !obj.ok) {
        toastToUi('error', '像素工作台保存失败（bad payload）', 2600);
        logToUi('ERROR', `像素工作台保存失败（bad payload） reason=${r}`);
        logToUi('ERROR', text);
        return;
    }

    const st = obj.state;
    const savedAssets = st && Array.isArray(st.assets) ? st.assets : [];
    if (savedAssets.length > 0) {
        const byId = new Map();
        savedAssets.forEach((a) => {
            if (!a) return;
            const id = String(a.id || '').trim();
            const src = String(a.matrix_src || '').trim();
            if (!id || !src) return;
            byId.set(id, src);
        });
        const items = Array.isArray(_pxAssets) ? _pxAssets : [];
        items.forEach((a) => {
            if (!a) return;
            const id = String(a.id || '').trim();
            if (!id) return;
            const src = byId.get(id);
            if (!src) return;
            a.persistedMatrixSrc = String(src);
            a.matrixDirty = false;
        });
    }

    logToUi('INFO', `像素工作台：已保存到项目 reason=${r} assets=${savedAssets.length}`);
}

async function _pxBootRestorePixelWorkbenchStateFromProject() {
    const resp = await fetch('/api/shape_editor/pixel_workbench_state', { method: 'GET' });
    const text = await resp.text();
    if (!resp.ok) {
        logToUi('WARN', `像素工作台恢复失败（HTTP ${resp.status}）`);
        return;
    }
    const obj = JSON.parse(text);
    if (!obj || !obj.ok || !obj.has_data) {
        return;
    }
    const st = obj.state;
    const assets = st && Array.isArray(st.assets) ? st.assets : [];
    if (assets.length <= 0) return;

    if (st && st.options) {
        _pxApplyPixelWorkbenchOptionsFromProject(st.options);
    }

    const restored = [];
    for (let i = 0; i < assets.length; i++) {
        const a0 = assets[i];
        if (!a0) continue;
        const id = String(a0.id || '').trim();
        const src = String(a0.matrix_src || '').trim();
        if (!id || !src) continue;
        const rw = Math.max(0, Math.round(Number(a0.refined_w || 0)));
        const rh = Math.max(0, Math.round(Number(a0.refined_h || 0)));
        let keepMask = null;
        const keepKind = String(a0.keep_mask_kind || '').trim();
        const keepB64 = String(a0.keep_mask_b64 || '').trim();
        if (keepKind === 'bitset_b64_v1' && keepB64 && rw > 0 && rh > 0) {
            keepMask = _pxUnpackKeepMaskFromBitsetB64(keepB64, rw * rh);
        }
        const a = _pxCreateAssetFromFile(null);
        a.id = id;
        a.file = null;
        a.inputDataUrl = '';
        a.fileName = String(a0.file_name || '').trim();
        a.refinedDataUrl = src;
        a.refinedW = rw;
        a.refinedH = rh;
        a.lastRefineSig = '';
        a.persistedMatrixSrc = src;
        a.matrixDirty = false;
        a.generatedRelPath = String(a0.generated_rel_path || '').trim();
        a.matrixCacheKey = '';
        a.matrixCache = null;
        a.ignoreMaskKey = '';
        a.ignoreMask = null;
        a.ignoreMaskBgIdx = -1;
        a.originalMatrixKey = '';
        a.originalIdxArr = null;
        a.originalCounts = null;
        a.originalBgIdx = -1;
        a.originalIgnoreMask = null;
        a.keepMask = keepMask;
        a.editHistory = [];
        a.status = 'ready';
        a.error = '';
        restored.push(a);
    }

    if (restored.length <= 0) return;

    // reset current session before selecting (avoid capturing stale globals into assets)
    _pxAutoRefineCancel = true;
    _pxAutoRefineRunning = false;
    _pxAutoRefineProcessedCount = 0;
    _pxInputFileName = '';
    _pxInputDataUrl = '';
    _pxRefinedDataUrl = '';
    _pxRefinedW = 0;
    _pxRefinedH = 0;
    _pxLastRefineSig = '';
    _pxResetMatrixAndPreviewCaches();
    _pxHidePreviewCanvas();

    _pxAssets = restored;
    const want = String(st && st.selected_asset_id ? st.selected_asset_id : '').trim();
    const pickId = want && restored.some(it => it && it.id === want) ? want : String(restored[0].id || '');
    _pxSelectedAssetId = '';
    _pxRenderAssetList();
    logToUi('INFO', `像素工作台：已从项目恢复 assets=${restored.length}`);
    if (pickId) {
        await _pxSelectAssetById(pickId);
    }
}

async function _pxSelectAssetById(id) {
    const nextId = String(id || '').trim();
    if (!nextId) return;

    const items = Array.isArray(_pxAssets) ? _pxAssets : [];
    const next = items.find(it => it && it.id === nextId) || null;
    if (!next) return;

    const cur = _pxGetSelectedAsset();
    if (_pxEditStroke) {
        await _pxCommitPaintStroke();
    }
    if (cur) {
        _pxCaptureCurrentSessionIntoAsset(cur);
    }

    _pxSelectedAssetId = nextId;
    _pxApplyAssetToCurrentSession(next);

    // Update UI: if ready, jump to edit and enable edit by default.
    if (_pxRefinedDataUrl && _pxRefinedW > 0 && _pxRefinedH > 0) {
        _pxSetPixelWorkbenchTab('edit');
        _pxSetPixelEditEnabled(true);
        await _pxRebuildQuantizedPreviewForCurrentOptions();
    } else {
        _pxSetPixelWorkbenchTab('import');
        _pxSetPixelEditEnabled(false);
        _pxHidePreviewCanvas();
    }

    _pxUpdateMeta();
    _pxRenderAssetList();
}

function _pxClearAllAssets() {
    _pxAssets = [];
    _pxSelectedAssetId = '';
    _pxAutoRefineCancel = true;
    _pxAutoRefineRunning = false;
    _pxAutoRefineProcessedCount = 0;

    _pxInputFileName = '';
    _pxInputDataUrl = '';
    _pxRefinedDataUrl = '';
    _pxRefinedW = 0;
    _pxRefinedH = 0;
    _pxLastRefineSig = '';
    _pxResetMatrixAndPreviewCaches();
    _pxHidePreviewCanvas();
    _pxUpdateMeta();
    _pxRenderAssetList();
    _pxSchedulePersistPixelWorkbenchState('clear_assets');
}

function _pxIsImageFile(file) {
    const f = file;
    if (!f) return false;
    const t = String(f.type || '').toLowerCase();
    if (t.startsWith('image/')) return true;
    const name = String(f.name || '').toLowerCase();
    return name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.webp') || name.endsWith('.bmp') || name.endsWith('.gif');
}

function _pxAddFilesAsAssets(filesLike) {
    const arr0 = Array.from(filesLike || []).filter(_pxIsImageFile);
    if (arr0.length === 0) {
        toastToUi('warn', '未选择图片文件');
        return;
    }

    const items = Array.isArray(_pxAssets) ? _pxAssets : [];
    arr0.forEach((f) => {
        const a = _pxCreateAssetFromFile(f);
        items.push(a);
    });
    _pxAssets = items;

    if (!_pxSelectedAssetId && items.length > 0) {
        _pxSelectedAssetId = String(items[0].id || '');
        _pxApplyAssetToCurrentSession(items[0]);
        _pxUpdateMeta();
    }

    _pxRenderAssetList();
    _pxStartAutoRefineQueue();
}

async function _pxRequestPerfectPixelRefine(opts) {
    const o = opts || {};
    const imageDataUrl = String(o.imageDataUrl || '').trim();
    if (!imageDataUrl) {
        return { ok: false, error: 'image_data_url is empty' };
    }
    const body = JSON.stringify({
        image_data_url: imageDataUrl,
        sample_method: String(o.sampleMethod || 'center'),
        refine_intensity: Number(o.refineIntensity || 0.30),
        fix_square: !!o.fixSquare,
        palette_hex: Array.isArray(RECT_COLORS) ? RECT_COLORS.slice() : []
    });
    const resp = await fetch('/api/shape_editor/perfect_pixel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body
    });
    const text = await resp.text();
    if (!resp.ok) {
        return { ok: false, error: `HTTP ${resp.status}`, detail: text };
    }
    const obj = JSON.parse(text);
    if (!obj || !obj.ok) {
        return { ok: false, error: 'bad payload', detail: text };
    }
    return obj;
}

function _pxStartAutoRefineQueue() {
    if (_pxAutoRefineRunning) return;
    const items = Array.isArray(_pxAssets) ? _pxAssets : [];
    const hasPending = items.some(it => it && it.status === 'pending');
    if (!hasPending) return;
    _pxAutoRefineRunning = true;
    _pxAutoRefineCancel = false;
    _pxAutoRefineProcessedCount = 0;
    Promise.resolve().then(_pxRunAutoRefineQueue);
}

async function _pxRunAutoRefineQueue() {
    const items = Array.isArray(_pxAssets) ? _pxAssets : [];
    for (let i = 0; i < items.length; i++) {
        if (_pxAutoRefineCancel) break;
        const a = items[i];
        if (!a || a.status !== 'pending') continue;

        _pxSetAssetStatus(a, 'reading', '');
        _pxRenderAssetList();
        await _pxYieldToUi();

        if (!a.inputDataUrl) {
            const dataUrl = await _pxReadFileAsDataUrl(a.file);
            a.inputDataUrl = String(dataUrl || '').trim();
        }
        if (!a.inputDataUrl) {
            _pxSetAssetStatus(a, 'error', '读取失败');
            _pxRenderAssetList();
            continue;
        }

        const uiOpts = _pxGetOptionsFromUi();
        const sig = _pxComputeRefineSig(uiOpts);

        _pxSetAssetStatus(a, 'refining', '');
        a.lastRefineSig = sig;
        _pxRenderAssetList();
        logToUi('INFO', `批量标准像素化：${a.fileName || '(unnamed)'} (${i + 1}/${items.length})`);
        await _pxYieldToUi();

        const refined = await _pxRequestPerfectPixelRefine({
            imageDataUrl: a.inputDataUrl,
            sampleMethod: uiOpts.sampleMethod,
            refineIntensity: uiOpts.refineIntensity,
            fixSquare: uiOpts.fixSquare
        });

        if (!refined || !refined.ok) {
            const err = refined && refined.error ? String(refined.error) : '标准像素化失败';
            _pxSetAssetStatus(a, 'error', err);
            _pxRenderAssetList();
            continue;
        }

        a.refinedDataUrl = String(refined.image_data_url || '').trim();
        a.refinedW = Math.max(0, Math.round(Number(refined.refined_w || 0)));
        a.refinedH = Math.max(0, Math.round(Number(refined.refined_h || 0)));
        a.persistedMatrixSrc = '';
        a.matrixDirty = true;
        _pxSetAssetStatus(a, 'ready', '');
        _pxAutoRefineProcessedCount += 1;

        // If this asset is selected, update current session + preview immediately.
        if (a.id === _pxSelectedAssetId) {
            _pxApplyAssetToCurrentSession(a);
            _pxResetMatrixAndPreviewCaches();
            _pxUpdateMeta();
            await _pxRebuildQuantizedPreviewForCurrentOptions();
            _pxSetPixelWorkbenchTab('edit');
            _pxSetPixelEditEnabled(true);
            _pxUpdateMeta();
        }

        _pxRenderAssetList();
        await _pxYieldToUi();
    }

    _pxAutoRefineRunning = false;
    _pxAutoRefineCancel = false;
    _pxRenderAssetList();
    if (_pxAutoRefineProcessedCount > 0) {
        toastToUi('info', `批量标准像素化完成：${_pxAutoRefineProcessedCount} 个`, 2000);
        _pxSchedulePersistPixelWorkbenchState('auto_refine_done');
    }
}

function _pxSetMeta(text) {
    const el = _pxEl('px-meta');
    if (!el) return;
    el.textContent = String(text || '');
}

function _pxGetPreviewCanvas() {
    return _pxEl('px-preview');
}

function _pxHidePreviewCanvas() {
    const el = _pxGetPreviewCanvas();
    if (!el) return;
    el.classList.add('hidden');
    el.classList.remove('editing');
    el.style.width = '';
    el.style.height = '';
    el.style.transform = '';
    _pxPreviewCtx = null;
    _pxPreviewW = 0;
    _pxPreviewH = 0;
    _pxPreviewIgnoreMask = null;
    _pxSyncPreviewViewUi();
}

function _pxFitPreviewCanvasCssSize(anchor) {
    const el = _pxGetPreviewCanvas();
    const wrap = _pxEl('px-preview-wrap');
    if (!el || !wrap) {
        _pxSyncPreviewViewUi();
        return;
    }
    const w = Math.max(0, Math.round(Number(el.width || _pxPreviewW || 0)));
    const h = Math.max(0, Math.round(Number(el.height || _pxPreviewH || 0)));
    if (w <= 0 || h <= 0) {
        _pxSyncPreviewViewUi();
        return;
    }

    const cs = window.getComputedStyle ? window.getComputedStyle(wrap) : null;
    const pl = cs ? Number.parseFloat(cs.paddingLeft || '0') : 0;
    const pr = cs ? Number.parseFloat(cs.paddingRight || '0') : 0;
    const pt = cs ? Number.parseFloat(cs.paddingTop || '0') : 0;
    const pb = cs ? Number.parseFloat(cs.paddingBottom || '0') : 0;
    const blw = cs ? Number.parseFloat(cs.borderLeftWidth || '0') : 0;
    const btw = cs ? Number.parseFloat(cs.borderTopWidth || '0') : 0;
    const ww = Math.max(0, Number(wrap.clientWidth || 0) - (Number.isFinite(pl) ? pl : 0) - (Number.isFinite(pr) ? pr : 0));
    const hh = Math.max(0, Number(wrap.clientHeight || 0) - (Number.isFinite(pt) ? pt : 0) - (Number.isFinite(pb) ? pb : 0));
    if (ww <= 0 || hh <= 0) {
        _pxSyncPreviewViewUi();
        return;
    }

    const fitScale = Math.max(0.01, Math.min(ww / w, hh / h));
    _pxPreviewFitScale = fitScale;

    const zoom = _pxClampPreviewZoom(_pxPreviewZoom);
    if (_pxPreviewZoom !== zoom) _pxPreviewZoom = zoom;
    const scale = fitScale * zoom;

    const cssW = Math.max(1, Math.floor(w * scale));
    const cssH = Math.max(1, Math.floor(h * scale));
    const cssWStr = `${cssW}px`;
    const cssHStr = `${cssH}px`;
    if (el.style.width !== cssWStr) el.style.width = cssWStr;
    if (el.style.height !== cssHStr) el.style.height = cssHStr;

    const maxPanX = Math.max(0, (cssW - ww) / 2);
    const maxPanY = Math.max(0, (cssH - hh) / 2);

    let panX = _coerceFiniteNumber(_pxPreviewPanX, 0);
    let panY = _coerceFiniteNumber(_pxPreviewPanY, 0);

    // Zoom anchor: keep the same relative point under cursor (wheel zoom).
    const ax = anchor && Number.isFinite(Number(anchor.clientX)) ? Number(anchor.clientX) : null;
    const ay = anchor && Number.isFinite(Number(anchor.clientY)) ? Number(anchor.clientY) : null;
    if (ax !== null && ay !== null) {
        const wrapRect = wrap.getBoundingClientRect();
        const contentLeft = Number(wrapRect.left || 0) + (Number.isFinite(blw) ? blw : 0) + (Number.isFinite(pl) ? pl : 0);
        const contentTop = Number(wrapRect.top || 0) + (Number.isFinite(btw) ? btw : 0) + (Number.isFinite(pt) ? pt : 0);
        const baseLeft = contentLeft + (ww - cssW) / 2;
        const baseTop = contentTop + (hh - cssH) / 2;

        const nx0 = anchor && Number.isFinite(Number(anchor.nx)) ? Number(anchor.nx) : 0.5;
        const ny0 = anchor && Number.isFinite(Number(anchor.ny)) ? Number(anchor.ny) : 0.5;
        const nx = Math.max(0, Math.min(1, nx0));
        const ny = Math.max(0, Math.min(1, ny0));

        const desiredLeft = ax - nx * cssW;
        const desiredTop = ay - ny * cssH;
        panX = desiredLeft - baseLeft;
        panY = desiredTop - baseTop;
    }

    if (maxPanX <= 0.5) panX = 0;
    if (maxPanY <= 0.5) panY = 0;
    if (panX > maxPanX) panX = maxPanX;
    if (panX < -maxPanX) panX = -maxPanX;
    if (panY > maxPanY) panY = maxPanY;
    if (panY < -maxPanY) panY = -maxPanY;

    _pxPreviewPanX = panX;
    _pxPreviewPanY = panY;
    const t = `translate3d(${Math.round(panX)}px, ${Math.round(panY)}px, 0)`;
    if (el.style.transform !== t) el.style.transform = t;
    _pxSyncPreviewViewUi();
}

function _pxClampPreviewZoom(z) {
    const n0 = _coerceFiniteNumber(z, 1.0);
    const n = Number(n0);
    return Math.max(_PX_PREVIEW_ZOOM_MIN, Math.min(_PX_PREVIEW_ZOOM_MAX, n));
}

function _pxSetPreviewZoom(z, anchor) {
    const next = _pxClampPreviewZoom(z);
    _pxPreviewZoom = next;
    _pxFitPreviewCanvasCssSize(anchor);
}

function _pxZoomPreviewByFactor(factor, anchor) {
    const f0 = _coerceFiniteNumber(factor, 1.0);
    const f = Number(f0);
    if (!(f > 0)) return;
    _pxSetPreviewZoom(Number(_pxPreviewZoom || 1.0) * f, anchor);
}

function _pxResetPreviewViewToFit() {
    _pxPreviewZoom = 1.0;
    _pxPreviewPanX = 0;
    _pxPreviewPanY = 0;
    _pxPreviewPanning = null;
    _pxFitPreviewCanvasCssSize();
}

function _pxCenterPreviewView() {
    _pxPreviewPanX = 0;
    _pxPreviewPanY = 0;
    _pxFitPreviewCanvasCssSize();
}

function _pxSyncPreviewViewUi() {
    const zoomEl = _pxEl('px-view-zoom');
    const statusEl = _pxEl('px-view-status');
    const zoomOutBtn = _pxEl('btn-px-zoom-out');
    const zoomInBtn = _pxEl('btn-px-zoom-in');
    const fitBtn = _pxEl('btn-px-view-fit');
    const centerBtn = _pxEl('btn-px-view-center');

    const preview = _pxGetPreviewCanvas();
    const visible = !!(preview && !preview.classList.contains('hidden') && Number(preview.width || 0) > 0 && Number(preview.height || 0) > 0);

    const zoom = _pxClampPreviewZoom(_pxPreviewZoom);
    if (_pxPreviewZoom !== zoom) _pxPreviewZoom = zoom;
    const z1 = Math.round(zoom * 10) / 10;

    if (zoomEl) {
        if (zoomEl.disabled !== !visible) zoomEl.disabled = !visible;
        const cur = _coerceFiniteNumber(zoomEl.value, z1);
        if (Math.abs(Number(cur) - z1) > 0.05) {
            zoomEl.value = String(z1);
        }
    }
    [zoomOutBtn, zoomInBtn, fitBtn, centerBtn].forEach((btn) => {
        if (!btn) return;
        if (btn.disabled !== !visible) btn.disabled = !visible;
    });

    if (statusEl) {
        let nextText = '（无预览）';
        if (visible) {
            const isFit = Math.abs(z1 - 1.0) < 0.05;
            const isCentered = Math.abs(Number(_pxPreviewPanX || 0)) < 1 && Math.abs(Number(_pxPreviewPanY || 0)) < 1;
            nextText = (isFit && isCentered) ? '适配' : `×${z1.toFixed(1)}`;
        }
        if (statusEl.textContent !== nextText) statusEl.textContent = nextText;
    }
}

function _pxSetupPreviewViewUi() {
    if (_pxPreviewViewUiSetupDone) return;
    _pxPreviewViewUiSetupDone = true;

    const zoomEl = _pxEl('px-view-zoom');
    const zoomOutBtn = _pxEl('btn-px-zoom-out');
    const zoomInBtn = _pxEl('btn-px-zoom-in');
    const fitBtn = _pxEl('btn-px-view-fit');
    const centerBtn = _pxEl('btn-px-view-center');

    if (zoomEl) {
        zoomEl.addEventListener('input', () => _pxSetPreviewZoom(zoomEl.value));
        zoomEl.addEventListener('change', () => _pxSetPreviewZoom(zoomEl.value));
    }
    if (zoomOutBtn) zoomOutBtn.onclick = () => _pxZoomPreviewByFactor(1 / 1.2);
    if (zoomInBtn) zoomInBtn.onclick = () => _pxZoomPreviewByFactor(1.2);
    if (fitBtn) fitBtn.onclick = () => _pxResetPreviewViewToFit();
    if (centerBtn) centerBtn.onclick = () => _pxCenterPreviewView();

    _pxSyncPreviewViewUi();
}

function _pxOnPreviewWheel(e) {
    const preview = _pxGetPreviewCanvas();
    if (!preview || preview.classList.contains('hidden')) return;
    if (!e) return;
    const dy = _coerceFiniteNumber(e.deltaY, 0);
    if (dy === 0) return;

    e.preventDefault();
    e.stopPropagation();

    const rect = preview.getBoundingClientRect();
    const rw = Number(rect.width || 0);
    const rh = Number(rect.height || 0);
    let nx = 0.5;
    let ny = 0.5;
    if (rw > 0 && rh > 0) {
        nx = (Number(e.clientX || 0) - Number(rect.left || 0)) / rw;
        ny = (Number(e.clientY || 0) - Number(rect.top || 0)) / rh;
    }
    nx = Math.max(0, Math.min(1, nx));
    ny = Math.max(0, Math.min(1, ny));

    const base = e.ctrlKey ? 1.25 : 1.12;
    const factor = dy < 0 ? base : (1 / base);
    _pxZoomPreviewByFactor(factor, { clientX: Number(e.clientX || 0), clientY: Number(e.clientY || 0), nx, ny });
}

function _pxEnsurePreviewCtx(w, h) {
    const el = _pxGetPreviewCanvas();
    if (!el) return null;
    const ww = Math.max(1, Math.round(Number(w || 0)));
    const hh = Math.max(1, Math.round(Number(h || 0)));
    if (ww <= 0 || hh <= 0) return null;

    if (Number(el.width) !== ww) el.width = ww;
    if (Number(el.height) !== hh) el.height = hh;

    const ctx = el.getContext('2d', { willReadFrequently: true });
    if (!ctx) return null;
    ctx.imageSmoothingEnabled = false;
    _pxPreviewCtx = ctx;
    _pxPreviewW = ww;
    _pxPreviewH = hh;
    el.classList.remove('hidden');
    _pxFitPreviewCanvasCssSize();
    return ctx;
}

function _pxRenderPreviewFromMatrixInfo(matrixInfo, ignoreMask) {
    if (!matrixInfo) return;
    const w = Number(matrixInfo.w || 0);
    const h = Number(matrixInfo.h || 0);
    const idxArr = matrixInfo.idxArr;
    const transparentIdx = Number(matrixInfo.transparentIdx);
    const palette = Array.isArray(matrixInfo.palette) ? matrixInfo.palette : [];
    if (w <= 0 || h <= 0 || !(idxArr instanceof Uint16Array) || palette.length === 0) {
        _pxHidePreviewCanvas();
        return;
    }
    const ctx = _pxEnsurePreviewCtx(w, h);
    if (!ctx) return;

    const mask = (ignoreMask instanceof Uint8Array) ? ignoreMask : null;
    _pxPreviewIgnoreMask = mask;
    const keepMask = (_pxKeepMask instanceof Uint8Array && _pxKeepMask.length === idxArr.length) ? _pxKeepMask : null;

    const imgData = ctx.createImageData(w, h);
    const data = imgData.data;
    for (let i = 0; i < w * h; i++) {
        const idx = Number(idxArr[i]);
        const o = i * 4;
        if (idx === transparentIdx || ((mask && mask[i] === 1) && !(keepMask && keepMask[i] === 1))) {
            data[o + 3] = 0;
            continue;
        }
        const color = String(palette[idx] || '').trim();
        const rgb = hexToRgb(color);
        data[o] = Number(rgb.r) & 255;
        data[o + 1] = Number(rgb.g) & 255;
        data[o + 2] = Number(rgb.b) & 255;
        data[o + 3] = 255;
    }
    ctx.putImageData(imgData, 0, 0);
    _pxFitPreviewCanvasCssSize();
}

function _pxPreviewFillPixel(pos, fillColor) {
    const ctx = _pxPreviewCtx;
    const w = Number(_pxPreviewW || 0);
    const h = Number(_pxPreviewH || 0);
    if (!ctx || w <= 0 || h <= 0) return;
    const p = Number(pos);
    if (!(p >= 0) || p >= w * h) return;
    const x = p % w;
    const y = (p / w) | 0;
    ctx.fillStyle = String(fillColor || '').trim() || '#000000';
    ctx.fillRect(x, y, 1, 1);
}

function _pxFileStem(fileName) {
    const name = String(fileName || '').trim();
    if (!name) return '';
    const idx = name.lastIndexOf('.');
    if (idx <= 0) return name;
    return name.slice(0, idx);
}

function _pxGetOptionsFromUi() {
    const cellEl = _pxEl('px-cell-size');
    const refineEl = _pxEl('px-refine-intensity');
    const sampleEl = _pxEl('px-sample-method');
    const fixEl = _pxEl('px-fix-square');
    const ignoreEl = _pxEl('px-ignore-bg');
    const genModeEl = _pxEl('px-generate-mode');

    const cellSizePx0 = _coerceFiniteNumber(cellEl ? cellEl.value : 12, 12);
    const cellSizePx = Math.max(1, Math.min(400, Math.round(cellSizePx0)));

    const refine0 = _coerceFiniteNumber(refineEl ? refineEl.value : 0.30, 0.30);
    const refineIntensity = Math.max(0, Math.min(0.5, Number(refine0)));

    const sampleMethod = String(sampleEl && sampleEl.value ? sampleEl.value : 'center').trim() || 'center';
    const fixSquare = !!(fixEl && fixEl.checked);
    const ignoreBg = !!(ignoreEl && ignoreEl.checked);
    const genMode0 = String(genModeEl && genModeEl.value ? genModeEl.value : 'merge_rects').trim() || 'merge_rects';
    const generateMode = (genMode0 === 'pixel_points') ? 'pixel_points' : 'merge_rects';

    return { cellSizePx, refineIntensity, sampleMethod, fixSquare, ignoreBg, generateMode };
}

// ------------------------------------------------------------ palette snapping (perceptual, Lab ΔE)

function _pxSrgbToLinear01(v01) {
    const v = Number(v01);
    if (v <= 0.04045) return v / 12.92;
    return Math.pow((v + 0.055) / 1.055, 2.4);
}

function _pxRgbToLab(r8, g8, b8) {
    const r01 = _pxSrgbToLinear01(Number(r8) / 255.0);
    const g01 = _pxSrgbToLinear01(Number(g8) / 255.0);
    const b01 = _pxSrgbToLinear01(Number(b8) / 255.0);

    // sRGB D65
    const x = r01 * 0.4124564 + g01 * 0.3575761 + b01 * 0.1804375;
    const y = r01 * 0.2126729 + g01 * 0.7151522 + b01 * 0.0721750;
    const z = r01 * 0.0193339 + g01 * 0.1191920 + b01 * 0.9503041;

    // reference white
    const xn = 0.95047;
    const yn = 1.0;
    const zn = 1.08883;

    function f(t) {
        const d = 6.0 / 29.0;
        const d3 = d * d * d;
        if (t > d3) return Math.cbrt(t);
        return (t / (3.0 * d * d)) + (4.0 / 29.0);
    }

    const fx = f(x / xn);
    const fy = f(y / yn);
    const fz = f(z / zn);

    const L = 116.0 * fy - 16.0;
    const a = 500.0 * (fx - fy);
    const b = 200.0 * (fy - fz);
    return [L, a, b];
}

function _pxDeltaE76Sq(lab1, lab2) {
    const dL = Number(lab1[0]) - Number(lab2[0]);
    const da = Number(lab1[1]) - Number(lab2[1]);
    const db = Number(lab1[2]) - Number(lab2[2]);
    return dL * dL + da * da + db * db;
}

function _pxEnsureRectPaletteColorSpaces() {
    const palette = Array.isArray(RECT_COLORS) ? RECT_COLORS : [];
    if (_pxRectPaletteRgb && _pxRectPaletteLab && _pxRectPaletteRgb.length === palette.length) {
        return;
    }
    _pxRectPaletteRgb = palette.map((c) => {
        const rgb = hexToRgb(String(c || ''));
        return { r: Number(rgb.r) || 0, g: Number(rgb.g) || 0, b: Number(rgb.b) || 0 };
    });
    _pxRectPaletteLab = _pxRectPaletteRgb.map((p) => _pxRgbToLab(p.r, p.g, p.b));
    _pxRgbKeyToPaletteIdx.clear();
    _pxRgbKeyToLab.clear();
}

function _pxNearestRectPaletteIdx(r8, g8, b8) {
    _pxEnsureRectPaletteColorSpaces();
    const r = Number(r8) & 255;
    const g = Number(g8) & 255;
    const b = Number(b8) & 255;
    const key = (r << 16) | (g << 8) | b;
    const cached = _pxRgbKeyToPaletteIdx.get(key);
    if (cached !== undefined) return Number(cached);

    let lab = _pxRgbKeyToLab.get(key);
    if (!lab) {
        lab = _pxRgbToLab(r, g, b);
        // 控制缓存大小，避免极端情况下无限增长
        if (_pxRgbKeyToLab.size < 50000) {
            _pxRgbKeyToLab.set(key, lab);
        }
    }

    const palLab = _pxRectPaletteLab || [];
    let bestIdx = 0;
    let bestDist = Infinity;
    for (let i = 0; i < palLab.length; i++) {
        const dist = _pxDeltaE76Sq(lab, palLab[i]);
        if (dist < bestDist) {
            bestDist = dist;
            bestIdx = i;
        }
    }

    if (_pxRgbKeyToPaletteIdx.size < 50000) {
        _pxRgbKeyToPaletteIdx.set(key, bestIdx);
    }
    return bestIdx;
}

function _pxUpdateMeta() {
    if (!_pxInputDataUrl) {
        _pxSetMeta('（未选择图片）');
        _pxHidePreviewCanvas();
        if (typeof _pxSyncPixelEditUi === 'function') _pxSyncPixelEditUi();
        return;
    }

    const opts = _pxGetOptionsFromUi();
    const sigNow = _pxComputeRefineSig(opts);
    const parts = [];
    const stem = _pxFileStem(_pxInputFileName) || _pxInputFileName || '(unnamed)';
    const genMode = String(opts.generateMode || 'merge_rects').trim() || 'merge_rects';
    parts.push(`输入: ${stem}`);
    parts.push(`参数: cell=${opts.cellSizePx}px refine=${opts.refineIntensity.toFixed(2)} sample=${opts.sampleMethod} fixSquare=${opts.fixSquare ? 'on' : 'off'} ignoreBg=${opts.ignoreBg ? 'on' : 'off'}`);
    parts.push(`实体化: ${genMode === 'pixel_points' ? `像素点（每像素 1 矩形，不合并）` : '合并矩形（同色相邻像素合并为更少矩形）'}`);
    parts.push(`吸附: Lab(ΔE) -> RECT_COLORS`);
    if (_pxRefinedDataUrl && _pxRefinedW > 0 && _pxRefinedH > 0) {
        parts.push(`已标准像素化: ${_pxRefinedW}×${_pxRefinedH}`);
        if (_pxLastRefineSig && _pxLastRefineSig !== sigNow) {
            parts.push('提示: 参数已变更，建议重新“标准像素化”以刷新结果');
        }
        if (opts.ignoreBg && _pxQuantizedBgColor) {
            parts.push(`背景(忽略): ${_pxQuantizedBgColor}`);
        }
    } else {
        parts.push('状态: 未标准像素化（导入后会自动处理；也可手动点“标准像素化”）');
        _pxHidePreviewCanvas();
    }
    _pxSetMeta(parts.join('\n'));
    if (typeof _pxSyncPixelEditUi === 'function') _pxSyncPixelEditUi();
}

// ------------------------------------------------------------ pixel edit (matrix-level recolor before merge)

function _pxEnsureOriginalMatrixSnapshot(matrixInfo) {
    const key = String(_pxMatrixCacheKey || _pxRefinedDataUrl || '').trim();
    if (!key || !matrixInfo || !(matrixInfo.idxArr instanceof Uint16Array)) return;
    const idxArr = matrixInfo.idxArr;

    if (_pxOriginalMatrixKey === key && _pxOriginalIdxArr && _pxOriginalIdxArr.length === idxArr.length) {
        return;
    }

    _pxOriginalMatrixKey = key;
    _pxOriginalIdxArr = new Uint16Array(idxArr);
    _pxOriginalCounts = Array.isArray(matrixInfo.counts) ? matrixInfo.counts.slice() : null;
    _pxOriginalBgIdx = -1;
    _pxOriginalIgnoreMask = null;
    _pxEditHistory = [];
    _pxEditStroke = null;
    _pxSyncPixelEditUi();
}

function _pxEnsureKeepMask(matrixInfo) {
    const info = matrixInfo;
    if (!info || !(info.idxArr instanceof Uint16Array)) return null;
    const n = info.idxArr.length;
    if (_pxKeepMask instanceof Uint8Array && _pxKeepMask.length === n) {
        return _pxKeepMask;
    }
    _pxKeepMask = new Uint8Array(n);
    return _pxKeepMask;
}

function _pxEnsureOriginalIgnoreMask(matrixInfo) {
    if (!matrixInfo) return { bgIdx: -1, ignoreMask: null };
    const w = Number(matrixInfo.w || 0);
    const h = Number(matrixInfo.h || 0);
    const transparentIdx = Number(matrixInfo.transparentIdx);
    if (w <= 0 || h <= 0) return { bgIdx: -1, ignoreMask: null };
    if (!(_pxOriginalIdxArr instanceof Uint16Array) || _pxOriginalIdxArr.length !== w * h) {
        return { bgIdx: -1, ignoreMask: null };
    }
    if (_pxOriginalIgnoreMask && _pxOriginalIgnoreMask.length === _pxOriginalIdxArr.length && _pxOriginalBgIdx >= 0) {
        return { bgIdx: Number(_pxOriginalBgIdx), ignoreMask: _pxOriginalIgnoreMask };
    }
    const info0 = { w, h, idxArr: _pxOriginalIdxArr, transparentIdx };
    const bgIdx = _pxPickBgIdxFromBorder(info0);
    if (!(bgIdx >= 0)) {
        _pxOriginalBgIdx = -1;
        _pxOriginalIgnoreMask = null;
        return { bgIdx: -1, ignoreMask: null };
    }
    const ignoreMask = _pxBuildIgnoreMaskForBackground(info0, bgIdx);
    _pxOriginalBgIdx = Number(bgIdx);
    _pxOriginalIgnoreMask = ignoreMask;
    return { bgIdx: Number(bgIdx), ignoreMask };
}

function _pxIsPosEditable(pos, matrixInfo, ignoreBg) {
    if (!matrixInfo) return false;
    const idxArr = matrixInfo.idxArr;
    const transparentIdx = Number(matrixInfo.transparentIdx);
    const p = Number(pos);
    if (!(p >= 0) || !(idxArr instanceof Uint16Array) || p >= idxArr.length) return false;

    const allowBlank = _pxEditAllowBlank === true;
    const keepMask = (_pxKeepMask instanceof Uint8Array && _pxKeepMask.length === idxArr.length) ? _pxKeepMask : null;
    if (!allowBlank && keepMask && keepMask[p] === 1 && Number(idxArr[p]) !== transparentIdx) {
        // 已经“长出来”的像素：即使关闭 allowBlank，也应允许继续改色/擦除
        return true;
    }
    if (_pxOriginalIdxArr instanceof Uint16Array && _pxOriginalIdxArr.length === idxArr.length) {
        if (!allowBlank) {
            // 关键：默认只允许在“原始非透明区域”里改色（避免长出新像素）
            if (Number(_pxOriginalIdxArr[p]) === transparentIdx) return false;
            if (ignoreBg) {
                const { ignoreMask } = _pxEnsureOriginalIgnoreMask(matrixInfo);
                if (ignoreMask && ignoreMask[p] === 1) return false;
                // fallback：若未能构建原始 ignoreMask，至少禁止当前预览里显示为透明的区域
                if (!ignoreMask && _pxPreviewIgnoreMask && _pxPreviewIgnoreMask[p] === 1 && !(keepMask && keepMask[p] === 1)) return false;
            }
        }
        return true;
    }

    if (!allowBlank) {
        // fallback：至少保证不能从“当前透明像素”长出新颜色
        if (Number(idxArr[p]) === transparentIdx) return false;
        if (ignoreBg && _pxPreviewIgnoreMask && _pxPreviewIgnoreMask[p] === 1 && !(keepMask && keepMask[p] === 1)) return false;
    }
    return true;
}

function _pxNormalizeToRectPaletteColor(color) {
    const c0 = normalizeColor(String(color || '').trim());
    let c = c0;
    if (!RECT_COLORS.includes(c)) {
        const rgb = hexToRgb(c0);
        c = getNearestRectPaletteColor(rgb.r, rgb.g, rgb.b);
    }
    if (!RECT_COLORS.includes(c)) {
        c = RECT_COLORS[0] || '#FFFFFF';
    }
    return c;
}

function _pxGetPixelEditColor() {
    if (_pxEditColor) return _pxEditColor;
    const fallback = (typeof _lastRectFill !== 'undefined' && _lastRectFill) ? String(_lastRectFill) : (RECT_COLORS[0] || '#FFFFFF');
    _pxEditColor = _pxNormalizeToRectPaletteColor(fallback);
    return _pxEditColor;
}

function _pxSetPixelEditColor(color) {
    // 选择目标色一般意味着继续用“画笔”涂色（避免处于垃圾桶模式时产生困惑）
    _pxEditTool = 'brush';
    _pxEditColor = _pxNormalizeToRectPaletteColor(color);
    if (typeof _lastRectFill !== 'undefined' && RECT_COLORS.includes(_pxEditColor)) {
        _lastRectFill = _pxEditColor;
    }
    _pxHidePixelBrushIndicator();
    _pxSyncPixelEditUi();
}

function _pxGetPixelEditTool() {
    const t = String(_pxEditTool || '').trim().toLowerCase();
    return t === 'trash' ? 'trash' : 'brush';
}

function _pxSetPixelEditTool(tool) {
    const t = String(tool || '').trim().toLowerCase() === 'trash' ? 'trash' : 'brush';
    _pxEditTool = t;
    _pxHidePixelBrushIndicator();
    _pxSyncPixelEditUi();
}

function _pxSetPixelEditBrushSize(sizePx) {
    const n0 = _coerceFiniteNumber(sizePx, _pxEditBrushSize || 1);
    const n = Math.max(1, Math.min(12, Math.round(Number(n0))));
    _pxEditBrushSize = n;
    _pxSyncPixelEditUi();
}

function _pxSetPixelEditAllowBlank(enabled) {
    _pxEditAllowBlank = !!enabled;
    _pxHidePixelBrushIndicator();
    _pxSyncPixelEditUi();
}

function _pxSetPixelEditEnabled(enabled) {
    const next = !!enabled;
    if (next && !_pxRefinedDataUrl) {
        toastToUi('warn', '请先“标准像素化”后再改色');
        _pxEditEnabled = false;
        _pxSyncPixelEditUi();
        return;
    }
    _pxEditEnabled = next;
    if (!_pxEditEnabled) {
        _pxEditStroke = null;
    }
    _pxSyncPixelEditUi();
}

function _pxInvalidateIgnoreMaskCache() {
    _pxIgnoreMaskKey = '';
    _pxIgnoreMask = null;
    _pxIgnoreMaskBgIdx = -1;
}

function _pxSyncPixelEditUi() {
    const onBtn = _pxEl('px-edit-on');
    const offBtn = _pxEl('px-edit-off');
    if (onBtn) onBtn.classList.toggle('active', _pxEditEnabled === true);
    if (offBtn) offBtn.classList.toggle('active', !(_pxEditEnabled === true));

    const toolBrushBtn = _pxEl('px-edit-tool-brush');
    const toolTrashBtn = _pxEl('px-edit-tool-trash');
    const tool = _pxGetPixelEditTool();
    if (toolBrushBtn) toolBrushBtn.classList.toggle('active', tool !== 'trash');
    if (toolTrashBtn) toolTrashBtn.classList.toggle('active', tool === 'trash');

    const sizeEl = _pxEl('px-edit-size');
    const sizeNumEl = _pxEl('px-edit-size-number');
    const size = Math.max(1, Math.round(Number(_pxEditBrushSize || 1)));
    if (sizeEl && Number(sizeEl.value) !== size) sizeEl.value = String(size);
    if (sizeNumEl && Number(sizeNumEl.value) !== size) sizeNumEl.value = String(size);

    const allowBlankEl = _pxEl('px-edit-allow-blank');
    if (allowBlankEl) {
        allowBlankEl.checked = _pxEditAllowBlank === true;
    }

    const pal = _pxEl('px-edit-palette');
    if (pal) {
        const target = normalizeColor(_pxGetPixelEditColor());
        const buttons = pal.querySelectorAll('[data-px-edit-color]');
        buttons.forEach((btn) => {
            const v = normalizeColor(String(btn.getAttribute('data-px-edit-color') || ''));
            btn.classList.toggle('active', v === target);
        });
    }

    const undoBtn = _pxEl('btn-px-undo');
    const resetBtn = _pxEl('btn-px-reset');
    const canEdit = !!_pxRefinedDataUrl;
    const canUndo = canEdit && Array.isArray(_pxEditHistory) && _pxEditHistory.length > 0;
    if (undoBtn) undoBtn.disabled = !canUndo;
    if (resetBtn) resetBtn.disabled = !canEdit;
    if (allowBlankEl) allowBlankEl.disabled = !canEdit;
    if (toolBrushBtn) toolBrushBtn.disabled = !canEdit;
    if (toolTrashBtn) toolTrashBtn.disabled = !canEdit;

    const preview = _pxGetPreviewCanvas();
    if (preview) {
        preview.classList.toggle('editing', _pxEditEnabled === true);
    }

    if (!_pxEditEnabled) {
        _pxHidePixelBrushIndicator();
    }
}

function _pxGetPixelBrushIndicatorEl() {
    return _pxEl('px-brush-indicator');
}

function _pxHidePixelBrushIndicator() {
    const el = _pxGetPixelBrushIndicatorEl();
    if (!el) return;
    el.classList.add('hidden');
    el.classList.remove('not-allowed');
    el.style.left = '';
    el.style.top = '';
    el.style.width = '';
    el.style.height = '';
    el.style.borderColor = '';
    el.style.background = '';
}

function _pxUpdatePixelBrushIndicatorByPos(pos, matrixInfo) {
    const ind = _pxGetPixelBrushIndicatorEl();
    const canvasEl = _pxGetPreviewCanvas();
    const wrap = _pxEl('px-preview-wrap');
    if (!ind || !canvasEl || !wrap) return;
    if (canvasEl.classList.contains('hidden')) {
        _pxHidePixelBrushIndicator();
        return;
    }

    const w = Math.max(0, Math.round(Number(matrixInfo && matrixInfo.w || 0)));
    const h = Math.max(0, Math.round(Number(matrixInfo && matrixInfo.h || 0)));
    if (w <= 0 || h <= 0) {
        _pxHidePixelBrushIndicator();
        return;
    }

    const p0 = Number(pos);
    if (!(p0 >= 0) || p0 >= w * h) {
        _pxHidePixelBrushIndicator();
        return;
    }

    const ignoreBg = !!(_pxGetOptionsFromUi().ignoreBg);
    const allowed = _pxIsPosEditable(p0, matrixInfo, ignoreBg);

    const size = Math.max(1, Math.round(Number(_pxEditBrushSize || 1)));
    const cx = p0 % w;
    const cy = (p0 / w) | 0;
    const start = -Math.floor(size / 2);
    const x0 = cx + start;
    const y0 = cy + start;
    const x1 = x0 + size;
    const y1 = y0 + size;
    const x0c = Math.max(0, x0);
    const y0c = Math.max(0, y0);
    const x1c = Math.min(w, x1);
    const y1c = Math.min(h, y1);

    const wrapRect = wrap.getBoundingClientRect();
    const canvasRect = canvasEl.getBoundingClientRect();
    const rw = Number(canvasRect.width || 0);
    const rh = Number(canvasRect.height || 0);
    if (rw <= 0 || rh <= 0) {
        _pxHidePixelBrushIndicator();
        return;
    }

    const offX = Number(canvasRect.left || 0) - Number(wrapRect.left || 0);
    const offY = Number(canvasRect.top || 0) - Number(wrapRect.top || 0);
    const sx = rw / w;
    const sy = rh / h;

    const left = offX + x0c * sx;
    const top = offY + y0c * sy;
    const ww = (x1c - x0c) * sx;
    const hh = (y1c - y0c) * sy;

    ind.style.left = `${Math.round(left)}px`;
    ind.style.top = `${Math.round(top)}px`;
    ind.style.width = `${Math.max(1, Math.round(ww))}px`;
    ind.style.height = `${Math.max(1, Math.round(hh))}px`;

    if (allowed) {
        ind.classList.remove('not-allowed');
        if (_pxGetPixelEditTool() === 'trash') {
            // 垃圾桶/擦除：用中性色显示笔刷范围（避免与“目标色”混淆）
            ind.style.borderColor = 'rgba(220,220,220,0.85)';
            ind.style.background = 'rgba(220,220,220,0.08)';
        } else {
            const c = _pxGetPixelEditColor();
            const rgb = hexToRgb(c);
            ind.style.borderColor = `rgba(${Number(rgb.r) || 0},${Number(rgb.g) || 0},${Number(rgb.b) || 0},0.85)`;
            ind.style.background = `rgba(${Number(rgb.r) || 0},${Number(rgb.g) || 0},${Number(rgb.b) || 0},0.10)`;
        }
    } else {
        ind.classList.add('not-allowed');
        ind.style.borderColor = '';
        ind.style.background = '';
    }

    ind.classList.remove('hidden');
}

function _pxRenderPixelEditPalette() {
    const container = _pxEl('px-edit-palette');
    if (!container) return;
    container.innerHTML = '';
    const colors = Array.isArray(RECT_COLORS) ? RECT_COLORS : [];
    colors.forEach((color) => {
        const c = _pxNormalizeToRectPaletteColor(color);
        const btn = document.createElement('button');
        btn.className = 'color-btn';
        btn.style.backgroundColor = c;
        btn.setAttribute('data-px-edit-color', c);
        btn.title = `目标色：${c}`;
        btn.onclick = () => _pxSetPixelEditColor(c);
        container.appendChild(btn);
    });
    _pxSyncPixelEditUi();
}

function _pxGetPixelPosFromPointerEvent(e, matrixInfo) {
    const el = _pxGetPreviewCanvas();
    if (!el || !e || !matrixInfo) return -1;
    const w = Number(matrixInfo.w || 0);
    const h = Number(matrixInfo.h || 0);
    if (w <= 0 || h <= 0) return -1;
    const rect = el.getBoundingClientRect();
    const rw = Number(rect.width || 0);
    const rh = Number(rect.height || 0);
    if (rw <= 0 || rh <= 0) return -1;
    const nx = (Number(e.clientX || 0) - Number(rect.left || 0)) / rw;
    const ny = (Number(e.clientY || 0) - Number(rect.top || 0)) / rh;
    const x = Math.max(0, Math.min(w - 1, Math.floor(nx * w)));
    const y = Math.max(0, Math.min(h - 1, Math.floor(ny * h)));
    return y * w + x;
}

function _pxGetTargetPaletteIdx(matrixInfo) {
    const palette = Array.isArray(matrixInfo && matrixInfo.palette) ? matrixInfo.palette : [];
    const color = _pxGetPixelEditColor();
    const idx = palette.indexOf(color);
    if (idx >= 0) return idx;
    // fallback: RECT_COLORS is the canonical palette; matrixInfo.palette should match it.
    const idx2 = (Array.isArray(RECT_COLORS) ? RECT_COLORS : []).indexOf(color);
    return idx2 >= 0 ? idx2 : 0;
}

function _pxGetTargetIdxForCurrentTool(matrixInfo) {
    if (!matrixInfo) return 0;
    if (_pxGetPixelEditTool() === 'trash') {
        return Number(matrixInfo.transparentIdx);
    }
    return _pxGetTargetPaletteIdx(matrixInfo);
}

function _pxApplyIdxChange(matrixInfo, pos, nextIdx, strokeChanges, allowBlank) {
    const idxArr = matrixInfo.idxArr;
    const transparentIdx = Number(matrixInfo.transparentIdx);
    const p = Number(pos);
    const ni = Number(nextIdx);
    if (!(p >= 0) || p >= idxArr.length) return false;
    const before = Number(idxArr[p]);
    if (before === ni) return false;
    const allow = (allowBlank === true);
    if (before === transparentIdx && !allow) return false; // default: keep transparent immutable

    if (strokeChanges && strokeChanges instanceof Map && !strokeChanges.has(p)) {
        strokeChanges.set(p, before);
    }

    idxArr[p] = ni;

    const counts = Array.isArray(matrixInfo.counts) ? matrixInfo.counts : null;
    if (counts) {
        if (before >= 0 && before < counts.length) counts[before] = Number(counts[before] || 0) - 1;
        if (ni >= 0 && ni < counts.length) counts[ni] = Number(counts[ni] || 0) + 1;
    }

    return true;
}

function _pxApplyKeepMaskChange(keepMask, pos, nextKeep, keepChanges) {
    const m = keepMask;
    if (!(m instanceof Uint8Array)) return false;
    const p = Number(pos);
    if (!(p >= 0) || p >= m.length) return false;
    const nk = nextKeep ? 1 : 0;
    const before = Number(m[p] || 0);
    if (before === nk) return false;
    if (keepChanges && keepChanges instanceof Map && !keepChanges.has(p)) {
        keepChanges.set(p, before);
    }
    m[p] = nk;
    return true;
}

function _pxBeginPaintStroke(matrixInfo, pointerId, ignoreBg) {
    const targetIdx = _pxGetTargetIdxForCurrentTool(matrixInfo);
    const ignore = !!ignoreBg;
    const allowBlank = (_pxEditAllowBlank === true);
    const lockMask = (!allowBlank && ignore) ? (_pxEnsureOriginalIgnoreMask(matrixInfo).ignoreMask || null) : null;
    const origIdxArr = (!allowBlank && _pxOriginalIdxArr instanceof Uint16Array && _pxOriginalIdxArr.length === (matrixInfo.idxArr || []).length)
        ? _pxOriginalIdxArr
        : null;
    const keepMask = _pxEnsureKeepMask(matrixInfo);
    _pxEditStroke = {
        changes: new Map(),
        keepChanges: new Map(),
        targetIdx: Number(targetIdx),
        w: Number(matrixInfo.w || 0),
        h: Number(matrixInfo.h || 0),
        pointerId: Number(pointerId),
        matrixInfo: matrixInfo,
        ignoreBg: ignore,
        allowBlank: allowBlank,
        lockMask: lockMask,
        origIdxArr: origIdxArr,
        keepMask: keepMask,
        transparentIdx: Number(matrixInfo.transparentIdx)
    };
}

function _pxApplyPaintAtPos(matrixInfo, pos) {
    const st = _pxEditStroke;
    if (!st || !matrixInfo) return;
    const w = Number(matrixInfo.w || 0);
    const h = Number(matrixInfo.h || 0);
    if (w <= 0 || h <= 0) return;

    const p0 = Number(pos);
    const cx = p0 % w;
    const cy = (p0 / w) | 0;

    const size = Math.max(1, Math.round(Number(_pxEditBrushSize || 1)));
    const start = -Math.floor(size / 2);
    const end = start + size - 1;
    const ctx = _pxPreviewCtx;

    const allowBlank = !!st.allowBlank;
    const transparentIdx = Number(st.transparentIdx);
    const isErase = Number(st.targetIdx) === transparentIdx;
    if (ctx && !isErase) {
        const fillColor = String((matrixInfo.palette || [])[st.targetIdx] || _pxGetPixelEditColor() || '').trim();
        ctx.fillStyle = fillColor || '#000000';
    }
    const origIdxArr = st.origIdxArr;
    const lockMask = st.lockMask;
    const keepMask = (st.keepMask instanceof Uint8Array && st.keepMask.length === (matrixInfo.idxArr || []).length) ? st.keepMask : null;
    const keepChanges = st.keepChanges;
    const nextKeep = isErase ? 0 : 1;

    for (let dy = start; dy <= end; dy++) {
        const y = cy + dy;
        if (y < 0 || y >= h) continue;
        for (let dx = start; dx <= end; dx++) {
            const x = cx + dx;
            if (x < 0 || x >= w) continue;
            const p = y * w + x;
            if (!allowBlank) {
                // 默认：只允许改“原始非透明区域”，并在 ignoreBg=on 时禁止改背景（透明区域）
                const kept = (keepMask && keepMask[p] === 1);
                if (!kept) {
                    if (origIdxArr && Number(origIdxArr[p]) === transparentIdx) continue;
                    if (lockMask && lockMask[p] === 1) continue;
                }
            }
            const keepChanged = _pxApplyKeepMaskChange(keepMask, p, nextKeep, keepChanges);
            const idxChanged = _pxApplyIdxChange(matrixInfo, p, st.targetIdx, st.changes, allowBlank);
            if (!idxChanged && !keepChanged) continue;
            if (ctx) {
                if (isErase) {
                    ctx.clearRect(x, y, 1, 1);
                } else {
                    ctx.fillRect(x, y, 1, 1);
                }
            }
        }
    }
}

async function _pxCommitPaintStroke() {
    const st = _pxEditStroke;
    _pxEditStroke = null;
    const hasIdxChanges = !!(st && st.changes && st.changes.size > 0);
    const hasKeepChanges = !!(st && st.keepChanges && st.keepChanges.size > 0);
    if (!st || (!hasIdxChanges && !hasKeepChanges)) return;

    const changes = [];
    if (hasIdxChanges) {
        for (const [pos, prevIdx] of st.changes.entries()) {
            changes.push([Number(pos), Number(prevIdx)]);
        }
    }
    const keepChanges = [];
    if (hasKeepChanges) {
        for (const [pos, prevKeep] of st.keepChanges.entries()) {
            keepChanges.push([Number(pos), Number(prevKeep)]);
        }
    }
    const item = { kind: 'paint', changes };
    if (keepChanges.length > 0) item.keep_changes = keepChanges;
    _pxEditHistory.push(item);
    if (hasIdxChanges) {
        _pxInvalidateIgnoreMaskCache();
    }
    await _pxRebuildQuantizedPreviewForCurrentOptions();
    _pxUpdateMeta();
    if (hasIdxChanges) {
        _pxMarkSelectedAssetMatrixDirty('paint');
    }
    _pxSchedulePersistPixelWorkbenchState('paint');
}

async function _pxReplaceAllPixelsByIdx(matrixInfo, srcIdx, dstIdx, ignoreBg) {
    const idxArr = matrixInfo.idxArr;
    const transparentIdx = Number(matrixInfo.transparentIdx);
    const s = Number(srcIdx);
    const d = Number(dstIdx);
    if (s === d) return 0;
    const allowBlank = (_pxEditAllowBlank === true);
    if (s === transparentIdx && !allowBlank) return 0;
    const keepMask = _pxEnsureKeepMask(matrixInfo);
    const keepChanges = [];
    const nextKeep = (d === transparentIdx) ? 0 : 1;
    const changedPos = [];
    const ignore = !!ignoreBg;
    const lockMask = (!allowBlank && ignore) ? (_pxEnsureOriginalIgnoreMask(matrixInfo).ignoreMask || null) : null;
    const origIdxArr = (!allowBlank && _pxOriginalIdxArr instanceof Uint16Array && _pxOriginalIdxArr.length === idxArr.length)
        ? _pxOriginalIdxArr
        : null;
    for (let p = 0; p < idxArr.length; p++) {
        if (!allowBlank) {
            const kept = (keepMask && keepMask[p] === 1);
            if (!kept) {
                if (origIdxArr && Number(origIdxArr[p]) === transparentIdx) continue;
                if (lockMask && lockMask[p] === 1) continue;
            }
        }
        if (Number(idxArr[p]) !== s) continue;
        idxArr[p] = d;
        changedPos.push(p);
        if (keepMask) {
            const prev = Number(keepMask[p] || 0);
            if (prev !== nextKeep) {
                keepChanges.push([Number(p), prev]);
            }
            keepMask[p] = nextKeep;
        }
    }

    const counts = Array.isArray(matrixInfo.counts) ? matrixInfo.counts : null;
    if (counts) {
        const n = changedPos.length;
        if (s >= 0 && s < counts.length) counts[s] = Number(counts[s] || 0) - n;
        if (d >= 0 && d < counts.length) counts[d] = Number(counts[d] || 0) + n;
    }

    if (changedPos.length > 0) {
        const item = { kind: 'replace', srcIdx: s, dstIdx: d, positions: changedPos };
        if (keepChanges.length > 0) item.keep_changes = keepChanges;
        _pxEditHistory.push(item);
        _pxInvalidateIgnoreMaskCache();
        await _pxRebuildQuantizedPreviewForCurrentOptions();
        _pxUpdateMeta();
        _pxMarkSelectedAssetMatrixDirty('replace');
        _pxSchedulePersistPixelWorkbenchState('replace');
    }
    return changedPos.length;
}

async function _pxUndoLastPixelEdit() {
    const matrixInfo = await _pxEnsureMatrixInfo();
    if (!matrixInfo) return;
    if (!Array.isArray(_pxEditHistory) || _pxEditHistory.length === 0) {
        toastToUi('warn', '没有可撤销的改色操作');
        return;
    }
    const last = _pxEditHistory.pop();
    if (!last) return;

    const idxArr = matrixInfo.idxArr;
    const transparentIdx = Number(matrixInfo.transparentIdx);
    const counts = Array.isArray(matrixInfo.counts) ? matrixInfo.counts : null;
    const keepMask = _pxEnsureKeepMask(matrixInfo);

    if (last.kind === 'paint' && Array.isArray(last.changes)) {
        last.changes.forEach((pair) => {
            const p = Number(pair && pair[0]);
            const prev = Number(pair && pair[1]);
            if (!(p >= 0) || p >= idxArr.length) return;
            const cur = Number(idxArr[p]);
            if (cur === prev) return;
            idxArr[p] = prev;
            if (counts) {
                if (cur !== transparentIdx && cur >= 0 && cur < counts.length) counts[cur] = Number(counts[cur] || 0) - 1;
                if (prev !== transparentIdx && prev >= 0 && prev < counts.length) counts[prev] = Number(counts[prev] || 0) + 1;
            }
        });
        if (keepMask && Array.isArray(last.keep_changes)) {
            last.keep_changes.forEach((pair) => {
                const p = Number(pair && pair[0]);
                const prev = Number(pair && pair[1]);
                if (!(p >= 0) || p >= keepMask.length) return;
                keepMask[p] = prev ? 1 : 0;
            });
        }
    } else if (last.kind === 'replace' && Array.isArray(last.positions)) {
        const s = Number(last.srcIdx);
        const d = Number(last.dstIdx);
        last.positions.forEach((p) => {
            const pp = Number(p);
            if (!(pp >= 0) || pp >= idxArr.length) return;
            const cur = Number(idxArr[pp]);
            if (cur !== d) return;
            idxArr[pp] = s;
        });
        if (counts) {
            const n = last.positions.length;
            if (d >= 0 && d < counts.length) counts[d] = Number(counts[d] || 0) - n;
            if (s >= 0 && s < counts.length) counts[s] = Number(counts[s] || 0) + n;
        }
        if (keepMask && Array.isArray(last.keep_changes)) {
            last.keep_changes.forEach((pair) => {
                const p = Number(pair && pair[0]);
                const prev = Number(pair && pair[1]);
                if (!(p >= 0) || p >= keepMask.length) return;
                keepMask[p] = prev ? 1 : 0;
            });
        }
    }

    _pxInvalidateIgnoreMaskCache();
    await _pxRebuildQuantizedPreviewForCurrentOptions();
    _pxUpdateMeta();
    _pxMarkSelectedAssetMatrixDirty('undo');
    _pxSchedulePersistPixelWorkbenchState('undo');
}

async function _pxResetPixelEditsToOriginal() {
    const matrixInfo = await _pxEnsureMatrixInfo();
    if (!matrixInfo) return;
    if (!(_pxOriginalIdxArr instanceof Uint16Array) || _pxOriginalIdxArr.length !== matrixInfo.idxArr.length) {
        toastToUi('warn', '没有可重置的原始像素矩阵');
        return;
    }

    matrixInfo.idxArr.set(_pxOriginalIdxArr);
    if (_pxOriginalCounts && Array.isArray(_pxOriginalCounts)) {
        matrixInfo.counts = _pxOriginalCounts.slice();
    }
    const keepMask = _pxEnsureKeepMask(matrixInfo);
    if (keepMask) keepMask.fill(0);
    _pxEditHistory = [];
    _pxInvalidateIgnoreMaskCache();
    await _pxRebuildQuantizedPreviewForCurrentOptions();
    _pxUpdateMeta();
    _pxMarkSelectedAssetMatrixDirty('reset');
    _pxSchedulePersistPixelWorkbenchState('reset');
}

async function _pxOnPreviewPointerDown(e) {
    if (!e) return;

    // Middle button drag: pan preview (even when edit is off).
    if (e.button === 1) {
        e.preventDefault();
        const preview = _pxGetPreviewCanvas();
        if (preview && preview.setPointerCapture) {
            preview.setPointerCapture(Number(e.pointerId));
        }
        _pxPreviewPanning = {
            pointerId: Number(e.pointerId),
            startX: Number(e.clientX || 0),
            startY: Number(e.clientY || 0),
            panX0: _coerceFiniteNumber(_pxPreviewPanX, 0),
            panY0: _coerceFiniteNumber(_pxPreviewPanY, 0),
        };
        _pxHidePixelBrushIndicator();
        return;
    }

    if (!_pxEditEnabled) return;
    if (e.button !== 0) return;
    e.preventDefault();

    const refinedKey = String(_pxRefinedDataUrl || '').trim();
    let matrixInfo = (_pxMatrixCache && _pxMatrixCacheKey === refinedKey) ? _pxMatrixCache : null;
    if (!matrixInfo) {
        matrixInfo = await _pxEnsureMatrixInfo();
    }
    if (!matrixInfo) return;
    _pxEnsureOriginalMatrixSnapshot(matrixInfo);

    const ignoreBg = !!(_pxGetOptionsFromUi().ignoreBg);
    const pos = _pxGetPixelPosFromPointerEvent(e, matrixInfo);
    if (!(pos >= 0)) return;
    const idx = Number(matrixInfo.idxArr[pos]);

    if (e.altKey) {
        if (!_pxIsPosEditable(pos, matrixInfo, ignoreBg)) {
            toastToUi('warn', '取色：此处为透明背景/忽略背景区域');
            return;
        }
        const color = String((matrixInfo.palette || [])[idx] || '').trim();
        if (color) {
            _pxSetPixelEditColor(color);
            toastToUi('info', `取色：${color}`, 900);
        } else {
            toastToUi('warn', '取色失败：该像素为透明/无色', 1100);
        }
        return;
    }

    if (e.shiftKey) {
        if (!_pxIsPosEditable(pos, matrixInfo, ignoreBg)) {
            toastToUi('warn', '整色替换：此处为透明背景/忽略背景区域');
            return;
        }
        const targetIdx = _pxGetTargetIdxForCurrentTool(matrixInfo);
        const verb = (_pxGetPixelEditTool() === 'trash') ? '整色删除' : '整色替换';
        const n = await _pxReplaceAllPixelsByIdx(matrixInfo, idx, targetIdx, ignoreBg);
        toastToUi('info', `${verb}：${n} px`, 1100);
        return;
    }

    if (!_pxIsPosEditable(pos, matrixInfo, ignoreBg)) {
        // 透明背景区域：不允许“长出新像素”
        return;
    }
    const preview = _pxGetPreviewCanvas();
    if (preview && preview.setPointerCapture) {
        preview.setPointerCapture(Number(e.pointerId));
    }
    _pxBeginPaintStroke(matrixInfo, e.pointerId, ignoreBg);
    _pxApplyPaintAtPos(matrixInfo, pos);
}

function _pxOnPreviewPointerMove(e) {
    const pan = _pxPreviewPanning;
    if (pan && e && Number(e.pointerId) === Number(pan.pointerId)) {
        e.preventDefault();
        const dx = Number(e.clientX || 0) - Number(pan.startX || 0);
        const dy = Number(e.clientY || 0) - Number(pan.startY || 0);
        _pxPreviewPanX = Number(pan.panX0 || 0) + dx;
        _pxPreviewPanY = Number(pan.panY0 || 0) + dy;
        _pxFitPreviewCanvasCssSize();
        _pxHidePixelBrushIndicator();
        return;
    }

    if (!_pxEditEnabled) {
        _pxHidePixelBrushIndicator();
        return;
    }

    const st = _pxEditStroke;
    const refinedKey = String(_pxRefinedDataUrl || '').trim();
    const matrixInfo = st
        ? st.matrixInfo
        : ((_pxMatrixCache && _pxMatrixCacheKey === refinedKey) ? _pxMatrixCache : null);

    if (e && matrixInfo) {
        const pos = _pxGetPixelPosFromPointerEvent(e, matrixInfo);
        if (pos >= 0) {
            _pxUpdatePixelBrushIndicatorByPos(pos, matrixInfo);
        }
    }

    if (!st) return;
    if (!e || Number(e.pointerId) !== Number(st.pointerId)) return;
    e.preventDefault();
    if (!matrixInfo) return;
    const pos = _pxGetPixelPosFromPointerEvent(e, matrixInfo);
    if (!(pos >= 0)) return;
    _pxApplyPaintAtPos(matrixInfo, pos);
}

async function _pxOnPreviewPointerUp(e) {
    const pan = _pxPreviewPanning;
    if (pan && e && Number(e.pointerId) === Number(pan.pointerId)) {
        e.preventDefault();
        const preview = _pxGetPreviewCanvas();
        if (preview && preview.releasePointerCapture) {
            preview.releasePointerCapture(Number(e.pointerId));
        }
        _pxPreviewPanning = null;
        return;
    }

    const st = _pxEditStroke;
    if (!st) return;
    if (!e || Number(e.pointerId) !== Number(st.pointerId)) return;
    e.preventDefault();
    const preview = _pxGetPreviewCanvas();
    if (preview && preview.releasePointerCapture) {
        preview.releasePointerCapture(Number(e.pointerId));
    }
    await _pxCommitPaintStroke();
}

function _pxSetupPixelEditPanel() {
    if (_pxPixelEditPanelSetupDone) return;
    _pxPixelEditPanelSetupDone = true;

    _pxRenderPixelEditPalette();

    const onBtn = _pxEl('px-edit-on');
    const offBtn = _pxEl('px-edit-off');
    if (onBtn) onBtn.onclick = () => _pxSetPixelEditEnabled(true);
    if (offBtn) offBtn.onclick = () => _pxSetPixelEditEnabled(false);

    const toolBrushBtn = _pxEl('px-edit-tool-brush');
    const toolTrashBtn = _pxEl('px-edit-tool-trash');
    if (toolBrushBtn) toolBrushBtn.onclick = () => _pxSetPixelEditTool('brush');
    if (toolTrashBtn) toolTrashBtn.onclick = () => _pxSetPixelEditTool('trash');

    const sizeEl = _pxEl('px-edit-size');
    const sizeNumEl = _pxEl('px-edit-size-number');
    [sizeEl, sizeNumEl].forEach((el) => {
        if (!el) return;
        el.addEventListener('input', () => _pxSetPixelEditBrushSize(el.value));
        el.addEventListener('change', () => _pxSetPixelEditBrushSize(el.value));
    });

    const allowBlankEl = _pxEl('px-edit-allow-blank');
    if (allowBlankEl) {
        allowBlankEl.addEventListener('change', () => _pxSetPixelEditAllowBlank(!!allowBlankEl.checked));
    }

    const undoBtn = _pxEl('btn-px-undo');
    const resetBtn = _pxEl('btn-px-reset');
    if (undoBtn) undoBtn.onclick = () => _pxUndoLastPixelEdit();
    if (resetBtn) resetBtn.onclick = () => _pxResetPixelEditsToOriginal();

    const preview = _pxGetPreviewCanvas();
    if (preview) {
        preview.addEventListener('pointerdown', _pxOnPreviewPointerDown);
        preview.addEventListener('pointermove', _pxOnPreviewPointerMove);
        preview.addEventListener('pointerup', _pxOnPreviewPointerUp);
        preview.addEventListener('pointercancel', _pxOnPreviewPointerUp);
        preview.addEventListener('pointerleave', () => _pxHidePixelBrushIndicator());
        preview.addEventListener('dblclick', () => _pxResetPreviewViewToFit());
        preview.addEventListener('contextmenu', (e) => e.preventDefault());
    }

    const wrap = _pxEl('px-preview-wrap');
    if (wrap) {
        wrap.addEventListener('wheel', _pxOnPreviewWheel, { passive: false });
    }

    _pxSyncPixelEditUi();
}

function _pxSetPixelWorkbenchTab(tab) {
    const t = String(tab || '').trim().toLowerCase() === 'edit' ? 'edit' : 'import';
    const importBtn = _pxEl('px-wb-tab-import');
    const editBtn = _pxEl('px-wb-tab-edit');
    const importPanel = _pxEl('px-wb-panel-import');
    const editPanel = _pxEl('px-wb-panel-edit');

    if (importBtn) importBtn.classList.toggle('active', t === 'import');
    if (editBtn) editBtn.classList.toggle('active', t === 'edit');
    if (importPanel) importPanel.classList.toggle('hidden', t !== 'import');
    if (editPanel) editPanel.classList.toggle('hidden', t !== 'edit');

    if (t !== 'edit') {
        _pxSetPixelEditEnabled(false);
        _pxHidePixelBrushIndicator();
    } else {
        if (_pxRefinedDataUrl) {
            _pxSetPixelEditEnabled(true);
        }
    }

    // 切到改色页：预览若已存在，确保按当前容器尺寸重新 fit
    requestAnimationFrame(() => _pxFitPreviewCanvasCssSize());
}

function isPixelWorkbenchVisible() {
    const wb = _pxEl('px-workbench');
    if (!wb) return false;
    return !wb.classList.contains('hidden');
}

function _pxMoveLogPanelToWorkbench(enabled) {
    const panel = document.getElementById('log-panel');
    if (!panel) return;

    if (enabled) {
        const slot = _pxEl('px-wb-log-slot');
        if (!slot) return;
        if (panel.parentNode !== slot) slot.appendChild(panel);
        return;
    }

    const host = document.getElementById('log-host');
    if (!host) return;
    if (panel.parentNode !== host) host.appendChild(panel);
}

function _pxSetMidView(mode) {
    const m = String(mode || '').trim().toLowerCase() === 'pixel' ? 'pixel' : 'canvas';
    _pxMidViewMode = m;
    const btnCanvas = _pxEl('mid-tab-canvas');
    const btnPixel = _pxEl('mid-tab-pixel');
    const wb = _pxEl('px-workbench');
    const backdrop = _pxEl('px-workbench-backdrop');

    if (document && document.body) {
        document.body.classList.toggle('mode-pixel', m === 'pixel');
        document.body.classList.toggle('mode-canvas', m !== 'pixel');
    }

    if (btnCanvas) btnCanvas.classList.toggle('active', m === 'canvas');
    if (btnPixel) btnPixel.classList.toggle('active', m === 'pixel');
    if (wb) wb.classList.toggle('hidden', m !== 'pixel');
    if (backdrop) backdrop.classList.toggle('hidden', m !== 'pixel');

    if (m !== 'pixel') {
        _pxMoveLogPanelToWorkbench(false);
        if (_pxEditStroke) {
            // 关闭面板时，尽量提交当前笔画，避免“松手没触发 pointerup”导致丢失
            Promise.resolve().then(() => _pxCommitPaintStroke());
        }
        _pxSchedulePersistPixelWorkbenchState('leave_pixel');
        _pxSetPixelEditEnabled(false);
        _pxHidePixelBrushIndicator();
        return;
    }

    // Pixel workbench is modal: avoid mixing with canvas paint/pick tools.
    if (typeof setPickMode === 'function') {
        setPickMode('off');
    }
    if (typeof isPaintBrushEnabled === 'function' && typeof setPaintMode === 'function') {
        if (isPaintBrushEnabled()) {
            setPaintMode('off');
        }
    }

    _pxMoveLogPanelToWorkbench(true);
    requestAnimationFrame(() => _pxFitPreviewCanvasCssSize());
}

function _pxSetupPixelWorkbenchUi() {
    if (_pxWorkbenchUiSetupDone) return;
    _pxWorkbenchUiSetupDone = true;

    const openBtn = _pxEl('btn-open-px-workbench');
    const closeBtn = _pxEl('px-wb-close');
    const midCanvas = _pxEl('mid-tab-canvas');
    const midPixel = _pxEl('mid-tab-pixel');
    const backdrop = _pxEl('px-workbench-backdrop');
    const tabImport = _pxEl('px-wb-tab-import');
    const tabEdit = _pxEl('px-wb-tab-edit');

    _pxSetupPreviewViewUi();

    if (openBtn) {
        openBtn.onclick = () => {
            _pxSetMidView('pixel');
            const tab = (_pxRefinedDataUrl && _pxRefinedW > 0 && _pxRefinedH > 0) ? 'edit' : 'import';
            _pxSetPixelWorkbenchTab(tab);
        };
    }
    if (closeBtn) closeBtn.onclick = () => _pxSetMidView('canvas');
    if (midCanvas) midCanvas.onclick = () => _pxSetMidView('canvas');
    if (midPixel) midPixel.onclick = () => {
        _pxSetMidView('pixel');
        const tab = (_pxRefinedDataUrl && _pxRefinedW > 0 && _pxRefinedH > 0) ? 'edit' : 'import';
        _pxSetPixelWorkbenchTab(tab);
    };
    if (backdrop) backdrop.onclick = () => _pxSetMidView('canvas');
    if (tabImport) tabImport.onclick = () => _pxSetPixelWorkbenchTab('import');
    if (tabEdit) tabEdit.onclick = () => _pxSetPixelWorkbenchTab('edit');

    // 预览 resize：跟随窗口变化
    window.addEventListener('resize', () => _pxFitPreviewCanvasCssSize());

    _pxSetPixelWorkbenchTab('import');
    _pxSetMidView('canvas');
}

function _pxComputeRefineSig(opts) {
    const o = opts || {};
    return JSON.stringify({
        sample_method: String(o.sampleMethod || ''),
        refine_intensity: Number(o.refineIntensity || 0),
        fix_square: !!o.fixSquare
    });
}

async function _pxEnsureRefined(opts, forceRefine = false) {
    if (!_pxInputDataUrl) {
        toastToUi('warn', '请先选择一张图片');
        logToUi('WARN', 'PerfectPixel：未选择图片');
        return null;
    }

    const sig = _pxComputeRefineSig(opts);
    const hasRefined = !!(_pxRefinedDataUrl && _pxRefinedW > 0 && _pxRefinedH > 0);
    if (hasRefined && !forceRefine) {
        _pxSetPixelWorkbenchTab('edit');
        _pxSetPixelEditEnabled(true);
        const asset = _pxGetSelectedAsset();
        if (asset) {
            asset.inputDataUrl = String(_pxInputDataUrl || asset.inputDataUrl || '').trim();
            asset.refinedDataUrl = String(_pxRefinedDataUrl || '').trim();
            asset.refinedW = Math.max(0, Math.round(Number(_pxRefinedW || 0)));
            asset.refinedH = Math.max(0, Math.round(Number(_pxRefinedH || 0)));
            asset.lastRefineSig = String(_pxLastRefineSig || sig || '').trim();
            _pxSetAssetStatus(asset, 'ready', '');
            _pxRenderAssetList();
        }
        return {
            ok: true,
            refined_w: _pxRefinedW,
            refined_h: _pxRefinedH,
            image_data_url: _pxRefinedDataUrl
        };
    }

    if (hasRefined && forceRefine && _pxLastRefineSig === sig) {
        _pxSetPixelWorkbenchTab('edit');
        _pxSetPixelEditEnabled(true);
        return {
            ok: true,
            refined_w: _pxRefinedW,
            refined_h: _pxRefinedH,
            image_data_url: _pxRefinedDataUrl
        };
    }

    logToUi('INFO', `PerfectPixel：开始标准像素化 sample=${opts.sampleMethod} refine=${opts.refineIntensity.toFixed(2)} fixSquare=${opts.fixSquare ? 'on' : 'off'}`);
    toastToUi('info', 'PerfectPixel：开始标准像素化…', 1400);

    const asset0 = _pxGetSelectedAsset();
    if (asset0) {
        asset0.lastRefineSig = String(sig || '').trim();
        _pxSetAssetStatus(asset0, 'refining', '');
        _pxRenderAssetList();
    }

    const obj = await _pxRequestPerfectPixelRefine({
        imageDataUrl: String(_pxInputDataUrl),
        sampleMethod: String(opts.sampleMethod),
        refineIntensity: Number(opts.refineIntensity),
        fixSquare: !!opts.fixSquare,
    });
    if (!obj || !obj.ok) {
        const err = obj && obj.error ? String(obj.error) : '标准像素化失败';
        toastToUi('error', `标准像素化失败：${err}`, 2600);
        logToUi('ERROR', `PerfectPixel：标准像素化失败：${err}`);
        if (obj && obj.detail) logToUi('ERROR', String(obj.detail));
        if (asset0) {
            _pxSetAssetStatus(asset0, 'error', err);
            _pxRenderAssetList();
        }
        return null;
    }

    _pxRefinedDataUrl = String(obj.image_data_url || '').trim();
    _pxRefinedW = Math.max(0, Math.round(Number(obj.refined_w || 0)));
    _pxRefinedH = Math.max(0, Math.round(Number(obj.refined_h || 0)));
    _pxLastRefineSig = sig;
    _pxResetMatrixAndPreviewCaches();

    await _pxRebuildQuantizedPreviewForCurrentOptions();
    _pxUpdateMeta();
    toastToUi('info', `标准像素化完成：${_pxRefinedW}×${_pxRefinedH}`);
    logToUi('INFO', `PerfectPixel：标准像素化完成 refined=${_pxRefinedW}x${_pxRefinedH}`);
    _pxSetPixelWorkbenchTab('edit');
    _pxSetPixelEditEnabled(true);

    const asset = _pxGetSelectedAsset();
    if (asset) {
        asset.inputDataUrl = String(_pxInputDataUrl || asset.inputDataUrl || '').trim();
        asset.refinedDataUrl = String(_pxRefinedDataUrl || '').trim();
        asset.refinedW = Math.max(0, Math.round(Number(_pxRefinedW || 0)));
        asset.refinedH = Math.max(0, Math.round(Number(_pxRefinedH || 0)));
        asset.lastRefineSig = String(sig || '').trim();
        asset.persistedMatrixSrc = '';
        asset.matrixDirty = true;
        _pxSetAssetStatus(asset, 'ready', '');
        _pxRenderAssetList();
    }
    _pxSchedulePersistPixelWorkbenchState('refine_done');
    return obj;
}

function _pxLoadImage(dataUrl) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('图片加载失败'));
        img.src = String(dataUrl || '');
    });
}

async function _pxBuildPaletteIndexMatrixFromRefinedDataUrl(refinedDataUrl) {
    const img = await _pxLoadImage(refinedDataUrl);
    const w = Math.max(0, Math.round(Number(img.naturalWidth || img.width || 0)));
    const h = Math.max(0, Math.round(Number(img.naturalHeight || img.height || 0)));
    if (w <= 0 || h <= 0) {
        throw new Error('refined image 尺寸非法');
    }

    const off = document.createElement('canvas');
    off.width = w;
    off.height = h;
    const ctx = off.getContext('2d', { willReadFrequently: true });
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, 0, 0, w, h);
    const pixels = ctx.getImageData(0, 0, w, h).data;

    const palette = Array.isArray(RECT_COLORS) ? RECT_COLORS.slice() : [];
    const transparentIdx = palette.length;
    const idxArr = new Uint16Array(w * h);
    const counts = new Array(palette.length).fill(0);
    let transparentCount = 0;

    for (let i = 0; i < w * h; i++) {
        const a = pixels[i * 4 + 3];
        if (a === 0) {
            idxArr[i] = transparentIdx;
            transparentCount += 1;
            continue;
        }
        const r = pixels[i * 4];
        const g = pixels[i * 4 + 1];
        const b = pixels[i * 4 + 2];
        const idx = _pxNearestRectPaletteIdx(r, g, b);
        idxArr[i] = idx;
        if (idx >= 0 && idx < counts.length) {
            counts[idx] += 1;
        }
    }

    return { w, h, palette, transparentIdx, idxArr, counts, transparentCount };
}

function _pxPickMostFrequentPaletteIdx(counts) {
    const arr = Array.isArray(counts) ? counts : [];
    let bestIdx = -1;
    let bestCount = -1;
    for (let i = 0; i < arr.length; i++) {
        const c = Number(arr[i] || 0);
        if (c > bestCount) {
            bestCount = c;
            bestIdx = i;
        }
    }
    return bestIdx;
}

function _pxPickBgIdxFromBorder(matrixInfo) {
    if (!matrixInfo) return -1;
    const w = Number(matrixInfo.w || 0);
    const h = Number(matrixInfo.h || 0);
    const idxArr = matrixInfo.idxArr;
    const transparentIdx = Number(matrixInfo.transparentIdx);
    if (w <= 0 || h <= 0 || !(idxArr instanceof Uint16Array)) {
        return -1;
    }

    const freq = new Map();
    function addIdx(idx) {
        const v = Number(idx);
        if (v === transparentIdx) return;
        freq.set(v, Number(freq.get(v) || 0) + 1);
    }

    // top/bottom rows
    for (let x = 0; x < w; x++) {
        addIdx(idxArr[x]);
        addIdx(idxArr[(h - 1) * w + x]);
    }
    // left/right cols
    for (let y = 0; y < h; y++) {
        addIdx(idxArr[y * w]);
        addIdx(idxArr[y * w + (w - 1)]);
    }

    let bestIdx = -1;
    let bestCount = -1;
    for (const [idx, count] of freq.entries()) {
        if (count > bestCount) {
            bestCount = count;
            bestIdx = Number(idx);
        }
    }
    if (bestIdx >= 0) return bestIdx;

    // fallback: global most frequent
    return _pxPickMostFrequentPaletteIdx(matrixInfo.counts);
}

function _pxBuildIgnoreMaskForBackground(matrixInfo, bgIdx) {
    if (!matrixInfo) return null;
    const w = Number(matrixInfo.w || 0);
    const h = Number(matrixInfo.h || 0);
    const idxArr = matrixInfo.idxArr;
    const transparentIdx = Number(matrixInfo.transparentIdx);
    if (w <= 0 || h <= 0 || !(idxArr instanceof Uint16Array)) {
        return null;
    }
    const bg = Number(bgIdx);
    if (!(bg >= 0) || bg === transparentIdx) {
        return null;
    }

    const mask = new Uint8Array(w * h);
    const queue = new Int32Array(w * h);
    let head = 0;
    let tail = 0;

    function tryPush(p) {
        if (mask[p] === 1) return;
        if (Number(idxArr[p]) !== bg) return;
        mask[p] = 1;
        queue[tail] = p;
        tail += 1;
    }

    // seed: border pixels
    for (let x = 0; x < w; x++) {
        tryPush(x);
        tryPush((h - 1) * w + x);
    }
    for (let y = 0; y < h; y++) {
        tryPush(y * w);
        tryPush(y * w + (w - 1));
    }

    // flood fill (4-neighborhood)
    while (head < tail) {
        const p = queue[head];
        head += 1;
        const x = p % w;
        const y = (p / w) | 0;
        if (x > 0) tryPush(p - 1);
        if (x < w - 1) tryPush(p + 1);
        if (y > 0) tryPush(p - w);
        if (y < h - 1) tryPush(p + w);
    }

    return mask;
}

function _pxGetIgnoreMaskForOptions(matrixInfo, opts) {
    const ignoreBg = !!(opts && opts.ignoreBg);
    if (!ignoreBg) {
        return { bgIdx: -1, ignoreMask: null };
    }
    // 重要：背景色推断应基于“原始矩阵”，不能被用户在背景区涂色影响
    // 否则 bgIdx 可能翻转成“当前涂的颜色”，导致刚涂的像素在预览里又被当背景抹掉（表现为“涂成空白”）
    let bgIdx = -1;
    const w = Number(matrixInfo.w || 0);
    const h = Number(matrixInfo.h || 0);
    const idxArr = matrixInfo.idxArr;
    if (_pxOriginalIdxArr instanceof Uint16Array && (idxArr instanceof Uint16Array) && _pxOriginalIdxArr.length === idxArr.length && w > 0 && h > 0) {
        const info0 = {
            w: w,
            h: h,
            idxArr: _pxOriginalIdxArr,
            transparentIdx: Number(matrixInfo.transparentIdx),
            counts: Array.isArray(_pxOriginalCounts) ? _pxOriginalCounts : null,
        };
        bgIdx = _pxPickBgIdxFromBorder(info0);
    }
    if (!(bgIdx >= 0)) {
        bgIdx = _pxPickBgIdxFromBorder(matrixInfo);
    }
    if (!(bgIdx >= 0)) {
        return { bgIdx: -1, ignoreMask: null };
    }
    const key = `${String(_pxRefinedDataUrl || '').trim()}|bgIdx=${bgIdx}`;
    if (_pxIgnoreMask && _pxIgnoreMaskKey === key) {
        return { bgIdx: Number(_pxIgnoreMaskBgIdx), ignoreMask: _pxIgnoreMask };
    }
    const ignoreMask = _pxBuildIgnoreMaskForBackground(matrixInfo, bgIdx);
    _pxIgnoreMaskKey = key;
    _pxIgnoreMask = ignoreMask;
    _pxIgnoreMaskBgIdx = Number(bgIdx);
    return { bgIdx: Number(bgIdx), ignoreMask };
}

async function _pxEnsureMatrixInfo() {
    const key = String(_pxRefinedDataUrl || '').trim();
    if (!key) return null;
    if (_pxMatrixCache && _pxMatrixCacheKey === key) {
        if (typeof _pxEnsureOriginalMatrixSnapshot === 'function') {
            _pxEnsureOriginalMatrixSnapshot(_pxMatrixCache);
        }
        if (typeof _pxEnsureKeepMask === 'function') {
            _pxEnsureKeepMask(_pxMatrixCache);
        }
        return _pxMatrixCache;
    }
    const info = await _pxBuildPaletteIndexMatrixFromRefinedDataUrl(key);
    _pxMatrixCacheKey = key;
    _pxMatrixCache = info;
    if (typeof _pxEnsureOriginalMatrixSnapshot === 'function') {
        _pxEnsureOriginalMatrixSnapshot(info);
    }
    if (typeof _pxEnsureKeepMask === 'function') {
        _pxEnsureKeepMask(info);
    }
    return info;
}

async function _pxRebuildQuantizedPreviewForCurrentOptions() {
    if (!_pxRefinedDataUrl) {
        _pxQuantizedBgColor = '';
        _pxIgnoreMaskKey = '';
        _pxIgnoreMask = null;
        _pxIgnoreMaskBgIdx = -1;
        _pxHidePreviewCanvas();
        return;
    }
    const opts = _pxGetOptionsFromUi();
    const matrixInfo = await _pxEnsureMatrixInfo();
    if (!matrixInfo) return;

    const { bgIdx, ignoreMask } = _pxGetIgnoreMaskForOptions(matrixInfo, opts);
    _pxQuantizedBgColor = (opts.ignoreBg && bgIdx >= 0 && bgIdx < (matrixInfo.palette || []).length)
        ? String((matrixInfo.palette || [])[bgIdx] || '')
        : '';
    _pxRenderPreviewFromMatrixInfo(matrixInfo, ignoreMask);
}

function _pxMergePaletteIndexMatrixToRects(payload) {
    const w = Number(payload.w || 0);
    const h = Number(payload.h || 0);
    const idxArr = payload.idxArr;
    const transparentIdx = Number(payload.transparentIdx);
    const bgIdx = payload.bgIdx;
    const ignoreBg = payload.ignoreBg === true;
    const ignoreMask = payload.ignoreMask;
    const keepMask = payload.keepMask;

    if (w <= 0 || h <= 0 || !(idxArr instanceof Uint16Array)) {
        throw new Error('palette index matrix 非法');
    }

    const rects = [];
    let active = new Map();

    function _ignoreAt(p, idx) {
        if (idx === transparentIdx) return true;
        if (ignoreMask && ignoreMask[p] === 1 && !(keepMask && keepMask[p] === 1)) return true;
        // backward compat: if ignoreMask not provided, fall back to ignoring all bgIdx
        if (!ignoreMask && ignoreBg && idx === bgIdx && !(keepMask && keepMask[p] === 1)) return true;
        return false;
    }

    for (let y = 0; y < h; y++) {
        const newActive = new Map();
        let x = 0;
        while (x < w) {
            const p0 = y * w + x;
            const idx = idxArr[p0];
            if (_ignoreAt(p0, idx)) {
                x += 1;
                continue;
            }
            const x0 = x;
            while (x < w) {
                const p = y * w + x;
                const idx2 = idxArr[p];
                if (_ignoreAt(p, idx2)) break;
                if (idx2 !== idx) break;
                x += 1;
            }
            const x1 = x;
            const key = `${x0},${x1},${idx}`;
            const prevIndex = active.get(key);
            if (prevIndex !== undefined) {
                rects[prevIndex].y1 = y + 1;
                newActive.set(key, prevIndex);
            } else {
                rects.push({ x0, x1, y0: y, y1: y + 1, idx: idx });
                newActive.set(key, rects.length - 1);
            }
        }
        active = newActive;
    }

    return rects;
}

function _pxBuildPaletteIndexMatrixToPixelRects(payload) {
    const w = Number(payload.w || 0);
    const h = Number(payload.h || 0);
    const idxArr = payload.idxArr;
    const transparentIdx = Number(payload.transparentIdx);
    const bgIdx = payload.bgIdx;
    const ignoreBg = payload.ignoreBg === true;
    const ignoreMask = payload.ignoreMask;
    const keepMask = payload.keepMask;

    if (w <= 0 || h <= 0 || !(idxArr instanceof Uint16Array)) {
        throw new Error('palette index matrix 非法');
    }

    const rects = [];
    function _ignoreAt(p, idx) {
        if (idx === transparentIdx) return true;
        if (ignoreMask && ignoreMask[p] === 1 && !(keepMask && keepMask[p] === 1)) return true;
        // backward compat: if ignoreMask not provided, fall back to ignoring all bgIdx
        if (!ignoreMask && ignoreBg && idx === bgIdx && !(keepMask && keepMask[p] === 1)) return true;
        return false;
    }

    for (let y = 0; y < h; y++) {
        const row = y * w;
        for (let x = 0; x < w; x++) {
            const p = row + x;
            const idx = idxArr[p];
            if (_ignoreAt(p, idx)) continue;
            rects.push({ x0: x, x1: x + 1, y0: y, y1: y + 1, idx: idx });
        }
    }
    return rects;
}

function _pxBuildCanvasPayloadFromRects(rects, matrixInfo, opts) {
    const canvasW = canvas.getWidth();
    const canvasH = canvas.getHeight();
    const genMode = String(opts && opts.generateMode ? opts.generateMode : 'merge_rects').trim() || 'merge_rects';
    const cell = Math.max(1, Math.round(Number(opts.cellSizePx || 12)));
    const w = Number(matrixInfo.w || 0);
    const h = Number(matrixInfo.h || 0);
    const palette = matrixInfo.palette || [];

    const mosaicW = w * cell;
    const mosaicH = h * cell;
    const left0 = Math.round(canvasW / 2 - mosaicW / 2);
    const top0 = Math.round(canvasH / 2 - mosaicH / 2);

    const objects = [];
    for (let i = 0; i < rects.length; i++) {
        const r = rects[i];
        const color = String(palette[Number(r.idx)] || '').trim();
        if (!color) continue;

        const left = left0 + Number(r.x0) * cell;
        const top = top0 + Number(r.y0) * cell;
        const width = (Number(r.x1) - Number(r.x0)) * cell;
        const height = (Number(r.y1) - Number(r.y0)) * cell;

        const fill = normalizeColor(color);
        const isBottomCenterPivot = BOTTOM_CENTER_PIVOT_COLORS.has(fill);
        const pivot = isBottomCenterPivot ? 'bottom_center' : 'center';

        const centerPx = { x: Number(left) + Number(width) / 2, y: Number(top) + Number(height) / 2 };
        const anchorPx = isBottomCenterPivot ? { x: centerPx.x, y: Number(top) + Number(height) } : centerPx;
        const centered = _pxPointToCentered(centerPx);
        const anchorCentered = _pxPointToCentered(anchorPx);

        objects.push({
            type: 'rect',
            label: `px_${i + 1}`,
            id: getNewObjectId(),
            color: fill,
            src: '',
            left: Math.round(left),
            top: Math.round(top),
            width: Math.round(width),
            height: Math.round(height),
            angle: 0,
            anchor: { x: Math.round(anchorPx.x), y: Math.round(anchorPx.y) },
            centered: { x: centered.x, y: centered.y },
            anchor_centered: { x: anchorCentered.x, y: anchorCentered.y },
            pivot: pivot,
            opacity: 1.0,
            isReference: false,
            isLocked: false,
            group: null
        });
    }

    return {
        meta: {
            timestamp: new Date().toISOString(),
            tool: 'qx-shape-editor',
            mode: 'pixel_art_import',
            target_rel_path: '',
            coord_origin: 'center',
            coord_y_axis: 'up',
            pixel_art: {
                refined_w: Number(w),
                refined_h: Number(h),
                cell_size_px: Number(cell),
                ignore_bg: !!opts.ignoreBg,
                generate_mode: String(genMode),
            }
        },
        canvas: { width: canvasW, height: canvasH },
        objects: objects
    };
}

async function _pxSaveAsNewEntity(canvasPayload, name) {
    const resp = await fetch('/api/shape_editor/entities/save_as', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ name: String(name || '').trim(), canvas_payload: canvasPayload })
    });
    const text = await resp.text();
    if (!resp.ok) {
        toastToUi('error', `生成实体失败（HTTP ${resp.status}）`, 2600);
        logToUi('ERROR', `生成实体失败（HTTP ${resp.status}）`);
        logToUi('ERROR', text);
        return null;
    }
    return JSON.parse(text);
}

async function _pxExportGiaEntity(canvasPayload) {
    const body = JSON.stringify(canvasPayload);
    logToUi('INFO', `导出：实体 请求发送 bytes=${body.length}`);
    const resp = await fetch('/api/shape_editor/export_gia_entity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body
    });
    const text = await resp.text();
    if (!resp.ok) {
        toastToUi('error', `导出为实体失败（HTTP ${resp.status}）`, 2600);
        logToUi('ERROR', `导出为实体失败（HTTP ${resp.status}）`);
        logToUi('ERROR', text);
        return null;
    }
    return JSON.parse(text);
}

async function _pxGenerateEntityFromCurrentSessionCore() {
    if (_pxEditStroke) {
        await _pxCommitPaintStroke();
    }
    const opts = _pxGetOptionsFromUi();
    const refined = await _pxEnsureRefined(opts);
    if (!refined) return null;

    logToUi('INFO', '像素矩阵：开始吸附到矩形支持色并合并矩形…');
    toastToUi('info', '开始生成矩形…', 1400);
    await _pxYieldToUi();

    const matrixInfo = await _pxEnsureMatrixInfo();
    if (!matrixInfo) return null;
    const { bgIdx, ignoreMask } = _pxGetIgnoreMaskForOptions(matrixInfo, opts);
    const keepMask = (_pxKeepMask instanceof Uint8Array && _pxKeepMask.length === (matrixInfo.idxArr || []).length) ? _pxKeepMask : null;
    await _pxYieldToUi();

    const genMode = String(opts.generateMode || 'merge_rects').trim() || 'merge_rects';
    const rects = genMode === 'pixel_points' ? _pxBuildPaletteIndexMatrixToPixelRects({
        w: matrixInfo.w,
        h: matrixInfo.h,
        idxArr: matrixInfo.idxArr,
        transparentIdx: matrixInfo.transparentIdx,
        bgIdx: bgIdx,
        ignoreBg: !!opts.ignoreBg,
        ignoreMask: ignoreMask,
        keepMask: keepMask
    }) : _pxMergePaletteIndexMatrixToRects({
        w: matrixInfo.w,
        h: matrixInfo.h,
        idxArr: matrixInfo.idxArr,
        transparentIdx: matrixInfo.transparentIdx,
        bgIdx: bgIdx,
        ignoreBg: !!opts.ignoreBg,
        ignoreMask: ignoreMask,
        keepMask: keepMask
    });

    const bgColor = (bgIdx >= 0 && bgIdx < matrixInfo.palette.length) ? String(matrixInfo.palette[bgIdx]) : '';
    const cellEff = Number(opts.cellSizePx || 1);
    logToUi('INFO', `像素矩阵：refined=${matrixInfo.w}x${matrixInfo.h} rects=${rects.length} mode=${genMode} cell_eff=${cellEff} ignoreBg=${opts.ignoreBg ? 'on' : 'off'} bg=${bgColor || '-'}`);
    if (rects.length > (genMode === 'pixel_points' ? 16000 : 6000)) {
        const hint = genMode === 'pixel_points' ? '建议降低分辨率（像素点模式会≈像素数）' : '建议降低分辨率或增大像素块';
        toastToUi('warn', `矩形数量较多：${rects.length}（${hint}）`, 2600);
    }
    await _pxYieldToUi();

    const canvasPayload = _pxBuildCanvasPayloadFromRects(rects, matrixInfo, opts);
    const entityNameStem = _pxFileStem(_pxInputFileName) || '像素实体';
    const entityName = `像素画 ${entityNameStem}`.trim();

    logToUi('INFO', `生成实体：开始另存为新实体 name=${entityName}`);
    toastToUi('info', '生成实体：保存到项目…', 1600);
    const saved = await _pxSaveAsNewEntity(canvasPayload, entityName);
    if (!saved || !saved.ok) return null;

    const relPath = String(saved.rel_path || '').trim();
    if (!relPath) {
        toastToUi('error', '生成实体失败：后端未返回 rel_path', 2600);
        logToUi('ERROR', '生成实体失败：后端未返回 rel_path');
        return null;
    }

    return {
        ok: true,
        rel_path: relPath,
        entity_name: entityName,
        rects_count: rects.length,
    };
}

async function _pxRunGenerateEntity() {
    const result = await _pxGenerateEntityFromCurrentSessionCore();
    if (!result || !result.ok) return;

    const relPath = String(result.rel_path || '').trim();
    logToUi('INFO', `已生成实体（已保存到项目）：${relPath}`);

    await refreshProjectPlacements();
    await loadProjectPlacement(relPath);
    _pxSetMidView('canvas');
    toastToUi('info', '已生成实体：已切回画布（未自动导出）', 2000);
}

async function _pxRunGenerateAllEntities() {
    const items = Array.isArray(_pxAssets) ? _pxAssets : [];
    if (items.length <= 0) {
        toastToUi('warn', '没有可生成的素材');
        return;
    }

    // 不允许“处理中”就生成：用户期望是“全部完成后统一生成”
    const hasWorking = items.some(it => it && (it.status === 'pending' || it.status === 'reading' || it.status === 'refining'));
    if (hasWorking) {
        toastToUi('warn', '仍有素材在处理中，请等待标准像素化完成后再生成全部实体', 2600);
        return;
    }

    if (_pxEditStroke) {
        await _pxCommitPaintStroke();
    }
    const cur = _pxGetSelectedAsset();
    if (cur) {
        _pxCaptureCurrentSessionIntoAsset(cur);
    }

    logToUi('INFO', `批量生成实体：开始 count=${items.length}`);
    toastToUi('info', `批量生成实体：开始（${items.length} 个）`, 1800);
    await _pxYieldToUi();

    const generated = [];
    for (let i = 0; i < items.length; i++) {
        const a = items[i];
        if (!a || a.status !== 'ready') continue;

        _pxApplyAssetToCurrentSession(a);
        _pxSelectedAssetId = String(a.id || '');
        _pxUpdateMeta();
        _pxRenderAssetList();

        logToUi('INFO', `批量生成实体：${a.fileName || '(unnamed)'} (${i + 1}/${items.length})`);
        await _pxYieldToUi();

        const result = await _pxGenerateEntityFromCurrentSessionCore();
        if (result && result.ok && result.rel_path) {
            a.generatedRelPath = String(result.rel_path || '').trim();
            generated.push(a.generatedRelPath);
        }

        _pxCaptureCurrentSessionIntoAsset(a);
        await _pxYieldToUi();
    }

    // restore previous selection (best-effort)
    if (cur && cur.id) {
        _pxSelectedAssetId = String(cur.id || '');
        _pxApplyAssetToCurrentSession(cur);
    }
    _pxRenderAssetList();
    _pxUpdateMeta();

    if (generated.length <= 0) {
        toastToUi('warn', '批量生成：没有生成任何实体（请看日志）', 2600);
        return;
    }

    await refreshProjectPlacements();
    const last = generated[generated.length - 1];
    if (last) {
        await loadProjectPlacement(last);
    }
    _pxSetMidView('canvas');
    toastToUi('info', `批量生成完成：${generated.length} 个（已切回画布）`, 2400);
    logToUi('INFO', `批量生成实体：完成 generated=${generated.length}`);
}

function setupPixelArtImportPanel() {
    const upload = _pxEl('px-upload');
    if (upload) {
        upload.addEventListener('change', (e) => {
            const files = e && e.target && e.target.files ? e.target.files : null;
            if (!files || files.length <= 0) return;
            const before = Array.isArray(_pxAssets) ? _pxAssets.length : 0;
            _pxAddFilesAsAssets(files);
            const items = Array.isArray(_pxAssets) ? _pxAssets : [];
            const last = items.length > before ? items[items.length - 1] : null;
            if (last && last.id) {
                Promise.resolve().then(() => _pxSelectAssetById(last.id));
            }
            upload.value = '';
        });
    }

    const uploadMulti = _pxEl('px-upload-multi');
    if (uploadMulti) {
        uploadMulti.addEventListener('change', (e) => {
            const files = e && e.target && e.target.files ? e.target.files : null;
            if (!files || files.length <= 0) return;
            _pxAddFilesAsAssets(files);
            uploadMulti.value = '';
        });
    }

    const uploadFolder = _pxEl('px-upload-folder');
    if (uploadFolder) {
        uploadFolder.addEventListener('change', (e) => {
            const files = e && e.target && e.target.files ? e.target.files : null;
            if (!files || files.length <= 0) return;
            _pxAddFilesAsAssets(files);
            uploadFolder.value = '';
        });
    }

    const clearAssetsBtn = _pxEl('btn-px-clear-assets');
    if (clearAssetsBtn) clearAssetsBtn.onclick = () => _pxClearAllAssets();

    const genAllBtn = _pxEl('btn-px-generate-all');
    if (genAllBtn) genAllBtn.onclick = () => Promise.resolve().then(_pxRunGenerateAllEntities);

    const refineBtn = _pxEl('btn-px-refine');
    if (refineBtn) {
        refineBtn.onclick = () => {
            const opts = _pxGetOptionsFromUi();
            return _pxEnsureRefined(opts, true);
        };
    }

    const genBtn = _pxEl('btn-px-generate-entity');
    if (genBtn) {
        genBtn.onclick = () => {
            logToUi('INFO', '像素图：开始生成实体');
            return Promise.resolve().then(_pxRunGenerateEntity);
        };
    }
    const genBtnEdit = _pxEl('btn-px-generate-entity-edit');
    if (genBtnEdit) {
        genBtnEdit.onclick = () => {
            logToUi('INFO', '像素图：开始生成实体');
            return Promise.resolve().then(_pxRunGenerateEntity);
        };
    }

    const cellEl = _pxEl('px-cell-size');
    const refineEl = _pxEl('px-refine-intensity');
    const sampleEl = _pxEl('px-sample-method');
    const fixEl = _pxEl('px-fix-square');
    const ignoreEl = _pxEl('px-ignore-bg');
    const genModeEl = _pxEl('px-generate-mode');
    [cellEl, refineEl, sampleEl, fixEl, ignoreEl, genModeEl].forEach(el => {
        if (!el) return;
        el.addEventListener('change', () => {
            if (el === ignoreEl) {
                Promise.resolve()
                    .then(_pxRebuildQuantizedPreviewForCurrentOptions)
                    .then(() => _pxUpdateMeta());
                return;
            }
            _pxUpdateMeta();
        });
        el.addEventListener('input', () => {
            if (el === ignoreEl) {
                Promise.resolve()
                    .then(_pxRebuildQuantizedPreviewForCurrentOptions)
                    .then(() => _pxUpdateMeta());
                return;
            }
            _pxUpdateMeta();
        });
    });

    _pxSetupPixelEditPanel();
    _pxSetupPixelWorkbenchUi();
    _pxUpdateMeta();
    _pxRenderAssetList();
    Promise.resolve().then(_pxBootRestorePixelWorkbenchStateFromProject);
}

