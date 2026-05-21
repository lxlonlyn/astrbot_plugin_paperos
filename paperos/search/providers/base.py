from abc import ABC, abstractmethod

from ..models import FulltextLocation, PaperCandidate, SearchPlan


class MetadataProvider(ABC):
    """Abstract metadata provider.

    New APIs such as OpenAlex, Crossref, Semantic Scholar should implement this
    interface instead of being called directly from pipeline/service.
    """

    name: str

    @abstractmethod
    async def search(self, plan: SearchPlan) -> list[PaperCandidate]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class FulltextProvider(ABC):
    """Abstract fulltext provider.

    It only proposes candidate locations. Verification and downloading are handled
    in acquire/verifier.py and acquire/downloader.py.
    """

    name: str

    @abstractmethod
    async def resolve(self, paper: PaperCandidate) -> list[FulltextLocation]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None
