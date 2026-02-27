---
name: project-intake
description: >
  Onboards a new project into the harness system. Creates the ai/ directory
  structure, initializes memory files, scans the codebase, and configures
  tools. Use when the user says "set up harness", "initialize project",
  "onboard this repo", starts working in a new repository, or runs /intake.
  Also use when the ai/ directory doesn't exist yet.
---

# Project Intake

Replaces the harness `PROJECT_INTAKE.md` and `bootstrap.sh` system.

## Intake Questionnaire

Ask the user (or infer from the repo):

1. **Project type**: Code repo, docs-only, monorepo, or mixed?
2. **Tech stack**: Languages, frameworks, build tools?
3. **Testing**: What test framework? Where do tests live?
4. **Deployment**: How is this deployed? CI/CD pipeline?
5. **APIs used**: What external services does this connect to?
6. **Team size**: Solo dev or team? (affects approval workflow config)

## Initialization Steps

### 1. Create directory structure
```bash
mkdir -p ai/{context,memory,tests,research,vendor,_backups,_locks}
```

### 2. Initialize memory files
Create starter files:
- `ai/memory/WORKING_MEMORY.md` — Empty template
- `ai/memory/DECISIONS.md` — With header only
- `ai/memory/LEARNING_LOG.md` — With header only
- `ai/memory/SESSION_LOG.md` — With header only

### 3. Run context primer
Execute the context-primer skill to generate:
- `ai/context/REPO_MAP.md`
- `ai/context/CONTEXT_PACK.md`

### 4. Configure .gitignore
Append to .gitignore if not already present:
```
ai/vendor/
ai/_backups/
ai/_locks/
```

### 5. Detect and configure APIs
Check for existing `.env` files or config for:
- Tavily, Reka, Modulate, Yutori keys
- Database connections
- Deployment targets

### 6. Generate initial test plan
If tests exist, scan and summarize coverage in `ai/tests/TEST_PLAN.md`.
If no tests exist, draft a testing strategy based on the tech stack.

## Output
Present a summary of what was set up and recommended next steps.
