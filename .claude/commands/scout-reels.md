---
description: "Monitor Instagram profiles for AI tool discoveries. Usage: /scout-reels <profile_or_hashtag>"
allowed-tools: Bash, Read, Write, WebFetch, WebSearch, Glob, Grep
---

Start the HackForge Reel Scout pipeline on $ARGUMENTS.

## Instructions

1. Parse the target from $ARGUMENTS:
   - Instagram handle: @username
   - Hashtag: #topic
   - Direct reel URL: https://instagram.com/reel/...
2. If a direct URL: spawn **reel-scout** to analyze that single reel
3. If a handle or hashtag: start continuous monitoring via Yutori scout
4. For each reel analyzed:
   - Use Reka AI to analyze video visuals and extract audio transcript
   - Use Fastino to extract tool/method entities
   - Present discoveries to the user
   - Feed tools into the `/hackforge` pipeline if the user wants to integrate
5. Save discoveries to `ai/research/reel-scout-[target]-[date].md`
