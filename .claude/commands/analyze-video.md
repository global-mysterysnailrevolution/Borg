---
description: "Extract tools and methods from a YouTube/Instagram video. Usage: /analyze-video <url>"
allowed-tools: Bash, Read, Write, WebFetch, WebSearch, Glob, Grep
---

Run the HackForge Video Intelligence pipeline on $ARGUMENTS.

## Instructions

1. Accept a video URL (YouTube, Instagram reel, TikTok)
2. Use Reka AI (reka-core model) to:
   - Analyze the video visually (identify tools, UIs, code, logos)
   - Extract the audio transcript (capture spoken tool names, URLs)
3. Use Fastino to extract entities from the combined visual + audio text:
   - Tool names, API names, company names
   - Methods, techniques, frameworks
   - URLs mentioned or shown
4. If any Luma links are found, automatically offer to run `/hackforge` on them
5. Present a structured report:
   - Tools discovered with integration potential
   - Methods/techniques that could be built as skills
   - URLs and resources found
6. Save to `ai/research/video-intel-[date].md`

This command can also analyze YouTube playlists or channels:
- For playlists, analyze each video and compile a unified report
- For channels, find the most recent AI-related videos and analyze them
