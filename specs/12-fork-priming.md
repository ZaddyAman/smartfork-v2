# SmartFork v2 — Fork Priming / Handoff (Layer 8)

> **Design:** Generate handoff documents that prime new AI sessions with context from past sessions.
> **Philosophy:** Hybrid approach — Reference external artifacts (Matt Pocock's handoff pattern) + Extract session-specific reasoning (SmartFork's unique value).
> **Core rule:** NEVER duplicate content that exists elsewhere. Reference it by path/URL. Only summarize what's unique to the session transcript.
> **Inspiration:** https://github.com/mattpocock/skills/blob/main/skills/in-progress/handoff/SKILL.md

---

## The Hybrid Philosophy

**Matt Pocock's Insight:** *"Do not duplicate content already captured in other artifacts (PRDs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead."*

**SmartFork's Unique Value:** Session transcripts contain decisions, gotchas, dead-ends, and reasoning that exist NOWHERE else. This is what we extract.

**Result:** Reference what's external. Summarize what's internal. Structure for the next agent to act on immediately.

---

## ForkAssembler

**File:** `src/smartfork/fork/assembler.py`

```python
class ForkAssembler:
    def __init__(self, llm: LLMProvider, chroma_client,
                 metadata_store: MetadataStore): ...
    
    def assemble(self, session_id: str, intent: ForkIntent,
                 user_query: str = "", 
                 max_tokens: int = 2000,
                 use_llm: bool = True) -> ContextReport: ...
```

**Two modes:**
1. **LLM mode (default):** Agent reads session context → produces structured handoff
2. **Raw fallback:** Assembled from structured data without LLM (when Ollama unavailable)

---

## 4 Fork Intents + 1 Bonus Intent

| Intent | What the user wants | Focus |
|--------|-------------------|-------|
| CONTINUE | Pick up where they left off | Incomplete items, current state, next steps |
| REFERENCE | Understand a pattern or decision | Decisions, alternatives considered, gotchas |
| DEBUG | Understand a bug fix | Error, root cause, what was tried, fix |
| SYNTHESIZE | Combine context from multiple sessions | Overview, timeline, architectural shifts |

Each intent filters what context is relevant — don't dump everything.

---

## Context Layers (assembled BEFORE LLM call)

| Layer | Content | Source |
|-------|---------|--------|
| A | Task + project + domains + languages + top 10 files | SessionDocument |
| B | LLM-generated 3-sentence summary | SessionDocument.summary_doc |
| C | Key decisions (filtered reasoning: "decided", "chose", "approach", "rejected", "opted") | reasoning_docs |
| D | Files touched with edit counts and status | SessionDocument |
| E | Error context (reasoning with error/traceback/bug keywords) | reasoning_docs |
| F | Reasoning trail (for CONTINUE only — full step-by-step) | reasoning_docs |
| G | External artifact detection (git commits, PRDs, ADRs, issues) | git log, filesystem, session metadata |

---

## LLM Prompt Template (CONTINUE intent)

```
You are SmartFork's handoff assembler. Generate a handoff document 
that primes a NEW AI coding session with context from a PAST session 
the developer wants to CONTINUE.

CRITICAL RULE: Never duplicate content that exists in other artifacts.
Reference them by path/URL instead. Only summarize what's unique to
this session transcript.

PAST SESSION:
- Title: {title}
- Task: {task_raw}
- Summary: {summary_doc}
- Files: {top_10_files_with_status}
- Duration: {duration} min | Quality: {quality_tag}
- Agent: {agent_id} | Model: {model_used}

EXTERNAL ARTIFACTS (reference, don't duplicate):
{detected_artifacts}

KEY EXCHANGES (from session transcript):
{filtered_reasoning_blocks}

LAST EXCHANGES (incomplete items, TODOs):
{last_3_exchanges}

SUPERSESSION INFO:
{supersession_warning}

USER'S FOCUS FOR NEXT SESSION:
{user_query}

Generate a handoff with these EXACT sections:

## Artifacts to Reference
(table: artifact type | path/URL | what it contains | why it matters)

## What Was Happening
(2-3 sentences: what this session was doing)

## Decisions Made  
(bullet list of WHAT was decided, WHY, and WHAT was rejected)

## Current State
### ✅ Completed
(checklist of finished items)

### 🚧 In Progress  
(checklist of partially done items)

### ❌ Not Started
(checklist of known remaining items)

## Key Files
| File | Status | Key Insight |
|------|--------|-------------|
(file name | ✅/🚧/❌ | what this agent needs to know about this file)

## Gotchas / Warnings
(alerts with ⚠️ prefix: things to avoid, dependencies, known pitfalls)

## Skills Suggested
(list of skills/tools the next session should load)

## Next Steps
(3-5 concrete actions the next agent should take, in priority order)

Keep output under {max_tokens} tokens. Be specific with file paths.
Format as clean markdown. No preamble, no sign-off.
```

---

## Prompt Templates for Other Intents

### REFERENCE
Same structure but:
- Skip "Current State" and "Next Steps"
- Expand "Decisions Made" — include alternatives and their tradeoffs
- Add "Patterns to Follow" section

### DEBUG
Same structure but:
- Add "Error Encountered" section (at top): exact error message, stack trace
- Add "What Was Tried" section: approaches that failed BEFORE the solution
- Add "Root Cause" section: why the error happened
- Add "Fix Applied" section: exactly what code changed
- Add "Prevention" section: how to avoid this in the future
- Skip "Artifacts to Reference" (debug sessions rarely have external artifacts)

### SYNTHESIZE
Same structure but:
- Add "Overview" section at top: what was the overall goal
- Add "Timeline" section: chronological sequence of work
- Add "Architectural Shifts" section: what changed structurally
- "Current State" becomes broader: state of the entire system

---

## Output Format (/fork.md)

```markdown
# Handoff: {session_title}
**Context from:** {agent_display} session {session_id[:12]}... — {date}
**Intent:** CONTINUE | **Project:** {project_name} | **Quality:** {quality_badge}
**Focus:** {user_query}

## Artifacts to Reference
| Artifact | Path / Link | What It Contains | Why |
|----------|-------------|------------------|-----|
| PRD | `specs/auth-flow.md#token-rotation` | Token refresh requirements | Defines what must be built |
| Commit | `abc1234` — "Add JWT middleware" | Middleware implementation | Starting point for code |
| Issue | Linear #247 | Bug report: "Refresh race condition" | Explains the problem |

## What Was Happening
This session built the JWT authentication middleware for the BharatLawAI 
backend. The developer implemented token validation, refresh endpoint, and 
began debugging a race condition where concurrent token refreshes caused 
401 errors.

## Decisions Made  
- **Chose JWT over session-based auth** — Needed stateless scaling across 
  multiple API instances. Session auth would require Redis.
- **Used mutex lock for token refresh** — Prevents concurrent refreshes 
  from issuing duplicate tokens. Found via debugging race condition.
- **Rejected polling approach for refresh** — Would add unnecessary server 
  load. Mutex is cleaner and handles edge cases better.
- **Rejected storing tokens in database** — Defeats the purpose of 
  stateless JWT. Tokens live only in memory + client cookies.

## Current State
### ✅ Completed
- [x] JWT validation middleware (auth.py:45-120)
- [x] Token refresh endpoint POST /auth/refresh
- [x] Basic 401 handling for expired tokens

### 🚧 In Progress
- [ ] Mutex lock implementation on refresh (refresh.py:30 — partially done)
- [ ] Race condition reproduction test

### ❌ Not Started
- [ ] Token revocation / blacklist on logout
- [ ] Refresh token rotation (issue new refresh token on each use)
- [ ] Integration tests for race condition scenario
- [ ] Redis setup for token blacklist (if needed later)

## Key Files
| File | Status | Key Insight |
|------|--------|-------------|
| `auth.py:45-120` | ✅ | JWT validation middleware — working, tested |
| `refresh.py:1-35` | 🚧 | Token refresh — mutex partially implemented at line 30 |
| `refresh.py:36+` | ❌ | Remainder of refresh logic not written |
| `middleware.py` | ✅ | Route registration — auth routes mounted |
| `conftest.py` | ❌ | No tests written for auth module |

## Gotchas / Warnings
- ⚠️ **DON'T call refresh_token() inside the auth middleware** — will 
  cause recursive loop (middleware checks token → expired → tries 
  refresh → middleware checks again...)
- ⚠️ **This session was COMPACTED** — some debugging context was lost. 
  Check the pre-compaction export at `~/.smartfork/cache/pre_compaction_exports/`
  for full error logs and failed approaches.
- ⚠️ **This session was SUPERSEDED** by session `def12345` — check that 
  session for newer code. Run `smartfork fork def12345` to see it.
- ⚠️ Tests require Redis running on port 6379 (for integration tests)

## Skills Suggested
- Load `prd` skill if you need full requirements context
- Use `dev-browser` to test auth endpoints in browser
- Load `test-runner` to verify auth tests pass after changes

## Next Steps
1. Complete the mutex lock implementation in refresh.py:30
2. Write a test that reproduces the race condition (concurrent refresh calls)
3. Implement refresh token rotation (issue new refresh token on each use)
4. Add token blacklist for logout
5. Run full test suite: `pytest tests/auth/ -v`

---
*Generated by SmartFork v2 • {date}*
*Fork with: `claude --resume {session_id} --append /fork.md`*
```

---

## Raw Fallback Mode

When LLM unavailable, assemble without narrative:

```markdown
# Handoff: {title}
**Context from:** {agent} session {session_id[:12]}... — {date}
**Intent:** {intent}

## Artifacts to Reference
{detected_artifacts as plain list}

## What Was Happening  
{summary_doc}

## Files
| File | Edits | Status |
|------|-------|--------|
{files table}

## Key Exchanges
{first 3 reasoning blocks, truncated}

## Gotchas
- {extracted from reasoning — regex search for "don't", "never", "warning", "careful", "⚠️"}

---
*Generated by SmartFork v2 — raw mode (no LLM)*
```

---

## Artifact Detection

**File:** `src/smartfork/fork/artifact_detector.py`

Before assembling the handoff, SmartFork scans for external artifacts:

```python
class ArtifactDetector:
    def detect(self, session: SessionDocument) -> List[Artifact]:
        """Find external artifacts referenced in or relevant to this session."""
        artifacts = []
        
        # 1. Git commits from the session's timeframe
        commits = get_commits_in_range(
            session.workspace_dir,
            session.session_start,
            session.session_end
        )
        for commit in commits:
            artifacts.append(Artifact(
                type="commit",
                path=commit.hash,
                description=commit.message,
                relevance="Code changes from this session"
            ))
        
        # 2. PRDs / spec files referenced in task or reasoning
        for ref in find_file_refs(session.task_raw):
            if "spec" in ref or "prd" in ref or "plan" in ref:
                artifacts.append(Artifact(
                    type="spec",
                    path=ref,
                    description="Specification document",
                    relevance="Defines requirements for this work"
                ))
        
        # 3. Issues / tickets
        for ref in find_issue_refs(session.task_raw, session.reasoning_docs):
            artifacts.append(Artifact(
                type="issue",
                path=ref,  # e.g., "Linear #247" or "GitHub issue #42"
                description="Issue/ticket",
                relevance="Tracks this specific task"
            ))
        
        # 4. ADRs (Architecture Decision Records)
        adrs = find_adrs(session.workspace_dir)
        for adr in adrs:
            if adr_matches_session(adr, session):
                artifacts.append(Artifact(
                    type="adr",
                    path=adr.path,
                    description=adr.title,
                    relevance="Architecture decision relevant here"
                ))
        
        return artifacts
```

**Artifact type priorities:**
1. **PRDs/Specs** — define WHAT must be built (highest value)
2. **Commits** — show WHAT changed (git blame on relevant files)
3. **Issues/Tickets** — track WHY and current status
4. **ADRs** — document architecture decisions

---

## Compaction Gap Analysis

When a session was compacted:

```python
def analyze_gaps(self, session_id: str) -> GapReport:
```

1. Check if pre-compaction export exists for this session
2. Agent compares compacted summary ↔ full pre-compaction transcript
3. Identifies: missing error messages, lost decisions, incomplete context
4. Synthesizes: gaps filled → added to "Gotchas / Warnings" section
5. Adds: "⚠ This session was compacted — check pre-compaction export at {path}"

---

## Share/Export

```python
class ForkExporter:
    def save_to_file(self, report: ContextReport, 
                     output_path: Path = None) -> Path:
        """Default: handoff_{session_id[:8]}_{intent}.md"""
    
    def copy_to_clipboard(self, report: ContextReport) -> None: ...
    def deliver_via_mcp(self, report: ContextReport) -> dict: ...
```

---

## Testing

- Test all 4 intents produce correct section structure
- Test artifact detection finds real commits/PRDs/issues
- Test that extracted content is NOT duplicated from artifacts
- Test compaction gap analysis with real compacted session
- Test LLM mode vs raw fallback structure consistency
- Test supersession warnings appear in handoff
- Test focus query tailors the handoff content
- Test with session that has no external artifacts
