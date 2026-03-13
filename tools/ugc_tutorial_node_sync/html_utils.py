from __future__ import annotations

"""UGC 教程页面 HTML 抽取与参数表解析工具。"""

import html as html_lib
import re
from typing import List, Optional, Tuple


DOC_PARAM_TABLE_HEADERS = ("参数类型", "参数名", "类型", "说明")


def strip_heading_index(text: str) -> str:
    # Remove heading numeric prefixes and normalize whitespace for stable node names.
    t = str(text or "").strip()
    t = re.sub(r"^\s*\d+\s*[\.、]\s*", "", t)
    t = re.sub(r"\s+", "", t)
    return t.strip()


def normalize_doc_type(type_text: str) -> str:
    # Normalize upstream doc type names into Graph_Generater port type names.
    t = str(type_text or "").strip()
    mapping = {
        "布尔": "布尔值",
        "bool": "布尔值",
        "Boolean": "布尔值",
        "整型": "整数",
        "int": "整数",
        "Integer": "整数",
        "string": "字符串",
        "String": "字符串",
        "float": "浮点数",
        "Float": "浮点数",
    }
    if t in mapping:
        return mapping[t]
    if t == "":
        raise ValueError("Empty doc type")
    return t


def extract_text_by_tag(html: str, tag: str) -> List[str]:
    # Extract text content from HTML elements of the given tag.
    pat = re.compile(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}>", re.IGNORECASE)
    out: List[str] = []
    for m in pat.finditer(html):
        inner = m.group(1)
        text = re.sub(r"<[^>]+>", " ", inner)
        text = html_lib.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        out.append(text)
    return out


def extract_h1_h2_titles(html: str) -> Tuple[List[str], List[str]]:
    # Extract h1/h2 titles from HTML.
    h1 = extract_text_by_tag(html, "h1")
    h2 = extract_text_by_tag(html, "h2")
    return h1, h2


def iter_tables(html: str):
    # Iterate over <table> blocks found in HTML.
    pat = re.compile(r"<table\b[\s\S]*?</table>", re.IGNORECASE)
    for m in pat.finditer(html):
        yield m.group(0)


def extract_td_cells_text(table_html: str) -> List[str]:
    # Extract a flat list of <td> cell texts from a table HTML fragment.
    td_blocks = re.findall(r"<td\b[\s\S]*?</td>", table_html, flags=re.IGNORECASE)
    out: List[str] = []
    for td in td_blocks:
        text = re.sub(r"<[^>]+>", " ", td)
        text = html_lib.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        out.append(text)
    return out


def try_parse_param_table_rows(table_html: str) -> Optional[List[Tuple[str, str, str, str]]]:
    # Parse a UGC doc param table into fixed 4-column rows when headers match.
    cells = extract_td_cells_text(table_html)
    if len(cells) < len(DOC_PARAM_TABLE_HEADERS):
        return None

    col_count = len(DOC_PARAM_TABLE_HEADERS)
    if len(cells) % col_count != 0:
        return None

    rows: List[Tuple[str, str, str, str]] = []
    for i in range(0, len(cells), col_count):
        rows.append((cells[i], cells[i + 1], cells[i + 2], cells[i + 3]))

    if DOC_PARAM_TABLE_HEADERS not in rows:
        return None
    return rows

