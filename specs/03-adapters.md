# SmartFork v2 — Multi-Agent Adapter System (Layer 1)

> **Build target:** Pluggable session format parsers for 7 coding agents.
> **Design:** Each agent has its own adapter implementing the `SessionAdapter` interface.
> The core pipeline NEVER knows which agent produced the data.
> **Reference base:** https://github.com/ZaddyAman/smart-fork/blob/multisession-intillegent/smartfork/src/smartfork/adapters/base.py
> **Reference registry:** https://github.com/ZaddyAman/smart-fork/blob/multisession-intillegent/smartfork/src/smartfork/adapters/registry.py
> **Reference kilocode:** https://github.com/ZaddyAman/smart-fork/blob/multisession-intillegent/smartfork/src/smartfork/adapters/kilocode.py
> **Reference claudecode:** https://github.com/ZaddyAman/smart-fork/blob/multisession-intillegent/smartfork/src/smartfork/adapters/claudecode.py
> **Reference opencode:** https://github.com/ZaddyAman/smart-fork/blob/multisession-intillegent/smartfork/src/smartfork/adapters/opencode.py

---

## Architecture

```
┌──────────────────────────────────────────┐
│         ADAPTER REGISTRY                  │
│  _REGISTRY: Dict[str, SessionAdapter]    │
│  @register decorator                     │
│  get_adapter(agent_id) → adapter         │
└──────────────────────────────────────────┘
         │
         ├── KiloCodeAdapter    (kilocode)
         ├── ClaudeCodeAdapter  (claudecode)
         ├── OpenCodeAdapter    (opencode)
         ├── CursorAgentAdapter (cursor_agent)
         ├── AntiGravityAdapter (antigravity)
         ├── ClineAdapter       (cline)
         └── GeminiAdapter      (gemini)
```

Every adapter:
1. Is decorated with `@register` — auto-registers on import
2. Implements `SessionAdapter` abstract base class
3. Produces `RawSessionData` — the normalized contract
4. Never interacts with the database directly

---

## Base Class

### File: `src/smartfork/adapters/base.py`

```python
class SessionAdapter(ABC):
    agent_id: str = ""           # "kilocode" | "claudecode" | ...
    display_name: str = ""       # "Kilo Code", "Claude Code"
    session_type: str = "dir"   # "dir" | "file" | "sqlite"

    @abstractmethod
    def is_valid_session(self, session_path: Path) -> bool: ...
    
    @abstractmethod
    def get_session_files(self, session_path: Path) -> List[str]: ...
    
    @abstractmethod
    def parse_raw(self, session_path: Path) -> Optional[RawSessionData]: ...

    def get_default_sessions_paths(self) -> List[Path]:
        return []
    
    def get_ide_choices(self) -> List[str]:
        return []
    
    def get_default_path_for_ide(self, ide: str) -> Optional[Path]:
        return None
```

---

## Adapter 1: KiloCodeAdapter

**agent_id:** `"kilocode"`
**Session format:** Directory with 3 JSON files
**Files:** `task_metadata.json` + `api_conversation_history.json` + `ui_messages.json`

### Parsing logic:
1. Read `task_metadata.json` → extract files_edited, files_read, files_mentioned, files_user_edited, final_files
2. Read `api_conversation_history.json` → extract turns (user/assistant), task_raw, workspace_dir, model_used
3. Read `ui_messages.json` → extract ONLY `say:"reasoning"` blocks → append as assistant turns
4. Filter tool-call content from assistant turns (15+ tool call tags to detect)
5. Clean reasoning text: remove `<file_content>`, `<environment_details>`, code blocks, terminal output

### Tool call detection keywords:
`<read_file>`, `<write_to_file>`, `<search_files>`, `<list_files>`, `<execute_command>`, `<ask_followup_question>`, `<attempt_completion>`, `<replace_in_file>`, `<insert_code_block>`, `<browser_action>`, `<use_mcp_tool>`, `<access_mcp_resource>`, `<switch_mode>`, `<update_todo_list>`

### IDE support:
- Cursor → `%APPDATA%/Cursor/User/globalStorage/kilocode.kilo-code/tasks`
- VS Code → `%APPDATA%/Code/User/globalStorage/kilocode.kilo-code/tasks`
- AntiGravity → `%APPDATA%/AntiGravity/User/globalStorage/kilocode.kilo-code/tasks`
- macOS/Linux equivalents for all three

### Content extraction:
- Handle both string content AND array-of-parts (OpenAI format): `[{"type": "text", "text": "..."}]`
- Handle nested dict format: `{"type": "text", "text": {"value": "..."}}`

---

## Adapter 2: ClaudeCodeAdapter

**agent_id:** `"claudecode"`
**Session format:** `.jsonl` files in `~/.claude/projects/<project-name>/<session>.jsonl`

### Parsing logic:
1. Each line is a JSON record (jsonl format)
2. Extract role, content, timestamp per line
3. Handle content as list (Claude Tool Use format): detect `type: "tool_use"` blocks
4. Extract tool inputs for file signals: `read_file/view_file` → files_read, `write_file/edit_file/replace_in_file` → files_edited
5. `session_id` = stem of the .jsonl filename
6. Default model = `"claude-3-5-sonnet"` if not detectable
7. Check `cwd` field in records for workspace_dir

### Session type: `"project"` — sessions are nested: `projects/<project>/<session>.jsonl`

### Path detection:
- Respect `CLAUDE_CONFIG_DIR` env var
- Default: `~/.claude/projects`
- Scan subdirectories for `.jsonl` files

---

## Adapter 3: OpenCodeAdapter

**agent_id:** `"opencode"`
**Session format:** SQLite database at `~/.local/share/opencode/opencode.db`

### Parsing logic:
1. Connect to SQLite database
2. Query `session` table: id, project_id, directory, title, time_created, time_updated
3. For each session: query `message` table, then `part` table
4. Extract parts by type:
   - `type: "text"` from user parts → turns (role="user")
   - `type: "reasoning"` from assistant parts → turns (role="assistant")
   - `type: "tool"` from assistant parts → turns (role="assistant", is_tool_call=True)
5. Extract file paths from tool input dicts (keys: file_path, path, file, filepath)
6. Model detection from message data's `model.modelID` field

### Database tables used:
- `session` (id, directory, title, time_created, time_updated)
- `message` (id, session_id, time_created, data — JSON string)
- `part` (message_id, data — JSON string, time_created)

---

## Adapter 4: CursorAgentAdapter

**agent_id:** `"cursor_agent"`
**Session format:** To be determined (Cursor's native session format)
**IDE support:** Cursor only

### Research needed:
- Cursor stores sessions in its own format
- Likely JSON-based, similar to Kilo Code but with Cursor-specific fields
- Path: `%APPDATA%/Cursor/User/workspaceStorage/...`

### Placeholder implementation:
- `is_valid_session()` returns False until format is ported
- The adapter is registered but inactive
- Setup wizard can enable it when format is confirmed

---

## Adapter 5: AntiGravityAdapter

**agent_id:** `"antigravity"`
**Session format:** Same as Kilo Code (AntiGravity uses Kilo Code under the hood)
**IDE support:** AntiGravity IDE only

### Implementation:
- Extends or wraps KiloCodeAdapter
- Only difference: default path detection points to AntiGravity's app data directory

---

## Adapter 6: ClineAdapter

**agent_id:** `"cline"`
**Session format:** VS Code extension storage
**IDE support:** VS Code / Cursor with Cline extension

### Research needed:
- Cline is a VS Code extension
- Sessions stored in VS Code's extension storage
- Format likely JSON

### Placeholder implementation:
- `is_valid_session()` returns False until format is ported
- Registered but inactive

---

## Adapter 7: GeminiAdapter

**agent_id:** `"gemini"`
**Session format:** Google Gemini CLI session format
**IDE support:** Gemini CLI / Google AI Studio

### Research needed:
- Gemini CLI may store sessions similarly to Claude Code (.jsonl)
- Path likely `~/.gemini/` or Google AI Studio export format

### Placeholder implementation:
- `is_valid_session()` returns False until format is ported
- Registered but inactive

---

## Registry

### File: `src/smartfork/adapters/registry.py`

```python
_REGISTRY: Dict[str, SessionAdapter] = {}

def register(adapter_class: Type[SessionAdapter]) -> Type[SessionAdapter]:
    """Decorator: register an adapter by its agent_id."""
    instance = adapter_class()
    _REGISTRY[instance.agent_id] = instance
    return adapter_class

def get_adapter(agent_id: str) -> Optional[SessionAdapter]: ...
def get_adapter_or_raise(agent_id: str) -> SessionAdapter: ...
def list_adapters() -> List[SessionAdapter]: ...
def list_agent_ids() -> List[str]: ...
def is_registered(agent_id: str) -> bool: ...
```

---

## Adapter __init__.py

### File: `src/smartfork/adapters/__init__.py`

```python
from .base import SessionAdapter, RawSessionData, RawTurn
from .registry import register, get_adapter, get_adapter_or_raise, list_adapters, list_agent_ids, is_registered

# Import all adapters to trigger @register
from . import kilocode
from . import claudecode
from . import opencode
from . import cursor_agent
from . import antigravity
from . import cline
from . import gemini
```

---

## Scanner Integration

The `SessionScanner` uses adapters to discover sessions:

```python
class SessionScanner:
    def __init__(self, config: SmartForkConfig):
        self.adapters = self._get_enabled_adapters(config)
    
    def scan_all(self) -> List[Path]:
        """Scan all enabled agents for valid sessions."""
        sessions = []
        for adapter in self.adapters:
            paths = adapter.get_default_sessions_paths()
            for path in paths:
                if path.exists():
                    sessions.extend(self._scan_path(path, adapter))
        return sessions
    
    def _scan_path(self, path: Path, adapter: SessionAdapter) -> List[Path]:
        """Recursively scan a path for valid sessions."""
```

---

## Implementation Order for Ralph

1. `adapters/base.py` — SessionAdapter, RawSessionData, RawTurn
2. `adapters/registry.py` — @register decorator, get_adapter, list functions
3. `adapters/kilocode.py` — KiloCodeAdapter (most complex, reference implementation)
4. `adapters/claudecode.py` — ClaudeCodeAdapter
5. `adapters/opencode.py` — OpenCodeAdapter (SQLite-based)
6. `adapters/antigravity.py` — AntiGravityAdapter (simple wrapper)
7. `adapters/cursor_agent.py` — Placeholder (inactive)
8. `adapters/cline.py` — Placeholder (inactive)
9. `adapters/gemini.py` — Placeholder (inactive)
10. `adapters/__init__.py` — Exports + auto-import all adapters
