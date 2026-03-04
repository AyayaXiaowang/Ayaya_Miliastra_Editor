from __future__ import annotations

from pathlib import Path
from typing import Optional


class _UiWorkbenchBridgeExportTokenStoreMixin:
    def try_resolve_exported_gil_by_token(self, token: str) -> Optional[Path]:
        key = str(token or "").strip()
        if key == "":
            return None
        path = self._exported_gil_paths_by_token.get(key)
        if path is None:
            return None
        resolved = Path(path).resolve()
        if not resolved.is_file():
            return None
        return resolved

    def try_resolve_exported_gia_by_token(self, token: str) -> Optional[Path]:
        key = str(token or "").strip()
        if key == "":
            return None
        path = self._exported_gia_paths_by_token.get(key)
        if path is None:
            return None
        resolved = Path(path).resolve()
        if not resolved.is_file():
            return None
        return resolved

