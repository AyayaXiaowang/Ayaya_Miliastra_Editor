// PS 式外圈旋转 + 空白拖拽创建矩形
let _paintBrushState = null; // { changed, painted:Set, targets:[{obj, br}], prevSelection, prevSkipTargetFind }
let _paintBrushSizeDragState = null; // { startSizePx, startClientX, startClientY }

function _isPointInRect(p, rect) {
    if (!p || !rect) return false;
    const x = Number(p.x);
    const y = Number(p.y);
    const left = Number(rect.left);
    const top = Number(rect.top);
    const w = Number(rect.width);
    const h = Number(rect.height);
    return x >= left && x <= (left + w) && y >= top && y <= (top + h);
}

function _normalizeRadDelta(rad) {
    let v = Number(rad);
    while (v > Math.PI) v -= Math.PI * 2;
    while (v < -Math.PI) v += Math.PI * 2;
    return v;
}

function _distPointToSegment(p, a, b) {
    const px = Number(p && p.x);
    const py = Number(p && p.y);
    const ax = Number(a && a.x);
    const ay = Number(a && a.y);
    const bx = Number(b && b.x);
    const by = Number(b && b.y);
    if (!Number.isFinite(px) || !Number.isFinite(py) || !Number.isFinite(ax) || !Number.isFinite(ay) || !Number.isFinite(bx) || !Number.isFinite(by)) {
        return Infinity;
    }
    const vx = bx - ax;
    const vy = by - ay;
    const wx = px - ax;
    const wy = py - ay;
    const c1 = vx * wx + vy * wy;
    if (c1 <= 0) {
        const dx = px - ax;
        const dy = py - ay;
        return Math.hypot(dx, dy);
    }
    const c2 = vx * vx + vy * vy;
    if (c2 <= c1) {
        const dx = px - bx;
        const dy = py - by;
        return Math.hypot(dx, dy);
    }
    const t = c1 / c2;
    const projX = ax + t * vx;
    const projY = ay + t * vy;
    return Math.hypot(px - projX, py - projY);
}

function _isPointInConvexPolygon(point, polygon) {
    const pts = Array.isArray(polygon) ? polygon : [];
    if (!point || pts.length < 3) return false;
    const px = Number(point.x);
    const py = Number(point.y);
    if (!Number.isFinite(px) || !Number.isFinite(py)) return false;

    let sign = 0;
    for (let i = 0; i < pts.length; i++) {
        const a = pts[i];
        const b = pts[(i + 1) % pts.length];
        const ax = Number(a && a.x);
        const ay = Number(a && a.y);
        const bx = Number(b && b.x);
        const by = Number(b && b.y);
        if (!Number.isFinite(ax) || !Number.isFinite(ay) || !Number.isFinite(bx) || !Number.isFinite(by)) return false;
        const cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax);
        if (cross === 0) continue; // on edge
        const s = cross > 0 ? 1 : -1;
        if (sign === 0) sign = s;
        else if (sign !== s) return false;
    }
    return true; // inside or on edge
}

function _minDistanceToPolygonEdges(point, polygon) {
    const pts = Array.isArray(polygon) ? polygon : [];
    if (!point || pts.length < 2) return Infinity;
    let min = Infinity;
    for (let i = 0; i < pts.length; i++) {
        const a = pts[i];
        const b = pts[(i + 1) % pts.length];
        const d = _distPointToSegment(point, a, b);
        if (d < min) min = d;
    }
    return min;
}

function _ensurePsRotateHud() {
    const id = 'ps-rotate-hud';
    let el = document.getElementById(id);
    if (el) return el;
    el = document.createElement('div');
    el.id = id;
    el.style.position = 'fixed';
    el.style.zIndex = '9999';
    el.style.pointerEvents = 'none';
    el.style.display = 'none';
    el.style.padding = '6px 8px';
    el.style.borderRadius = '10px';
    el.style.border = '1px solid rgba(255,255,255,0.14)';
    el.style.background = 'rgba(30,30,30,0.92)';
    el.style.boxShadow = '0 18px 40px rgba(0,0,0,0.45)';
    el.style.color = '#e0e0e0';
    el.style.fontFamily = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';
    el.style.fontSize = '12px';
    el.style.lineHeight = '1.35';
    document.body.appendChild(el);
    return el;
}

function _hidePsRotateHud() {
    const el = document.getElementById('ps-rotate-hud');
    if (el) el.style.display = 'none';
}

function _updatePsRotateHud(e, angleDeg) {
    const el = _ensurePsRotateHud();
    const deg = Math.round(Number(angleDeg) || 0);
    const snapped = e && e.shiftKey ? '（Shift：15°吸附）' : '';
    el.textContent = `角度 ${deg}°${snapped}`;
    el.style.display = 'block';

    const margin = 12;
    const vw = Math.max(0, Number(window.innerWidth) || 0);
    const vh = Math.max(0, Number(window.innerHeight) || 0);
    const w = Math.max(120, el.offsetWidth || 0);
    const h = Math.max(24, el.offsetHeight || 0);
    const maxX = Math.max(margin, vw - w - margin);
    const maxY = Math.max(margin, vh - h - margin);
    const x = Math.min(maxX, Math.max(margin, Number(e.clientX || 0) + 14));
    const y = Math.min(maxY, Math.max(margin, Number(e.clientY || 0) + 14));
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
}

// ------------------------------------------------------------ paint brush cursor (visualize brush size)
let _paintBrushCursorEl = null;
let _paintBrushCursorRafId = 0;
let _paintBrushCursorLastEvent = null;

function _ensurePaintBrushCursor() {
    const id = 'paint-brush-cursor';
    let el = document.getElementById(id);
    if (el) return el;
    el = document.createElement('div');
    el.id = id;
    el.style.position = 'fixed';
    el.style.zIndex = '9997';
    el.style.pointerEvents = 'none';
    el.style.display = 'none';
    el.style.transform = 'translate(-50%, -50%)';
    el.style.borderRadius = '999px';
    el.style.border = '2px solid rgba(55,148,255,0.85)';
    el.style.background = 'rgba(55,148,255,0.10)';
    el.style.boxShadow = '0 0 0 1px rgba(0,0,0,0.35), 0 14px 32px rgba(0,0,0,0.35)';
    document.body.appendChild(el);
    return el;
}

function _hidePaintBrushCursor() {
    const el = document.getElementById('paint-brush-cursor');
    if (el) el.style.display = 'none';
    _paintBrushCursorLastEvent = null;
    if (_paintBrushCursorRafId) {
        cancelAnimationFrame(_paintBrushCursorRafId);
        _paintBrushCursorRafId = 0;
    }
}

function _updatePaintBrushCursorNow(e) {
    const el = _ensurePaintBrushCursor();
    _paintBrushCursorEl = el;
    if (!e) {
        el.style.display = 'none';
        return;
    }
    const sizePx = (typeof getPaintBrushSizePx === 'function') ? getPaintBrushSizePx() : 16;
    const radius = Math.max(1, Math.round(Number(sizePx || 1)));
    const dia = radius * 2;

    const c = normalizeColor(typeof getPaintBrushColor === 'function' ? getPaintBrushColor() : '');
    const rgb = c ? hexToRgb(c) : { r: 55, g: 148, b: 255 };
    const r = Number(rgb.r) || 0;
    const g = Number(rgb.g) || 0;
    const b = Number(rgb.b) || 0;

    el.style.width = `${dia}px`;
    el.style.height = `${dia}px`;
    el.style.left = `${Number(e.clientX || 0)}px`;
    el.style.top = `${Number(e.clientY || 0)}px`;
    el.style.border = `2px solid rgba(${r},${g},${b},0.85)`;
    el.style.background = `rgba(${r},${g},${b},0.10)`;
    el.style.display = 'block';
}

function _scheduleUpdatePaintBrushCursor(e) {
    _paintBrushCursorLastEvent = e || null;
    if (_paintBrushCursorRafId) return;
    _paintBrushCursorRafId = requestAnimationFrame(() => {
        _paintBrushCursorRafId = 0;
        _updatePaintBrushCursorNow(_paintBrushCursorLastEvent);
    });
}

function _isPointerNearAnyControl(obj, pointer, radiusPx) {
    if (!obj || !pointer) return false;
    const r = Math.max(4, Number(radiusPx || 0));
    const rr = r * r;
    obj.setCoords();
    const coords = obj.oCoords || null;
    if (!coords) return false;

    const keys = ['tl', 'tr', 'bl', 'br', 'ml', 'mt', 'mr', 'mb', 'mtr'];
    for (const k of keys) {
        const c = coords[k];
        if (!c) continue;
        const dx = Number(pointer.x) - Number(c.x);
        const dy = Number(pointer.y) - Number(c.y);
        if (dx * dx + dy * dy <= rr) return true;
    }
    return false;
}

function _shouldStartPsLikeRotate(obj, pointer) {
    if (!obj || !pointer) return false;
    if (obj.isLocked) return false;

    const cornerSize = Number(obj.cornerSize || fabric.Object.prototype.cornerSize || 12);
    const padding = Number(obj.padding || fabric.Object.prototype.padding || 6);
    const excludeRadius = Math.max(24, cornerSize + padding + 10);
    if (_isPointerNearAnyControl(obj, pointer, excludeRadius)) return false;

    // PS 手感：旋转只在“选中框外侧、贴近边框的一圈”触发
    obj.setCoords();
    const coords = obj.oCoords || null;
    if (!coords || !coords.tl || !coords.tr || !coords.br || !coords.bl) return false;

    const quad = [coords.tl, coords.tr, coords.br, coords.bl];
    // 选中框内部：必须让“拖拽移动 / 缩放控制点”优先
    if (_isPointInConvexPolygon(pointer, quad)) return false;

    // 外圈旋转 ring：离边框越近越容易触发，远离边框则不触发（避免“到处都能旋转”）
    const ringWidthPx = Math.max(18, cornerSize + padding + 4);
    const d = _minDistanceToPolygonEdges(pointer, quad);
    if (!Number.isFinite(d)) return false;
    if (d > ringWidthPx) return false;

    return true;
}

function _getDefaultRectFill() {
    const c = normalizeColor(String(_lastRectFill || ''));
    if (RECT_COLORS.includes(c)) return c;
    return RECT_COLORS[0];
}

function _pickRectFillFromReference(pointer, fallbackColor) {
    const fb = normalizeColor(String(fallbackColor || ''));
    const fallback = RECT_COLORS.includes(fb) ? fb : RECT_COLORS[0];
    const img = _findTopmostImageAtPointer(pointer);
    if (!img) return fallback;
    const sampled = sampleColorFromImage(img, pointer);
    if (!sampled) return fallback;
    const rgb = hexToRgb(sampled);
    return getNearestRectPaletteColor(rgb.r, rgb.g, rgb.b);
}

function _cancelTransientInteractions() {
    if (_dragCreateRectState) {
        const st = _dragCreateRectState;
        if (st.started && st.rectObj) {
            canvas.remove(st.rectObj);
        }
        _dragCreateRectState = null;
        canvas.requestRenderAll();
    }
    if (_psRotateState) {
        const st = _psRotateState;
        if (st && st.obj) {
            st.obj.set({ angle: st.startAngle });
            if (st.center) {
                st.obj.setPositionByOrigin(new fabric.Point(st.center.x, st.center.y), 'center', 'center');
            }
            st.obj.setCoords();
            if (st.restoreToActiveSelection && st.obj.type === 'group' && st.obj.toActiveSelection) {
                st.obj.toActiveSelection();
            }
        }
        _psRotateState = null;
        canvas.setCursor('default');
        const upper = canvas.upperCanvasEl;
        if (upper) {
            if (upper.dataset && upper.dataset.psRotateHover === '1') {
                delete upper.dataset.psRotateHover;
            }
            upper.style.cursor = '';
        }
        _hidePsRotateHud();
        canvas.requestRenderAll();
    }
    if (_paintBrushState) {
        _finishPaintBrushStroke({ commit: true });
    }
    if (_paintBrushSizeDragState) {
        _paintBrushSizeDragState = null;
    }
}

function setupPsLikeRotateDrag() {
    const upperCanvas = canvas.upperCanvasEl;
    if (!upperCanvas) return;

    const DRAG_START_THRESHOLD_PX = 3;

    upperCanvas.addEventListener('mousemove', (e) => {
        if (!e) return;
        if (typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled()) return;
        if (_psRotateState) return;
        if (isPanning) return;
        if (_dragCreateRectState) return;
        // ALT+拖拽复制：不改光标，避免误导
        if (e.altKey) return;

        const obj = canvas.getActiveObject();
        if (!obj || obj.isLocked) {
            // 仅在我们曾设置过旋转提示光标时才清理，避免抢 Fabric 的 hover 光标
            if (upperCanvas.dataset && upperCanvas.dataset.psRotateHover === '1') {
                delete upperCanvas.dataset.psRotateHover;
                upperCanvas.style.cursor = '';
            }
            return;
        }
        const pointer = canvas.getPointer(e);
        if (_shouldStartPsLikeRotate(obj, pointer)) {
            // 旋转光标（PS：外圈出现旋转提示）
            upperCanvas.dataset.psRotateHover = '1';
            upperCanvas.style.cursor = 'grab';
            return;
        }
        if (upperCanvas.dataset && upperCanvas.dataset.psRotateHover === '1') {
            delete upperCanvas.dataset.psRotateHover;
            upperCanvas.style.cursor = '';
        }
    }, true);

    // 捕获阶段：像 PS 一样，在选中框外圈拖拽即可旋转（Shift 吸附 15°）
    upperCanvas.addEventListener('mousedown', (e) => {
        if (!e) return;
        if (typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled()) return;
        if (e.button !== 0) return;
        if (e.altKey) return;
        if (isPanning) return;
        if (_dragCreateRectState) return;

        let obj = canvas.getActiveObject();
        if (!obj || obj.isLocked) return;

        const pointer = canvas.getPointer(e);
        if (!_shouldStartPsLikeRotate(obj, pointer)) return;

        const target = canvas.findTarget(e);
        if (target && target !== obj) return;

        e.preventDefault();
        e.stopImmediatePropagation();
        e.stopPropagation();

        // ActiveSelection：用临时 group 承接旋转（否则只改 selection box 不会落到子对象）
        let restoreToActiveSelection = false;
        if (obj.type === 'activeSelection' && obj.toGroup) {
            obj = obj.toGroup();
            restoreToActiveSelection = true;
        }

        const center = obj.getPointByOrigin('center', 'center');
        const startRad = Math.atan2(pointer.y - center.y, pointer.x - center.x);
        _psRotateState = {
            obj,
            center,
            startRad,
            lastRad: startRad,
            accumulatedRad: 0,
            startAngle: Number(obj.angle || 0),
            startClientX: Number(e.clientX),
            startClientY: Number(e.clientY),
            didRotate: false,
            restoreToActiveSelection
        };
        canvas.setCursor('grabbing');
        upperCanvas.style.cursor = 'grabbing';
        if (upperCanvas.dataset && upperCanvas.dataset.psRotateHover === '1') {
            delete upperCanvas.dataset.psRotateHover;
        }
        _updatePsRotateHud(e, Number(obj.angle || 0));
    }, true);

    window.addEventListener('mousemove', (e) => {
        if (!_psRotateState) return;
        const st = _psRotateState;
        const dxClient = Math.abs(Number(e.clientX) - st.startClientX);
        const dyClient = Math.abs(Number(e.clientY) - st.startClientY);
        if (!st.didRotate && Math.max(dxClient, dyClient) < DRAG_START_THRESHOLD_PX) return;

        const pointer = canvas.getPointer(e);
        const dx = pointer.x - st.center.x;
        const dy = pointer.y - st.center.y;
        const rad = Math.atan2(dy, dx);
        const step = _normalizeRadDelta(rad - st.lastRad);
        st.lastRad = rad;
        st.accumulatedRad += step;
        let angle = st.startAngle + (st.accumulatedRad * 180 / Math.PI);
        if (e.shiftKey) {
            angle = Math.round(angle / 15) * 15;
        }
        st.didRotate = true;
        st.obj.set({ angle });
        // 关键：旋转保持“几何中心点”不漂移（避免围绕左上角/非中心点打转）
        st.obj.setPositionByOrigin(new fabric.Point(st.center.x, st.center.y), 'center', 'center');
        st.obj.setCoords();
        canvas.requestRenderAll();
        _updatePsRotateHud(e, angle);
    }, true);

    window.addEventListener('mouseup', () => {
        if (!_psRotateState) return;
        const st = _psRotateState;
        _psRotateState = null;
        canvas.setCursor('default');
        const upper = canvas.upperCanvasEl;
        if (upper) {
            if (upper.dataset && upper.dataset.psRotateHover === '1') {
                delete upper.dataset.psRotateHover;
            }
            upper.style.cursor = '';
        }
        _hidePsRotateHud();

        // 恢复 ActiveSelection（若起手是多选）
        if (st.restoreToActiveSelection && st.obj && st.obj.type === 'group' && st.obj.toActiveSelection) {
            st.obj.toActiveSelection();
        }

        st.obj.setCoords();
        canvas.requestRenderAll();
        if (!st.didRotate) return;
        updatePropPanel();
        saveToLocal();
        saveHistory();
    }, true);
}

function setupBlankDragCreateRect() {
    const upperCanvas = canvas.upperCanvasEl;
    if (!upperCanvas) return;

    const DRAG_START_THRESHOLD_PX = 4;
    const MIN_COMMIT_SIZE_PX = 2;

    // 捕获阶段：空白处左键拖拽直接创建矩形（起点在参考图上则取色，锁定参考图也可取）
    upperCanvas.addEventListener('mousedown', (e) => {
        if (!e) return;
        if (typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled()) return;
        if (e.button !== 0) return;
        if (e.altKey) return;
        if (isPanning) return;
        if (_psRotateState) return;
        if (pickMode !== 'off') return;
        // Ctrl/Meta：保留 Fabric 自带框选（多选）
        if (e.ctrlKey || e.metaKey) return;

        const target = canvas.findTarget(e);
        // 点到可交互对象：交给 Fabric 的移动/缩放/选择
        if (target) return;

        const pointer = canvas.getPointer(e);
        const active = canvas.getActiveObject();
        if (active && !active.isLocked && _shouldStartPsLikeRotate(active, pointer)) return;

        e.preventDefault();
        e.stopImmediatePropagation();
        e.stopPropagation();

        const fill = _pickRectFillFromReference(pointer, _getDefaultRectFill());
        _dragCreateRectState = {
            started: false,
            startClientX: Number(e.clientX),
            startClientY: Number(e.clientY),
            startPointer: { x: pointer.x, y: pointer.y },
            rectFill: fill,
            rectObj: null
        };
    }, true);

    window.addEventListener('mousemove', (e) => {
        const st = _dragCreateRectState;
        if (!st) return;

        const dxClient = Math.abs(Number(e.clientX) - st.startClientX);
        const dyClient = Math.abs(Number(e.clientY) - st.startClientY);
        if (!st.started && Math.max(dxClient, dyClient) < DRAG_START_THRESHOLD_PX) return;

        const pointer = canvas.getPointer(e);
        if (!st.started) {
            st.started = true;
            const color = st.rectFill;
            const rect = new fabric.Rect({
                left: st.startPointer.x,
                top: st.startPointer.y,
                fill: color,
                width: 1,
                height: 1,
                angle: 0,
                opacity: 1.0,
                strokeWidth: 0,
                cornerColor: '#f1c40f',
                borderColor: '#f1c40f',
                transparentCorners: false,
                label: getNextLabel('rect'),
                id: getNewObjectId(),
                lockSkewingX: true,
                lockSkewingY: true
            });
            rect.isLocked = false;
            canvas.add(rect);
            canvas.setActiveObject(rect);
            st.rectObj = rect;
        }

        const x0 = st.startPointer.x;
        const y0 = st.startPointer.y;
        const x1 = pointer.x;
        const y1 = pointer.y;
        const left = Math.min(x0, x1);
        const top = Math.min(y0, y1);
        const width = Math.max(1, Math.abs(x1 - x0));
        const height = Math.max(1, Math.abs(y1 - y0));
        st.rectObj.set({ left, top, width, height });
        st.rectObj.setCoords();
        canvas.requestRenderAll();
    }, true);

    window.addEventListener('mouseup', () => {
        const st = _dragCreateRectState;
        if (!st) return;
        _dragCreateRectState = null;

        if (!st.started) {
            // 单击空白：模拟 Fabric 的“清空选择”
            canvas.discardActiveObject();
            canvas.requestRenderAll();
            updatePropPanel();
            updateLayerListUI();
            return;
        }

        const rect = st.rectObj;
        if (!rect) return;
        rect.setCoords();
        const w = Math.round(rect.getScaledWidth());
        const h = Math.round(rect.getScaledHeight());
        if (w < MIN_COMMIT_SIZE_PX || h < MIN_COMMIT_SIZE_PX) {
            canvas.remove(rect);
            canvas.requestRenderAll();
            updatePropPanel();
            updateLayerListUI();
            return;
        }

        _lastRectFill = normalizeColor(rect.fill);
        canvas.setActiveObject(rect);
        canvas.requestRenderAll();
        updatePropPanel();
        saveToLocal();
        saveHistory();
    }, true);
}

function _paintDistPointToAabb(point, rect) {
    const px = Number(point && point.x);
    const py = Number(point && point.y);
    const left = Number(rect && rect.left);
    const top = Number(rect && rect.top);
    const w = Number(rect && rect.width);
    const h = Number(rect && rect.height);
    if (!Number.isFinite(px) || !Number.isFinite(py) || !Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(w) || !Number.isFinite(h)) {
        return Infinity;
    }
    const right = left + w;
    const bottom = top + h;
    const dx = px < left ? (left - px) : (px > right ? (px - right) : 0);
    const dy = py < top ? (top - py) : (py > bottom ? (py - bottom) : 0);
    return Math.hypot(dx, dy);
}

function _collectPaintBrushTargets() {
    const out = [];
    const objects = canvas.getObjects();
    function walk(obj, lockedParent) {
        if (!obj) return;
        const locked = lockedParent || !!obj.isLocked;
        if (locked) return;
        if (obj.type === 'group' && obj.getObjects) {
            obj.getObjects().forEach(child => walk(child, locked));
            return;
        }
        if (obj.type !== 'rect') return;
        if (obj.isReference) return;
        if (typeof obj.setCoords === 'function') obj.setCoords();
        const br0 = obj.getBoundingRect ? obj.getBoundingRect(true, true) : null;
        if (!br0) return;
        const br = { left: Number(br0.left), top: Number(br0.top), width: Number(br0.width), height: Number(br0.height) };
        out.push({ obj, br });
    }
    objects.forEach(o => walk(o, false));
    return out;
}

function _applyPaintBrushAtPointer(pointer) {
    const st = _paintBrushState;
    if (!st) return;
    const p = pointer || { x: 0, y: 0 };
    const radius = (typeof getPaintBrushRadiusCanvasPx === 'function')
        ? Math.max(0.1, Number(getPaintBrushRadiusCanvasPx() || 0))
        : 0.1;
    const brushColor = normalizeColor(typeof getPaintBrushColor === 'function' ? getPaintBrushColor() : '');
    if (!brushColor) return;

    let changed = false;
    for (let i = 0; i < st.targets.length; i++) {
        const t = st.targets[i];
        if (!t || !t.obj) continue;
        const obj = t.obj;
        if (st.painted.has(obj)) continue;
        const d = _paintDistPointToAabb(p, t.br);
        if (d > radius) continue;

        const before = normalizeColor(String(obj.fill || ''));
        if (before !== brushColor) {
            obj.set({ fill: brushColor });
            obj.dirty = true;
            changed = true;
        }
        st.painted.add(obj);
    }
    if (changed) {
        st.changed = true;
        canvas.requestRenderAll();
    }
}

function _finishPaintBrushStroke(opts = {}) {
    const st = _paintBrushState;
    if (!st) return;
    _paintBrushState = null;

    canvas.selection = st.prevSelection;
    canvas.skipTargetFind = st.prevSkipTargetFind;

    if (!st.changed) return;
    updateLayerListUI();
    saveToLocal();
    saveHistory();
}

function setupPaintBrushTool() {
    const upperCanvas = canvas.upperCanvasEl;
    if (!upperCanvas) return;

    const DRAG_START_THRESHOLD_PX = 2;

    // Alt + 右键拖拽：调整涂抹画笔大小（PS 手势）
    // 说明：右键菜单（取色创建/选择菜单）是通过 contextmenu 事件触发的，
    // 为避免调大小松手后弹出菜单，这里需要在捕获阶段吞掉对应事件。
    upperCanvas.addEventListener('contextmenu', (ev) => {
        if (!ev) return;
        if (!(typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled())) return;
        if (!_paintBrushSizeDragState && !ev.altKey) return;
        ev.preventDefault();
        ev.stopImmediatePropagation();
        ev.stopPropagation();
    }, true);

    // hover cursor: show brush size under mouse
    upperCanvas.addEventListener('mousemove', (e) => {
        if (typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled()) {
            _scheduleUpdatePaintBrushCursor(e);
        } else {
            _hidePaintBrushCursor();
        }
    }, true);
    upperCanvas.addEventListener('mouseleave', () => {
        // 非 stroke 时离开画布则隐藏，避免停留在屏幕上
        if (!_paintBrushState) _hidePaintBrushCursor();
    }, true);
    window.addEventListener('blur', () => _hidePaintBrushCursor(), true);

    upperCanvas.addEventListener('mousedown', (e) => {
        if (!e) return;
        if (!(typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled())) return;
        if (e.button !== 2) return;
        if (!e.altKey) return;
        if (isPanning) return;
        if (_psRotateState) return;
        if (_dragCreateRectState) return;
        if (pickMode !== 'off') return;

        // 让快捷键（Ctrl+Z 等）回到画布语义：避免焦点还在输入框导致只撤销输入框内容
        const ae = document.activeElement;
        if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA') && typeof ae.blur === 'function') {
            ae.blur();
        }

        e.preventDefault();
        e.stopImmediatePropagation();
        e.stopPropagation();

        const startSize = (typeof getPaintBrushSizePx === 'function') ? getPaintBrushSizePx() : 16;
        _paintBrushSizeDragState = {
            startSizePx: Number(startSize || 16),
            startClientX: Number(e.clientX || 0),
            startClientY: Number(e.clientY || 0),
        };
        _scheduleUpdatePaintBrushCursor(e);
    }, true);

    upperCanvas.addEventListener('mousedown', (e) => {
        if (!e) return;
        if (!(typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled())) return;
        if (e.button !== 0) return;
        if (e.altKey) return;
        if (isPanning) return;
        if (_psRotateState) return;
        if (_dragCreateRectState) return;
        if (pickMode !== 'off') return;

        // 让快捷键（Ctrl+Z 等）回到画布语义：避免焦点还在输入框导致只撤销输入框内容
        const ae = document.activeElement;
        if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA') && typeof ae.blur === 'function') {
            ae.blur();
        }

        const pointer = canvas.getPointer(e);
        // 点到对象/空白都允许涂抹：涂抹模式下优先级最高，避免误触拖拽/缩放/旋转
        e.preventDefault();
        e.stopImmediatePropagation();
        e.stopPropagation();

        const targets = _collectPaintBrushTargets();
        _paintBrushState = {
            changed: false,
            painted: new Set(),
            targets,
            prevSelection: !!canvas.selection,
            prevSkipTargetFind: !!canvas.skipTargetFind,
            startClientX: Number(e.clientX || 0),
            startClientY: Number(e.clientY || 0),
            started: false,
        };
        canvas.selection = false;
        canvas.skipTargetFind = true;
        _applyPaintBrushAtPointer(pointer);
        _scheduleUpdatePaintBrushCursor(e);
    }, true);

    window.addEventListener('mousemove', (e) => {
        const sizeSt = _paintBrushSizeDragState;
        if (sizeSt) {
            if (!e) return;
            if (!(typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled())) {
                _paintBrushSizeDragState = null;
                _hidePaintBrushCursor();
                return;
            }
            // buttons: 1=左键 2=右键 4=中键；右键抬起则结束
            const buttons = Number(e.buttons || 0);
            if ((buttons & 2) === 0) {
                _paintBrushSizeDragState = null;
                return;
            }

            const dx = Number(e.clientX || 0) - Number(sizeSt.startClientX || 0);
            const nextSize = Number(sizeSt.startSizePx || 16) + dx;
            if (typeof setPaintBrushSizePx === 'function') {
                setPaintBrushSizePx(nextSize);
            }

            e.preventDefault();
            e.stopImmediatePropagation();
            e.stopPropagation();
            _scheduleUpdatePaintBrushCursor(e);
            return;
        }

        const st = _paintBrushState;
        if (!st) return;
        if (!e) return;
        _scheduleUpdatePaintBrushCursor(e);
        if (!(typeof isPaintBrushEnabled === 'function' && isPaintBrushEnabled())) {
            _finishPaintBrushStroke({ commit: true });
            _hidePaintBrushCursor();
            return;
        }
        const dxClient = Math.abs(Number(e.clientX || 0) - st.startClientX);
        const dyClient = Math.abs(Number(e.clientY || 0) - st.startClientY);
        if (!st.started && Math.max(dxClient, dyClient) < DRAG_START_THRESHOLD_PX) return;
        st.started = true;
        const pointer = canvas.getPointer(e);
        _applyPaintBrushAtPointer(pointer);
    }, true);

    window.addEventListener('mouseup', (e) => {
        if (_paintBrushSizeDragState) {
            _paintBrushSizeDragState = null;
            _scheduleUpdatePaintBrushCursor(e);
        }
        if (!_paintBrushState) return;
        _finishPaintBrushStroke({ commit: true });
    }, true);
}

