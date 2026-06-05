# OpenCode-Native Ralph — Design Document

> How to run the Ralph autonomous agent loop natively inside OpenCode's TUI, without a shell script.

---

## 1. What is Ralph?

Ralph is an autonomous AI agent loop pattern by Geoffrey Huntley. The core idea:

- A coding agent picks ONE task from a PRD, implements it, runs tests, commits
- Then loops back and does the next task
- Memory between loops: git history + progress.txt + prd.json
- Each task gets **fresh context** — never carry-forward stale reasoning

The original implementation is a bash one-liner: `while :; do cat PROMPT.md | claude-code ; done`

This document describes an OpenCode-native implementation that achieves the same fresh-context guarantees using OpenCode's built-in subagent system.

---

## 2. Why OpenCode-Native?

### The shell approach

```
while :; do cat ralph/prompt.md | claude-code ; done
```

Problems:
- Requires bash/WSL/jq (not Windows-native)
- No live visibility — output stream only
- If the agent gets stuck, you find out hours later
- Can't redirect mid-session when Ralph goes wrong
- Each iteration cold-starts: re-reads all specs, AGENTS.md, prd.json

### The OpenCode-native approach

Using OpenCode's agent harness (primary agent + Task tool + subagents):

| Benefit | How |
|---------|-----|
| **Fresh context per story** | Each story's implementation happens in a fresh subagent, not the orchestrator's context |
| **Live visibility** | Watch Ralph work in the TUI — every subagent session is inspectable |
| **Mid-session redirection** | Stop a bad subagent, adjust approach, continue |
| **No cold start penalty** | Orchestrator persists across iterations, subagents start fresh |
| **Platform-native** | Works on Windows, macOS, Linux — no bash/jq required |
| **Lean orchestrator** | Orchestrator only holds ~3k tokens of prompt + summaries, never touches code |

---

## 3. Architecture

```
┌────────────────────────────────────────────────────────────┐
│  OpenCode TUI                                               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Ralph Orchestrator (Primary Agent)                   │  │
│  │  Model: Your strongest model (e.g. deepseek-v4-pro)   │  │
│  │  Context: ~3k base + 1k per story (trivial)           │  │
│  │                                                       │  │
│  │  Per Loop:                                             │  │
│  │  1. Read prd.json → pick next story                   │  │
│  │  2. Delegate to subagents (fresh context each)        │  │
│  │  3. If tests pass → commit → update PRD               │  │
│  │  4. If stories remain → loop to (1)                   │  │
│  │  5. If all done → <promise>COMPLETE</promise>         │  │
│  └──────┬──────────────┬──────────────┬─────────────────┘  │
│         │              │              │                     │
│         ▼              ▼              ▼                     │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │ralph-plan  │ │ralph-worker│ │ralph-test  │             │
│  │FRESH       │ │FRESH       │ │FRESH       │             │
│  │CONTEXT     │ │CONTEXT     │ │CONTEXT     │             │
│  │            │ │            │ │            │             │
│  │Read-only   │ │Full access │ │Bash + read │             │
│  │Studies     │ │Searches,   │ │only        │             │
│  │specs +     │ │reads,      │ │Runs ruff,  │             │
│  │codebase    │ │writes code │ │mypy, pytest│             │
│  │            │ │Parallel ✓  │ │STRICTLY 1  │             │
│  └────────────┘ └────────────┘ └────────────┘             │
│         │              │              │                     │
│         └──────────────┴──────────────┘                     │
│                        │                                    │
│               Returns summary                               │
│               to orchestrator                               │
│               (NOT raw context)                             │
└────────────────────────────────────────────────────────────┘
```

### Why this preserves fresh context

Each subagent spawn is a **new LLM session** with a clean 170k token window:

```
Orchestrator context over 27 stories:

  [prompt.md: 2k] + [config: 500] + [subagent summaries: 27 × 1k]
  = ~30k tokens
  = 17% of context window
  = Zero quality impact
```

The orchestrator **never reads code files**. It never executes grep, never opens src/*. It only reads PRD metadata and subagent return summaries. Its context window stays clean regardless of how many stories have been implemented.

---

## 4. Subagent Design

### 4.1 ralph-plan (Read-Only Planner)

| Property | Value |
|----------|-------|
| **Mode** | subagent |
| **Model** | Lighter model (e.g. kimi-k2.6, qwen2.5-coder:7b) |
| **Temperature** | 0.1 |
| **Permissions** | read, glob, grep — NO edit, NO bash |
| **Purpose** | Study a spec file + existing codebase, identify what exists vs what needs building |

The plan agent answers: "What code already exists for story US-XXX? What's missing? What's the recommended implementation order?"

### 4.2 ralph-worker (Implementation Workers)

| Property | Value |
|----------|-------|
| **Mode** | subagent |
| **Model** | Lighter model (e.g. kimi-k2.6, qwen2.5-coder:7b) |
| **Temperature** | 0.1 |
| **Permissions** | read, edit, glob, grep, bash, task, webfetch — full access |
| **Parallelism** | Up to 10 concurrent |
| **Purpose** | Search codebase, read files, write implementation code |

The worker handles all "expensive allocation work" — reading file contents, writing code, running build steps. The orchestrator delegates but never does this itself.

### 4.3 ralph-test (Validation — STRICTLY 1)

| Property | Value |
|----------|-------|
| **Mode** | subagent |
| **Model** | Lighter model (e.g. kimi-k2.6) |
| **Temperature** | 0.0 |
| **Permissions** | bash, read — NO edit, NO task |
| **Parallelism** | STRICTLY 1 at a time |
| **Purpose** | Run ruff → mypy → pytest, report PASS/FAIL with exact errors |

The test agent is **read-only for code**. It runs quality checks and reports results. It never fixes issues — that's the worker's job. This separation prevents the "fix in test agent" anti-pattern.

---

## 5. Orchestrator Loop Logic

The orchestrator's system prompt encodes the loop. No shell script needed:

```
Pseudo-code:

while True:
    1. Read ralph/prd.json
    2. Count userStories where passes == false
    3. If count == 0: output <promise>COMPLETE</promise> and STOP
    4. Pick the story with highest priority where passes == false
    5. Get the spec file name from the story's "spec" field
    6. Spawn ralph-plan subagent with:
       - Task: "Study specs/{spec}.md and existing codebase for story {id}"
    7. Review plan output → decide implementation approach
    8. Spawn ralph-worker subagent(s) to implement:
       - Full implementation only (no placeholders)
       - Include tests
    9. Spawn ralph-test subagent (EXACTLY 1) to validate:
       - ruff check src/
       - mypy src/
       - pytest tests/ -x
    10. If tests PASS:
        - git add -A
        - git commit -m "feat: {id} - {title}"
        - Update prd.json: set story.passes = true
        - Append progress to ralph/progress.txt
        - Update AGENTS.md if patterns discovered
        - CONTINUE to next story
    11. If tests FAIL:
        - Review ralph-test output for error details
        - Spawn ralph-worker subagent(s) to fix failures
        - GOTO step 9 (retest)
```

---

## 6. File Structure

```
project/
├── .opencode/
│   └── agents/
│       ├── ralph.md              # PRIMARY: Orchestrator with loop logic
│       ├── ralph-plan.md         # SUBAGENT: Read-only planner
│       ├── ralph-worker.md       # SUBAGENT: Implementation worker
│       └── ralph-test.md         # SUBAGENT: Test validator
│
├── ralph/
│   ├── prd.json                  # User stories (the task list)
│   ├── progress.txt              # Auto-appended learnings
│   ├── prompt.md                 # Legacy prompt (used by ralph.sh fallback)
│   ├── ralph.sh                  # Legacy bash loop (optional fallback)
│   └── ralph.ps1                 # Legacy PowerShell loop (optional fallback)
│
├── specs/                        # Specification files
│   ├── 00-architecture.md
│   ├── 01-providers.md
│   └── ...
│
├── src/                          # Project source
├── tests/                        # Test suite
└── AGENTS.md                     # Codebase conventions
```

---

## 7. Setup Guide

### 7.1 Prerequisites

- [OpenCode](https://opencode.ai) installed (`opencode --version`)
- A provider configured with at least two models:
  - **Strong model** for orchestrator (reasoning-heavy)
  - **Lighter model** for subagents (focused tasks)
- A git repository with a `ralph/prd.json` file

### 7.2 Installation

**Step 1: Copy agent files**

Copy the contents of `.opencode/agents/` into your project:

```
project/
└── .opencode/
    └── agents/
        ├── ralph.md
        ├── ralph-plan.md
        ├── ralph-worker.md
        └── ralph-test.md
```

**Step 2: Adjust model names**

In each agent's frontmatter, update `model:` to match your provider:

```yaml
# ralph.md (orchestrator)
# Uses your default model — no explicit model needed

# ralph-plan.md (planner)
model: opencode-go/kimi-k2.6  # Thinking enabled by default

# ralph-worker.md (worker)
model: opencode-go/kimi-k2.6  # Thinking enabled by default

# ralph-test.md (validator)
model: opencode-go/kimi-k2.6  # Thinking enabled by default
```

Check available models: `opencode models`

**Step 3: Create your PRD**

Use `ralph/prd.json` following the standard format:

```json
{
  "project": "MyProject",
  "branchName": "ralph/my-feature",
  "userStories": [
    {
      "id": "US-001",
      "title": "Add database migration",
      "spec": "05-database.md",
      "priority": 1,
      "passes": false
    }
  ]
}
```

**Step 4: Start Ralph**

```bash
cd your-project
opencode                    # Start TUI
# Press Tab to switch to the "ralph" agent
# Type: "Start the Ralph loop"
```

Or directly:

```bash
opencode --agent ralph "Start the Ralph loop"
```

### 7.3 Watching Ralph Work

- The main TUI shows the orchestrator's decisions
- Use `session_child_first` keybind (default: `<Leader>+Down`) to inspect subagent sessions
- Use `session_child_cycle` (default: `Right`/`Left`) to navigate between subagents
- The orchestrator session shows the high-level progress

---

## 8. Tuning Guide

### 8.1 Common failure modes and fixes

| Failure | Tuning |
|---------|--------|
| **Ralph re-implements existing code** | Strengthen `ralph-plan` prompt: "Search the codebase THOROUGHLY before planning. Use both glob AND grep. If it exists, report it." |
| **Placeholder implementations** | Add to `ralph-worker`: "DO NOT IMPLEMENT PLACEHOLDER OR MINIMAL IMPLEMENTATIONS. FULL IMPLEMENTATIONS ONLY." Set temperature to 0.1. |
| **Tests pass but code is wrong** | Add to `ralph-test`: "Read the spec file and verify the implementation covers all acceptance criteria." |
| **Orchestrator loses track of state** | The PRD is the single source of truth. If orchestrator seems confused, check `ralph/prd.json` manually. |
| **Subagent spends too many tokens** | Add `maxSteps` or `steps` limit to agent config. |
| **Wrong code patterns** | Update `AGENTS.md` with correct patterns. Both orchestrator and workers auto-read it. |

### 8.2 When to intervene

- **Ralph stuck on same story 3+ loops**: Stop, review the spec — likely ambiguous
- **Ralph implements wrong thing**: The spec is wrong or ambiguous. Fix specs, reset branch, restart.
- **Build broke**: `git reset --hard`, restart Ralph. Huntley: "any problem created by AI can be resolved through a different series of prompts"
- **Context window filling up**: If the orchestrator's context exceeds ~100k tokens, restart the session. The PRD and git history preserve state.

---

## 9. Comparison: Shell Ralph vs OpenCode-Native Ralph

| Aspect | Shell Ralph | OpenCode-Native Ralph |
|--------|-------------|----------------------|
| **Implementation** | `while :; do opencode run ...; done` | Primary agent with loop in system prompt |
| **Fresh context** | Process exit resets | Subagent spawn resets (equivalent) |
| **Live visibility** | stdout stream only | Full TUI, all subagent sessions inspectable |
| **Mid-run intervention** | Kill process, read logs | Stop subagent, redirect in-session |
| **Platform** | Requires bash + jq | OpenCode only (Windows/Linux/macOS) |
| **Cold starts** | Re-reads everything each iteration | Orchestrator persists, subagents start fresh |
| **Cost** | Identical per story | Slightly less (no redundant PRD parsing) |
| **Battle-tested** | 18k GitHub stars, proven on CURSED language | New pattern, same guarantees |
| **When to use** | Headless CI/CD, overnight runs | Interactive development, supervised runs |

---

## 10. FAQ

**Q: Doesn't the orchestrator's context grow over time?**

A: The orchestrator receives only ~1k token summaries from each subagent. After 27 stories: ~30k tokens (17% of window). Subagents always start fresh.

**Q: What if a subagent fails?**

A: The orchestrator sees the failure, decides whether to retry (spawns new fresh subagent) or adjust approach. Failed subagent context is discarded.

**Q: Can I use the same model for everything?**

A: Yes. The architecture works with a single model. Using a lighter model for subagents saves cost but isn't required.

**Q: How do I stop Ralph mid-loop?**

A: In the TUI, just interrupt (Ctrl+C) and redirect. The PRD preserves which stories are done. To restart: switch to Ralph agent, type "continue the loop."

**Q: How does this compare to the snarktank/ralph repo?**

A: snarktank/ralph is a project-agnostic toolkit (prompt.md, ralph.sh, skills for PRD generation). OpenCode-native Ralph is the same concept implemented inside OpenCode's agent system. The loop logic is in the agent prompt instead of a shell script.

---

## 11. Reference

- [Geoffrey Huntley's Ralph article](https://ghuntley.com/ralph/)
- [snarktank/ralph — Reference implementation](https://github.com/snarktank/ralph)
- [OpenCode Agents documentation](https://opencode.ai/docs/agents/)
- [OpenCode CLI documentation](https://opencode.ai/docs/cli/)
