from __future__ import annotations

from dataclasses import dataclass

import pytest

from paperos.utils.astrbot_files import (
    copy_pdf_to_upload_tmp,
    event_has_file_message,
    extract_local_pdf_from_event,
)


@dataclass
class FileComponent:
    file: str = ""
    name: str = "paper.pdf"


class Event:
    def __init__(self, message):
        self.message_obj = type("MessageObj", (), {"message": message})()


def test_extract_local_pdf_from_event_and_copy_to_upload_tmp(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.7\ncontent")
    event = Event([FileComponent(file=str(source), name="source.pdf")])

    ref = extract_local_pdf_from_event(event)

    assert ref is not None
    assert ref.name == "source.pdf"
    assert ref.size_bytes == source.stat().st_size
    dest = copy_pdf_to_upload_tmp(ref, tmp_dir=tmp_path / "tmp", max_size_mb=1)
    assert dest.exists()
    assert dest.parent.name == "uploads"
    assert dest.read_bytes() == source.read_bytes()


def test_extract_local_pdf_from_event_ignores_url_only_files():
    event = Event([FileComponent(file="https://example.test/paper.pdf")])

    assert event_has_file_message(event) is True
    assert extract_local_pdf_from_event(event) is None


def test_copy_pdf_to_upload_tmp_rejects_oversized_pdf(tmp_path):
    source = tmp_path / "big.pdf"
    source.write_bytes(b"%PDF-" + b"x" * 2048)
    ref = extract_local_pdf_from_event(Event([FileComponent(file=str(source))]))

    assert ref is not None
    with pytest.raises(ValueError, match="PDF 文件过大"):
        copy_pdf_to_upload_tmp(ref, tmp_dir=tmp_path / "tmp", max_size_mb=0)
