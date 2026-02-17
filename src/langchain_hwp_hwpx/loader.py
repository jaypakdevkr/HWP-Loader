"""LangChain loaders for HWP/HWPX documents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Iterator, Literal

from ._version import __version__
from .compat import BaseLoader, Document

LOGGER = logging.getLogger(__name__)

Mode = Literal["single", "elements"]
StatusPolicy = Literal["raise", "skip", "placeholder"]
ErrorPolicy = Literal["raise", "skip", "warn"]
ImageDocumentMode = Literal["metadata_only", "save_and_reference"]

_VALID_MODES = {"single", "elements"}
_VALID_STATUS_POLICIES = {"raise", "skip", "placeholder"}
_VALID_ERROR_POLICIES = {"raise", "skip", "warn"}
_VALID_IMAGE_DOCUMENT_MODES = {"metadata_only", "save_and_reference"}
_SUPPORTED_EXTENSIONS = {".hwp", ".hwpx"}


class HwpHwpxLoaderError(RuntimeError):
    """Base loader exception with concise parsing context."""


class _SkipFile(Exception):
    """Internal signal for skip policies."""


def _import_parser() -> Any:
    try:
        import hwp_hwpx_parser as parser  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "hwp-hwpx-parser is required. Install with: pip install hwp-hwpx-parser"
        ) from exc
    return parser


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _parser_version() -> str:
    try:
        return importlib_metadata.version("hwp-hwpx-parser")
    except importlib_metadata.PackageNotFoundError:
        return "unknown"


def _validate_literal(value: str, name: str, allowed: set[str]) -> None:
    if value not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValueError(f"Invalid {name}={value!r}. Expected one of: {options}")


def _normalize_file_type(value: Any, file_path: Path) -> str:
    candidates: list[str] = []
    if value is not None:
        candidates.append(_string(value))
        name = getattr(value, "name", None)
        if name is not None:
            candidates.append(_string(name))
        raw_value = getattr(value, "value", None)
        if raw_value is not None:
            candidates.append(_string(raw_value))

    candidates.append(file_path.suffix.lstrip("."))

    for token in candidates:
        lowered = token.lower()
        if "hwpx" in lowered:
            return "hwpx"
        if "hwp5" in lowered or lowered == "hwp":
            return "hwp"
        if lowered.endswith(".hwpx"):
            return "hwpx"
        if lowered.endswith(".hwp"):
            return "hwp"

    return file_path.suffix.lstrip(".").lower()


def _normalize_hyperlink(hyperlink: Any) -> tuple[str, str]:
    if isinstance(hyperlink, (tuple, list)):
        text = _string(hyperlink[0]) if len(hyperlink) > 0 else ""
        url = _string(hyperlink[1]) if len(hyperlink) > 1 else ""
        return text.strip(), url.strip()

    if isinstance(hyperlink, dict):
        text = _string(hyperlink.get("text", ""))
        url = _string(hyperlink.get("url", ""))
        return text.strip(), url.strip()

    text = _string(getattr(hyperlink, "text", ""))
    url = _string(getattr(hyperlink, "url", ""))
    return text.strip(), url.strip()


class HwpHwpxLoader(BaseLoader):
    """Load a single HWP/HWPX file into LangChain Document objects."""

    def __init__(
        self,
        file_path: str | Path,
        mode: Mode = "single",
        extract_options: Any | None = None,
        include_tables: bool = True,
        include_notes: bool = True,
        include_memos: bool = True,
        include_hyperlinks: bool = True,
        include_images: bool = False,
        images_dir: str | Path | None = None,
        image_document_mode: ImageDocumentMode = "metadata_only",
        on_encrypted: StatusPolicy = "raise",
        on_invalid: StatusPolicy = "raise",
        on_error: ErrorPolicy = "raise",
        extra_metadata: dict[str, Any] | None = None,
        include_extracted_at: bool = True,
    ) -> None:
        _validate_literal(mode, "mode", _VALID_MODES)
        _validate_literal(on_encrypted, "on_encrypted", _VALID_STATUS_POLICIES)
        _validate_literal(on_invalid, "on_invalid", _VALID_STATUS_POLICIES)
        _validate_literal(on_error, "on_error", _VALID_ERROR_POLICIES)
        _validate_literal(
            image_document_mode, "image_document_mode", _VALID_IMAGE_DOCUMENT_MODES
        )

        self.file_path = Path(file_path)
        self.mode = mode
        self.extract_options = extract_options
        self.include_tables = include_tables
        self.include_notes = include_notes
        self.include_memos = include_memos
        self.include_hyperlinks = include_hyperlinks
        self.include_images = include_images
        self.images_dir = Path(images_dir) if images_dir is not None else None
        self.image_document_mode = image_document_mode
        self.on_encrypted = on_encrypted
        self.on_invalid = on_invalid
        self.on_error = on_error
        self.extra_metadata = dict(extra_metadata or {})
        self.include_extracted_at = include_extracted_at

    def lazy_load(self) -> Iterator[Document]:
        file_path = self.file_path
        if file_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported extension for {file_path}. Use .hwp or .hwpx")
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            reader = self._create_reader(file_path)
            base_metadata = self._build_common_metadata(file_path, reader)
            placeholder = self._handle_file_status(reader, base_metadata)
            if placeholder is not None:
                yield placeholder
                return

            result = self._extract_result(reader)
            if self.mode == "single":
                yield self._build_single_document(file_path, reader, result, base_metadata)
                return

            yield from self._build_element_documents(file_path, reader, result, base_metadata)
        except _SkipFile:
            return
        except HwpHwpxLoaderError:
            raise
        except Exception as exc:
            self._handle_runtime_error(file_path, exc)
            return

    def _create_reader(self, file_path: Path) -> Any:
        parser = _import_parser()
        return parser.Reader(str(file_path))

    def _extract_result(self, reader: Any) -> Any:
        if self.extract_options is None:
            return reader.extract_text_with_notes()
        return reader.extract_text_with_notes(self.extract_options)

    def _build_common_metadata(self, file_path: Path, reader: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "source": str(file_path),
            "file_name": file_path.name,
            "file_type": _normalize_file_type(getattr(reader, "file_type", None), file_path),
            "loader": f"langchain_hwp_hwpx/{__version__}",
            "parser": f"hwp-hwpx-parser/{_parser_version()}",
        }
        if self.include_extracted_at:
            metadata["extracted_at"] = _iso_utc_now()
        metadata.update(self.extra_metadata)
        return metadata

    def _handle_file_status(self, reader: Any, base_metadata: dict[str, Any]) -> Document | None:
        if bool(getattr(reader, "is_encrypted", False)):
            return self._resolve_status_policy(
                policy=self.on_encrypted,
                status="encrypted",
                file_path=self.file_path,
                base_metadata=base_metadata,
            )

        if not bool(getattr(reader, "is_valid", True)):
            return self._resolve_status_policy(
                policy=self.on_invalid,
                status="invalid",
                file_path=self.file_path,
                base_metadata=base_metadata,
            )

        return None

    def _resolve_status_policy(
        self,
        policy: StatusPolicy,
        status: str,
        file_path: Path,
        base_metadata: dict[str, Any],
    ) -> Document | None:
        message = f"Document skipped because it is {status}: {file_path}"
        if policy == "raise":
            raise HwpHwpxLoaderError(message)
        if policy == "skip":
            raise _SkipFile
        placeholder_metadata = dict(base_metadata)
        placeholder_metadata["status"] = status
        placeholder_metadata["element_type"] = "placeholder"
        return Document(
            page_content=f"[{status.upper()}] {file_path.name} cannot be parsed by policy.",
            metadata=placeholder_metadata,
        )

    def _handle_runtime_error(self, file_path: Path, exc: Exception) -> None:
        message = f"Failed to parse {file_path}: {exc.__class__.__name__}"
        if self.on_error == "raise":
            if isinstance(exc, HwpHwpxLoaderError):
                raise exc
            raise HwpHwpxLoaderError(message) from exc
        if self.on_error == "warn":
            LOGGER.warning("%s (%s)", message, exc)

    def _build_single_document(
        self,
        file_path: Path,
        reader: Any,
        result: Any,
        base_metadata: dict[str, Any],
    ) -> Document:
        chunks: list[str] = []

        body_text = self._extract_body_text(reader, result)
        if body_text:
            chunks.append(body_text)

        if self.include_tables:
            table_text = self._render_tables_for_single(reader, result)
            if table_text:
                chunks.append(table_text)

        if self.include_notes:
            note_text = self._render_notes_for_single(result)
            if note_text:
                chunks.append(note_text)

        if self.include_memos:
            memo_text = self._render_memos_for_single(result)
            if memo_text:
                chunks.append(memo_text)

        if self.include_hyperlinks:
            hyperlink_text = self._render_hyperlinks_for_single(result)
            if hyperlink_text:
                chunks.append(hyperlink_text)

        if self.include_images:
            image_text = self._render_images_for_single(file_path, reader)
            if image_text:
                chunks.append(image_text)

        metadata = dict(base_metadata)
        metadata["element_type"] = "document"
        content = "\n\n".join(part for part in chunks if part).strip()
        return Document(page_content=content, metadata=metadata)

    def _build_element_documents(
        self,
        file_path: Path,
        reader: Any,
        result: Any,
        base_metadata: dict[str, Any],
    ) -> Iterator[Document]:
        index = 0

        body_text = self._extract_body_text(reader, result)
        if body_text:
            yield Document(
                page_content=body_text,
                metadata=self._element_metadata(base_metadata, "body", index),
            )
            index += 1

        if self.include_tables:
            for table in self._collect_tables(reader, result):
                table_metadata = self._element_metadata(base_metadata, "table", index)
                row_count = _safe_int(getattr(table, "row_count", None))
                col_count = _safe_int(getattr(table, "col_count", None))
                if row_count is not None:
                    table_metadata["row_count"] = row_count
                if col_count is not None:
                    table_metadata["col_count"] = col_count
                yield Document(
                    page_content=self._render_table(table),
                    metadata=table_metadata,
                )
                index += 1

        if self.include_notes:
            for note in self._collect_notes(result):
                note_type = _string(getattr(note, "note_type", "footnote")).lower()
                element_type = "endnote" if note_type == "endnote" else "footnote"
                note_metadata = self._element_metadata(base_metadata, element_type, index)
                note_metadata["note_type"] = note_type
                number = _safe_int(getattr(note, "number", None))
                if number is not None:
                    note_metadata["note_number"] = number
                yield Document(
                    page_content=_string(getattr(note, "text", "")).strip(),
                    metadata=note_metadata,
                )
                index += 1

        if self.include_memos:
            for memo in self._collect_memos(result):
                memo_metadata = self._element_metadata(base_metadata, "memo", index)
                for key in ("id", "memo_id", "author", "referenced_text"):
                    value = getattr(memo, key, None)
                    if value not in (None, ""):
                        memo_metadata[key] = value
                yield Document(
                    page_content=_string(getattr(memo, "text", "")).strip(),
                    metadata=memo_metadata,
                )
                index += 1

        if self.include_hyperlinks:
            for hyperlink in self._collect_hyperlinks(result):
                hyperlink_metadata = self._element_metadata(base_metadata, "hyperlink", index)
                text, url = _normalize_hyperlink(hyperlink)
                if not text and not url:
                    continue
                if url:
                    hyperlink_metadata["url"] = url
                if text:
                    hyperlink_metadata["text"] = text
                content = text if text else url
                yield Document(page_content=content, metadata=hyperlink_metadata)
                index += 1

        if self.include_images:
            for image_index, image in enumerate(self._collect_images(reader)):
                image_metadata = self._element_metadata(base_metadata, "image", index)
                image_content = self._materialize_image(
                    file_path, image_index, image, image_metadata
                )
                yield Document(page_content=image_content, metadata=image_metadata)
                index += 1

    def _element_metadata(
        self,
        base_metadata: dict[str, Any],
        element_type: str,
        element_index: int,
    ) -> dict[str, Any]:
        metadata = dict(base_metadata)
        metadata["element_type"] = element_type
        metadata["element_index"] = element_index
        return metadata

    def _extract_body_text(self, reader: Any, result: Any) -> str:
        text = _string(getattr(result, "text", "")).strip()
        if text:
            return text
        return _string(getattr(reader, "text", "")).strip()

    def _collect_tables(self, reader: Any, result: Any) -> list[Any]:
        if hasattr(result, "tables") and getattr(result, "tables") is not None:
            return list(getattr(result, "tables"))
        if hasattr(reader, "get_tables"):
            return list(reader.get_tables())
        return []

    def _collect_notes(self, result: Any) -> list[Any]:
        if hasattr(result, "notes") and getattr(result, "notes") is not None:
            return list(getattr(result, "notes"))
        return []

    def _collect_memos(self, result: Any) -> list[Any]:
        if hasattr(result, "memos") and getattr(result, "memos") is not None:
            return list(getattr(result, "memos"))
        return []

    def _collect_hyperlinks(self, result: Any) -> list[Any]:
        if hasattr(result, "hyperlinks") and getattr(result, "hyperlinks") is not None:
            return list(getattr(result, "hyperlinks"))
        return []

    def _collect_images(self, reader: Any) -> list[Any]:
        if hasattr(reader, "get_images"):
            return list(reader.get_images())
        return []

    def _render_tables_for_single(self, reader: Any, result: Any) -> str:
        tables = self._collect_tables(reader, result)
        if not tables:
            return ""
        delimiter = _string(getattr(self.extract_options, "paragraph_separator", "\n\n")).strip()
        if not delimiter:
            delimiter = "\n\n"
        rendered = [self._render_table(table) for table in tables]
        return "## Tables\n" + delimiter.join(rendered)

    def _render_table(self, table: Any) -> str:
        style_name = _string(
            getattr(getattr(self.extract_options, "table_style", None), "name", "")
        )
        if not style_name:
            style_name = _string(getattr(self.extract_options, "table_style", ""))
        style_name = style_name.upper()
        if "CSV" in style_name and hasattr(table, "to_csv"):
            csv_delimiter = _string(getattr(self.extract_options, "table_delimiter", ",")).strip()
            if not csv_delimiter:
                csv_delimiter = ","
            return _string(table.to_csv(csv_delimiter)).strip()
        if "INLINE" in style_name and hasattr(table, "to_inline"):
            return _string(table.to_inline()).strip()
        if hasattr(table, "to_markdown"):
            return _string(table.to_markdown()).strip()
        return _string(getattr(table, "rows", table)).strip()

    def _render_notes_for_single(self, result: Any) -> str:
        notes = self._collect_notes(result)
        if not notes:
            return ""
        lines = ["## Notes"]
        for note in notes:
            note_type = _string(getattr(note, "note_type", "footnote")).lower()
            number = _safe_int(getattr(note, "number", None))
            marker = f"[{note_type}:{number}]" if number is not None else f"[{note_type}]"
            text = _string(getattr(note, "text", "")).strip()
            lines.append(f"{marker} {text}".strip())
        return "\n".join(lines)

    def _render_memos_for_single(self, result: Any) -> str:
        memos = self._collect_memos(result)
        if not memos:
            return ""
        lines = ["## Memos"]
        for idx, memo in enumerate(memos, start=1):
            author = _string(getattr(memo, "author", "")).strip()
            text = _string(getattr(memo, "text", "")).strip()
            label = f"[memo:{idx}]"
            if author:
                label = f"{label} ({author})"
            lines.append(f"{label} {text}".strip())
        return "\n".join(lines)

    def _render_hyperlinks_for_single(self, result: Any) -> str:
        links = self._collect_hyperlinks(result)
        if not links:
            return ""
        lines = ["## Hyperlinks"]
        for hyperlink in links:
            text, url = _normalize_hyperlink(hyperlink)
            if text and url:
                lines.append(f"- {text}: {url}")
            elif url:
                lines.append(f"- {url}")
            elif text:
                lines.append(f"- {text}")
        return "\n".join(lines)

    def _render_images_for_single(self, file_path: Path, reader: Any) -> str:
        images = self._collect_images(reader)
        if not images:
            return ""
        lines = ["## Images"]
        for image_index, image in enumerate(images):
            metadata: dict[str, Any] = {}
            content = self._materialize_image(file_path, image_index, image, metadata)
            lines.append(content)
        return "\n".join(lines)

    def _materialize_image(
        self,
        file_path: Path,
        image_index: int,
        image: Any,
        metadata: dict[str, Any],
    ) -> str:
        filename = _string(getattr(image, "filename", "")).strip()
        fmt = _string(getattr(image, "format", "bin")).strip().lower() or "bin"
        generated_name = f"image_{image_index:03d}.{fmt}"
        resolved_name = filename or generated_name

        metadata["filename"] = resolved_name
        metadata["image_format"] = fmt

        if self.image_document_mode == "save_and_reference" and self.images_dir is not None:
            self.images_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.images_dir / resolved_name
            if output_path.suffix == "":
                output_path = output_path.with_suffix(f".{fmt}")
            if hasattr(image, "save"):
                image.save(str(output_path))
                metadata["saved_path"] = str(output_path)
                return f"{resolved_name} -> {output_path}"

        return f"{resolved_name} ({fmt}) from {file_path.name}"


class HwpHwpxDirectoryLoader(BaseLoader):
    """Load all supported files in a directory tree with stable ordering."""

    def __init__(
        self,
        dir_path: str | Path,
        glob: str = "**/*",
        recursive: bool = True,
        extensions: tuple[str, ...] = (".hwp", ".hwpx"),
        **loader_kwargs: Any,
    ) -> None:
        self.dir_path = Path(dir_path)
        self.glob = glob
        self.recursive = recursive
        self.extensions = tuple(self._normalize_extension(ext) for ext in extensions)
        self.loader_kwargs = dict(loader_kwargs)
        self.on_error = _string(self.loader_kwargs.get("on_error", "raise"))
        _validate_literal(self.on_error, "on_error", _VALID_ERROR_POLICIES)
        if "on_error" not in self.loader_kwargs:
            self.loader_kwargs["on_error"] = self.on_error

    def lazy_load(self) -> Iterator[Document]:
        if not self.dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {self.dir_path}")
        if not self.dir_path.is_dir():
            raise NotADirectoryError(f"Expected directory path: {self.dir_path}")

        for file_path in self._collect_files():
            try:
                loader = HwpHwpxLoader(file_path=file_path, **self.loader_kwargs)
                yield from loader.lazy_load()
            except Exception as exc:
                message = f"Failed to load file {file_path}: {exc.__class__.__name__}"
                if self.on_error == "raise":
                    raise HwpHwpxLoaderError(message) from exc
                if self.on_error == "warn":
                    LOGGER.warning("%s (%s)", message, exc)

    def _collect_files(self) -> list[Path]:
        pattern = self.glob
        if self.recursive:
            candidates = self.dir_path.glob(pattern)
        else:
            local_pattern = pattern.replace("**/", "").replace("**", "*")
            candidates = self.dir_path.glob(local_pattern)

        files = [
            path
            for path in candidates
            if path.is_file() and path.suffix.lower() in self.extensions
        ]
        return sorted(files, key=lambda item: str(item))

    @staticmethod
    def _normalize_extension(extension: str) -> str:
        extension = extension.strip().lower()
        if not extension:
            raise ValueError("extensions must not contain empty values")
        if not extension.startswith("."):
            return f".{extension}"
        return extension
