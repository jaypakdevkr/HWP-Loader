"""Compatibility helpers for LangChain imports used in tests and runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from langchain_core.documents import Document as Document

    try:
        from langchain_core.document_loaders.base import BaseLoader as BaseLoader
    except Exception:  # pragma: no cover - typing fallback
        from langchain_core.document_loaders import BaseLoader as BaseLoader
else:
    try:
        from langchain_core.documents import Document as _RuntimeDocument
    except Exception:  # pragma: no cover - fallback for environments without langchain-core

        @dataclass
        class _RuntimeDocument:
            """Fallback Document for local tests when langchain-core is unavailable."""

            page_content: str
            metadata: dict[str, Any] = field(default_factory=dict)

    try:
        from langchain_core.document_loaders.base import BaseLoader as _RuntimeBaseLoader
    except Exception:  # pragma: no cover - fallback path for older langchain-core
        try:
            from langchain_core.document_loaders import BaseLoader as _RuntimeBaseLoader
        except Exception:

            class _RuntimeBaseLoader:
                """Fallback BaseLoader with the same load/lazy_load contract."""

                def lazy_load(self) -> Iterator[_RuntimeDocument]:
                    raise NotImplementedError

                def load(self) -> list[_RuntimeDocument]:
                    return list(self.lazy_load())

    Document = _RuntimeDocument
    BaseLoader = _RuntimeBaseLoader
