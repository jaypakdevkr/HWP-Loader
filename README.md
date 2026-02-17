# LangChain HWP/HWPX Loader

`langchain-hwp-hwpx-loader`는 `hwp-hwpx-parser` 기반의 순수 Python LangChain 로더입니다.  
한국어 문서(`.hwp`, `.hwpx`)를 오프라인/온프렘 환경에서 읽어 RAG 파이프라인에 넣기 쉽게 만듭니다.

## 한국어 사용 가이드

### 1) 설치

```bash
pip install langchain-hwp-hwpx-loader
```

### 2) 단일 파일 로딩 (`mode="single"`)

문서 전체를 `Document` 1개로 반환합니다.

```python
from pathlib import Path

from hwp_hwpx_parser import ExtractOptions, ImageMarkerStyle, TableStyle
from langchain_hwp_hwpx import HwpHwpxLoader

options = ExtractOptions(
    table_style=TableStyle.MARKDOWN,
    image_marker=ImageMarkerStyle.SIMPLE,
)

loader = HwpHwpxLoader(
    file_path=Path("docs/sample.hwp"),
    mode="single",
    extract_options=options,
    include_tables=True,
    include_notes=True,
    include_memos=True,
    include_hyperlinks=True,
)

docs = loader.load()
print("docs:", len(docs))
print("metadata:", docs[0].metadata)
print("content preview:", docs[0].page_content[:400])
```

### 3) 요소 단위 로딩 (`mode="elements"`)

본문/표/각주/미주/메모/링크/이미지를 분리된 `Document`로 반환합니다.

```python
from langchain_hwp_hwpx import HwpHwpxLoader

loader = HwpHwpxLoader("docs/sample.hwpx", mode="elements")

for doc in loader.lazy_load():
    print(
        doc.metadata["element_index"],
        doc.metadata["element_type"],
        doc.metadata.get("note_number"),
        doc.metadata.get("url"),
    )
```

### 4) 폴더 단위 로딩

디렉토리 전체를 재귀 탐색해 `.hwp`, `.hwpx` 파일을 순서대로 로딩합니다.

```python
from langchain_hwp_hwpx import HwpHwpxDirectoryLoader

loader = HwpHwpxDirectoryLoader(
    dir_path="docs",
    glob="**/*",
    recursive=True,
    mode="single",
    on_error="warn",
)

docs = loader.load()
print("loaded:", len(docs))
```

### 5) 주요 옵션

- `mode`: `"single"` 또는 `"elements"`
- `include_tables`, `include_notes`, `include_memos`, `include_hyperlinks`
- `include_images`, `images_dir`, `image_document_mode`
- `on_encrypted`: `"raise" | "skip" | "placeholder"`
- `on_invalid`: `"raise" | "skip" | "placeholder"`
- `on_error`: `"raise" | "skip" | "warn"`
- `extract_options`: `hwp_hwpx_parser.ExtractOptions` 전달 가능

### 6) 반환 메타데이터

공통 메타데이터:

- `source`, `file_name`, `file_type`
- `loader`, `parser`
- `extracted_at` (기본: UTC ISO timestamp)

`mode="elements"` 추가 메타데이터:

- `element_type`, `element_index`
- 표: `row_count`, `col_count`
- 각주/미주: `note_type`, `note_number`
- 링크: `url`, `text`
- 이미지: `filename`, `image_format`, `saved_path`(저장 모드일 때)

### 7) 자주 묻는 점

- 암호화 문서 복호화는 지원하지 않습니다(감지 후 정책 처리).
- OCR/레이아웃 렌더링은 범위 밖입니다.
- Python 3.14에서 `langchain-core` 경고가 보일 수 있어, 실무에서는 Python 3.11/3.12를 권장합니다.

## English (Brief)

Pure-Python LangChain loader for Korean `.hwp` / `.hwpx` documents.

- Install: `pip install langchain-hwp-hwpx-loader`
- Main classes: `HwpHwpxLoader`, `HwpHwpxDirectoryLoader`
- Modes: `single`, `elements`
- Python: `>=3.10,<4.0`
