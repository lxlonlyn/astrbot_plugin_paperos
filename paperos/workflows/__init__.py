"""Cross-module workflows that compose PaperOS core modules."""

from .paper_discovery import (
    DiscoveryPipelineResult,
    PaperDiscoveryWorkflow,
)
from .search_storage import (
    SearchStorageImportResult,
    SearchStorageImportSummary,
    SearchStorageImportWorkflow,
    paper_candidate_to_record,
)

__all__ = [
    "DiscoveryPipelineResult",
    "PaperDiscoveryWorkflow",
    "SearchStorageImportResult",
    "SearchStorageImportSummary",
    "SearchStorageImportWorkflow",
    "paper_candidate_to_record",
]
