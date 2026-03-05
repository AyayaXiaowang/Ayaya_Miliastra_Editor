function _setHeaderStatus(text) {
    const el = document.getElementById('shape-status');
    if (!el) return;
    el.textContent = String(text || '');
}

function _setPlacementStatus(text) {
    const el = document.getElementById('placement-status');
    if (!el) return;
    el.textContent = String(text || '');
}

function _normalizeTextForSearch(text) {
    return String(text || '').trim().toLowerCase();
}

let _placementsCache = [];
let _selectedPlacementRelPath = '';
let _placementContextRelPath = '';
let _placementRenameRelPath = '';

function _formatTimeHHMMSS() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
}

function logToUi(level, message) {
    const el = document.getElementById('log-window');
    if (!el) return;
    const lvl = String(level || 'INFO').toUpperCase();
    const msg = String(message || '').trim();
    const line = `[${_formatTimeHHMMSS()}] [${lvl}] ${msg}`;
    const prev = el.textContent || '';
    el.textContent = prev ? (prev + '\n' + line) : line;
    el.scrollTop = el.scrollHeight;
}

function toastToUi(level, message, timeoutMs = 1800) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const lvl = String(level || 'info').toLowerCase();
    const msg = String(message || '').trim();
    if (!msg) return;

    const node = document.createElement('div');
    node.className = `toast ${lvl}`;

    const title = document.createElement('div');
    title.className = 't-title';
    title.textContent = lvl === 'error' ? '错误' : (lvl === 'warn' ? '提示' : '信息');
    node.appendChild(title);

    const body = document.createElement('div');
    body.className = 't-msg';
    body.textContent = msg;
    node.appendChild(body);

    container.appendChild(node);
    const ms = Number(timeoutMs || 0);
    const ttl = Number.isFinite(ms) && ms > 0 ? ms : 1800;
    setTimeout(() => {
        if (node && node.parentNode) node.parentNode.removeChild(node);
    }, ttl);
}

