# Changelog

All notable changes to LegacyGraph-MCP are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] — 2026-10-16

### Added
- **`send_feedback` and `submit_feedback` MCP tools**:
  - Lets users and coding agents submit feedback, bug reports, and feature requests directly from their MCP client.
  - Multi-target dispatch:
    - Webhook integration supporting generic JSON POST endpoints, Discord rich embeds, and Slack Block Kit messages.
    - GitHub Issues integration via GitHub REST API (`POST /repos/{owner}/{repo}/issues`) with automatic labels (`feedback`, `enhancement`, `bug`).
    - Local append-only JSONL audit log (`data/feedback.jsonl`) with resilient file locking and fallback.
  - Configurable via `FEEDBACK_WEBHOOK_URL`, `GITHUB_TOKEN`, and `GITHUB_REPO` environment variables or runtime tool arguments.
  - Fully registered in both local and cloud deployment modes and reflected on the live server card.

---

## [2.0.0] — 2026-07-07


### Changed — MCP 2.0 Upgrade
- **Migrated from the legacy `mcp.server.fastmcp` (FastMCP 1.0 bundled in the
  official SDK) to standalone FastMCP 2.x** (`fastmcp >=2.14,<3`), bringing
  current MCP spec support (structured output, elicitation, auth, middleware)
- `src/server.py` — transport settings (host/port/path) moved out of the
  `FastMCP()` constructor into `mcp.run()` per the FastMCP 2.x API; server
  now advertises `version="2.0.0"` and `website_url` metadata
- `src/__main__.py` — canonical HTTP transport renamed to `http`
  (`streamable-http` still accepted as an alias); stdio runs banner-free
- Server card (`/.well-known/mcp/server-card.json`) now derives its tool list
  from the live FastMCP registry instead of a hand-maintained copy
- `pyproject.toml` — dropped direct `mcp` pin (provided by fastmcp) and the
  unused `gitpython` dependency

### Added
- **CI pipeline** (`.github/workflows/ci.yml`) — ruff, strict mypy (`src/`),
  pytest on Python 3.11/3.12/3.13, and the end-to-end verifier on every
  push and pull request
- `poetry.lock` regenerated for the FastMCP 2.x stack (the stale lock would
  have kept building Docker images against `mcp 1.x`)

### Fixed
- **Codebase now passes `ruff check` and strict `mypy` cleanly** — fixed
  undefined forward references, untyped overrides, and `Optional` leaks;
  `_scan_directory` now raises a clear error instead of crashing when no
  graph is available in cloud mode
- **Logging no longer writes to stdout** — in stdio transport, stdout carries
  the JSON-RPC stream; log lines there corrupt the protocol. All logs go to
  stderr now
- **`tools/verifier.py` and three tests were broken since the GraphPool
  refactor** — they queried without `project_id`, hitting an empty default
  graph. Verifier reports 100% accuracy again
- **Patch-aware cache check** — `analyze_codebase(repo_url=..., patch_content=...)`
  no longer short-circuits on an unchanged remote HEAD, so a new patch is
  always applied
- `analyze_codebase(directory_path=...)` result message now includes the
  parsed file count
- Removed `logging.basicConfig()` side effect from `src/core/parser.py`

---

## [0.3.0] — 2026-03-21

### Added
- **Modular sub-package architecture:** Reorganized flat `src/` into `src/core/`, `src/tools/`, and `src/utils/`
- `src/__main__.py` — Clean CLI entry point (`python -m src`)
- `ARCHITECTURE.md` — Detailed architecture documentation with Mermaid diagrams
- `CONTRIBUTING.md` — Development standards, git workflow, PR checklist
- `CHANGELOG.md` — Version history (this file)

### Changed
- `src/server.py` — Slimmed from 577 lines to ~150 lines (thin MCP registration layer)
- `src/tools/analysis.py` — `analyze_codebase` extracted from server
- `src/tools/queries.py` — Query tools (`get_callers`, `get_callees`, etc.) extracted from server
- `src/tools/export.py` — Mermaid export tools extracted from server
- `README.md` — Rewritten with updated project structure and commands
- `PROJECT_MANUAL.md` — Rewritten with updated API reference and architecture
- `tests/test_core.py` — Updated imports for new package structure
- `tools/verifier.py` — Updated imports for new package structure

### Removed
- Flat module files: `src/graph.py`, `src/parser.py`, `src/config.py`, `src/logger.py`, `src/services.py`, `src/helpers.py` (moved into sub-packages)

---

## [0.2.0] — 2026-03-20

### Added
- Hybrid cloud/local deployment (`MCP_MODE`)
- `generate_mermaid_graph` tool — inline Mermaid diagrams (cloud-friendly)
- `export_ide_graph` tool — save Mermaid to local `.md` files
- `analyze_codebase` — unified ingestion tool (repo_url, raw_files, directory_path)
- Mode-aware tool registration (`_register_tools`)
- Server card endpoint (`/.well-known/mcp/server-card.json`)
- Streamable HTTP and SSE transport support
- Auto-mode detection from `--transport` flag

### Changed
- Server now supports both `stdio` and HTTP transports
- Tool functions conditionally registered based on deployment mode

---

## [0.1.0] — 2026-01-17

### Added
- Initial release
- Tree-sitter-based C++ parser (`CppParser`)
- NetworkX dependency graph (`DependencyGraph`)
- File-aware node tagging
- MCP server with 6 core tools
- Cycle detection, orphan detection, caller/callee analysis
- Cross-file dependency analysis
- Pytest test suite (12 test cases)
- End-to-end verifier (`tools/verifier.py`)
- Sample legacy C++ project (`data/legacy_project/`)
