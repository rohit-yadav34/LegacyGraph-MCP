"""
Remote-mode smoke tests for LegacyGraph-MCP.

These tests validate the full cloud execution path:
  - Tool registration (cloud mode must NOT expose local-only tools)
  - analyze_codebase via raw_files (no network, no local paths)
  - get_callers / get_callees graph queries
  - Confirm export_ide_graph is blocked in cloud mode

All tests are self-contained — no git clones, no filesystem side effects.
"""

import pytest

import src.utils.config as config
import src.utils.services as services
from src.core.graph import DependencyGraph
from src.utils.helpers import _get_raw_files_project_id


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Small C++ snippet used across multiple tests
_SAMPLE_RAW_FILES = [
    {
        "filename": "main.cpp",
        "content": (
            "void helper();\n"
            "void main() { helper(); logger(); }\n"
        ),
    },
    {
        "filename": "utils.cpp",
        "content": (
            "void logger() {}\n"
            "void helper() { logger(); }\n"
        ),
    },
]


# Pre-compute the stable target_id for _SAMPLE_RAW_FILES so query tests
# can pass it as project_id without duplicating the hashing logic.
_SAMPLE_TARGET_ID = _get_raw_files_project_id(_SAMPLE_RAW_FILES)


@pytest.fixture(autouse=True)
def _cloud_mode_and_fresh_graph():
    """
    Force cloud mode and a pristine graph_service for every test in this module.
    Restores to local mode on teardown so other test modules are unaffected.
    """
    original_mode = config.MCP_MODE
    original_graph_service = services.graph_service
    config.MCP_MODE = "cloud"
    services.graph_service = DependencyGraph()
    yield
    config.MCP_MODE = original_mode
    services.graph_service = original_graph_service


# ---------------------------------------------------------------------------
# Test 1 — Cloud tool registration omits local-only tools
# ---------------------------------------------------------------------------

def test_cloud_tool_registration():
    """
    _register_tools('cloud') must NOT register export_ide_graph.

    Uses a fresh FastMCP instance (instead of mutating the module-level
    singleton) and the public get_tools() API from FastMCP 2.x.
    """
    import asyncio
    from fastmcp import FastMCP
    from src.server import _register_tools

    fresh_server = FastMCP(name="test-cloud-registration")
    _register_tools("cloud", server=fresh_server)

    registered = list(asyncio.run(fresh_server.get_tools()).keys())

    assert "export_ide_graph" not in registered, (
        f"export_ide_graph must NOT be registered in cloud mode; got: {registered}"
    )
    for expected in ("analyze_codebase", "get_callers", "get_callees", "send_feedback"):
        assert expected in registered, (
            f"Expected tool '{expected}' to be registered in cloud mode; got: {registered}"
        )



# ---------------------------------------------------------------------------
# Test 2 — analyze_codebase accepts raw_files in cloud mode
# ---------------------------------------------------------------------------

def test_cloud_analyze_raw_files():
    """analyze_codebase with raw_files should succeed in cloud mode."""
    from src.tools.analysis import analyze_codebase

    result = analyze_codebase(raw_files=_SAMPLE_RAW_FILES)

    assert "error" not in result.lower(), f"Unexpected error: {result}"

    # Verify nodes via the pool graph (graph_service is not updated in cloud mode)
    nodes = services.graph_pool.get_graph(_SAMPLE_TARGET_ID).get_all_nodes()
    assert "main" in nodes
    assert "helper" in nodes
    assert "logger" in nodes


# ---------------------------------------------------------------------------
# Test 3 — get_callers works after raw_files analysis
# ---------------------------------------------------------------------------

def test_cloud_get_callers():
    """get_callers('logger') should return ['main', 'helper'] (any order)."""
    from src.tools.analysis import analyze_codebase
    from src.tools.queries import get_callers

    analyze_codebase(raw_files=_SAMPLE_RAW_FILES)
    result = get_callers("logger", project_id=_SAMPLE_TARGET_ID)

    # Result is a formatted string; verifiable by checking for caller names
    assert "helper" in result and "main" in result, (
        f"Expected callers of 'logger' to include both 'helper' and 'main'; got: {result}"
    )


# ---------------------------------------------------------------------------
# Test 4 — get_callees works after raw_files analysis
# ---------------------------------------------------------------------------

def test_cloud_get_callees():
    """get_callees('main') should include 'helper' and 'logger'."""
    from src.tools.analysis import analyze_codebase
    from src.tools.queries import get_callees

    analyze_codebase(raw_files=_SAMPLE_RAW_FILES)
    result = get_callees("main", project_id=_SAMPLE_TARGET_ID)

    assert "helper" in result and "logger" in result, (
        f"Expected callees of 'main' to include both 'helper' and 'logger'; got: {result}"
    )


# ---------------------------------------------------------------------------
# Test 5 — export_ide_graph is blocked in cloud mode
# ---------------------------------------------------------------------------

def test_cloud_no_local_tool_leakage():
    """export_ide_graph must return an error string in cloud mode."""
    from src.tools.export import export_ide_graph

    result = export_ide_graph(output_filename="should_not_be_created.md")

    assert "error" in result.lower(), (
        f"export_ide_graph should be blocked in cloud mode; got: {result}"
    )
    assert "local" in result.lower(), (
        f"Error message should mention 'local'; got: {result}"
    )


# ---------------------------------------------------------------------------
# Test 6 — directory_path is rejected in cloud mode
# ---------------------------------------------------------------------------

def test_cloud_rejects_directory_path():
    """analyze_codebase must reject directory_path when in cloud mode."""
    from src.tools.analysis import analyze_codebase

    result = analyze_codebase(directory_path="/any/local/path")

    assert "error" in result.lower()
    assert "cloud" in result.lower()
