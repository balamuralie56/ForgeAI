"""
History Engine module for ForgeAI.
Durable, per-run record of workflows and the reports each one produced.
"""

from .exceptions import HistoryError, InvalidSnapshotError
from .models import REPORT_KINDS, RunDetail, RunSummary, StorageUsage
from .service import ForgeAIHistoryService, HistoryService
from .store import SQLiteHistoryStore

__all__ = [
    "REPORT_KINDS",
    "ForgeAIHistoryService",
    "HistoryError",
    "HistoryService",
    "InvalidSnapshotError",
    "RunDetail",
    "RunSummary",
    "SQLiteHistoryStore",
    "StorageUsage",
]
