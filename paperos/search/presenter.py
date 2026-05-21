from ..config import PaperOSConfig
from .models import FulltextStatus, PaperCandidate, PaperSearchResult


class PaperSearchPresenter:
    """Format PaperOS search output for AstrBot command/tool responses."""

    def __init__(self, cfg: PaperOSConfig):
        self.cfg = cfg

    def format_config(self) -> str:
        key_state = "已配置" if self.cfg.core_api.api_key else "未配置"
        return (
            "PaperOS 配置：\n"
            f"- CORE API: {'启用' if self.cfg.core_api.enabled else '禁用'}\n"
            f"- CORE API Key: {key_state}\n"
            f"- 通用 Provider: {self.cfg.general.default_provider_id or '使用当前会话默认'}\n"
            f"- 思考 Provider: {self.cfg.general.thinking_provider_id or '回退到通用 Provider'}\n"
            f"- QueryAnalyzer: {'启用' if self.cfg.query_analyzer.enabled else '禁用'}"
        )

    def format_search_result(self, result: PaperSearchResult, *, compact: bool = False) -> str:
        if result.status == "disabled":
            return "CORE API 当前未启用。"

        header: list[str] = []
        if result.plan is not None:
            header.append(f"解析意图：{result.plan.intent.value}")
            if result.plan.translated_query:
                header.append(f"英文/规范化检索：{result.plan.translated_query}")
            if result.plan.hypotheses:
                kinds = ", ".join(h.kind.value for h in result.plan.hypotheses[:4])
                header.append(f"检索假设：{kinds}")

        if result.status in {"not_found", "error"} or not result.candidates:
            body = f"没有找到合适的论文。{result.message}".strip()
            return "\n".join(header + [body]) if header else body

        display_items = result.selected or result.candidates
        limit = min(len(display_items), self.cfg.search_policy.max_return_candidates)
        if result.selected:
            lines = header + [f"选中 {len(result.selected)} 篇，展示前 {limit} 篇："]
        else:
            lines = header + ["可能存在多个候选，建议人工确认：", f"候选数量：{len(result.candidates)}"]

        for i, cand in enumerate(display_items[:limit], 1):
            lines.append(self.format_candidate(cand, i=i, compact=compact))
        return "\n".join(lines)

    def format_candidate(self, cand: PaperCandidate, *, i: int | None = None, compact: bool = False) -> str:
        prefix = f"{i}. " if i is not None else ""
        authors = ", ".join(cand.authors[:3])
        if len(cand.authors) > 3:
            authors += " et al."

        parts = [
            f"{prefix}{cand.title or '(无标题)'}",
            f" 年份：{cand.year or '未知'}；分数：{cand.score:.2f}；来源：{cand.source}",
        ]
        if authors:
            parts.append(f" 作者：{authors}")
        if cand.venue:
            parts.append(f" 期刊/会议/来源：{cand.venue}")
        if cand.doi:
            parts.append(f" DOI：{cand.doi}")
        if cand.arxiv_id:
            parts.append(f" arXiv：{cand.arxiv_id}")
        if cand.core_id:
            parts.append(f" CORE ID：{cand.core_id}")

        verified_pdf = next(
            (loc for loc in cand.fulltext_locations if loc.status == FulltextStatus.VERIFIED_PDF),
            None,
        )
        if verified_pdf:
            parts.append(f" 已验证 PDF：{verified_pdf.url}")
        elif cand.download_url:
            parts.append(f" PDF/下载候选：{cand.download_url}")
        elif cand.landing_url:
            parts.append(f" Landing：{cand.landing_url}")

        if not compact and cand.score_reason:
            parts.append(f" 匹配依据：{cand.score_reason}")
        return "\n".join(parts)
