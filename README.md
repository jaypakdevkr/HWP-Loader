# LangChain HWP/HWPX Loader

`langchain-hwp-hwpx-loader`는 `hwp-hwpx-parser` 기반의 순수 Python LangChain 로더입니다.  
한국어 문서(`.hwp`, `.hwpx`)를 오프라인/온프렘 환경에서 읽어 RAG 파이프라인에 넣기 쉽게 만듭니다.

## 왜 중요한가

- 국내 문서 생태계에서 한컴 문서 수요는 여전히 큽니다.
- 2025-10-09 보도에서 "업계에서는 한컴오피스가 차지하는 비중을 약 30%로 보고 있다."고 언급되었습니다.
- 출처: [ChosunBiz](https://biz.chosun.com/it-science/ict/2025/10/09/NHYQN77XSFAWXJFFGSKU47IPZQ/)

## 한국어 사용 가이드

### 1) 설치

```bash
pip install langchain-hwp-hwpx-loader
```

### 배포용 HWP와 0.2.0 변경 사항

배포용 HWP는 일반 HWP와 본문 저장 위치가 다릅니다. 기본 설치는 이를 감지하면
오류를 발생시켜 안내문만 정상 본문으로 처리하는 일을 방지합니다.
실제 본문을 읽으려면 선택 의존성과 백엔드를 명시하세요.

```bash
pip install -U "langchain-hwp-hwpx-loader[distribution]==0.2.1"
```

```python
from langchain_hwp_hwpx import HwpHwpxLoader

docs = HwpHwpxLoader(
    "배포용문서.hwp",
    mode="elements",
    distribution_backend="pyhwp",
).load()
```

- `pyhwp`는 **AGPLv3+** 라이선스의 선택 의존성입니다. 이 로더의 MIT 라이선스와 별개입니다.
- `on_unsupported="raise" | "skip" | "placeholder"`로 미지원 파일 정책을 지정합니다.
  암호로 보호된 문서는 기존 `on_encrypted` 정책을 따릅니다.
- 본문과 표를 분리하여 표 중복을 제거했습니다. `include_tables=False`는 표 안의 텍스트도 제외합니다.
- 병합 셀은 시작 셀에 `[rowspan=2, colspan=1]`, 덮인 셀에 `[merged:R1C1]`처럼 표시됩니다.
  R/C 표시는 1부터 시작합니다. `mode="elements"`의 표 메타데이터 `cells`에는 JSON 문자열로
  **0부터 시작하는** `row`, `col`과 `rowspan`, `colspan`, `text`가 들어갑니다.
- 중첩 표는 상위 표의 셀 안에서 한 번만 렌더링합니다. `cells`는 해당 최상위 표의 셀 정보입니다.
- 이미지는 문서 경로 해시 하위 폴더에 순번으로 저장하여 동명 이미지 충돌을 피합니다.
  원래 파일명은 메타데이터에 남습니다. 동일 문서를 같은 경로로 다시 읽으면 저장 파일을 갱신합니다.
- 기존 벡터 인덱스는 재생성하세요. 표 내용과 이미지 저장 경로가 이전 버전과 달라집니다.
- 검증한 `hwp-hwpx-parser==1.0.0`의 내부 API를 사용합니다. 원본 페이지 배치/OCR을 복원하는 기능은 아닙니다.
- `lazy_load()`를 중간에 중단한다면 반환된 제너레이터의 `close()`를 호출해 즉시 파일을 해제하세요.

### Chroma 호환성 (0.2.1)

0.2.0에서 표의 `metadata["cells"]`를 딕셔너리 목록으로 반환하여
`Chroma.from_documents()`가 실패하는 문제를 수정했습니다.
0.2.1부터는 셀 구조를 JSON 문자열로 저장합니다. 본문과 표 텍스트는 바뀌지 않으며,
기본 로딩 결과는 `filter_complex_metadata()` 없이 Chroma에 저장할 수 있습니다.
직접 `extra_metadata`를 지정하는 경우에는 사용하는 벡터 저장소에서 허용하는 자료형을 사용하세요.

셀 구조를 직접 처리하는 코드는 다음과 같이 JSON 문자열을 복원하세요.

```python
import json

for doc in docs:
    if doc.metadata.get("element_type") == "table":
        cells = json.loads(doc.metadata["cells"])
        # cells: row, col, rowspan, colspan, text를 가진 딕셔너리 목록
```

Colab에서 업그레이드한 경우 런타임을 다시 시작한 뒤 문서 로딩부터 실행하세요.
이미 메모리에 로드된 0.2.0 문서 객체의 메타데이터는 자동으로 변경되지 않습니다.

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

## English Guide

`langchain-hwp-hwpx-loader` is a pure-Python LangChain integration for Korean
`.hwp` / `.hwpx` documents.

### Why this matters

- Korean enterprise/public workflows still involve HWP-family documents.
- A 2025-10-09 industry report says that industry estimates place Hancom Office
  market share at around 30% in Korea.
- Source: [ChosunBiz](https://biz.chosun.com/it-science/ict/2025/10/09/NHYQN77XSFAWXJFFGSKU47IPZQ/)

### Installation

```bash
pip install langchain-hwp-hwpx-loader
```

### Quickstart (`single`)

```python
from pathlib import Path

from langchain_hwp_hwpx import HwpHwpxLoader

loader = HwpHwpxLoader(
    file_path=Path("docs/sample.hwp"),
    mode="single",
    include_tables=True,
    include_notes=True,
)

docs = loader.load()
print(len(docs))
print(docs[0].metadata)
```

### Quickstart (`elements`)

```python
from langchain_hwp_hwpx import HwpHwpxLoader

loader = HwpHwpxLoader("docs/sample.hwpx", mode="elements")
for doc in loader.lazy_load():
    print(doc.metadata["element_type"], doc.metadata["element_index"])
```

### Main options

- `mode`: `"single"` or `"elements"`
- `include_tables`, `include_notes`, `include_memos`, `include_hyperlinks`
- `include_images`, `images_dir`, `image_document_mode`
- `on_encrypted`: `"raise" | "skip" | "placeholder"`
- `on_invalid`: `"raise" | "skip" | "placeholder"`
- `on_error`: `"raise" | "skip" | "warn"`

### Compatibility

- Python: `>=3.10,<4.0`
- `langchain-core>=1.0.0,<2.0.0`
- `hwp-hwpx-parser>=1.0.0,<2.0.0`
