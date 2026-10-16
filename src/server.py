"""
LegacyGraph-MCP Server — MCP registration and server card.

This module is a thin orchestration layer. Business logic lives in
src.tools, graph model in src.core, and infrastructure in src.utils.

Built on FastMCP 2.x (standalone framework, https://gofastmcp.com).
Transport configuration (host/port/path) is passed to mcp.run() in
src.__main__ rather than the constructor, per the FastMCP 2.x API.
"""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from starlette.responses import JSONResponse

from src.utils.logger import logger
import src.utils.config as config
import src.utils.services as services
from src.utils.tasks import TaskState
from src.tools import (
    analyze_codebase,
    get_file_functions,
    get_file_coupling,
    get_callers,
    get_callees,
    detect_cycles,
    get_orphan_functions,
    generate_mermaid_graph,
    export_ide_graph,
    send_feedback,
    submit_feedback,
)

SERVER_NAME = "legacy-mcp-analyzer"
SERVER_VERSION = "2.1.0"


try:
    from fastmcp import FastMCP
except ImportError:
    logger.warning("FastMCP 2.x not found. Using mock for logic verification.")

    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, name: str, **kwargs: Any):
            self.name = name

        def tool(self) -> Any:
            return lambda f: f

        def run(self, *args: Any, **kwargs: Any) -> None:
            logger.error(
                "Cannot start server: FastMCP dependency missing. "
                "Please `pip install fastmcp` or add it to pyproject.toml."
            )

        def custom_route(self, *args: Any, **kwargs: Any) -> Any:
            return lambda f: f

        async def get_tools(self) -> dict[str, Any]:
            return {}


# Initialize Server with rich metadata for MCP clients / Smithery
mcp = FastMCP(
    name=SERVER_NAME,
    instructions=(
        "LegacyGraph-MCP exposes a parsed C++ call graph over MCP. "
        "1. Use analyze_codebase to ingest code and get a project_id. "
        "2. Pass the project_id to other tools to query that specific graph. "
        "3. Use send_feedback to send feedback, bug reports, or feature requests."
    ),
    version=SERVER_VERSION,
    website_url="https://github.com/RohitYadav34980/LegacyGraph-MCP",
)


# ============================================================
# Tool Registration (mode-aware)
# ============================================================

def _register_tools(mode: str, server: Optional["FastMCP"] = None) -> "FastMCP":
    """
    Register MCP tools on a FastMCP instance.

    Called from __main__ AFTER the deployment mode is resolved so that
    cloud mode never exposes local-only tools like export_ide_graph.

    Args:
        mode:   Resolved deployment mode ("local" or "cloud").
        server: Target FastMCP instance. Defaults to the module-level
                singleton; tests may pass a fresh instance for isolation.

    Returns:
        The FastMCP instance the tools were registered on.
    """
    target = server if server is not None else mcp

    # Always available
    target.tool()(analyze_codebase)
    target.tool()(get_file_functions)
    target.tool()(get_file_coupling)
    target.tool()(get_callers)
    target.tool()(get_callees)
    target.tool()(detect_cycles)
    target.tool()(get_orphan_functions)
    target.tool()(generate_mermaid_graph)
    target.tool()(send_feedback)
    target.tool()(submit_feedback)


    # Task Management (SEP-1686)
    @target.tool()
    def get_task_status(task_id: str) -> dict[str, Any]:
        """Check the status of a long-running task."""
        task = services.task_registry.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found."}

        return {
            "taskId": task.id,
            "state": task.state.value,
            "progress": task.progress,
            "status_text": task.status_text,
            "updated_at": task.updated_at.isoformat(),
        }

    @target.tool()
    def get_task_result(task_id: str) -> dict[str, Any]:
        """Retrieve the result of a completed task."""
        task = services.task_registry.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found."}

        if task.state == TaskState.COMPLETED:
            return {
                "taskId": task.id,
                "result": task.result,
            }

        if task.state in (TaskState.FAILED, TaskState.CANCELLED):
            return {
                "taskId": task.id,
                "state": task.state.value,
                "error": task.error or task.status_text,
            }

        return {
            "taskId": task.id,
            "state": task.state.value,
            "message": "Task not yet completed.",
        }

    # Local-only tools
    if mode == "local":
        target.tool()(export_ide_graph)
        logger.info("Registered local-only tool: export_ide_graph")
    else:
        logger.info("Cloud mode: export_ide_graph is NOT registered.")

    return target


# ============================================================
# Server Card
# ============================================================

@mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET"])
async def server_card(_: object) -> "JSONResponse":
    """
    Serve a discovery card reflecting the *actually registered* tools.

    The tool list is derived from the live FastMCP registry instead of a
    hand-maintained copy, so it can never drift from reality (and
    automatically respects mode-aware registration).
    """
    from starlette.responses import JSONResponse

    registered = await mcp.get_tools()
    tools = [
        {
            "name": name,
            "description": (tool.description or "").strip(),
        }
        for name, tool in sorted(registered.items())
    ]

    return JSONResponse(
        {
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "capabilities": {
                "modes": ["local", "cloud"],
                "currentMode": config.MCP_MODE,
            },
            "tools": tools,
            "resources": [],
            "prompts": [],
        }
    )

# HF Spaces Ping Route
@mcp.custom_route("/", methods=["GET"])
async def root_ping(_: object) -> "JSONResponse":
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "healthy", "service": "LegacyGraph-MCP Cloud Node"})
