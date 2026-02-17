# PRD: LangChain HWP/HWPX Loader

### 0) 문서 정보

* 문서명: `LangChain HWP/HWPX Loader PRD`
* 버전: v0.1 (초안)
* 목표 릴리즈: MVP v0.1.0 (PyPI 공개)

---

## 1) 배경 및 문제 정의

한국 공공/기업 문서가 **`.hwp`/`.hwpx`**로 많이 존재하고, RAG 파이프라인에서 가장 큰 난관이 **로딩(텍스트+표+각주/미주+메모) 품질**이다. 기존 방식은 다음 문제가 많다:

* Windows COM(한글 설치 필요) 의존 → 온프렘 Linux/컨테이너 환경에 부적합
* Java/JVM 또는 외부 API 의존 → 보안/운영 부담
* 텍스트만 가져오고 **표/각주/미주/메모**가 누락되거나 구조가 깨짐

최근 `hwp-hwpx-parser`는 **순수 Python**으로 HWP/HWPX에서 텍스트/표/각주/미주/메모/하이퍼링크/이미지를 추출하고, 통합 Reader API를 제공한다. (Apache-2.0, 2026-01-29 릴리즈) ([PyPI][1])

따라서 본 프로젝트는 `hwp-hwpx-parser`를 엔진으로 사용해, **LangChain Document Loader(BaseLoader)** 형태로 감싸고, RAG용으로 “표/각주/미주까지 최대한 보존”된 문서 로딩을 지원한다. LangChain Loader는 `lazy_load()`를 구현하는 형태가 권장된다. ([LangChain Reference][2])

---

## 2) 목표(Goals) / 비목표(Non‑Goals)

### Goals (반드시 달성)

1. **온프렘/오프라인**에서 `.hwp/.hwpx`를 LangChain `Document`로 로딩

   * 네트워크 호출/외부 API 없음
   * JVM/한글 설치 불필요 (엔진은 `hwp-hwpx-parser`) ([PyPI][1])
2. **표(테이블)**를 Markdown 또는 CSV 등으로 안정적으로 보존
3. **각주/미주(footnote/endnote)**를 누락 없이 포함(최소 1) 본문 마커, 2) 각주/미주 본문)
4. Loader가 **LangChain `BaseLoader` 규약**에 맞게 동작 (`lazy_load()` 구현) ([LangChain Reference][2])
5. **PyPI 배포** 가능한 품질 (패키징/문서/테스트/CI 포함)

### Non‑Goals (이번 범위에서 제외)

* 문서 편집(쓰기) 기능 (읽기 전용)
* OCR(스캔 이미지 텍스트화), 레이아웃 렌더링(페이지 좌표/박스)
* 완전한 “문단/표/그림” 시각적 읽기 흐름 재구성(엔진이 제공하는 범위 내)
* 벡터DB 저장/임베딩/스플릿 로직(사용자가 LangChain 모듈로 수행)

---

## 3) 타겟 사용자 / 핵심 사용 시나리오

### Personas

* (A) 온프렘 RAG 구축 엔지니어: 사내 문서(.hwp/.hwpx) 수만 건을 인덱싱
* (B) 백엔드 개발자: 특정 폴더의 문서를 주기적으로 적재
* (C) 데이터 엔지니어: 표/각주가 중요한 규정/지침 문서 QA

### 주요 시나리오

1. 단일 파일 로딩: `doc.hwp` → LangChain `Document` 1개(또는 여러 개)
2. 디렉토리 로딩: `/data/docs/**/*.hwp(x)` → 여러 `Document`
3. 보안: 인터넷 차단된 서버에서도 동일 동작
4. 품질: 표/각주/미주가 “본문에서 참조 가능”하고 “실제 내용도 포함”

---

## 4) 제품 범위(Scope)

### MVP(v0.1.0) 범위

* `HwpHwpxLoader` (단일 파일)
* `HwpHwpxDirectoryLoader` (디렉토리/글롭)
* 출력 모드 2종:

  * `mode="single"`: 문서 전체를 1개의 Document로 반환 (RAG 기본형)
  * `mode="elements"`: 본문/표/각주/미주/메모를 여러 Document로 분리 반환 (구조형)
* 표/각주/미주/메모 포함 옵션화
* 암호화/유효성 처리 옵션(`on_encrypted`, `on_invalid`, `on_error`)
* 이미지 추출은 **옵션(기본 off)**, 저장은 `images_dir` 지정 시에만

### v0.2+ (후속)

* “읽기 순서 보존(element sequencing)” 강화(표 블록 위치 기반 분리)
* 단락/헤딩 단위 메타데이터(가능 범위에서)
* `BytesIO`/바이너리 입력 지원 (현재 엔진이 파일 경로 기반이므로 검토 필요)
* LlamaIndex Reader도 함께 제공(선택)

---

## 5) 의존성 / 호환성

### 핵심 의존성

* `hwp-hwpx-parser>=1.0.0`

  * Reader 통합 API 제공: `Reader.text`, `Reader.tables`, `extract_text_with_notes()`, 이미지/메모/하이퍼링크 등 ([PyPI][1])
* `langchain-core>=1.0.0,<2.0.0` 권장

  * LangChain BaseLoader/Document 호환
  * `langchain-core`는 Python `>=3.10` 요구 ([PyPI][3])

### Python 버전

* `>=3.10,<4.0` (LangChain-core 기준) ([PyPI][3])

### OS

* OS independent (Windows/Linux/macOS)

---

## 6) 기능 요구사항 (Functional Requirements)

### FR-1. 단일 파일 Loader

**설명:** `.hwp` 또는 `.hwpx` 파일 경로를 받아 LangChain `Document`를 생성한다.

* Input: `file_path: str | pathlib.Path`
* Output: `Iterator[Document]` (`lazy_load()`), 또는 `List[Document]` (`load()`)

**수용 기준(Acceptance Criteria)**

* `.hwp/.hwpx` 확장자 자동 처리(엔진 Reader가 suffix 기반 감지) ([GitHub][4])
* `mode="single"`일 때:

  * `page_content`에 텍스트 포함
  * 표가 옵션에 따라 Markdown/CSV/Inline 형태로 포함 (엔진 `ExtractOptions.table_style`) ([GitHub][5])
  * 각주/미주/메모/하이퍼링크가 옵션에 따라 포함 (`extract_text_with_notes()` 결과 사용) ([GitHub][5])
* `metadata["source"] == str(file_path)` 포함

---

### FR-2. “elements” 분리 모드

**설명:** 문서를 여러 Document로 분리해 반환한다.

권장 분리 단위:

* `type="body"`: 본문 텍스트
* `type="table"`: 테이블(1개당 1 Document)
* `type="footnote"`: 각주(1개당 1 Document)
* `type="endnote"`: 미주(1개당 1 Document)
* `type="memo"`: 메모(1개당 1 Document)
* `type="hyperlink"`: 링크(1개당 1 Document 또는 묶어서 1 Document)

**수용 기준**

* `NoteData`는 `note_type`, `number`, `text`를 가지므로 이를 바탕으로 content를 구성 ([GitHub][5])
* `TableData`는 `rows` 및 `to_markdown()/to_csv()/to_inline()` 제공 ([GitHub][5])
* 모든 element document는 최소 다음 metadata 포함:

  * `source`: 원본 파일 경로
  * `file_type`: `"hwp"` 또는 `"hwpx"` (Reader.file_type 기반) ([GitHub][4])
  * `element_type`: body/table/footnote/endnote/memo/hyperlink/image
  * `element_index`: 0부터 시작하는 순번(문서별 안정적)

---

### FR-3. 추출 옵션(표/이미지 마커/구분자)

**설명:** 사용자가 표 스타일/이미지 마커/문단 구분자 등을 제어할 수 있어야 한다.

`hwp-hwpx-parser`의 옵션 모델을 그대로 사용하거나, 래핑 옵션 제공:

* `ExtractOptions`:

  * `table_style`: `TableStyle.MARKDOWN|CSV|INLINE`
  * `table_delimiter`
  * `image_marker`: `ImageMarkerStyle.NONE|SIMPLE|WITH_NAME`
  * `paragraph_separator`, `line_separator`, `include_empty_paragraphs` ([GitHub][5])

**수용 기준**

* Loader 생성자에서 `extract_options: Optional[ExtractOptions]` 또는 동등한 kwargs 지원
* 기본값은 `MARKDOWN + SIMPLE` (엔진 기본값과 정렬) ([GitHub][5])

---

### FR-4. 암호화/오류 처리 정책

**설명:** 암호화 파일 또는 손상 파일에서 동작 정책을 선택 가능.

* `on_encrypted`: `"raise" | "skip" | "placeholder"`
* `on_invalid`: `"raise" | "skip" | "placeholder"`
* `on_error`: `"raise" | "skip" | "warn"`

**수용 기준**

* Reader가 `is_encrypted`, `is_valid` 제공하므로 이를 활용 ([GitHub][4])
* `"placeholder"`일 때는 최소 metadata에 상태를 남기고, content에는 안내 텍스트

---

### FR-5. 디렉토리 Loader

**설명:** 폴더를 입력하면 `.hwp/.hwpx`를 재귀 탐색하고 문서를 로딩한다.

* Input:

  * `dir_path`
  * `glob`: 기본 `"**/*"`
  * `extensions`: 기본 `[".hwp", ".hwpx"]`
  * `recursive: bool = True`
* Output: files 순회하며 Document yield

**수용 기준**

* 파일 정렬은 안정적으로(예: path 문자열 기준 정렬)
* 에러 정책(`on_error`) 적용

---

### FR-6. 이미지(옵션)

**설명:** 이미지 추출은 기본 off. 켜면 이미지 바이너리 저장 또는 metadata 포함을 지원.

* `include_images: bool = False`
* `images_dir: Optional[Path] = None`
* `image_document_mode`: `"metadata_only" | "save_and_reference"`

**수용 기준**

* 엔진이 `get_images()` 및 `ImageData.save()` 제공 ([GitHub][5])
* 저장 시 파일명은 `img.filename` 우선, 없으면 `image_{index:03d}.{format}` 규칙(엔진 예시와 정렬) ([GitHub][4])

---

## 7) 출력 포맷/메타데이터 규격

### 공통 metadata 필드

* `source`: 원본 파일 경로(str)
* `file_name`: 파일명
* `file_type`: `"hwp"` or `"hwpx"`
* `loader`: 패키지명/버전
* `parser`: `"hwp-hwpx-parser"` 및 버전(가능하면 `importlib.metadata.version`)
* `extracted_at`: ISO timestamp (옵션)

### element 모드 추가 metadata

* `element_type`: `"body"|"table"|"footnote"|"endnote"|"memo"|"hyperlink"|"image"`
* `element_index`: int
* table:

  * `row_count`, `col_count` (TableData property) ([GitHub][5])
* note:

  * `note_type`, `note_number` ([GitHub][5])
* memo:

  * `memo_id`, `author`, `referenced_text` 등(가능한 값) ([GitHub][5])
* hyperlink:

  * `url`, `text`

---

## 8) API 설계 (패키지 외부 인터페이스)

### 패키지명(제안)

* PyPI 프로젝트명 후보:

  * `langchain-hwp-hwpx-loader` (권장: 명확)
  * `langchain-hwp-hwpx` (짧지만 향후 확장 시 의미가 넓음)
* import 모듈명:

  * `langchain_hwp_hwpx_loader` (긴 편)
  * `langchain_hwp_hwpx` (권장)

> PRD 수용 기준: 배포 전 PyPI에서 이름 중복 여부 확인 후 확정.

### 클래스/함수(제안)

#### `HwpHwpxLoader(BaseLoader)`

```python
HwpHwpxLoader(
    file_path: str | Path,
    mode: Literal["single", "elements"] = "single",
    extract_options: Optional[hwp_hwpx_parser.ExtractOptions] = None,

    include_tables: bool = True,
    include_notes: bool = True,      # footnote+endnote
    include_memos: bool = True,
    include_hyperlinks: bool = True,

    include_images: bool = False,
    images_dir: Optional[str | Path] = None,
    image_document_mode: Literal["metadata_only", "save_and_reference"] = "metadata_only",

    on_encrypted: Literal["raise", "skip", "placeholder"] = "raise",
    on_invalid: Literal["raise", "skip", "placeholder"] = "raise",
    on_error: Literal["raise", "skip", "warn"] = "raise",

    extra_metadata: Optional[dict] = None,
)
```

* 필수 구현: `lazy_load(self) -> Iterator[Document]`
* `load()`는 BaseLoader가 제공하는 기본 구현을 사용(override 금지 권장) ([LangChain Reference][2])

#### `HwpHwpxDirectoryLoader(BaseLoader)`

```python
HwpHwpxDirectoryLoader(
    dir_path: str | Path,
    glob: str = "**/*",
    recursive: bool = True,
    extensions: tuple[str, ...] = (".hwp", ".hwpx"),
    **loader_kwargs,  # 내부적으로 HwpHwpxLoader에 전달
)
```

---

## 9) 아키텍처/구현 개요

### 내부 흐름(단일 파일)

1. `Reader(file_path)` 생성 (`hwp_hwpx_parser.Reader`) ([GitHub][4])
2. `is_valid`, `is_encrypted` 체크 (정책 적용) ([GitHub][4])
3. 추출:

   * `result = reader.extract_text_with_notes(extract_options)` ([GitHub][4])
   * tables/images/memos 등은 `reader.get_tables()`, `reader.get_images()`, `result.memos` 등으로 접근 ([GitHub][4])
4. mode에 따라 Document 생성/반환

### 성능/메모리

* `lazy_load()`는 generator로 문서를 순차 생성
* 파서가 내부적으로 파일을 한 번에 읽을 수 있어도, 최소한 “결과 Document 생성/전달”은 스트리밍 방식으로 구현

---

## 10) 비기능 요구사항 (NFR)

### NFR-1. 온프렘/보안

* 외부 네트워크 통신 없음
* 사용자 문서/내용을 로그에 남기지 않음(기본)
* 예외 메시지에 원문 전체를 포함하지 않음(경로 정도만)

### NFR-2. 안정성

* 잘못된 확장자/손상 파일 처리 정책 제공
* 파서 예외를 래핑하여 의미 있는 에러 제공

### NFR-3. 관측성(옵션)

* 표준 `logging` 사용
* `on_error="warn"` 시 warning 로그 남김(파싱 실패 파일/사유)

### NFR-4. 품질

* 타입 힌트/`py.typed` 제공
* CI에서 lint/test 통과

---

## 11) 테스트 계획

### Unit Tests (필수)

* `unittest.mock`으로 `hwp_hwpx_parser.Reader`를 patch하여:

  * `extract_text_with_notes()`가 반환하는 `ExtractResult` 기반으로 결과 문서 형식 검증 ([GitHub][5])
  * `get_tables()`가 반환하는 `TableData`로 markdown/csv 변환 검증 ([GitHub][5])
  * 암호화/유효성 플래그에 따른 정책 분기 검증 ([GitHub][4])
* “elements 모드”에서 Document 개수/metadata 정확성 검증

### Integration Tests (권장, optional)

* 작은 `.hwpx` fixture 포함(라이선스 문제 없는 자체 제작 파일)
* CI에서는 선택적으로 실행(`pytest -m integration`)

---

## 12) 문서화/예제

### README 필수 섹션

* 설치:

  * `pip install langchain-hwp-hwpx-loader` (가칭)
* Quickstart:

  * single mode 예제
  * elements mode 예제
* 옵션 설명:

  * table_style, image_marker, notes/memos 포함 여부
* 제한사항:

  * 암호화 파일은 감지만 가능(정책에 따라 skip/raise) ([PyPI][1])
* 의존성/호환성(Python>=3.10)

### Docstring / API Reference

* 클래스/인자/반환 Document.metadata 스키마 명시

---

## 13) 패키징/배포 요구사항 (PyPI)

### 빌드 시스템

* `pyproject.toml` 기반(PEP 517/518)
* 추천: `hatchling` 또는 `setuptools` + `build`
* 필수 포함 파일:

  * `LICENSE`
  * `README.md`
  * `CHANGELOG.md`

### 버전 정책

* SemVer (`0.1.0` → `0.1.1` bugfix → `0.2.0` 기능 추가)

### CI/CD (GitHub Actions)

* PR 시:

  * `ruff`/`black`/`mypy`(선택) + `pytest`
* tag push 시:

  * wheel/sdist 빌드
  * PyPI Trusted Publishing(OIDC)로 배포(권장; 최근 PyPI에서 일반화)
  * (선택) GitHub Release 자동 생성

---

## 14) 리스크 & 대응

1. **엔진 출력 포맷 변화 리스크**

   * `hwp-hwpx-parser`가 빠르게 발전 중(2026-01 릴리즈) ([PyPI][1])
   * 대응: 의존성 범위를 `>=1.0.0,<2.0.0`로 두고, CI에서 최소/최신 버전 매트릭스 테스트
2. **표/각주 중복 포함 문제**

   * 대응: `mode="single"`은 엔진 `ExtractResult.text`를 우선 신뢰하고, 필요한 경우 “append missing notes” 로직을 옵션으로 제공
3. **대용량 문서 성능**

   * 대응: `lazy_load`로 Document 생성은 streaming, 이미지 저장은 옵션화

---

## 15) 구현 체크리스트 (Codex 작업용 티켓 분해 예시)

### Epic A: Core Loader

* [ ] A1. `HwpHwpxLoader` 구현 (`lazy_load`)
* [ ] A2. `mode="single"` 구현
* [ ] A3. `mode="elements"` 구현
* [ ] A4. metadata 표준화/추가 메타데이터 병합
* [ ] A5. 암호화/유효성/에러 정책 구현

### Epic B: Directory Loader

* [ ] B1. glob/recursive 탐색
* [ ] B2. 파일 정렬/필터
* [ ] B3. 내부적으로 `HwpHwpxLoader` 재사용

### Epic C: Tests

* [ ] C1. mock 기반 unit tests
* [ ] C2. (선택) `.hwpx` fixture + integration tests

### Epic D: Packaging & Release

* [ ] D1. `pyproject.toml` / version / dependencies
* [ ] D2. README / CHANGELOG / LICENSE
* [ ] D3. GitHub Actions: test + publish workflow

---

## 16) MVP 사용 예시 (README에 들어갈 수준)

```python
from pathlib import Path
from hwp_hwpx_parser import ExtractOptions, TableStyle, ImageMarkerStyle
from langchain_hwp_hwpx import HwpHwpxLoader

opts = ExtractOptions(
    table_style=TableStyle.MARKDOWN,
    image_marker=ImageMarkerStyle.WITH_NAME,
)

loader = HwpHwpxLoader(
    file_path=Path("docs/sample.hwp"),
    mode="single",
    extract_options=opts,
    include_notes=True,
    include_tables=True,
)

docs = loader.load()
print(docs[0].page_content[:500])
print(docs[0].metadata)
```

---