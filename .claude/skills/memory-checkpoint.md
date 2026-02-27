---
name: memory-checkpoint
description: >
  Persists session state to ai/memory/ for cross-session continuity.
  Use this skill when context is getting large, before switching tasks,
  when the user says "save state", "checkpoint", "remember this", or
  when you detect the conversation is approaching context limits.
  Also triggers on /checkpoint command and automatically via Stop hook.
---

# Memory Checkpoint

Replaces the harness `ai/memory/` worker and 15%-context auto-trigger.

## When to Trigger

- **Automatic**: Stop hook fires `session-save.js` on every session end
- **Manual**: User runs `/checkpoint`
- **Proactive**: When you estimate context usage is above 70%, suggest checkpointing

## What to Save

### ai/memory/WORKING_MEMORY.md

```markdown
# Working Memory — [timestamp]

## Current Task
[What we're actively working on]

## Progress
[What's been completed this session]

## Blocked On
[Any blockers or waiting items]

## Next Steps
[Ordered list of what to do next]

## Open Questions
[Unresolved decisions or unknowns]

## Files Modified
[List of files changed this session]

## Key Context
[Critical information that would be lost without this checkpoint]
```

### ai/memory/DECISIONS.md

Append-only log of architectural and design decisions:

```markdown
## [timestamp] — [Decision Title]
**Context**: Why this came up
**Decision**: What we chose
**Alternatives**: What we rejected and why
**Consequences**: What this means going forward
```

### ai/memory/SESSION_LOG.md

Brief session summary for history:

```markdown
## Session [timestamp]
- **Duration**: ~[estimate]
- **Focus**: [main task]
- **Completed**: [bullet list]
- **Pending**: [bullet list]
```

## Restore Process

On session start (via `/prime` or context-primer skill):
1. Read `ai/memory/WORKING_MEMORY.md`
2. Read `ai/memory/DECISIONS.md`
3. Summarize state to user
4. Suggest picking up from Next Steps
