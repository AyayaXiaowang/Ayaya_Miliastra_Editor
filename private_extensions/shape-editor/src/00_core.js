// 配置常量
const RECT_COLORS = [
    '#E0D6C8', '#FBAF5C', '#BAB296', '#C47F5C', 
    '#AF5254', '#9D482F', '#3E7B5C', '#464749', '#765F51'
];

// 注意：以 `ugc_file_tools/out/gia_entities_画布功能组.json` 为基准同步
const CIRCLE_COLORS = [
    '#F3D199', '#DBA4A2', '#E9D7A5', '#EEECE7'
];

const ALL_COLORS = Array.from(new Set([...RECT_COLORS, ...CIRCLE_COLORS]));

const DEFAULT_SIZE = 100; // 默认 1:1 大小

// 部分形状在真源里是“底部中心”为 pivot（缩放/旋转绕底边中心）
// 以用户提供的规则为准：#3E7B5C #C47F5C #BAB296 #FBAF5C #AF5254
const BOTTOM_CENTER_PIVOT_COLORS = new Set([
    '#3E7B5C', '#C47F5C', '#BAB296', '#FBAF5C', '#AF5254'
]);

// 初始化 Fabric
const canvas = new fabric.Canvas('c', {
    preserveObjectStacking: true, // 选中时保持层级，不自动置顶
    backgroundColor: 'transparent'
});
canvas.fireMiddleClick = true;
canvas.uniformScaling = false;
canvas.uniScaleKey = 'shiftKey';

// 自定义属性，导出时包含
fabric.Object.prototype.toObject = (function (toObject) {
    return function (propertiesToInclude) {
        return toObject.call(this, ['id', 'label'].concat(propertiesToInclude));
    };
})(fabric.Object.prototype.toObject);

fabric.Object.prototype.lockSkewingX = true;
fabric.Object.prototype.lockSkewingY = true;
fabric.Object.prototype.cornerSize = 12;
fabric.Object.prototype.touchCornerSize = 20;
fabric.Object.prototype.padding = 6;

// 状态管理
let activeObject = null;
let clipboard = null; // 剪贴板
let pickMode = 'off';
let objectCounter = 0;
let isPanning = false;
let lastPosX = 0;
let lastPosY = 0;
let _lastRectFill = RECT_COLORS[0];

// 涂抹工具（Brush）：改色（仅矩形）
let paintMode = 'off'; // 'off' | 'brush'
let _paintBrushColor = RECT_COLORS[0];
let _paintBrushSizePx = 16; // 屏幕像素半径；会按 zoom 折算到画布坐标

// 图层逐显（延时摄影）
const LAYER_TIMELAPSE_STEP_MS = 10;
let _isLayerTimelapsePlaying = false;

// ---- Performance: batch operations guard ----
// 在批量添加/移除对象时（如加载实体、像素图导入），抑制昂贵的级联操作
// （renderLayerList / saveHistory / saveToLocal），结束后由调用方统一刷新。
let _batchDepth = 0;

function beginBatch() {
    _batchDepth++;
    if (_batchDepth === 1) {
        canvas.renderOnAddRemove = false;
    }
}

function endBatch() {
    if (_batchDepth <= 0) return;
    _batchDepth--;
    if (_batchDepth === 0) {
        canvas.renderOnAddRemove = true;
    }
}

function isBatching() {
    return _batchDepth > 0;
}

// ---- Performance: debounced layer list rendering ----
// 将连续的 renderLayerList 请求合并到同一动画帧，避免 object:added 事件
// 在非批量场景下（如粘贴多个对象）导致的密集 DOM 重建。
let _renderLayerListRafId = 0;

function scheduleRenderLayerList() {
    if (isBatching()) return;
    if (_renderLayerListRafId) return;
    _renderLayerListRafId = requestAnimationFrame(() => {
        _renderLayerListRafId = 0;
        renderLayerList();
    });
}

function isPaintBrushEnabled() {
    return paintMode === 'brush';
}

function getPaintBrushColor() {
    return String(_paintBrushColor || '').trim();
}

function getPaintBrushSizePx() {
    return Math.max(1, Math.round(Number(_paintBrushSizePx || 1)));
}

function getPaintBrushRadiusCanvasPx() {
    const zoom = Math.max(0.0001, Number(canvas.getZoom ? canvas.getZoom() : 1) || 1);
    return getPaintBrushSizePx() / zoom;
}

function _sleepMs(ms) {
    const waitMs = Number(ms);
    const safeMs = Number.isFinite(waitMs) && waitMs >= 0 ? waitMs : 0;
    return new Promise((resolve) => {
        window.setTimeout(resolve, safeMs);
    });
}

function _setLayerTimelapseButtonState(isRunning, progress = 0, total = 0) {
    const btn = document.getElementById('btn-layer-timelapse');
    if (!btn) return;
    const running = !!isRunning;
    btn.disabled = running;
    if (!running) {
        btn.textContent = '图层逐显';
        return;
    }
    const p = Math.max(0, Math.round(Number(progress || 0)));
    const t = Math.max(0, Math.round(Number(total || 0)));
    if (t > 0) {
        btn.textContent = `播放中 ${Math.min(p, t)}/${t}`;
    } else {
        btn.textContent = '播放中…';
    }
}

function _setFabricObjectVisible(obj, visible) {
    if (!obj) return;
    const v = visible !== false;
    if (typeof obj.set === 'function') {
        obj.set('visible', v);
    } else {
        obj.visible = v;
    }
}

async function playLayerTimelapseReveal() {
    if (_isLayerTimelapsePlaying) return;

    // 像素工作台是 modal，播放图层逐显前强制切回画布视图。
    if (typeof isPixelWorkbenchVisible === 'function' && isPixelWorkbenchVisible() && typeof _pxSetMidView === 'function') {
        _pxSetMidView('canvas');
    }

    const allObjects = (canvas && typeof canvas.getObjects === 'function') ? canvas.getObjects().slice() : [];
    const revealEntries = [];
    for (let i = 0; i < allObjects.length; i++) {
        const obj = allObjects[i];
        if (!obj) continue;
        if (obj.visible === false) continue;
        revealEntries.push({ obj: obj });
    }

    if (revealEntries.length <= 0) {
        toastToUi('warn', '当前画布没有可播放的可见图层', 1800);
        logToUi('WARN', '图层逐显：没有可播放的可见图层');
        return;
    }

    _isLayerTimelapsePlaying = true;
    _setLayerTimelapseButtonState(true, 0, revealEntries.length);

    const previousSelection = (canvas && typeof canvas.getActiveObjects === 'function')
        ? canvas.getActiveObjects().slice()
        : [];

    try {
        if (canvas && typeof canvas.discardActiveObject === 'function') {
            canvas.discardActiveObject();
        }

        for (let i = 0; i < revealEntries.length; i++) {
            _setFabricObjectVisible(revealEntries[i].obj, false);
        }
        if (canvas && typeof canvas.requestRenderAll === 'function') {
            canvas.requestRenderAll();
        }

        for (let i = 0; i < revealEntries.length; i++) {
            await _sleepMs(LAYER_TIMELAPSE_STEP_MS);
            _setFabricObjectVisible(revealEntries[i].obj, true);
            _setLayerTimelapseButtonState(true, i + 1, revealEntries.length);
            if (canvas && typeof canvas.requestRenderAll === 'function') {
                canvas.requestRenderAll();
            }
        }

        if (previousSelection.length > 0 && typeof _setCanvasSelectionObjects === 'function') {
            _setCanvasSelectionObjects(previousSelection, { toastOnLockedMulti: false });
        }

        toastToUi('info', `图层逐显完成（${revealEntries.length} 层）`, 1600);
        logToUi('INFO', `图层逐显完成：layers=${revealEntries.length}, step_ms=${LAYER_TIMELAPSE_STEP_MS}`);
    } catch (err) {
        for (let i = 0; i < revealEntries.length; i++) {
            _setFabricObjectVisible(revealEntries[i].obj, true);
        }
        if (canvas && typeof canvas.requestRenderAll === 'function') {
            canvas.requestRenderAll();
        }
        const msg = err && err.message ? String(err.message) : String(err || 'unknown error');
        toastToUi('error', `图层逐显失败：${msg}`, 2400);
        logToUi('ERROR', `图层逐显失败：${msg}`);
    } finally {
        _isLayerTimelapsePlaying = false;
        _setLayerTimelapseButtonState(false);
    }
}

function setPaintMode(mode) {
    const next = String(mode || '').trim().toLowerCase() === 'brush' ? 'brush' : 'off';
    paintMode = next;
    if (paintMode !== 'brush' && typeof _hidePaintBrushCursor === 'function') {
        _hidePaintBrushCursor();
    }
    // 避免与“参考图取色创建”冲突：开启涂抹时强制关闭 pickMode
    if (paintMode === 'brush' && typeof setPickMode === 'function') {
        setPickMode('off');
    }
    syncPaintToolUi();
    if (typeof toastToUi === 'function') {
        toastToUi('info', paintMode === 'brush' ? '涂抹：已开启' : '涂抹：已关闭', 1100);
    }
    if (typeof logToUi === 'function') {
        logToUi('INFO', paintMode === 'brush' ? '涂抹工具：开启' : '涂抹工具：关闭');
    }
}

function setPaintBrushColor(color) {
    const c0 = normalizeColor(String(color || '').trim());
    let c = c0;
    if (!RECT_COLORS.includes(c)) {
        const rgb = hexToRgb(c0);
        c = getNearestRectPaletteColor(rgb.r, rgb.g, rgb.b);
    }
    _paintBrushColor = c;
    if (RECT_COLORS.includes(c)) {
        _lastRectFill = c;
    }
    syncPaintToolUi();
}

function setPaintBrushSizePx(sizePx) {
    const n0 = _coerceFiniteNumber(sizePx, getPaintBrushSizePx());
    const n = Math.max(1, Math.min(120, Math.round(Number(n0))));
    _paintBrushSizePx = n;
    syncPaintToolUi();
}

function syncPaintToolUi() {
    const onBtn = document.getElementById('paint-on');
    const offBtn = document.getElementById('paint-off');
    if (onBtn) onBtn.classList.toggle('active', paintMode === 'brush');
    if (offBtn) offBtn.classList.toggle('active', paintMode !== 'brush');

    const sizeEl = document.getElementById('paint-size');
    const sizeNumEl = document.getElementById('paint-size-number');
    const size = getPaintBrushSizePx();
    if (sizeEl && Number(sizeEl.value) !== size) sizeEl.value = String(size);
    if (sizeNumEl && Number(sizeNumEl.value) !== size) sizeNumEl.value = String(size);

    const pal = document.getElementById('paint-palette');
    if (pal) {
        const target = normalizeColor(getPaintBrushColor());
        const buttons = pal.querySelectorAll('[data-paint-color]');
        buttons.forEach((btn) => {
            const v = normalizeColor(String(btn.getAttribute('data-paint-color') || ''));
            btn.classList.toggle('active', v === target);
        });
    }
}

// PS 式交互：拖拽创建矩形 / 外圈拖拽旋转
let _dragCreateRectState = null;
let _psRotateState = null;

// 坐标系约定（导出/属性面板统一口径）：
// - 原点在画布中心
// - X 向右为正
// - Y 向上为正（与画布像素 Y 向下相反）
function _getCanvasCenterPx() {
    return { x: canvas.getWidth() / 2, y: canvas.getHeight() / 2 };
}

function _pxPointToCentered(pointPx) {
    const p = pointPx || { x: 0, y: 0 };
    const c = _getCanvasCenterPx();
    return {
        x: Math.round(Number(p.x) - c.x),
        y: Math.round(-(Number(p.y) - c.y))
    };
}

function _centeredToPxPoint(centered) {
    const v = centered || { x: 0, y: 0 };
    const c = _getCanvasCenterPx();
    return {
        x: Number(v.x) + c.x,
        y: c.y - Number(v.y)
    };
}

// ALT+拖拽复制：用于合成一次 mousedown，避免递归
let _altDuplicateDispatching = false;

// 图层面板（右侧列表）选择锚点：用于 Shift 连选
let _layerListOrderIds = [];
let _layerListAnchorId = '';

const layerFilters = {
    query: '',
    shape: 'all',
    color: 'all'
};

// 历史记录系统
const history = [];
let historyIndex = -1;
let historyProcessing = false;

// 初始化
function init() {
    setupCanvasResponsive();
    renderPalettes();
    renderLayerColorFilter();
    setupLayerFilters();
    setupEventListeners();
    setupHotkeys();
    loadFromLocal(); // 加载后会触发一次 saveHistory
    // 初始状态入栈
    saveHistory();
    setPickMode('off');
    setupProjectPlacementsPanel();
    setupPixelArtImportPanel();
}

async function _persistLastOpenedPlacement(relPath) {
    const rel = String(relPath || '').trim();
    // 空字符串也允许写入（代表“清空最近选择”）
    const resp = await fetch('/api/shape_editor/project_state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ rel_path: rel })
    });
    const text = await resp.text();
    if (!resp.ok) {
        logToUi('WARN', `写入项目状态失败（HTTP ${resp.status}）`);
        logToUi('WARN', text);
    }
}

async function _tryRestoreLastOpenedPlacementFromProject() {
    const resp = await fetch('/api/shape_editor/project_state', { method: 'GET' });
    if (!resp.ok) {
        logToUi('WARN', `读取项目状态失败（HTTP ${resp.status}）`);
        return false;
    }
    const obj = await resp.json();
    if (!obj || !obj.ok || !obj.has_data) return false;
    const rel = String(obj.last_opened_rel_path || '').trim();
    if (!rel) return false;
    await loadProjectPlacement(rel);
    toastToUi('info', '已恢复上次打开的实体');
    logToUi('INFO', `已恢复上次打开的实体：${rel}`);
    return true;
}

async function bootRestoreProjectCanvas() {
    // 状态栏与实体列表：这里集中 await，避免 init 里 fire-and-forget 导致时序混乱
    await refreshHeaderStatus();
    await refreshProjectPlacements();

    const restored = await _tryRestoreLastOpenedPlacementFromProject();
    if (restored) return;

    await tryLoadProjectCanvas();
    const loaded = localStorage.getItem('qx_shape_editor_data');
    if (loaded) {
        // 作为兜底：项目无数据时仍可手动从本地恢复（注意：localStorage 受端口影响）
        loadFromLocal();
        saveHistory();
        toastToUi('info', '已从本地存储恢复（兜底）');
        logToUi('INFO', '已从本地存储恢复（兜底）');
    }
}

// 响应式画布
function setupCanvasResponsive() {
    const wrapper = document.getElementById('canvas-wrapper');
    
    function resize() {
        canvas.setWidth(wrapper.clientWidth);
        canvas.setHeight(wrapper.clientHeight);
        canvas.renderAll();
    }
    
    window.addEventListener('resize', resize);
    setTimeout(resize, 100);
}

// 历史记录操作
function saveHistory() {
    if (historyProcessing) return;
    if (isBatching()) return;
    
    // 如果当前处于历史记录中间，删除后面的
    if (historyIndex < history.length - 1) {
        history.splice(historyIndex + 1);
    }
    
    const json = JSON.stringify(canvas.toJSON(['isReference', 'id', 'label', 'isLocked']));
    history.push(json);
    historyIndex++;

    // 限制历史步数
    if (history.length > 50) {
        history.shift();
        historyIndex--;
    }
    
    renderLayerList(); // 每次变动刷新图层列表
}

function undo() {
    // 避免在拖拽/涂抹等“半途中”直接回放 history 导致状态残留
    if (typeof _cancelTransientInteractions === 'function') {
        _cancelTransientInteractions();
    }
    if (historyIndex > 0) {
        historyProcessing = true;
        historyIndex--;
        const prevState = history[historyIndex];
        
        canvas.loadFromJSON(prevState, () => {
            canvas.renderAll();
            applyLockStates();
            historyProcessing = false;
            updateLayerListUI(); // 仅刷新UI不保存历史
            saveToLocal(false); // 保存到本地但不入栈
        });
    }
}

function redo() {
    if (typeof _cancelTransientInteractions === 'function') {
        _cancelTransientInteractions();
    }
    if (historyIndex < history.length - 1) {
        historyProcessing = true;
        historyIndex++;
        const nextState = history[historyIndex];

        canvas.loadFromJSON(nextState, () => {
            canvas.renderAll();
            applyLockStates();
            historyProcessing = false;
            updateLayerListUI();
            saveToLocal(false);
        });
    }
}

// 渲染调色板
function renderPalettes() {
    const rectContainer = document.getElementById('rect-palette');
    const circleContainer = document.getElementById('circle-palette');
    const paintContainer = document.getElementById('paint-palette');

    RECT_COLORS.forEach(color => {
        const btn = document.createElement('div');
        btn.className = 'color-btn';
        btn.style.backgroundColor = color;
        btn.onclick = () => createRect(color);
        
        // 拖拽支持
        btn.draggable = true;
        btn.ondragstart = (e) => {
            e.dataTransfer.setData('type', 'rect');
            e.dataTransfer.setData('color', color);
        };
        
        rectContainer.appendChild(btn);
    });

    CIRCLE_COLORS.forEach(color => {
        const btn = document.createElement('div');
        btn.className = 'color-btn rounded-full';
        btn.style.backgroundColor = color;
        btn.onclick = () => createCircle(color);
        
        // 拖拽支持
        btn.draggable = true;
        btn.ondragstart = (e) => {
            e.dataTransfer.setData('type', 'circle');
            e.dataTransfer.setData('color', color);
        };

        circleContainer.appendChild(btn);
    });

    if (paintContainer) {
        paintContainer.innerHTML = '';
        RECT_COLORS.forEach(color => {
            const btn = document.createElement('div');
            btn.className = 'color-btn';
            btn.style.backgroundColor = color;
            btn.setAttribute('data-paint-color', String(color));
            btn.onclick = () => setPaintBrushColor(color);
            paintContainer.appendChild(btn);
        });
    }
    syncPaintToolUi();
}

// 创建物体逻辑
function getCenter() {
    return {
        left: canvas.width / 2 - DEFAULT_SIZE / 2,
        top: canvas.height / 2 - DEFAULT_SIZE / 2
    };
}

function _coerceFiniteNumber(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) ? n : Number(fallback);
}

function _shouldPersistForCreateOptions(options) {
    // 默认：用户交互创建 -> 需要落盘 + 入历史
    // 恢复/批量导入 -> 可显式传 persist:false，避免污染撤销栈与频繁 localStorage 写入
    return !(options && options.persist === false);
}

function createRect(color, options = {}) {
    const select = options.select !== false;
    const { left, top } = options.left !== undefined ? options : getCenter();
    const width = _coerceFiniteNumber(options.width, DEFAULT_SIZE);
    const height = _coerceFiniteNumber(options.height, DEFAULT_SIZE);
    const angle = _coerceFiniteNumber(options.angle, 0);
    const opacity = _coerceFiniteNumber(options.opacity, 1.0);
    const label = String(options.label || '').trim() || getNextLabel('rect');
    const id = String(options.id || '').trim() || getNewObjectId();
    const rect = new fabric.Rect({
        left: left + (options.left !== undefined ? 0 : Math.random() * 20),
        top: top + (options.left !== undefined ? 0 : Math.random() * 20),
        fill: color,
        width: width,
        height: height,
        angle: angle,
        opacity: opacity,
        strokeWidth: 0,
        cornerColor: '#f1c40f',
        borderColor: '#f1c40f',
        transparentCorners: false,
        label: label,
        id: id,
        lockSkewingX: true,
        lockSkewingY: true
    });
    rect.isLocked = options.isLocked === true;
    if (rect.isLocked) {
        setObjectLocked(rect, true);
    }
    canvas.add(rect);
    if (select) {
        canvas.setActiveObject(rect);
    }
    if (_shouldPersistForCreateOptions(options)) {
        const normalizedFill = normalizeColor(String(color || ''));
        if (RECT_COLORS.includes(normalizedFill)) {
            _lastRectFill = normalizedFill;
        }
        saveToLocal();
        saveHistory();
    }
}

function createCircle(color, options = {}) {
    const select = options.select !== false;
    const { left, top } = options.left !== undefined ? options : getCenter();
    const width = _coerceFiniteNumber(options.width, DEFAULT_SIZE);
    const height = _coerceFiniteNumber(options.height, DEFAULT_SIZE);
    const angle = _coerceFiniteNumber(options.angle, 0);
    const opacity = _coerceFiniteNumber(options.opacity, 1.0);
    const label = String(options.label || '').trim() || getNextLabel('circle');
    const id = String(options.id || '').trim() || getNewObjectId();
    const radius = Math.max(1, width / 2);
    const circle = new fabric.Circle({
        left: left + (options.left !== undefined ? 0 : Math.random() * 20),
        top: top + (options.left !== undefined ? 0 : Math.random() * 20),
        fill: color,
        radius: radius,
        angle: angle,
        opacity: opacity,
        strokeWidth: 0,
        cornerColor: '#f1c40f',
        borderColor: '#f1c40f',
        transparentCorners: false,
        label: label,
        id: id,
        lockSkewingX: true,
        lockSkewingY: true
    });
    // 尝试用 scaleY 还原“拉伸后的圆”（导出时记录的是 scaled 宽高）
    if (width > 0 && height > 0) {
        circle.scaleX = 1.0;
        circle.scaleY = height / width;
    }
    circle.isLocked = options.isLocked === true;
    if (circle.isLocked) {
        setObjectLocked(circle, true);
    }
    canvas.add(circle);
    if (select) {
        canvas.setActiveObject(circle);
    }
    if (_shouldPersistForCreateOptions(options)) {
        saveToLocal();
        saveHistory();
    }
}

// 颜色工具
function hexToRgb(hex) {
    const clean = hex.replace('#', '').trim();
    if (clean.length === 3) {
        const r = parseInt(clean[0] + clean[0], 16);
        const g = parseInt(clean[1] + clean[1], 16);
        const b = parseInt(clean[2] + clean[2], 16);
        return { r, g, b };
    }
    if (clean.length === 6) {
        const r = parseInt(clean.slice(0, 2), 16);
        const g = parseInt(clean.slice(2, 4), 16);
        const b = parseInt(clean.slice(4, 6), 16);
        return { r, g, b };
    }
    return { r: 0, g: 0, b: 0 };
}

function rgbToHex(r, g, b) {
    const toHex = (v) => v.toString(16).padStart(2, '0');
    return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase();
}

function getNewObjectId() {
    objectCounter += 1;
    return `obj_${Date.now().toString(36)}_${objectCounter}`;
}

function ensureObjectId(obj) {
    if (!obj.id) {
        obj.id = getNewObjectId();
    }
}

function assignFreshObjectIdsDeep(obj) {
    if (!obj) return;
    obj.id = getNewObjectId();
    if (obj.type === 'group' && obj.getObjects) {
        obj.getObjects().forEach(assignFreshObjectIdsDeep);
    }
}

function getTypeLabelPrefix(type) {
    if (type === 'rect') return '矩形';
    if (type === 'circle') return '圆形';
    if (type === 'image') return '参考图';
    if (type === 'group') return '组合';
    return '图形';
}

function getNextLabel(type) {
    const prefix = getTypeLabelPrefix(type);
    let max = 0;
    let count = 0;
    canvas.getObjects().forEach(obj => {
        if (obj.type !== type) return;
        count += 1;
        const label = obj.label || '';
        const match = label.match(new RegExp(`^${prefix}\\s*(\\d+)$`));
        if (match) {
            max = Math.max(max, parseInt(match[1], 10));
        }
    });
    if (max === 0 && count > 0) {
        max = count;
    }
    return `${prefix}${max + 1}`;
}

function setObjectLocked(obj, locked) {
    if (!obj) return;
    obj.isLocked = locked;
    obj.evented = !locked;
    obj.selectable = !locked ? true : false;
    obj.lockMovementX = locked;
    obj.lockMovementY = locked;
    obj.lockScalingX = locked;
    obj.lockScalingY = locked;
    obj.lockRotation = locked;
    obj.lockSkewingX = true;
    obj.lockSkewingY = true;
    obj.hasControls = !locked;
    obj.hoverCursor = locked ? 'not-allowed' : 'move';
}

function applyLockStates() {
    canvas.getObjects().forEach(obj => {
        if (obj.isLocked) {
            setObjectLocked(obj, true);
        }
    });
    canvas.requestRenderAll();
}

function normalizeColor(color) {
    if (!color) return '';
    if (color.startsWith('#')) return color.toUpperCase();
    if (color.startsWith('rgb')) {
        const match = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (match) {
            return rgbToHex(parseInt(match[1], 10), parseInt(match[2], 10), parseInt(match[3], 10));
        }
    }
    return color.toUpperCase();
}

const ALL_COLORS_RGB = ALL_COLORS.map(hexToRgb);
const RECT_COLORS_RGB = RECT_COLORS.map(hexToRgb);
const CIRCLE_COLORS_RGB = CIRCLE_COLORS.map(hexToRgb);

function getNearestPaletteColor(r, g, b) {
    let minDist = Infinity;
    let best = ALL_COLORS[0];
    for (let i = 0; i < ALL_COLORS_RGB.length; i++) {
        const p = ALL_COLORS_RGB[i];
        const dr = r - p.r;
        const dg = g - p.g;
        const db = b - p.b;
        const dist = dr * dr + dg * dg + db * db;
        if (dist < minDist) {
            minDist = dist;
            best = ALL_COLORS[i];
        }
    }
    return best;
}

function getNearestColorInPalette(r, g, b, palette, paletteRgb) {
    const pal = Array.isArray(palette) ? palette : [];
    const rgbs = Array.isArray(paletteRgb) ? paletteRgb : [];
    if (pal.length === 0 || rgbs.length !== pal.length) {
        return ALL_COLORS[0] || '#FFFFFF';
    }
    let minDist = Infinity;
    let best = pal[0];
    for (let i = 0; i < rgbs.length; i++) {
        const p = rgbs[i];
        const dr = r - p.r;
        const dg = g - p.g;
        const db = b - p.b;
        const dist = dr * dr + dg * dg + db * db;
        if (dist < minDist) {
            minDist = dist;
            best = pal[i];
        }
    }
    return best;
}

function getNearestRectPaletteColor(r, g, b) {
    return getNearestColorInPalette(r, g, b, RECT_COLORS, RECT_COLORS_RGB);
}

function getNearestCirclePaletteColor(r, g, b) {
    return getNearestColorInPalette(r, g, b, CIRCLE_COLORS, CIRCLE_COLORS_RGB);
}

function renderLayerColorFilter() {
    const container = document.getElementById('layer-color-filter');
    if (!container) return;

    container.innerHTML = '';
    const allBtn = document.createElement('div');
    allBtn.className = 'filter-swatch all active';
    allBtn.innerText = '全部';
    allBtn.onclick = () => setLayerColorFilter('all');
    container.appendChild(allBtn);

    ALL_COLORS.forEach(color => {
        const swatch = document.createElement('div');
        swatch.className = 'filter-swatch';
        swatch.style.backgroundColor = color;
        swatch.title = color;
        swatch.onclick = () => setLayerColorFilter(color);
        container.appendChild(swatch);
    });
}

function setLayerColorFilter(color) {
    layerFilters.color = color;
    const swatches = document.querySelectorAll('#layer-color-filter .filter-swatch');
    swatches.forEach(swatch => {
        swatch.classList.remove('active');
        if (swatch.classList.contains('all') && color === 'all') {
            swatch.classList.add('active');
        }
        if (!swatch.classList.contains('all')) {
            const swatchColor = normalizeColor(swatch.style.backgroundColor);
            if (swatchColor === normalizeColor(color)) {
                swatch.classList.add('active');
            }
        }
    });
    renderLayerList();
}

function setupLayerFilters() {
    const searchInput = document.getElementById('layer-search');
    const shapeFilter = document.getElementById('layer-shape-filter');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            layerFilters.query = e.target.value.trim().toLowerCase();
            renderLayerList();
        });
    }
    if (shapeFilter) {
        shapeFilter.addEventListener('change', (e) => {
            layerFilters.shape = e.target.value;
            renderLayerList();
        });
    }
}

function getObjectTypeName(obj) {
    if (obj.type === 'rect') return '矩形';
    if (obj.type === 'circle') return '圆形';
    if (obj.type === 'image') return '参考图';
    if (obj.type === 'group') return '组合';
    return '未知';
}

function isGenericLabel(label, typeName) {
    if (!label) return true;
    if (label === typeName) return true;
    const match = label.match(new RegExp(`^${typeName}\\s*$`));
    return Boolean(match);
}

function getObjectDisplayName(obj, index, autoNameMap) {
    const typeName = getObjectTypeName(obj);
    const label = obj.label || '';
    if (isGenericLabel(label, typeName)) {
        return autoNameMap && autoNameMap.get(obj) ? autoNameMap.get(obj) : `${typeName}${index}`;
    }
    return label;
}

function objectMatchesColor(obj, color) {
    if (color === 'all') return true;
    const target = normalizeColor(color);
    if (obj.type === 'group' && obj.getObjects) {
        return obj.getObjects().some(child => objectMatchesColor(child, color));
    }
    const objColor = normalizeColor(obj.fill);
    return objColor === target;
}

function objectMatchesShape(obj, shape) {
    if (shape === 'all') return true;
    return obj.type === shape;
}

function objectMatchesSearch(obj, displayIndex, autoNameMap) {
    const query = layerFilters.query;
    if (!query) return true;
    const typeName = getObjectTypeName(obj);
    const label = getObjectDisplayName(obj, displayIndex, autoNameMap);
    let colors = '';
    if (obj.type === 'group' && obj.getObjects) {
        colors = obj.getObjects().map(child => normalizeColor(child.fill)).join(' ');
    } else {
        colors = normalizeColor(obj.fill);
    }
    const text = `${label} ${typeName} ${colors}`.toLowerCase();
    return text.includes(query);
}

