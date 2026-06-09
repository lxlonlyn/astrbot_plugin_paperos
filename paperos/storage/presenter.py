from __future__ import annotations

from typing import Any

from .diagnostics import StoragePaperInfo, StorageStatus


class StoragePresenter:
    def format_status(self, status: StorageStatus) -> str:
        lines = ["PaperOS Storage Status"]
        lines.extend(
            f"- {self._mark(check.ok)} {check.name}: {check.detail}"
            for check in status.checks
        )
        lines.append(f"- schema_version: {status.schema_version if status.schema_version is not None else '-'}")

        stats = status.stats
        jobs = stats.jobs_by_status
        lines.extend(
            [
                "",
                "Stats",
                f"- papers: {self._value(stats.papers)}",
                f"- objects: {self._value(stats.objects)}",
                f"- PDF objects: {self._value(stats.pdf_objects)}",
                f"- fulltext_locations: {self._value(stats.fulltext_locations)}",
                f"- chunks: {self._value(stats.chunks)}",
                (
                    "- jobs: "
                    f"pending={jobs.get('pending', 0)}, "
                    f"running={jobs.get('running', 0)}, "
                    f"done={jobs.get('done', 0)}, "
                    f"failed={jobs.get('failed', 0)}"
                ),
                f"- objects size: {self._size(stats.objects_size_bytes)}",
                f"- SQLite size: {self._size(stats.sqlite_size_bytes)}",
                f"- indexes size: {self._size(stats.indexes_size_bytes)}",
            ]
        )
        return "\n".join(lines)

    def format_info(self, info: StoragePaperInfo) -> str:
        if not info.found:
            lines = [f"PaperOS Storage Info: not found for {info.query!r}"]
            if info.matches:
                lines.append("Possible title matches:")
                lines.extend(f"- {paper_id}: {title}" for paper_id, title in info.matches)
            return "\n".join(lines)

        lines = [
            "PaperOS Storage Info",
            f"- paper_id: {info.paper_id}",
            f"- title: {info.title}",
            f"- year: {self._value(info.year)}",
            f"- venue: {self._value(info.venue)}",
            f"- current_version_id: {self._value(info.current_version_id)}",
            f"- verified_pdf: {self._value(info.verified_pdf_status)}",
            f"- chunks: {self._value(info.chunk_count)}",
        ]

        lines.append("Identifiers:")
        lines.extend(
            [f"- {scheme}: {value}" for scheme, value in info.identifiers]
            or ["- none"]
        )

        lines.append("Objects:")
        if info.objects:
            for obj in info.objects:
                exists = "exists" if obj.file_exists else "missing"
                lines.append(
                    f"- {obj.object_id}: kind={obj.kind}, role={obj.role or '-'}, "
                    f"size={self._size(obj.size_bytes)}, sha256={obj.sha256[:12]}, file={exists}"
                )
        else:
            lines.append("- none")

        lines.append("Index Status:")
        if info.index_status:
            for item in info.index_status:
                profile = item.get("profile") or "-"
                message = item.get("message") or ""
                suffix = f", message={message}" if message else ""
                lines.append(
                    f"- {item.get('index_name')}: status={item.get('status')}, "
                    f"profile={profile}, updated_at={item.get('updated_at')}{suffix}"
                )
        else:
            lines.append("- none")

        lines.append("Recent Jobs:")
        if info.recent_jobs:
            for job in info.recent_jobs:
                suffix = f", error={job.error_message}" if job.error_message else ""
                lines.append(
                    f"- {job.job_id}: type={job.job_type}, status={job.status}, "
                    f"updated_at={job.updated_at}{suffix}"
                )
        else:
            lines.append("- none")

        return "\n".join(lines)

    def format_import_summary(self, summary: Any) -> str:
        results = list(getattr(summary, "results", []) or [])
        if not results:
            return "Storage 入库：未写入任何论文"

        imported = getattr(summary, "imported_count", len(results))
        pdf_count = getattr(summary, "pdf_count", 0)
        job_count = getattr(summary, "job_count", 0)
        lines = [
                "Storage 入库：",
                f"- papers: {imported}",
                f"- PDF objects: {pdf_count}",
                f"- processing jobs: {job_count}",
        ]
        for idx, item in enumerate(results, start=1):
            title = self._short(getattr(item, "title", "") or "-", 72)
            paper_id = getattr(item, "paper_id", None) or "-"
            object_id = getattr(item, "object_id", None) or "-"
            job_id = getattr(item, "job_id", None) or "-"
            rag_job_id = getattr(item, "rag_job_id", None) or "-"
            parser_run_id = getattr(item, "parser_run_id", None) or "-"
            message = getattr(item, "message", None) or ""
            mode = "pdf" if getattr(item, "imported_pdf", False) else "metadata-only"
            cleanup = "cleaned" if getattr(item, "temporary_pdf_removed", False) else "kept"
            suffix = f"; parser_run_id={parser_run_id}"
            if message:
                suffix += f"; message={message}"
            lines.append(
                f"{idx}. {title}\n"
                f"   paper_id={paper_id}; object_id={object_id}; "
                f"job_id={job_id}; rag_job_id={rag_job_id}; "
                f"mode={mode}; temp={cleanup}{suffix}"
            )
        return "\n".join(lines)

    def format_rag_index_summary(self, attempts: list[Any]) -> str:
        if not attempts:
            return "RAG indexing：未执行"

        ok_count = sum(1 for item in attempts if getattr(item, "ok", False))
        failed = [item for item in attempts if not getattr(item, "ok", False)]
        vector_count = sum(int(getattr(item, "vector_count", 0) or 0) for item in attempts)
        lines = [
            "RAG indexing：",
            f"- parser_runs: {len(attempts)}",
            f"- indexed: {ok_count}",
            f"- failed: {len(failed)}",
            f"- vectors: {vector_count}",
        ]
        for item in failed:
            parser_run_id = getattr(item, "parser_run_id", None) or "-"
            paper_id = getattr(item, "paper_id", None) or "-"
            error = self._short(getattr(item, "error", "") or "vector indexing failed", 160)
            lines.append(
                f"- vector indexing failed: paper_id={paper_id}; parser_run_id={parser_run_id}; error={error}"
            )
        return "\n".join(lines)

    def _mark(self, ok: bool) -> str:
        return "OK" if ok else "WARN"

    def _value(self, value) -> str:
        return str(value) if value is not None and value != "" else "-"

    def _size(self, value: int | None) -> str:
        if value is None:
            return "-"
        units = ["B", "KB", "MB", "GB"]
        amount = float(value)
        for unit in units:
            if amount < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(amount)} {unit}"
                return f"{amount:.1f} {unit}"
            amount /= 1024

    def _short(self, text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 3] + "..."
