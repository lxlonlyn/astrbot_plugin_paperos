"""Cross-module workflows that compose PaperOS core modules."""

from .search_storage import (
    SearchStorageImportResult,
    SearchStorageImportSummary,
    SearchStorageImportWorkflow,
    paper_candidate_to_record,
)

__all__ = [
    "SearchStorageImportResult",
    "SearchStorageImportSummary",
    "SearchStorageImportWorkflow",
    "paper_candidate_to_record",
]
