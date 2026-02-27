---
name: contextforge
description: >
  Compiles and packages context from multiple sources into optimized prompts
  for subagents or external API calls. Use when spawning subagents that need
  specific context, preparing payloads for Reka/Tavily/Yutori API calls,
  or when you need to distill a large codebase into a focused context window.
  Triggers when delegating work, building API payloads, or the user asks to
  "package context", "prepare a brief", or "summarize for handoff".
---

# ContextForge

Replaces the harness `contextforge/` system. Compiles context optimized
for different consumers (subagents, external APIs, human reviewers).

## Context Compilation Targets

### For Subagents
Subagents get clean context windows. Compile only what they need:

```markdown
# Task Context for [agent-name]

## Objective
[Specific task description]

## Relevant Files
[Only the files this agent needs to read/modify]

## Constraints
[Rules from CLAUDE.md + DECISIONS.md that apply]

## Expected Output
[What format/content to return]
```

### For Reka API Calls
Package multimodal context for Reka:
- Text summaries under 4000 tokens for reka-flash
- Include image/video URLs when relevant
- Structure function calling schemas

### For Tavily Search
Compile search context:
- Extract key terms from the current task
- Build focused search queries (1-6 words each)
- Include context for result filtering

### For Human Reviewers
Generate readable summaries:
- Executive summary (3-5 sentences)
- Key decisions and their rationale
- Current state and next steps
- Risk areas or open questions

## Compilation Process

1. **Identify consumer** — Who/what needs this context?
2. **Gather sources** — Which files, memory, decisions are relevant?
3. **Filter** — Remove irrelevant content, keep only what matters
4. **Compress** — Summarize verbose content, preserve critical details
5. **Format** — Structure for the target consumer
6. **Validate** — Ensure nothing critical was lost

## Anti-Bloat Rules

- Never include full file contents when a summary suffices
- Never include git history unless specifically relevant
- Strip comments and whitespace from code snippets
- Prefer type signatures over full implementations
- Max 2000 tokens per subagent context (aim for 1000)
