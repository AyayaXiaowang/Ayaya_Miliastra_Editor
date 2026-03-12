from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AnalysisCenterStep1Widgets:
    scope_combo: Any
    package_id_label: Any
    scope_hint_label: Any
    picker_host: Any


@dataclass(frozen=True, slots=True)
class AnalysisCenterStep2Widgets:
    query_edit: Any
    type_combo: Any
    result_table: Any
    summary_label: Any
    hint_label: Any
    copy_btn: Any


@dataclass(frozen=True, slots=True)
class AnalysisCenterStep3Widgets:
    build_btn: Any
    cancel_btn: Any
    progress_bar: Any
    progress_label: Any
    log_text: Any
    failures_text: Any


@dataclass(frozen=True, slots=True)
class AnalysisCenterDialogWidgets:
    tabs: Any
    step1: AnalysisCenterStep1Widgets
    step2: AnalysisCenterStep2Widgets
    step3: AnalysisCenterStep3Widgets

