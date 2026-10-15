"""Integrity adapters for the tested hwp-hwpx-parser 1.0.x API.

HWP cell offsets follow Hancom HWP 5.0 revision 1.3, tables 65/79/80.
No pyhwp implementation is copied; optional distribution decoding uses its API.
"""

from __future__ import annotations

import struct
from functools import wraps
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from hwp_hwpx_parser import Reader
from hwp_hwpx_parser.hwp5 import HWPTAG_LIST_HEADER, HWPTAG_TABLE, HWP5Reader
from hwp_hwpx_parser.hwpx import HWPXReader
from hwp_hwpx_parser.models import ExtractOptions, TableData


@dataclass
class StructuredTable(TableData):
    cells: list[dict] = field(default_factory=list)
    body_only: bool = False

    def format(self, style, delimiter=","):
        return "" if self.body_only else super().format(style, delimiter)


def build_table(cells, rows, cols, body_only=False):
    if rows < 1 or cols < 1 or rows * cols > 1_000_000:
        raise ValueError("Invalid or excessively large table dimensions")
    grid = [[""] * cols for _ in range(rows)]
    occupied = set()
    for cell in cells:
        r, c, rs, cs = (cell[k] for k in ("row", "col", "rowspan", "colspan"))
        if min(r, c) < 0 or min(rs, cs) < 1 or r + rs > rows or c + cs > cols:
            raise ValueError("Cell span is outside table dimensions")
        for rr in range(r, r + rs):
            for cc in range(c, c + cs):
                if (rr, cc) in occupied:
                    raise ValueError("Overlapping table cells")
                occupied.add((rr, cc))
                if (rr, cc) != (r, c):
                    grid[rr][cc] = f"[merged:R{r+1}C{c+1}]"
        label = cell["text"]
        if rs > 1 or cs > 1:
            label += f" [rowspan={rs}, colspan={cs}]"
        grid[r][c] = label
    return StructuredTable(rows=grid, cells=cells, body_only=body_only)


def capture_table(method):
    """Keep top-level tables from the same pass as body/note extraction."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        depth = getattr(self, "_table_depth", 0)
        self._table_depth = depth + 1
        try:
            table = method(self, *args, **kwargs)
            if self.body_only and depth == 0:
                self._body_tables.append(table)
            return table
        finally:
            self._table_depth = depth

    return wrapped


class HwpReader(HWP5Reader):
    body_only = False
    distribution_backend = None
    _decoded_sections = None

    @property
    def distributable(self):
        header = self._open().openstream("FileHeader").read(40)
        return len(header) >= 40 and bool(struct.unpack_from("<I", header, 36)[0] & 4)

    def _sections(self):
        if self.distribution_backend != "pyhwp":
            raise ValueError("Distribution HWP requires distribution_backend='pyhwp'")
        if self._decoded_sections is None:
            try:
                from hwp5.filestructure import Hwp5File
            except ImportError as exc:
                raise ImportError("Install langchain-hwp-hwpx-loader[distribution]") from exc
            document = Hwp5File(str(self.filepath))
            try:
                self._decoded_sections = {}
                for name in document.text:
                    with document.text[name].open() as stream:
                        self._decoded_sections[int(name.removeprefix("Section"))] = stream.read()
            finally:
                document.close()
        return self._decoded_sections

    def _iter_sections(self):
        if self.distributable:
            return iter(sorted(self._sections()))
        return super()._iter_sections()

    def _read_section(self, section_idx):
        if self.distributable:
            return self._sections()[section_idx]
        return super()._read_section(section_idx)

    def _find_table_ranges(self, records):
        ranges = {}
        i = 0
        while i < len(records):
            tag, level, _ = records[i]
            if tag != HWPTAG_TABLE:
                i += 1
                continue
            end = i + 1
            while end < len(records) and records[end][1] >= level:
                end += 1
            ranges[i] = (i, end - 1)
            i = end
        return ranges

    @capture_table
    def _extract_table_at(self, records, table_record_idx, options):
        _, level, data = records[table_record_idx]
        shape = self._parse_table_record(data)
        if not shape:
            raise ValueError("Invalid HWP table record")
        rows, cols, _ = shape
        cells = []
        for idx in range(table_record_idx + 1, len(records)):
            tag, depth, data = records[idx]
            if depth < level:
                break
            # Cell list headers are siblings of the table record; nested lists are deeper.
            if tag != HWPTAG_LIST_HEADER or depth != level:
                continue
            if len(data) < 34:
                raise ValueError("Truncated HWP cell list header")
            col, row, colspan, rowspan = struct.unpack_from("<4H", data, 8)
            cells.append(
                dict(
                    row=row,
                    col=col,
                    rowspan=rowspan,
                    colspan=colspan,
                    text=self._extract_cell_text(records, idx, options),
                )
            )
        return build_table(cells, rows, cols, self.body_only)

    def _extract_tables_from_section(self, data, options):
        records = list(self._parse_records(data))
        return [
            self._extract_table_at(records, start, options)
            for start in self._find_table_ranges(records)
        ]


class HwpxReader(HWPXReader):
    body_only = False

    def _get_section_files(self):
        files = super()._get_section_files()
        return sorted(files, key=lambda name: int(name.rsplit("section", 1)[1][:-4]))

    @capture_table
    def _extract_table(self, tbl_elem):
        cells = []
        occupied = set()
        row_index = 0
        for tr in tbl_elem:
            if self._local_name(tr.tag) != "tr":
                continue
            col_index = 0
            for tc in tr:
                if self._local_name(tc.tag) != "tc":
                    continue
                props = {self._local_name(child.tag): child for child in tc}
                addr, span = props.get("cellAddr"), props.get("cellSpan")
                while (row_index, col_index) in occupied:
                    col_index += 1
                row = int(addr.get("rowAddr")) if addr is not None else row_index
                col = int(addr.get("colAddr")) if addr is not None else col_index
                rs = int(span.get("rowSpan", "1")) if span is not None else 1
                cs = int(span.get("colSpan", "1")) if span is not None else 1
                if min(row, col) < 0 or min(rs, cs) < 1 or (row + rs) * (col + cs) > 1_000_000:
                    raise ValueError("Invalid or excessively large cell span")
                cells.append(
                    dict(
                        row=row,
                        col=col,
                        rowspan=rs,
                        colspan=cs,
                        text=self._extract_cell_text_direct(tc),
                    )
                )
                occupied.update((r, c) for r in range(row, row + rs) for c in range(col, col + cs))
                col_index = col + cs
            row_index += 1
        if not cells:
            return StructuredTable()
        rows = int(tbl_elem.get("rowCnt", max(c["row"] + c["rowspan"] for c in cells)))
        cols = int(tbl_elem.get("colCnt", max(c["col"] + c["colspan"] for c in cells)))
        return build_table(cells, rows, cols, self.body_only)

    def get_tables(self, options=None):
        tables = []

        def visit(elem):
            if self._local_name(elem.tag) == "tbl":
                tables.append(self._extract_table(elem))
            else:
                for child in elem:
                    visit(child)

        for section in self._get_section_files():
            visit(ET.fromstring(self._open().read(section)))
        return tables


class IntegrityReader(Reader):
    def __init__(self, filepath, distribution_backend=None):
        super().__init__(filepath)
        self.distribution_backend = distribution_backend

    def _get_reader(self):
        if self._reader is None:
            self._reader = (
                HwpReader(self.filepath)
                if self.filepath.suffix.lower() == ".hwp"
                else HwpxReader(self.filepath)
            )
            self._reader.distribution_backend = self.distribution_backend
        return self._reader

    @property
    def unsupported_reason(self):
        backend = self._get_reader()
        if (
            isinstance(backend, HwpReader)
            and self.is_valid
            and backend.distributable
            and self.distribution_backend is None
        ):
            return "Distribution HWP: install [distribution] and set distribution_backend='pyhwp'"
        return None

    def extract_text_with_notes(self, options=None):
        backend = self._get_reader()
        backend._body_tables = []
        backend.body_only = True
        try:
            result = backend.extract_text_with_notes(options or ExtractOptions())
            result.tables = backend._body_tables
            return result
        finally:
            backend.body_only = False
