import { dom } from "../dom_refs.js";
import { copyTextToClipboard } from "../utils.js";

var variableSearchInputElement = dom.variableSearchInputElement;
var variableListContainerElement = dom.variableListContainerElement;
var variableCatalogStatusTextElement = dom.variableCatalogStatusTextElement;
var inputHtmlTextAreaElement = dom.inputHtmlTextAreaElement;

var _variableCatalog = null;

export function setVariableCatalogStatusText(text) {
    if (!variableCatalogStatusTextElement) return;
    variableCatalogStatusTextElement.textContent = String(text || "");
}

function insertTextIntoTextArea(textarea, text) {
    if (!textarea) {
        return;
    }
    var raw = String(text || "");
    if (!raw) {
        return;
    }
    var start = textarea.selectionStart || 0;
    var end = textarea.selectionEnd || 0;
    var oldValue = String(textarea.value || "");
    var nextValue = oldValue.slice(0, start) + raw + oldValue.slice(end);
    textarea.value = nextValue;
    var nextPos = start + raw.length;
    textarea.selectionStart = nextPos;
    textarea.selectionEnd = nextPos;
    textarea.focus();
}

export function renderVariableList() {
    if (!variableListContainerElement) return;
    variableListContainerElement.innerHTML = "";

    var q = String((variableSearchInputElement && variableSearchInputElement.value) || "").trim().toLowerCase();
    var catalog = _variableCatalog;
    if (!catalog || !catalog.ok) {
        setVariableCatalogStatusText("未加载");
        return;
    }

    function addSection(titleText) {
        var h = document.createElement("div");
        h.className = "wb-muted";
        h.style.fontSize = "12px";
        h.style.padding = "4px 2px";
        h.textContent = titleText;
        variableListContainerElement.appendChild(h);
    }

    function addVarItem(scope, item) {
        var name = String(item.variable_name || "");
        var type = String(item.variable_type || "");
        var row = document.createElement("div");
        row.className = "wb-list-item";
        row.dataset.scope = scope;
        row.dataset.variableName = name;

        var badge = document.createElement("span");
        badge.className = "wb-badge";
        badge.textContent = scope;

        var title = document.createElement("div");
        title.style.flex = "1";
        title.textContent = name + (type ? (" · " + type) : "");

        row.appendChild(badge);
        row.appendChild(title);

        row.addEventListener("click", function () {
            var placeholder = "{{" + scope + "." + name + "}}";
            if (inputHtmlTextAreaElement) {
                insertTextIntoTextArea(inputHtmlTextAreaElement, placeholder);
            }
            copyTextToClipboard(placeholder);
            setVariableCatalogStatusText("已插入并复制：" + placeholder);
        });

        if (q && name.toLowerCase().indexOf(q) === -1) {
            return;
        }
        variableListContainerElement.appendChild(row);
    }

    addSection("lv（关卡变量）");
    var lv = catalog.lv || [];
    for (var i = 0; i < lv.length; i++) {
        addVarItem("lv", lv[i] || {});
    }

    addSection("ps（玩家变量，仅普通自定义变量）");
    var ps = catalog.ps || [];
    for (var j = 0; j < ps.length; j++) {
        addVarItem("ps", ps[j] || {});
    }

    setVariableCatalogStatusText("lv: " + String(lv.length) + " / ps: " + String(ps.length));
}

export async function refreshVariableCatalog() {
    setVariableCatalogStatusText("正在加载...");
    var resp = await fetch("/api/ui_converter/variable_catalog");
    var contentType = String((resp.headers && resp.headers.get("content-type")) || "").toLowerCase();
    if (contentType.indexOf("application/json") === -1) {
        setVariableCatalogStatusText("未连接主程序（无法加载变量清单）。");
        _variableCatalog = null;
        renderVariableList();
        return;
    }
    var data = await resp.json();
    if (!data || !data.ok) {
        setVariableCatalogStatusText("加载失败：" + String((data && data.error) || resp.statusText || "unknown"));
        _variableCatalog = null;
        renderVariableList();
        return;
    }
    _variableCatalog = data;
    renderVariableList();
}

