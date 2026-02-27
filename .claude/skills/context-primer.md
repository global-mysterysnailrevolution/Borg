---
name: context-primer
description: >
  Generates a comprehensive repo map and context pack for the current project.
  Use this skill at the start of every new session, when switching tasks, or
  when the user says "prime", "map the repo", "load context", "what's the state",
  or starts a new feature. Also triggers on /prime command. Essential for
  maintaining continuity across sessions.
---

# Context Primer

Replaces the harness `ai/context/` worker. Generates three artifacts:

## Step 1: Generate REPO_MAP.md

Run a structured scan of the project:

```bash
# Get directory tree (exclude node_modules, .git, __pycache__, etc.)
find . -type f \
  -not -path './.git/*' \
  -not -path '*/node_modules/*' \
  -not -path '*/__pycache__/*' \
  -not -path '*/.next/*' \
  -not -path '*/dist/*' \
  -not -path '*/build/*' \
  -not -path '*/.claude/*' \
  -not -path '*/ai/_backups/*' \
  | head -200 | sort
```

Write the output to `ai/context/REPO_MAP.md` with sections:
- **Structure** — Directory tree
- **Key Files** — Entry points, configs, main modules
- **Dependencies** — package.json / pyproject.toml / requirements.txt summary
- **Recent Changes** — `git log --oneline -10`

## Step 2: Generate CONTEXT_PACK.md

Read and summarize:
1. Any existing `ai/memory/WORKING_MEMORY.md` (previous session state)
2. Any existing `ai/memory/DECISIONS.md` (architectural decisions)
3. The project's README.md or equivalent
4. Key config files (package.json, tsconfig, pyproject.toml, etc.)
5. Recent git diff (`git diff --stat HEAD~5..HEAD`)

Compile into `ai/context/CONTEXT_PACK.md` with:
- **Current State** — What was being worked on
- **Open Tasks** — Unfinished work from previous sessions
- **Key Decisions** — Architectural choices already made
- **Tech Stack** — Languages, frameworks, versions
- **Active Branch** — Current git branch and recent commits

## Step 3: Feature Research (if applicable)

If starting a new feature, create `ai/context/FEATURE_RESEARCH.md`:
- Research the feature requirements
- Check for existing implementations in the codebase
- Note relevant external docs or APIs
- Draft an implementation plan

## Output

After generation, present a brief summary to the user:
- Lines of code / file count
- Current branch and recent activity
- Any restored session state
- Suggested next steps
