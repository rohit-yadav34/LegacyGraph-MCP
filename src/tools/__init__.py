"""MCP tool functions for LegacyGraph-MCP."""

from src.tools.analysis import analyze_codebase
from src.tools.queries import (
    get_file_functions,
    get_file_coupling,
    get_callers,
    get_callees,
    detect_cycles,
    get_orphan_functions,
)
from src.tools.export import generate_mermaid_graph, export_ide_graph
from src.tools.feedback import send_feedback, submit_feedback

__all__ = [
    "analyze_codebase",
    "get_file_functions",
    "get_file_coupling",
    "get_callers",
    "get_callees",
    "detect_cycles",
    "get_orphan_functions",
    "generate_mermaid_graph",
    "export_ide_graph",
    "send_feedback",
    "submit_feedback",
]

