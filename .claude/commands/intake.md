---
description: Initialize the harness in a new project. Creates ai/ directories, scans codebase, and configures tools.
---

Run the project-intake skill:

1. Create ai/ directory structure if it doesn't exist
2. Ask project type, tech stack, testing, and deployment questions
3. Run context-primer to generate initial REPO_MAP and CONTEXT_PACK
4. Initialize empty memory files
5. Update .gitignore for ai/vendor/ and ai/_backups/
6. Run diagnostics to verify setup
7. Present summary and recommended next steps
