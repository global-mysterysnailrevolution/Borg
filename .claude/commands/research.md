---
description: Conduct deep web research on a topic using Tavily and Reka APIs. Usage - /research <topic>
allowed-tools: Bash, Read, Write, WebFetch, WebSearch
---

Spawn the research-agent subagent to research the topic provided in $ARGUMENTS.

Use Tavily for web search and Reka for cross-referencing. Save results to
ai/research/[topic-slug]-[date].md. Return a structured report with executive
summary, key findings, recommendations, and sources.
