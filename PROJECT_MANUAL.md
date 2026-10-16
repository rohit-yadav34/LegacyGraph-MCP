# LegacyGraph-MCP — Project Manual

## 1. Overview

LegacyGraph-MCP is an MCP (Model Context Protocol) server that bridges AI agents and legacy C++ codebases. By exposing a code dependency graph over MCP, it enables LLMs to *reason* about code structure — upstream/downstream dependencies, circular references, orphan functions — rather than just reading raw text.

### Key Capabilities

| Capability | Description |
|---|---|
| **AST Parsing** | Tree-sitter-based C++ parsing (handles broken/dirty code) |
| **Graph Analysis** | File-aware dependency graph with cycle detection |
| **Hybrid Deployment** | Local (stdio + disk) or Cloud (HTTP + ephemeral clones) |
| **Omni-Ingestion** | Clone repos, apply patches, accept raw files, scan directories |
| **Token-Safe Visuals** | Bounded Mermaid.js graphs — inline or file export |

---

## 2. Prerequisites

- **Python** 3.11+
- **Poetry** (dependency management)
- **Git** (for cloud-mode repo cloning)

---

## 3. Installation

```bash
git clone https://github.com/RohitYadav34980/LegacyGraph-MCP.git
cd LegacyGraph-MCP
poetry install
```

---

## 4. Running the Server

### Local Mode (Cursor / Claude Desktop — `stdio`)
```bash
python -m src --mode local
```
Uses stdio transport and direct disk access. Best for local AI clients.

### Cloud Mode (Smithery / Render — `streamable-http`)
```bash
python -m src --mode cloud
```
Uses HTTP transport. Repos are cloned into ephemeral `/tmp/` directories and deleted after parsing. The `directory_path` parameter is blocked in this mode.

### Advanced Transport Overrides
```bash
# Force SSE transport in local mode
python -m src --mode local --transport sse --path /mcp

# Force streamable-http in local mode
python -m src --mode local --transport streamable-http
```

### PaaS Deployment (Render, Railway, etc.)
Set `MCP_MODE=cloud` as an environment variable. The server binds to `0.0.0.0:$PORT` automatically.

---

## 5. MCP Client Configuration

### Smithery (Recommended)
```bash
npx -y @smithery/cli@latest mcp add labsofuniverse/legacy-mcp-analyzer --client claude-code
```

### Claude Desktop (Manual)
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "legacy-mcp-analyzer": {
      "command": "python",
      "args": ["-m", "src", "--mode", "local"],
      "cwd": "/path/to/LegacyGraph-MCP"
    }
  }
}
```

---

## 6. API Reference

### `analyze_codebase(...)`

Unified tool for ingesting C++ code from any source. Provide exactly **one** of the following:

| Parameter | Type | Description |
|---|---|---|
| `repo_url` | `str` (optional) | HTTPS URL of a git repo to clone |
| `patch_content` | `str` (optional) | Unified diff to apply on top of a cloned repo. **Requires `repo_url`** |
| `raw_files` | `List[Dict]` (optional) | `[{"filename": "main.cpp", "content": "..."}]` for small projects without a repo |
| `directory_path` | `str` (optional) | Absolute local path. **Rejected in cloud mode** |

**Returns:** Status string with file count and function count.

---

### `get_file_functions(filepath: str)`

Lists all functions defined in a specific source file. Use the relative path exactly as returned by `analyze_codebase`.

**Example:** `get_file_functions("src/engine.cpp")` → `"Functions in 'src/engine.cpp': render, draw, init"`

---

### `get_file_coupling()`

Aggregated cross-file coupling report showing how files depend on each other.

**Example output:**
```
Cross-File Coupling Report:
  main.cpp -> utils.cpp (3 call(s))
  engine.cpp -> render.cpp (2 call(s))
```

---

### `get_callers(function_name: str)`

Lists all functions that invoke `function_name` (upstream/parents).

---

### `get_callees(function_name: str)`

Lists all functions called by `function_name` (downstream/children).

---

### `detect_cycles()`

Scans the graph for circular dependency paths.

**Example output:** `"Circular dependencies detected: funcA -> funcB -> funcA"`

---

### `get_orphan_functions()`

Finds functions that are defined but never called by any other function.

---

### `generate_mermaid_graph(focus_node?, max_depth?)`

Returns a Mermaid.js diagram as an inline markdown string. Use `focus_node` and `max_depth` to limit graph size and save tokens.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `focus_node` | `str` (optional) | `None` | Center the graph on this function |
| `max_depth` | `int` | `2` | Max BFS hops from focus_node |

---

### `export_ide_graph(output_filename, focus_node?, max_depth?)`

Writes a Mermaid `.md` file to the user's local disk. **Local mode only.**

Returns a message telling the user to open the file in their IDE's Markdown Preview — the AI should **not** read the file contents.

---

### `send_feedback(message, category?, title?, target?, email?, metadata?, webhook_url?, github_repo?)`

Enables users or autonomous coding agents to submit feedback, report edge-case bugs, or request features directly from within the MCP session. Dispatches to incoming webhooks (Discord, Slack, Zapier, custom HTTP POST), creates GitHub Issues via the GitHub REST API, and maintains a persistent local JSONL audit trail.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `message` | `str` (required) | — | Detailed feedback description or feature request |
| `category` | `str` (optional) | `"feedback"` | Type of submission: `'feature_request'`, `'bug'`, `'feedback'`, `'general'` |
| `title` | `str` (optional) | `None` | Short summary (extracted from first line if omitted) |
| `target` | `str` (optional) | `"auto"` | Destination: `'auto'`, `'webhook'`, `'github'`, or `'local'` |
| `email` | `str` (optional) | `None` | Optional contact email or user identifier |
| `metadata` | `dict` (optional) | `None` | Contextual dictionary (project_id, client name, environment) |
| `webhook_url` | `str` (optional) | `None` | Explicit webhook URL override |
| `github_repo` | `str` (optional) | `None` | Explicit GitHub repository override (`owner/repo`) |

*Note: `submit_feedback` is also registered as an alias with identical arguments.*

---


## 7. Deployment Modes

| | Local Mode | Cloud Mode |
|---|---|---|
| **Transport** | `stdio` (default) | `streamable-http` (default) |
| **Ingestion** | All inputs accepted | `directory_path` blocked |
| **Repo Cloning** | Supported | Supported (ephemeral `/tmp/`) |
| **Mermaid** | `export_ide_graph` + `generate_mermaid_graph` | `generate_mermaid_graph` only |
| **Config** | `--mode local` or `MCP_MODE=local` | `--mode cloud` or `MCP_MODE=cloud` |
| **Auto-Detection** | Default when no `--transport` set | Auto when `--transport streamable-http` or `sse` |

---

## 8. Docker Deployment

LegacyGraph-MCP ships with a multi-stage `Dockerfile` and a `docker-compose.yml` for one-command deployment.

### Quick Start (docker-compose)
```bash
# Clone and start
git clone https://github.com/RohitYadav34980/LegacyGraph-MCP.git
cd LegacyGraph-MCP

# Create the data directory with correct ownership (Linux/macOS only)
mkdir -p ./data && chown -R $(id -u):$(id -g) ./data

# Start the server (cloud mode, port 8000)
docker compose up -d
```

The server will be available at `http://localhost:8000/mcp` (streamable-http transport).

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_MODE` | `cloud` | `local` or `cloud` |
| `PORT` | `8000` (compose) / `7860` (HF) | HTTP listen port |
| `HF_TOKEN` | — | Hugging Face API token (optional) |
| `HF_BUCKET_URL` | — | HF Storage Bucket URL for cache persistence |

Override defaults by creating a `.env` file:
```bash
MCP_MODE=cloud
PORT=8000
HF_TOKEN=hf_your_token_here
```

### Standalone Docker
```bash
# Build the image
docker build -t legacygraph-mcp:latest .

# Run with port mapping
docker run -d \
  --name legacy-mcp-analyzer \
  -p 8000:8000 \
  -e MCP_MODE=cloud \
  -e PORT=8000 \
  -v ./data:/home/user/app/data \
  legacygraph-mcp:latest
```

### Hugging Face Spaces Deployment

1. **Create a Space** — go to [huggingface.co/new-space](https://huggingface.co/new-space) and select **Docker** as the SDK.
2. **Push** — the `README.md` YAML header configures the Space automatically:
   ```yaml
   ---
   title: GraphPulse
   emoji: 🐺
   sdk: docker
   app_port: 7860
   pinned: false
   ---
   ```
3. **Push the repo** to your Space:
   ```bash
   git remote add hf https://huggingface.co/spaces/YourUser/YourSpace
   git push hf main --force
   ```
4. **Persistent storage** — HF Spaces provides a `/data` mount. The server caches `.legacygraph.json` files there when available.
5. **Health check** — the container exposes `/.well-known/mcp/server-card.json` for health monitoring.

### Resource Limits

The `docker-compose.yml` sets sensible defaults:
- **Memory**: 4 GB (sufficient for codebases up to ~100k files)
- **CPU**: 2 cores
- **Restart policy**: `unless-stopped`

---

## 9. Project Structure

```
LegacyGraph-MCP/
├── src/                          # Main package
│   ├── __init__.py               # Package root
│   ├── __main__.py               # CLI entry point
│   ├── server.py                 # MCP registration & server card
│   ├── core/                     # Business logic
│   │   ├── graph.py              # DependencyGraph (NetworkX)
│   │   └── parser.py             # CppParser (tree-sitter)
│   ├── tools/                    # MCP tool functions
│   │   ├── analysis.py           # analyze_codebase
│   │   ├── queries.py            # get_callers, get_callees, etc.
│   │   └── export.py             # Mermaid generation & file export
│   └── utils/                    # Infrastructure
│       ├── config.py             # Runtime configuration
│       ├── logger.py             # Logging setup
│       ├── services.py           # Global singletons
│       └── helpers.py            # Git ops, directory scanning
├── tests/                        # Pytest test suite
│   ├── test_core.py              # 20 unit test cases
│   ├── test_remote_smoke.py      # Remote endpoint smoke tests
│   └── benchmark_timing.py       # Performance benchmarks
├── tools/                        # Dev utilities
│   └── verifier.py               # End-to-end accuracy verifier
├── data/                         # Sample legacy C++ project
│   └── legacy_project/
├── Dockerfile                    # Multi-stage Docker build
├── docker-compose.yml            # One-command container orchestration
├── .dockerignore                 # Docker build exclusions
├── pyproject.toml                # Poetry config & dependencies
├── smithery.yaml                 # Smithery deployment config
├── README.md                     # Quick start guide (+ HF Spaces metadata)
├── ARCHITECTURE.md               # Detailed architecture docs
├── CONTRIBUTING.md               # Development standards
└── CHANGELOG.md                  # Version history
```

---

## 10. Testing & Verification

### Unit Tests (20 cases)
```bash
python -m pytest tests/ -v
```

Covers: parser robustness, graph construction, file-tagging, cross-file deps, cycle detection, orphan detection, mode gating, Mermaid generation, cloud/local guards.

### End-to-End Verifier
```bash
python tools/verifier.py
```

Runs against the sample C++ project in `data/legacy_project/` and validates:
- 10/10 expected dependency edges
- Cycle detection (recursive `main_loop`)
- Orphan detection (`hidden_backdoor`)

**Current accuracy:** 100%

---

## 11. Troubleshooting

| Issue | Solution |
|---|---|
| `tree-sitter` import fails | Run `poetry install` — ensure `tree-sitter-cpp` is in your env |
| `FastMCP not found` | Run `pip install fastmcp` or ensure `mcp` is in dependencies |
| `directory_path` rejected | You're in cloud mode — use `repo_url` or `raw_files` instead |
| `git clone` fails | Ensure `git` is installed and the repo URL is valid HTTPS |
| Server won't start on Render | Set `MCP_MODE=cloud` env var and ensure `PORT` is exposed |
| Docker build fails with poetry lock error | Run `poetry lock --no-update` then rebuild |
| Container exits immediately | Check `docker logs legacy-mcp-analyzer` — usually a missing env var |
| Port conflict on `docker compose up` | Change `PORT` in `.env` or stop conflicting services |
| HF Spaces shows "Build failed" | Ensure `README.md` YAML header has `sdk: docker` and `app_port: 7860` |
| Permission denied on `./data` mount | Run `mkdir -p ./data && chown -R $(id -u):$(id -g) ./data` on the host (Linux/macOS) |
