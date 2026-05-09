# SmartFork v2 — Session Parser & Project Extraction (Layer 2)

> **Design:** Generic parser that takes RawSessionData from ANY adapter → produces SessionDocument.
> **Zero LLM.** Pure code: regex, file extension maps, pattern matching.

---

## SessionParser

**File:** `src/smartfork/indexer/parser.py`

### Responsibility
Take adapter-agnostic `RawSessionData` and enrich it into a `SessionDocument` with derived properties.

No LLM. No database calls. Pure data transformation.

### parse_session()

```python
def parse_session(raw: RawSessionData, adapter: SessionAdapter) -> SessionDocument:
```

**Pipeline:**
1. Combine all file paths from raw (edited + read + mentioned + user_edited) — deduplicate
2. Derive project name from workspace_dir + file paths
3. Extract domains from file paths (see rules below)
4. Extract languages from file extensions (see map below)
5. Extract layers from file paths (backend/frontend)
6. Classify session pattern from tool call sequence
7. Extract reasoning documents (non-tool assistant turns > 30 chars)
8. Deduplicate reasoning by first 100 chars
9. Build and return SessionDocument

---

## Project Name Derivation

```python
def derive_project_name(workspace_dir: str, file_paths: List[str]) -> str:
```

**Rules (priority order):**
1. If workspace_dir is a real path: use its basename (last folder name)
2. If multiple file paths share a common root folder: use that folder name
3. Fallback: "unknown_project"

Examples:
- workspace="/home/user/bharatlaw-frontend" → "bharatlaw-frontend"
- workspace="" but files share "smartfork/" root → "smartfork"
- nothing works → "unknown_project"

---

## Domain Extraction

```python
def extract_domains(file_paths: List[str]) -> List[str]:
```

**Domain → file path patterns:**

| Domain | Matches paths containing |
|--------|-------------------------|
| auth | auth, login, jwt, oauth, session, token, permission |
| backend | api, server, routes, controllers, services, models, middleware |
| frontend | components, pages, views, hooks, styles, css, assets |
| database | db, database, models, migrations, schema, sql, queries, orm |
| rag | rag, retrieval, embedding, vector, chunk, search, pipeline |
| ingest | ingest, load, import, parse, extract, crawl, scraper |
| testing | test, spec, mock, fixture, conftest |
| devops | docker, k8s, deploy, ci, cd, github/workflows, terraform |
| config | config, settings, env, toml, yaml, json |
| cli | cli, command, typer, click, argparse |

Return unique domains, sorted alphabetically.

---

## Language Extraction

```python
def extract_languages(file_paths: List[str]) -> List[str]:
```

**Extension → Language map (30+ entries):**

| Extension | Language |
|-----------|----------|
| .py, .pyx, .pyi | python |
| .ts, .tsx | typescript |
| .js, .jsx, .mjs, .cjs | javascript |
| .rs | rust |
| .go | go |
| .java | java |
| .kt, .kts | kotlin |
| .swift | swift |
| .c, .h | c |
| .cpp, .hpp, .cc, .cxx | c++ |
| .cs | c# |
| .rb | ruby |
| .php | php |
| .sql | sql |
| .sh, .bash, .zsh | shell |
| .ps1 | powershell |
| .yaml, .yml | yaml |
| .json | json |
| .toml | toml |
| .xml, .html, .htm | markup |
| .css, .scss, .sass, .less | css |
| .md, .mdx | markdown |
| .dockerfile | docker |
| .graphql, .gql | graphql |
| .proto | protobuf |
| .tf | terraform |
| .r | r |
| .dart | dart |
| .lua | lua |
| .zig | zig |
| .nim | nim |

Return unique languages, sorted alphabetically. Unknown extensions ignored.

---

## Layer Extraction

```python
def extract_layers(file_paths: List[str]) -> List[str]:
```

**Rules:**
- If any file matches frontend patterns (components/, pages/, views/, hooks/, *.tsx, *.jsx, *.css) → "frontend"
- If any file matches backend patterns (api/, server/, routes/, controllers/, services/, models/, *.py without frontend path) → "backend"  
- Both can be true

---

## Session Pattern Classification

```python
def classify_session_pattern(tool_calls: List[str], 
                              user_edit_count: int, 
                              edit_count: int) -> str:
```

**Classify into one of 5 patterns:**

| Pattern | Conditions |
|---------|-----------|
| debugging_session | High ratio of read_file/search to write_file/edit calls (> 3:1), or task_raw contains error keywords |
| exploration_session | High ratio of list_files/search to any edit tools, low edit count |
| refactoring_session | High count of replace_in_file/edit calls (5+), files edited > 3 |
| configuration_session | Files are mostly config types (.yaml/.json/.toml/.env), no code files |
| standard_implementation | Default — moderate mix of reads and writes |

---

## Reasoning Extraction

```python
def extract_reasoning(turns: List[RawTurn]) -> List[str]:
```

**Rules:**
1. Filter turns: role="assistant", is_tool_call=False, content not empty, len > 30
2. Deduplicate: first 100 chars as key, skip if seen before
3. Return deduplicated list

---

## Error Handling

- If raw is None → return None
- If workspace_dir is empty → derive from file paths only
- If file_paths is empty → return empty lists for domains/languages/layers
- If no reasoning turns → return empty list (not an error)
- Never crash on missing/empty data

---

## Testing

Test with:
- RawSessionData from each adapter (kilocode, claudecode, opencode)
- Empty file lists
- Missing workspace_dir
- Mixed file types
- Sessions with only tool calls (no reasoning)
