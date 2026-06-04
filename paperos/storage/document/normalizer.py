from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .grobid_models import NormalizedDocument


class DocumentNormalizer:
    """Convert parsed TEI structures into PaperOS normalized JSON."""

    def to_jsonable(self, document: NormalizedDocument) -> dict[str, Any]:
        return asdict(document)
