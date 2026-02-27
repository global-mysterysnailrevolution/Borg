---
name: tool-broker
description: >
  Routes tasks to the appropriate external API based on task type.
  Manages Tavily (web search), Reka AI (multimodal/vision/speech/research),
  Modulate (voice moderation), and Yutori (scouting/browsing/research).
  Use this skill whenever a task could benefit from external API calls,
  multi-model verification, image/video/audio processing, web search for
  building apps, or when the user mentions any of these tools by name.
  Also use when building apps that need search, vision, or speech capabilities.
---

# Tool Broker

Replaces the harness `adapters/` and `mcp_execute_requests/` systems.
Routes work to the best available API for each task type.

## Available APIs

### Tavily — Web Search for LLMs
- **MCP Endpoint**: `$TAVILY_MCP_URL`
- **Use for**: Web search in apps we build, real-time data retrieval, fact-checking
- **REST API**: `https://api.tavily.com/search`
- **Auth**: API key in the MCP URL parameter

```javascript
// Example: Tavily search in an app
const response = await fetch('https://api.tavily.com/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    api_key: process.env.TAVILY_API_KEY,
    query: 'latest AI agent frameworks',
    search_depth: 'advanced',
    include_answer: true,
    max_results: 5
  })
});
```

### Reka AI — Multimodal Intelligence
- **Base URL**: `https://api.reka.ai/v1`
- **Auth Header**: `X-Api-Key: $REKA_API_KEY`
- **Models**: `reka-flash` (fast/cheap), `reka-core` (powerful), `reka-edge` (lightweight)

**Capabilities**:
- **Chat**: Text + image + video + audio input → text output with function calling
- **Vision**: Video understanding, search, Q&A, clip generation, metadata tagging, image search
- **Research**: Deep web research with reasoning steps, parallel thinking, structured output
- **Speech**: Transcription, translation, speech-to-speech translation

```bash
# Example: Reka chat with image
curl https://api.reka.ai/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $REKA_API_KEY" \
  -d '{
    "model": "reka-flash",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": "https://example.com/image.jpg"},
        {"type": "text", "text": "Describe this image"}
      ]
    }]
  }'
```

### Modulate — Voice/Audio Moderation
- **Base URL**: `https://modulate-developer-apis.com`
- **Auth**: API key `$MODULATE_API_KEY`
- **Use for**: Voice toxicity detection, audio content moderation

### Yutori — AI Scouting & Research Platform
- **Platform**: `https://platform.yutori.com`
- **Capabilities**: Scouting tasks, browsing automation, deep web research, model metrics (n1)
- **Use for**: Automated web scouting, competitive research, data gathering

## Routing Logic

| Task Type | Primary API | Fallback |
|-----------|-------------|----------|
| Web search (for building) | Tavily | Reka Research |
| Image understanding | Reka Vision | — |
| Video analysis/clips | Reka Vision | — |
| Audio transcription | Reka Speech | — |
| Speech translation | Reka Speech | — |
| Deep research | Reka Research | Tavily + synthesis |
| Voice moderation | Modulate | — |
| Web scouting/automation | Yutori | Tavily |
| Multi-model verification | Reka + Claude cross-check | — |
| Function calling | Reka Chat | — |

## Cross-Model Verification Pattern

For high-stakes outputs, use dual-model verification:
1. Generate with Claude (primary)
2. Verify with Reka (secondary)
3. Reconcile differences
4. Present unified result with confidence level
