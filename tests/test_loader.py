from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from types import SimpleNamespace

import pytest

from langchain_hwp_hwpx.loader import HwpHwpxLoader, HwpHwpxLoaderError


class FakeFileType(Enum):
    HWP5 = auto()
    HWPX = auto()


class FakeTable:
    row_count = 2
    col_count = 2

    def to_markdown(self) -> str:
        return "|A|B|\n|---|---|\n|1|2|"

    def to_csv(self, delimiter: str = ",") -> str:
        return f"A{delimiter}B\n1{delimiter}2"

    def to_inline(self) -> str:
        return "A:1, B:2"


class FakeImage:
    def __init__(self, filename: str | None = None, fmt: str = "png") -> None:
        self.filename = filename
        self.format = fmt
        self.saved = None

    def save(self, path: str) -> None:
        self.saved = path
        Path(path).write_bytes(b"img")


class FakeReader:
    def __init__(self, _: str) -> None:
        self.file_type = FakeFileType.HWP5
        self.is_encrypted = False
        self.is_valid = True
        self.text = "본문 텍스트"
        self.raise_extract = False

    def extract_text_with_notes(self, *_args):
        if self.raise_extract:
            raise RuntimeError("parse-fail")
        return SimpleNamespace(
            text="본문 [footnote:1]",
            notes=[
                SimpleNamespace(note_type="footnote", number=1, text="각주 내용"),
                SimpleNamespace(note_type="endnote", number=2, text="미주 내용"),
            ],
            memos=[SimpleNamespace(id="m1", author="tester", text="메모 내용")],
            hyperlinks=[("사이트", "https://example.com")],
        )

    def get_tables(self):
        return [FakeTable()]

    def get_images(self):
        return [FakeImage(filename="diagram.png", fmt="png")]


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "sample.hwp"
    file_path.write_text("dummy", encoding="utf-8")
    return file_path


@pytest.fixture
def fake_parser(monkeypatch):
    parser = SimpleNamespace(Reader=FakeReader)
    monkeypatch.setattr("langchain_hwp_hwpx.loader._import_parser", lambda: parser)
    return parser


def test_single_mode_contains_required_sections(sample_file: Path, fake_parser) -> None:
    loader = HwpHwpxLoader(
        file_path=sample_file,
        mode="single",
        include_tables=True,
        include_notes=True,
        include_memos=True,
        include_hyperlinks=True,
    )
    docs = list(loader.lazy_load())

    assert len(docs) == 1
    assert "본문" in docs[0].page_content
    assert "## Tables" in docs[0].page_content
    assert "## Notes" in docs[0].page_content
    assert "## Memos" in docs[0].page_content
    assert "## Hyperlinks" in docs[0].page_content
    assert "- 사이트: https://example.com" in docs[0].page_content
    assert docs[0].metadata["source"] == str(sample_file)
    assert docs[0].metadata["file_type"] == "hwp"


def test_elements_mode_returns_stable_metadata(sample_file: Path, fake_parser) -> None:
    loader = HwpHwpxLoader(
        file_path=sample_file,
        mode="elements",
        include_tables=True,
        include_notes=True,
        include_memos=True,
        include_hyperlinks=True,
        include_images=True,
    )
    docs = list(loader.lazy_load())

    element_types = [doc.metadata["element_type"] for doc in docs]
    assert element_types == [
        "body",
        "table",
        "footnote",
        "endnote",
        "memo",
        "hyperlink",
        "image",
    ]
    assert [doc.metadata["element_index"] for doc in docs] == list(range(len(docs)))
    assert docs[1].metadata["row_count"] == 2
    assert docs[1].metadata["col_count"] == 2
    assert docs[2].metadata["note_number"] == 1
    assert docs[5].metadata["url"] == "https://example.com"
    assert docs[5].metadata["text"] == "사이트"
    assert docs[5].page_content == "사이트"


def test_csv_style_uses_table_delimiter(sample_file: Path, fake_parser) -> None:
    opts = SimpleNamespace(
        table_style=SimpleNamespace(name="CSV"),
        table_delimiter=";",
        paragraph_separator="\n\n",
    )
    loader = HwpHwpxLoader(file_path=sample_file, mode="single", extract_options=opts)

    docs = list(loader.lazy_load())

    assert "A;B\n1;2" in docs[0].page_content


def test_encrypted_policy_placeholder(sample_file: Path, fake_parser, monkeypatch) -> None:
    class EncryptedReader(FakeReader):
        def __init__(self, value: str) -> None:
            super().__init__(value)
            self.is_encrypted = True

    parser = SimpleNamespace(Reader=EncryptedReader)
    monkeypatch.setattr("langchain_hwp_hwpx.loader._import_parser", lambda: parser)

    loader = HwpHwpxLoader(file_path=sample_file, on_encrypted="placeholder")
    docs = list(loader.lazy_load())

    assert len(docs) == 1
    assert "ENCRYPTED" in docs[0].page_content
    assert docs[0].metadata["status"] == "encrypted"


def test_encrypted_policy_skip_returns_empty(sample_file: Path, fake_parser, monkeypatch) -> None:
    class EncryptedReader(FakeReader):
        def __init__(self, value: str) -> None:
            super().__init__(value)
            self.is_encrypted = True

    parser = SimpleNamespace(Reader=EncryptedReader)
    monkeypatch.setattr("langchain_hwp_hwpx.loader._import_parser", lambda: parser)

    loader = HwpHwpxLoader(file_path=sample_file, on_encrypted="skip")
    docs = list(loader.lazy_load())

    assert docs == []


def test_on_error_raise_wraps_exception(sample_file: Path, fake_parser, monkeypatch) -> None:
    class FailingReader(FakeReader):
        def extract_text_with_notes(self, *_args):
            raise RuntimeError("boom")

    parser = SimpleNamespace(Reader=FailingReader)
    monkeypatch.setattr("langchain_hwp_hwpx.loader._import_parser", lambda: parser)

    loader = HwpHwpxLoader(file_path=sample_file, on_error="raise")
    with pytest.raises(HwpHwpxLoaderError):
        list(loader.lazy_load())


def test_on_error_warn_skips(sample_file: Path, fake_parser, caplog, monkeypatch) -> None:
    class FailingReader(FakeReader):
        def extract_text_with_notes(self, *_args):
            raise RuntimeError("boom")

    parser = SimpleNamespace(Reader=FailingReader)
    monkeypatch.setattr("langchain_hwp_hwpx.loader._import_parser", lambda: parser)

    loader = HwpHwpxLoader(file_path=sample_file, on_error="warn")
    docs = list(loader.lazy_load())

    assert docs == []
    assert any("Failed to parse" in record.message for record in caplog.records)
