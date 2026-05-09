#!/bin/bash
# Ralph Wiggum — Autonomous AI Agent Loop for SmartFork v2
# Usage: ./ralph.sh [max_iterations]

set -e

MAX_ITERATIONS=${1:-50}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRD_FILE="$SCRIPT_DIR/prd.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"

# Initialize progress file if it doesn't exist
if [ ! -f "$PROGRESS_FILE" ]; then
  echo "# Ralph Progress Log — SmartFork v2" > "$PROGRESS_FILE"
  echo "Started: $(date)" >> "$PROGRESS_FILE"
  echo "---" >> "$PROGRESS_FILE"
fi

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  Ralph Wiggum — SmartFork v2 Builder                      ║"
echo "║  Max iterations: $MAX_ITERATIONS"
echo "╚═══════════════════════════════════════════════════════════╝"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo "==============================================================="
  echo "  Ralph Iteration $i of $MAX_ITERATIONS"
  echo "==============================================================="

  # Check if all stories are complete
  REMAINING=$(jq '[.userStories[] | select(.passes == false)] | length' "$PRD_FILE" 2>/dev/null || echo "?")
  echo "  Remaining stories: $REMAINING"
  
  if [ "$REMAINING" = "0" ]; then
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║  ALL STORIES COMPLETE! SmartFork v2 built.               ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    exit 0
  fi

  # Run Claude Code with the Ralph prompt
  OUTPUT=$(cat "$SCRIPT_DIR/prompt.md" | claude --dangerously-skip-permissions --print 2>&1 | tee /dev/stderr) || true
  
  # Check for completion signal
  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║  Ralph completed all tasks at iteration $i!              ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    exit 0
  fi
  
  echo "Iteration $i complete. Continuing..."
  sleep 2
done

echo ""
echo "Ralph reached max iterations ($MAX_ITERATIONS) without completing all stories."
echo "Check $PROGRESS_FILE for status."
echo "Run ralph.sh again to continue."
exit 1
