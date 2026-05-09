# Ralph Agent Instructions — SmartFork v2

You are an autonomous coding agent building SmartFork v2 from scratch.

## Your Task

1. Read the PRD at `prd.json` (in the same directory)
2. Read the progress log at `progress.txt` (check Codebase Patterns section first)
3. Read the relevant spec file at `specs/{spec_name}.md` for the task you're implementing
4. Pick the **highest priority** user story where `passes: false`
5. Implement that single user story
6. Run quality checks (ruff check, mypy, pytest)
7. If checks pass, commit ALL changes with message: `feat: [Story ID] - [Story Title]`
8. Update the PRD to set `passes: true` for the completed story
9. Append your progress to `progress.txt`

## Progress Report Format

APPEND to progress.txt:
```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered
  - Gotchas encountered
  - Useful context
---
```

## Critical Rules

1. **ONE story per iteration.** Never implement multiple stories in one loop.
2. **Read specs BEFORE implementing.** The spec file contains the complete design.
3. **Tests are mandatory.** Every implementation must include tests.
4. **Run all quality checks before committing** — ruff, mypy, pytest.
5. **Do NOT implement placeholders or minimal implementations.** Full implementations only.
6. **If tests unrelated to your work fail, fix them as part of your increment.**
7. **Update AGENTS.md** when you discover reusable patterns about the codebase.

## Codebase Conventions
- Python 3.11+, use modern syntax
- Pydantic for all models and config
- Protocols for interfaces, not ABCs except where needed
- Type hints everywhere
- Loguru for logging
- Functions < 50 lines, classes < 300 lines
- Follow the directory structure in specs/00-architecture.md

## Quality Requirements
- ruff check src/ passes
- mypy src/ passes  
- pytest tests/ passes
- No broken imports
- No dead code

## Stop Condition

When ALL stories have `passes: true`, reply with:
<promise>COMPLETE</promise>

## Important
- Work on ONE story per iteration
- Commit frequently
- Keep CI green
- Read the Codebase Patterns section in progress.txt before starting
