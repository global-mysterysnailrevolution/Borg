---
description: Save current session state to ai/memory/ for cross-session continuity.
---

Run the memory-checkpoint skill immediately:

1. Write current working memory to ai/memory/WORKING_MEMORY.md
2. Append any new decisions to ai/memory/DECISIONS.md
3. Update ai/memory/SESSION_LOG.md with session summary
4. Capture any learning loop entries from this session
5. Confirm save with timestamp and file sizes
