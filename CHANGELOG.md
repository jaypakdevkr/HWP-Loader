# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows SemVer.

## [0.2.0] - 2026-10-15

### Fixed

- Detect distribution HWP files instead of silently indexing their compatibility notice.
- Close parser file handles after success, policy skips, errors, and generator closure.
- Extract tables once and honor `include_tables=False`, including table-only documents.
- Preserve HWP/HWPX cell coordinates and merged spans; expose `cells` in table metadata.
- Prevent cross-document image overwrites and ignore embedded filenames for output paths.
- Read HWPX sections in numeric order and avoid repeated nested tables.
- Align the package license classifier with the existing MIT LICENSE and fix repository URLs.

### Added

- Explicit `on_unsupported` policy and optional `distribution_backend="pyhwp"`.
  Install the `distribution` extra for this backend; pyhwp has its own AGPLv3+ license.
- Real-parser regression tests and release checks before publishing.

### Compatibility

- Parser is pinned to tested version 1.0.0 because adapters use its internal record APIs.
- Table text and image paths change; rebuild existing vector indexes after upgrading.
- `elements` groups body and top-level tables; it does not reconstruct page layout.

## [0.1.1] - 2026-02-17

### Changed

- Updated README with Korean-first usage guide and examples.
- Fixed hyperlink parsing for tuple/object/dict forms from parser results.
- Normalized `file_type` metadata to stable values (`hwp`, `hwpx`).
- Fixed CSV table rendering to respect `extract_options.table_delimiter`.
- Improved type-check compatibility and expanded tests for parser-realistic data shapes.

## [0.1.0] - 2026-02-17

### Added

- `HwpHwpxLoader` with `single` and `elements` modes.
- `HwpHwpxDirectoryLoader` with deterministic file ordering.
- Extraction toggles for tables, notes, memos, hyperlinks, and images.
- Error and policy handling for encrypted/invalid/parsing failures.
- Unit tests with parser reader mocking.
- Packaging metadata for PyPI and CI workflows.
