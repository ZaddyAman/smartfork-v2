# SmartFork v2 — MCP Server (Layer 11)

> **Design:** Model Context Protocol server for native Claude Code / IDE integration.
> **Framework:** Strands Agents (native MCP support) or raw `mcp` Python package.
> **Run mode:** Background process started by `smartfork mcp serve`

---

## Purpose

When SmartFork runs as an MCP server, Claude Code (and other MCP clients) can call SmartFork tools directly from within a session:

```
User (in Claude Code): "Detect fork for my current debug session about JWT"
→ Claude calls: detect_fork("debug session JWT race condition")
→ SmartFork searches index
→ Returns top 5 sessions as structured results
→ Claude presents results in conversation
```

No context switching. No terminal. Everything inside the coding session.

---

## Tools (Exposed via MCP)

| Tool | Description | Input | Output |
|------|-------------|-------|--------|
| `detect_fork` | Find relevant sessions | `query: str, n: int = 5` | List[ResultCard] |
| `fork_session` | Generate /fork.md context | `session_id: str, intent: str = "continue"` | ContextReport as markdown |
| `index_status` | Get index stats | None | dict with counts, projects, quality breakdown |
| `search_sessions` | Search indexed sessions | `query: str, filter_project: str, filter_quality: str` | List[ResultCard] |
| `list_projects` | List indexed projects | None | List[str] |
| `vault_export` | Generate Obsidian vault | `output_path: str` | Path to vault |
| `config_get` | Get current config | `key: str` | value |
| `config_set` | Set config value | `key: str, value: str` | confirmation |

---

## Implementation (with Strands Agents)

**File:** `src/smartfork/mcp/server.py`

```python
from strands_agents import Agent, tool

@tool
async def detect_fork(query: str, n: int = 5) -> list:
    """Find relevant past sessions to fork context from."""
    engine = get_search_engine()
    results = await engine.search(query, n_results=n)
    return [_card_to_dict(r) for r in results]

@tool
async def fork_session(session_id: str, intent: str = "continue") -> str:
    """Generate /fork.md context from a session."""
    assembler = get_fork_assembler()
    report = assembler.assemble(session_id, ForkIntent(intent))
    return report.to_markdown()

# ... register all tools ...

agent = Agent(
    name="smartfork",
    tools=[detect_fork, fork_session, index_status, search_sessions,
           list_projects, vault_export, config_get, config_set]
)

if __name__ == "__main__":
    agent.serve("mcp")  # Start MCP server
```

---

## Without Strands (raw MCP)

If Strands Agents is not installed, use the `mcp` Python package directly:

```python
from mcp.server import Server, stdio_server
from mcp.types import Tool, TextContent

server = Server("smartfork")

@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(name="detect_fork", description="Find relevant sessions",
             inputSchema={"type": "object", "properties": {...}}),
        # ... all tools
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    if name == "detect_fork":
        results = await detect_fork(**arguments)
        return [TextContent(type="text", text=json.dumps(results))]
    # ... handle all tools

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                        server.create_initialization_options())
```

---

## Configuration

Add to Claude Code's MCP config (`~/.claude/claude_desktop_config.json` or `.mcp.json`):

```json
{
  "mcpServers": {
    "smartfork": {
      "command": "python",
      "args": ["-m", "smartfork.mcp.server"],
      "env": {
        "SMARTFORK_CONFIG_DIR": "~/.smartfork"
      }
    }
  }
}
```

Or automatically via `smartfork mcp install`:
```bash
smartfork mcp install    # Auto-configure Claude Code MCP
smartfork mcp serve      # Start MCP server manually
smartfork mcp status     # Check if MCP server is configured
```

---

## CLI Commands

```bash
# Install MCP in Claude Code
smartfork mcp install

# Start MCP server (usually run by Claude Code automatically)
smartfork mcp serve

# Check status
smartfork mcp status

# Uninstall
smartfork mcp uninstall
```

---

## Security

- MCP server runs locally only (stdio transport, not HTTP)
- No authentication needed (local machine trust)
- Tools are read-only except config_set and vault_export
- Config modifications via MCP require explicit confirmation

---

## Testing

- Test MCP server starts and responds to tool listing
- Test each tool via MCP client
- Test with Claude Code integration (end-to-end)
- Test fallback: Strands not installed → raw MCP
- Test concurrent tool calls (two at once)
