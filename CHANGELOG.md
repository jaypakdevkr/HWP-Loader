# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows SemVer.

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
