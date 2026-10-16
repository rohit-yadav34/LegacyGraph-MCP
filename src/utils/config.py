import os
from pathlib import Path
from typing import List

# ============================================================
# Deployment Mode
# ============================================================
# Resolved at startup from --mode arg, --transport hint, or MCP_MODE env var.
# "local"  → direct disk access, stdio transport, export_ide_graph available
# "cloud"  → ephemeral /tmp/ clones, HTTP transport, export_ide_graph hidden
MCP_MODE: str = os.environ.get("MCP_MODE", "local")

# C++ file extensions to scan
CPP_EXTENSIONS: List[str] = ["*.cpp", "*.c", "*.h", "*.hpp", "*.cc"]

# ============================================================
# Persistence (Phase 3)
# ============================================================

# HF Spaces Storage Detection
# If a storage bucket or volume is mounted (typically at /data), we use it directly.
PERSISTENT_STORAGE_ROOT: str = os.environ.get("HF_STORAGE_MOUNT", "/data")
IS_STORAGE_MOUNTED: bool = (
    os.path.exists(PERSISTENT_STORAGE_ROOT) and 
    os.path.isdir(PERSISTENT_STORAGE_ROOT) and 
    os.access(PERSISTENT_STORAGE_ROOT, os.W_OK)
)

# Anchor path relative to this file's installation directory so it remains
# stable regardless of the working directory when the process is invoked.
_SRC_ROOT = Path(__file__).resolve().parent.parent.parent

if IS_STORAGE_MOUNTED and MCP_MODE == "cloud":
    # Use the mounted storage directly - this is the preferred persistence method for Spaces.
    LEGACYGRAPH_CACHE_ROOT = str(Path(PERSISTENT_STORAGE_ROOT) / "legacy_mcp_cache")
else:
    # Fallback to local data directory (ephemeral in cloud mode unless persistence is fixed)
    LEGACYGRAPH_CACHE_ROOT = str(_SRC_ROOT / "data" / "cache")

# HF Bucket URL — must be set explicitly via environment variable
# to enable cloud serialization. 
# An empty string is provided as the intentional safe default to prevent 
# accidental writes to a developer's personal bucket or unintended syncing.
HF_BUCKET_URL: str = os.environ.get("HF_BUCKET_URL", "")

# ============================================================
# Feedback & Feature Requests
# ============================================================

# Optional Webhook URL (e.g. Discord, Slack, Zapier, or generic HTTP POST)
FEEDBACK_WEBHOOK_URL: str = os.environ.get("FEEDBACK_WEBHOOK_URL", "")

# Optional GitHub API settings for creating issues
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))
GITHUB_REPO: str = os.environ.get(
    "GITHUB_REPO",
    os.environ.get("GITHUB_REPOSITORY", "rohit-yadav34/LegacyGraph-MCP"),
)

# Local feedback log destination (fallback or local audit trail)
if IS_STORAGE_MOUNTED and MCP_MODE == "cloud":
    FEEDBACK_LOCAL_PATH: str = os.environ.get(
        "FEEDBACK_LOCAL_PATH",
        str(Path(PERSISTENT_STORAGE_ROOT) / "feedback.jsonl"),
    )
else:
    FEEDBACK_LOCAL_PATH = os.environ.get(
        "FEEDBACK_LOCAL_PATH",
        str(_SRC_ROOT / "data" / "feedback.jsonl"),
    )

