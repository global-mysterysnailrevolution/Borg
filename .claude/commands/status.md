---
description: Show harness status including memory state, git state, and API connectivity.
---

Run a quick status check:

1. Show current git branch and uncommitted changes count
2. Check if ai/memory/WORKING_MEMORY.md exists and when last modified
3. Show last 3 entries from ai/memory/SESSION_LOG.md if it exists
4. Report approximate context window usage (suggest /checkpoint if high)
5. List configured APIs and their connection status

Format as a compact status block, not verbose output.
