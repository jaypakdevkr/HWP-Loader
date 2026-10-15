"""Regression tests with real parser inputs (no university document bundled)."""

import io
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from hwp_hwpx_parser.hwp5 import HWPTAG_LIST_HEADER, HWPTAG_PARA_TEXT, HWPTAG_TABLE
from hwp_hwpx_parser.models import ExtractOptions

from langchain_hwp_hwpx import HwpHwpxDirectoryLoader, HwpHwpxLoader, HwpHwpxLoaderError
from langchain_hwp_hwpx.parser_compat import HwpReader, IntegrityReader, build_table


def cell(row, col, text, rowspan=1, colspan=1):
    return (
        f'<tc><cellAddr rowAddr="{row}" colAddr="{col}"/>'
        f'<cellSpan rowSpan="{rowspan}" colSpan="{colspan}"/>'
        f"<subList><p><run><t>{text}</t></run></p></subList></tc>"
    )


def hwpx(path, sections, image=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        for number, content in sections.items():
            z.writestr(f"Contents/section{number}.xml", f"<sec>{content}</sec>")
        if image is not None:
            z.writestr("BinData/image1.png", image)
    return path


@pytest.fixture
def table_file(tmp_path):
    table = (
        '<tbl rowCnt="2" colCnt="2"><tr>'
        + cell(0, 0, "공통", rowspan=2)
        + cell(0, 1, "첫값")
        + "</tr><tr>"
        + cell(1, 1, "둘째값")
        + "</tr></tbl>"
    )
    return hwpx(tmp_path / "table.hwpx", {0: "<p><run><t>본문</t>" + table + "</run></p>"})


@pytest.mark.parametrize("mode", ["single", "elements"])
def test_table_once_and_excluded(table_file, mode):
    docs = HwpHwpxLoader(table_file, mode=mode).load()
    content = "\n".join(d.page_content for d in docs)
    assert content.count("첫값") == 1
    assert content.count("둘째값") == 1
    excluded = HwpHwpxLoader(table_file, mode=mode, include_tables=False).load()
    assert "\n".join(d.page_content for d in excluded) == "본문"


def test_merged_cell_position_and_metadata(table_file):
    table = HwpHwpxLoader(table_file, mode="elements").load()[1]
    assert "| [merged:R1C1] | 둘째값 |" in table.page_content
    assert table.metadata["cells"][0] == dict(row=0, col=0, rowspan=2, colspan=1, text="공통")
    assert table.metadata["cells"][2]["col"] == 1


def test_table_only_and_nested(tmp_path):
    inner = '<tbl rowCnt="1" colCnt="1"><tr>' + cell(0, 0, "INNER") + "</tr></tbl>"
    outer = '<tbl rowCnt="1" colCnt="1"><tr>' + cell(0, 0, "OUTER" + inner) + "</tr></tbl>"
    p = hwpx(tmp_path / "nested.hwpx", {0: "<p><run>" + outer + "</run></p>"})
    docs = HwpHwpxLoader(p, mode="elements").load()
    assert len(docs) == 1
    assert docs[0].page_content.count("INNER") == 1
    assert docs[0].page_content.count("OUTER") == 1
    assert HwpHwpxLoader(p, include_tables=False).load()[0].page_content == ""


def test_section_order(tmp_path):
    p = hwpx(
        tmp_path / "sections.hwpx",
        {
            10: "<p><run><t>ten</t></run></p>",
            2: "<p><run><t>two</t></run></p>",
            0: "<p><run><t>zero</t></run></p>",
        },
    )
    text = HwpHwpxLoader(p).load()[0].page_content
    assert text.index("zero") < text.index("two") < text.index("ten")


def test_real_zip_closed(table_file, monkeypatch):
    reader = IntegrityReader(table_file)
    archive = reader._get_reader()._open()
    monkeypatch.setattr(HwpHwpxLoader, "_create_reader", lambda *_: reader)
    HwpHwpxLoader(table_file).load()
    assert archive.fp is None


@pytest.mark.parametrize("policy", ["raise", "skip", "placeholder"])
@pytest.mark.parametrize("status", ["encrypted", "invalid", "unsupported"])
def test_reader_closed_on_status(table_file, monkeypatch, status, policy):
    closed = []
    reader = SimpleNamespace(
        is_encrypted=status == "encrypted",
        is_valid=status != "invalid",
        unsupported_reason="distribution" if status == "unsupported" else None,
        close=lambda: closed.append(True),
    )
    monkeypatch.setattr(HwpHwpxLoader, "_create_reader", lambda *_: reader)
    loader = HwpHwpxLoader(table_file, **{f"on_{status}": policy})
    if policy == "raise":
        with pytest.raises(HwpHwpxLoaderError):
            loader.load()
    else:
        result = loader.load()
        assert len(result) == (policy == "placeholder")
    assert closed == [True]


def test_close_on_failure_and_generator_close(table_file, monkeypatch):
    reader = IntegrityReader(table_file)
    archive = reader._get_reader()._open()
    monkeypatch.setattr(HwpHwpxLoader, "_create_reader", lambda *_: reader)
    gen = HwpHwpxLoader(table_file, mode="elements").lazy_load()
    next(gen)
    gen.close()
    assert archive.fp is None
    reader = IntegrityReader(table_file)
    archive = reader._get_reader()._open()

    def fail(*args):
        raise ValueError("fixture failure")

    monkeypatch.setattr(reader, "extract_text_with_notes", fail)
    with pytest.raises(HwpHwpxLoaderError):
        HwpHwpxLoader(table_file).load()
    assert archive.fp is None


def test_directory_images_do_not_overwrite(tmp_path):
    for name, data in [("one", b"\x89PNG\r\n\x1a\nfirst"), ("two", b"\x89PNG\r\n\x1a\nsecond")]:
        hwpx(tmp_path / f"{name}.hwpx", {0: "<p><run><t>body</t></run></p>"}, data)
    docs = HwpHwpxDirectoryLoader(
        tmp_path,
        mode="elements",
        include_images=True,
        image_document_mode="save_and_reference",
        images_dir=tmp_path / "images",
    ).load()
    paths = [Path(d.metadata["saved_path"]) for d in docs if d.metadata["element_type"] == "image"]
    assert len(paths) == len(set(paths)) == 2
    assert {p.read_bytes() for p in paths} == {
        b"\x89PNG\r\n\x1a\nfirst",
        b"\x89PNG\r\n\x1a\nsecond",
    }


def test_image_filename_cannot_escape(tmp_path):
    p = hwpx(tmp_path / "file.hwpx", {0: "<p/>"})
    image = SimpleNamespace(
        filename="../../escape.png",
        format="../png",
        save=lambda path: Path(path).write_bytes(b"image"),
    )
    metadata = {}
    HwpHwpxLoader(
        p, image_document_mode="save_and_reference", images_dir=tmp_path / "images"
    )._materialize_image(p, 0, image, metadata)
    assert Path(metadata["saved_path"]).is_relative_to(tmp_path / "images")
    assert not (tmp_path / "escape.png").exists()


def test_distribution_flag_uses_header_bit(monkeypatch):
    reader = HwpReader("unused.hwp")
    for flags, expected in [(0, False), (1, False), (5, True), (4, True)]:
        header = b"\0" * 36 + struct.pack("<I", flags)
        monkeypatch.setattr(
            reader, "_open", lambda: SimpleNamespace(openstream=lambda _: io.BytesIO(header))
        )
        assert reader.distributable is expected


def hwp_cell(row, col, text, rowspan=1, colspan=1):
    header = b"\0" * 8 + struct.pack("<4H", col, row, colspan, rowspan) + b"\0" * 18
    return [(HWPTAG_LIST_HEADER, 2, header), (HWPTAG_PARA_TEXT, 3, text.encode("utf-16le"))]


def test_hwp_binary_cells_and_table_boundary():
    reader = HwpReader("unused.hwp")
    # Table properties, dimensions, spacing/margins, per-row physical cell counts.
    shape = struct.pack("<IHH", 0, 2, 2) + b"\0" * 10 + struct.pack("<2H", 2, 1)
    records = [(HWPTAG_TABLE, 2, shape)]
    records += (
        hwp_cell(0, 0, "COMMON", rowspan=2) + hwp_cell(0, 1, "FIRST") + hwp_cell(1, 1, "SECOND")
    )
    records += [(HWPTAG_PARA_TEXT, 1, "AFTER".encode("utf-16le"))]
    table = reader._extract_table_at(records, 0, ExtractOptions())
    assert table.rows[1] == ["[merged:R1C1]", "SECOND"]
    assert reader._find_table_ranges(records) == {0: (0, 6)}
    binary = b"".join(
        struct.pack("<I", tag | level << 10 | len(data) << 20) + data
        for tag, level, data in records
    )
    reader._reset_counters()
    reader.body_only = True
    reader._body_tables = []
    assert reader._extract_section_text(binary, ExtractOptions()).strip() == "AFTER"
    assert len(reader._body_tables) == 1


@pytest.mark.parametrize(
    "cells,rows,cols",
    [
        ([dict(row=0, col=0, rowspan=3, colspan=1, text="x")], 2, 2),
        ([dict(row=0, col=0, rowspan=1, colspan=1, text="x")] * 2, 1, 1),
        ([], 1000000, 1000000),
    ],
)
def test_invalid_table_rejected(cells, rows, cols):
    with pytest.raises(ValueError):
        build_table(cells, rows, cols)


def test_note_in_table_keeps_matching_number(tmp_path):
    note = "<footNote><subList><p><run><t>NOTE</t></run></p></subList></footNote>"
    table = '<tbl rowCnt="1" colCnt="1"><tr>' + cell(0, 0, "VALUE" + note) + "</tr></tbl>"
    p = hwpx(tmp_path / "notes.hwpx", {0: "<p><run>" + table + "</run></p>"})
    docs = HwpHwpxLoader(p, mode="elements").load()
    assert [d.metadata["element_type"] for d in docs] == ["table", "footnote"]
    assert "[^1]" in docs[0].page_content
    assert docs[1].metadata["note_number"] == 1
    assert docs[1].page_content == "NOTE"


def test_optional_distribution_dependency_missing(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "hwp5.filestructure", None)
    reader = HwpReader("unused.hwp")
    reader.distribution_backend = "pyhwp"
    with pytest.raises(ImportError, match=r"\[distribution\]"):
        reader._sections()


def test_horizontal_span(tmp_path):
    table = '<tbl rowCnt="2" colCnt="2"><tr>' + cell(0, 0, "HEADER", colspan=2)
    table += "</tr><tr>" + cell(1, 0, "LEFT") + cell(1, 1, "RIGHT") + "</tr></tbl>"
    p = hwpx(tmp_path / "horizontal.hwpx", {0: "<p><run>" + table + "</run></p>"})
    doc = HwpHwpxLoader(p, mode="elements").load()[0]
    assert "| HEADER [rowspan=1, colspan=2] | [merged:R1C1] |" in doc.page_content
    assert "| LEFT | RIGHT |" in doc.page_content
