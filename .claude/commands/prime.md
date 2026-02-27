---
description: Map the repo, load previous session state, and prepare context for this session.
---

Run the context-primer skill:

1. Scan the repo structure and generate ai/context/REPO_MAP.md
2. Load any existing ai/memory/WORKING_MEMORY.md and ai/memory/DECISIONS.md
3. Check git status and recent commits
4. Compile ai/context/CONTEXT_PACK.md
5. Present a brief summary of project state and suggested next steps

If ai/ directory doesn't exist, run project-intake first.
