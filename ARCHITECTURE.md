# Architecture — LegacyGraph-MCP

This document describes the internal architecture, data flows, and design decisions behind LegacyGraph-MCP.

---

## 1. High-Level Architecture

```mermaid
graph TB
    subgraph Client Layer
        A[AI Agent / MCP Client]
    end

    subgraph MCP Server
        B[server.py — Registration & Routing]
        B --> T1[tools/analysis.py]
        B --> T2[tools/queries.py]
        B --> T3[tools/export.py]
    end

    subgraph Core Engine
        P[core/parser.py — CppParser]
        G[core/graph.py — DependencyGraph]
    end

    subgraph Infrastructure
        C[utils/config.py]
        L[utils/logger.py]
        S[utils/services.py — Singletons]
        H[utils/helpers.py — Git & Scan]
    end

    A <-->|JSON-RPC / stdio or HTTP| B
    T1 --> H
    T1 --> S
    T2 --> S
    T3 --> H
    H --> P
    H --> G
    S --> P
    S --> G
    P -->|tree-sitter-cpp| TS[tree-sitter AST]
    G -->|networkx| NX[DiGraph]
```

---

## 2. End-to-End Workflow

This flowchart illustrates the complete lifecycle of an Agent interacting with the system: from parsing code, to extracting insights, to formatting results.

```mermaid
flowchart TD
    %% Styling
    classDef start_end fill:#2d3436,stroke:#f39c12,stroke-width:2px,color:#fff
    classDef process fill:#0984e3,stroke:#fff,stroke-width:2px,color:#fff
    classDef decision fill:#8e44ad,stroke:#fff,stroke-width:2px,color:#fff
    classDef data fill:#00b894,stroke:#fff,stroke-width:2px,color:#fff
    classDef output fill:#d63031,stroke:#fff,stroke-width:2px,color:#fff

    Start([AI Agent Sends Request]):::start_end --> ActionType{What type of tool<br/>was called?}:::decision

    %% Pathway 1: Ingestion
    ActionType -->|analyze_codebase| Ingest[Ingest Codebase]:::process
    Ingest --> SourceType{What is the<br/>source?}:::decision
    SourceType -->|repo_url| Clone[Clone repo to /tmp via git]:::process
    SourceType -->|directory_path| Local[Scan local filesystem]:::process
    SourceType -->|raw_files| Inject[Read JSON code snippets]:::process
    
    Clone --> Parse[Tree-sitter AST Parsing<br/>src/parser.py]:::process
    Local --> Parse
    Inject --> Parse
    
    Parse --> BuildGraph[(Build NetworkX Graph<br/>src/graph.py)]:::data
    BuildGraph --> Ready([Return Success:<br/>Graph Built!]):::output

    %% Pathway 2: Graph Queries
    ActionType -->|Query Tools| QueryType{Which Query?}:::decision
    QueryType -->|detect_cycles| C[Run nx.simple_cycles]:::process
    QueryType -->|get_callers| U[Find Upstream Parents]:::process
    QueryType -->|get_callees| D[Find Downstream Children]:::process
    QueryType -->|get_orphan_functions| O[Find Unused Functions]:::process
    
    C --> Extract[Extract data from NetworkX]:::process
    U --> Extract
    D --> Extract
    O --> Extract
    
    Extract --> Response([Return text/JSON to Agent]):::output

    %% Pathway 3: Export/Visuals
    ActionType -->|Visual Tools| VisType{Which Export?}:::decision
    VisType -->|generate_mermaid_graph| GenMermaid[Build Mermaid String inline]:::process
    VisType -->|export_ide_graph| WriteFile[Write .md file to disk]:::process
    
    GenMermaid --> Response
    WriteFile --> Response
```

---

## 3. Package Structure

```
src/
├── __init__.py          Package root
├── __main__.py          CLI entry point (argparse → mode → transport → mcp.run)
├── server.py            FastMCP init, tool registration, server card
│
├── core/                Business logic (zero framework dependencies)
│   ├── graph.py         DependencyGraph wrapping networkx.DiGraph
│   └── parser.py        CppParser wrapping tree-sitter-cpp
│
├── tools/               MCP tool functions (one concern per file)
│   ├── analysis.py      analyze_codebase — ingestion workflows
│   ├── queries.py       get_callers, get_callees, detect_cycles, etc.
│   ├── export.py        generate_mermaid_graph, export_ide_graph
│   └── feedback.py      send_feedback, submit_feedback — webhook / GitHub
│
└── utils/               Cross-cutting infrastructure
    ├── config.py         Runtime config: MCP_MODE, CPP_EXTENSIONS
    ├── logger.py         Centralized logging setup
    ├── services.py       Global singletons (graph_service, parser_service)
    └── helpers.py        _clone_repo, _scan_directory, _build_mermaid_string
```

### Design Principles

| Principle | Implementation |
|---|---|
| **Separation of Concerns** | Core logic has no MCP imports; tools have no graph algorithms |
| **Dependency Direction** | `tools → utils → core` (never reversed) |
| **Thin Server** | `server.py` is ~150 lines — registration only, no business logic |
| **Testability** | Core classes are independently instantiable without MCP |
| **Singleton Access** | `utils/services.py` holds mutable module-level state, avoiding circular imports |

---

## 3. Data Flow

### Ingestion Pipeline

```mermaid
sequenceDiagram
    participant Agent as AI Agent
    participant Tool as tools/analysis.py
    participant Helper as utils/helpers.py
    participant Parser as core/parser.py
    participant Graph as core/graph.py

    Agent->>Tool: analyze_codebase(repo_url="...")
    Tool->>Helper: _clone_repo(url)
    Helper-->>Tool: Path(/tmp/legacymcp_xxx)
    Tool->>Helper: _scan_directory(path)
    
    loop For each *.cpp file
        Helper->>Parser: parse_source(code)
        Parser-->>Helper: [(func_name, {callees})]
        Helper->>Graph: build_from_parsed_data(data, filepath)
    end
    
    Helper-->>Tool: (files_parsed, files_skipped, node_count)
    Tool-->>Agent: "Parsed 5 file(s), tracking 12 function(s)."
```

### Query Pipeline

```mermaid
sequenceDiagram
    participant Agent as AI Agent
    participant Tool as tools/queries.py
    participant Graph as core/graph.py

    Agent->>Tool: get_callers("calculate_interest")
    Tool->>Graph: get_upstream_callers("calculate_interest")
    Graph-->>Tool: ["process_client"]
    Tool-->>Agent: "Called by: process_client"
```

---

## 4. Core Components

### `core/parser.py` — CppParser

- **Technology:** tree-sitter with `tree-sitter-cpp` bindings
- **Query strategy:** Uses tree-sitter's `Query` API with patterns `(function_definition)` and `(call_expression)` — tolerant of syntax errors
- **Output:** `List[Tuple[str, Set[str]]]` — function name → set of called functions
- **Robustness:** Handles broken C++, forward declarations, pointer/reference declarators, qualified identifiers

### `core/graph.py` — DependencyGraph

- **Technology:** `networkx.DiGraph`
- **File-awareness:** Every node carries a `file` attribute for per-file isolation
- **Key operations:**

| Method | Complexity | Description |
|---|---|---|
| `build_from_parsed_data` | O(V + E) | Populate graph from parser output |
| `detect_cycles` | O(V + E) | `nx.simple_cycles` |
| `get_upstream_callers` | O(degree) | `graph.predecessors()` |
| `get_downstream_dependencies` | O(degree) | `graph.successors()` |
| `get_file_subgraph` | O(V) | Filter nodes by `file` attribute |
| `get_cross_file_dependencies` | O(E) | Find edges crossing file boundaries |
| `get_orphan_functions` | O(V) | Nodes with in-degree = 0 |

---

## 5. Mode System

The server operates in two modes, resolved at startup with this priority chain:

```
--mode flag  →  MCP_MODE env var  →  auto-detect from --transport  →  default "local"
```

```mermaid
graph TD
    A[Startup] --> B{--mode flag?}
    B -->|yes| C[Use --mode value]
    B -->|no| D{MCP_MODE env?}
    D -->|yes| E[Use env value]
    D -->|no| F{--transport is HTTP?}
    F -->|yes| G[cloud]
    F -->|no| H[local]
```

### Mode Differences

| Aspect | Local | Cloud |
|---|---|---|
| Transport | `stdio` | `streamable-http` |
| `directory_path` | ✅ Allowed | ❌ Blocked |
| `export_ide_graph` | ✅ Registered | ❌ Hidden |
| Repo cloning | To local Path | To `/tmp/` (ephemeral) |

---

## 6. Tool Registration

Tools are **not** decorated with `@mcp.tool()` at definition time. Instead, `_register_tools(mode)` is called from `__main__.py` after mode resolution, enabling conditional tool exposure:

```python
# server.py
def _register_tools(mode: str) -> None:
    mcp.tool()(analyze_codebase)     # Always
    mcp.tool()(get_callers)          # Always
    # ...
    if mode == "local":
        mcp.tool()(export_ide_graph) # Local only
```

This prevents cloud-deployed instances from ever advertising local-only tools.

---

## 7. Server Card

The `/.well-known/mcp/server-card.json` endpoint dynamically reflects the current mode and available tools:

```json
{
  "serverInfo": { "name": "legacy-mcp-analyzer", "version": "0.3.0" },
  "capabilities": { "modes": ["local", "cloud"], "currentMode": "local" },
  "tools": [...]
}
```

---

## 8. Error Handling Strategy

| Layer | Pattern |
|---|---|
| **Parser** | Raises `ParseError` — never crashes on invalid C++ |
| **Graph** | Raises `GraphError` for missing nodes — caught by tools |
| **Tools** | Return user-friendly error strings (never raise to MCP layer) |
| **Helpers** | Raise `RuntimeError` for git failures — caught by `analyze_codebase` |

---

## 9. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `tree-sitter` | ^0.23.0 | Incremental parsing framework |
| `tree-sitter-cpp` | ^0.23.0 | C++ grammar for tree-sitter |
| `networkx` | ^3.2.1 | Directed graph data structure |
| `fastmcp` | >=2.14,<3 | FastMCP 2.x server framework (bundles the official `mcp` SDK) |
| `uvicorn` | ^0.41.0 | ASGI server for HTTP mode |
| `starlette` | ^0.52.1 | HTTP routing (server card) |
