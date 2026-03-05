from __future__ import annotations

import json
from typing import Any


def read_request_body_bytes(handler: object) -> bytes:
    headers = getattr(handler, "headers", None)
    length = int(headers.get("Content-Length", "0") or "0") if headers is not None else 0
    rfile = getattr(handler, "rfile", None)
    if rfile is None:
        return b""
    return rfile.read(length) if length > 0 else b""


def read_request_json_object(handler: object) -> dict[str, Any]:
    raw = read_request_body_bytes(handler)
    text = raw.decode("utf-8") if raw else "{}"
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("request json must be object(dict)")
    return payload


def send_json(handler: object, payload: dict[str, Any], *, status: int) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    getattr(handler, "send_response")(int(status))
    getattr(handler, "send_header")("Content-Type", "application/json; charset=utf-8")
    getattr(handler, "send_header")("Content-Length", str(len(body)))
    getattr(handler, "end_headers")()
    getattr(getattr(handler, "wfile"), "write")(body)


def get_bridge_or_send_error(handler: object, bridge: object | None, *, status: int, message: str) -> object | None:
    if bridge is None:
        getattr(handler, "send_error")(int(status), str(message))
        return None
    return bridge


def get_bridge_or_503_json(
    handler: object,
    bridge: object | None,
    *,
    connected_field: bool = True,
) -> object | None:
    if bridge is None:
        payload: dict[str, Any] = {"ok": False, "error": "bridge not ready"}
        if connected_field:
            payload["connected"] = False
        send_json(handler, payload, status=503)
        return None
    return bridge

