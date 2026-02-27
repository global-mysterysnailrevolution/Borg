---
name: learning-loop
description: >
  Captures patterns, mistakes, and improvements for continuous learning across sessions.
  Use this skill when something goes wrong and gets fixed, when a new pattern is discovered,
  when the user corrects an approach, or when a decision has broader implications.
  Also use when the user says "remember this pattern", "don't do that again",
  "that worked well", or "add this to lessons learned".
---

# Learning Loop

Replaces the harness `learning_loop_append.md` system.

## What to Capture

### Patterns (things that work)
```markdown
## Pattern: [Name]
**Context**: When this applies
**Approach**: What to do
**Example**: Concrete instance
**Added**: [timestamp]
```

### Anti-Patterns (things that don't work)
```markdown
## Anti-Pattern: [Name]
**Context**: When this was tried
**Problem**: What went wrong
**Better Approach**: What to do instead
**Added**: [timestamp]
```

### Corrections (user feedback)
```markdown
## Correction: [Summary]
**What I Did**: The incorrect approach
**What User Wanted**: The correct approach
**Root Cause**: Why the mismatch occurred
**Added**: [timestamp]
```

## Storage

Append entries to `ai/memory/LEARNING_LOG.md` — never overwrite, only append.

## Application

When the context-primer loads session state, it should also scan LEARNING_LOG.md
for relevant patterns that apply to the current task. Surface the top 3 most
relevant entries when starting related work.

## Trigger Points

- After fixing a bug: capture what caused it and how to prevent it
- After user correction: capture the preference or approach difference
- After a successful complex task: capture the pattern that worked
- After trying a new tool/API: capture integration notes
- When the user explicitly says to remember something
