from ..config import PaperOSConfig
from .models import PaperCandidate, PaperSearchResult


class PaperSearchPresenter:
    """Format PaperOS search output for AstrBot command/tool responses."""

    def __init__(self, cfg: PaperOSConfig):
        self.cfg = cfg

    def format_config(self) -> str:
        provider = self.cfg.query_analyzer.provider_id or self.cfg.general.default_provider_id or "使用当前会话默认"
        return (
            "PaperOS 配置：\n"
            f"- QueryAnalyzer: {'启用' if self.cfg.query_analyzer.enabled else '禁用'}\n"
            f"- QueryAnalyzer Provider: {provider}\n"
            f"- Targeted crawler: {'启用' if self.cfg.crawler.enabled else '禁用'}\n"
            "- 通用网页搜索后端: 不使用\n"
            "- 学术聚合 API 主链路: 不使用\n"
            f"- Fulltext PDF 下载验证: {'启用' if self.cfg.search_policy.enable_fulltext_verify else '禁用'}"
        )

    def format_search_result(self, result: PaperSearchResult, *, compact: bool = False) -> str:
        if result.status == "disabled":
            return f"PaperOS searcher 当前不可用：{result.message}"

        header: list[str] = []
        if result.plan is not None:
            header.append(f"解析意图：{result.plan.intent.value}")
            if result.plan.translated_query:
                header.append(f"英文/规范化描述：{result.plan.translated_query}")
            if result.plan.hypotheses:
                kinds = ", ".join(h.kind.value for h in result.plan.hypotheses[:4])
                header.append(f"检索假设：{kinds}")

        if result.status == "not_found":
            lines = header + [f"没有取得合格 PDF。{result.message}".strip()]
            if result.candidates:
                lines.append(f"候选数量：{len(result.candidates)}")
                lines.append("注意：HTML/landing 页面不算合格 fulltext，已被视为未取得 PDF。")
            return "\n".join(lines)

        if result.status == "error" or not result.candidates:
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
        prefix = f"{i}.\n" if i is not None else ""
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
        if cand.landing_url:
            parts.append(f" Landing：{cand.landing_url}")

        pdf = cand.best_verified_pdf()
        if pdf:
            parts.append(f" 已下载并验证 PDF：{pdf.local_path}")
            if pdf.sha256:
                parts.append(f" PDF sha256：{pdf.sha256[:16]}…")
            if pdf.page_count is not None:
                parts.append(f" PDF 页数：{pdf.page_count}")
        else:
            parts.append(" PDF：未取得可验证本地 PDF")

        if not compact and cand.score_reason:
            parts.append(f" 匹配依据：{cand.score_reason}")
        return "\n".join(parts)
