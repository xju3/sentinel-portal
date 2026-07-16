"""Compatibility wrapper for the shared quick-history Redis helpers."""

from pub.services import (
    QUICK_HISTORY_KEY_PREFIX,
    QUICK_HISTORY_LIMIT,
    QUICK_LAST_REGULAR_KEY_PREFIX,
    QuickDiagnosisSnapshot,
    build_quick_diagnosis_snapshot,
    get_last_regular_snapshot,
    get_recent_snapshots,
    record_quick_diagnosis_snapshot,
)

__all__ = [
    "QUICK_HISTORY_KEY_PREFIX",
    "QUICK_HISTORY_LIMIT",
    "QUICK_LAST_REGULAR_KEY_PREFIX",
    "QuickDiagnosisSnapshot",
    "build_quick_diagnosis_snapshot",
    "get_last_regular_snapshot",
    "get_recent_snapshots",
    "record_quick_diagnosis_snapshot",
]
