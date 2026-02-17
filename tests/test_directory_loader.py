from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langchain_hwp_hwpx.loader import HwpHwpxDirectoryLoader


class FakeReader:
    def __init__(self, file_path: str) -> None:
        path = Path(file_path)
        self.file_type = path.suffix.lstrip(".")
        self.is_encrypted = False
        self.is_valid = True
        self._name = path.name

    def extract_text_with_notes(self, *_args):
        return SimpleNamespace(text=f"body::{self._name}", notes=[], memos=[], hyperlinks=[])

    def get_tables(self):
        return []

    def get_images(self):
        return []


def test_directory_loader_orders_files_stably(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "b.hwp").write_text("x", encoding="utf-8")
    (tmp_path / "a.hwpx").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.hwp").write_text("x", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("x", encoding="utf-8")

    parser = SimpleNamespace(Reader=FakeReader)
    monkeypatch.setattr("langchain_hwp_hwpx.loader._import_parser", lambda: parser)

    loader = HwpHwpxDirectoryLoader(dir_path=tmp_path, mode="single")
    docs = loader.load()

    sources = [doc.metadata["source"] for doc in docs]
    assert sources == sorted(sources)
    assert len(sources) == 3
    assert all(source.endswith((".hwp", ".hwpx")) for source in sources)


def test_directory_loader_non_recursive(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "top.hwp").write_text("x", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "child.hwpx").write_text("x", encoding="utf-8")

    parser = SimpleNamespace(Reader=FakeReader)
    monkeypatch.setattr("langchain_hwp_hwpx.loader._import_parser", lambda: parser)

    loader = HwpHwpxDirectoryLoader(dir_path=tmp_path, recursive=False, mode="single")
    docs = loader.load()

    assert len(docs) == 1
    assert docs[0].metadata["source"].endswith("top.hwp")
