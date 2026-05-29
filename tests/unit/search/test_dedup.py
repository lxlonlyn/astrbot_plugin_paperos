from __future__ import annotations

from paperos.search.models import FulltextLocation, PaperCandidate
from paperos.search.resolve.dedup import PaperDeduplicator


def test_dedup_merges_truncated_pdf_title_with_arxiv_candidate():
    arxiv = PaperCandidate(
        title="DeepSDF: Learning Continuous Signed Distance Functions for Shape Representation",
        arxiv_id="1901.05103",
        landing_url="https://arxiv.org/abs/1901.05103",
        fulltext_locations=[
            FulltextLocation(url="https://arxiv.org/pdf/1901.05103.pdf", source="arxiv", confidence=0.96)
        ],
        source="arxiv_url",
        score=1.0,
    )
    cvf = PaperCandidate(
        title="[PDF] DeepSDF: Learning Continuous Signed Distance Functions for ...",
        landing_url=(
            "https://openaccess.thecvf.com/content_CVPR_2019/papers/"
            "Park_DeepSDF_Learning_Continuous_Signed_Distance_Functions_for_"
            "Shape_Representation_CVPR_2019_paper.pdf"
        ),
        fulltext_locations=[
            FulltextLocation(
                url=(
                    "https://openaccess.thecvf.com/content_CVPR_2019/papers/"
                    "Park_DeepSDF_Learning_Continuous_Signed_Distance_Functions_for_"
                    "Shape_Representation_CVPR_2019_paper.pdf"
                ),
                source="llm_url",
                confidence=0.85,
            )
        ],
        source="llm_url",
        score=1.0,
    )

    out = PaperDeduplicator().dedup([arxiv, cvf])

    assert len(out) == 1
    assert out[0].arxiv_id == "1901.05103"
    assert len(out[0].fulltext_locations) == 2
    assert out[0].raw["paperos_merged_duplicates"][0]["source"] == "llm_url"


def test_dedup_merges_locations_when_lower_quality_duplicate_arrives_later():
    old = PaperCandidate(
        title="Attention Is All You Need",
        doi="10.5555/attention",
        fulltext_locations=[
            FulltextLocation(url="https://example.test/a.pdf", source="a", confidence=0.9)
        ],
        score=1.0,
    )
    duplicate = PaperCandidate(
        title="Attention Is All You Need",
        doi="10.5555/attention",
        fulltext_locations=[
            FulltextLocation(url="https://example.test/b.pdf", source="b", confidence=0.8)
        ],
        score=0.5,
    )

    out = PaperDeduplicator().dedup([old, duplicate])

    assert len(out) == 1
    assert {loc.url for loc in out[0].fulltext_locations} == {
        "https://example.test/a.pdf",
        "https://example.test/b.pdf",
    }
