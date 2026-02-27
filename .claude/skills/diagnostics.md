---
name: diagnostics
description: >
  Runs health checks on the harness system, project state, and external API
  connectivity. Use when something seems broken, when the user says "diagnose",
  "what's wrong", "health check", "system status", or runs /diagnose.
  Also useful after setup to verify everything works.
---

# Diagnostics

Replaces the harness `diagnostics/` directory.

## Checks to Run

### 1. Directory Structure
Verify ai/ subdirectories exist:
```bash
for dir in ai/context ai/memory ai/tests ai/research; do
  [ -d "$dir" ] && echo "✅ $dir" || echo "❌ $dir missing"
done
```

### 2. Memory State
- Does WORKING_MEMORY.md exist and have content?
- When was it last modified?
- Is DECISIONS.md growing (not empty)?
- Any stale lock files in ai/_locks/?

### 3. Git State
```bash
git status --short
git branch --show-current
git log --oneline -3
```

### 4. API Connectivity
Test each configured API:
```bash
# Tavily
curl -s -o /dev/null -w "%{http_code}" https://api.tavily.com/search \
  -X POST -H "Content-Type: application/json" \
  -d '{"api_key":"'$TAVILY_API_KEY'","query":"test","max_results":1}'

# Reka
curl -s -o /dev/null -w "%{http_code}" https://api.reka.ai/v1/chat \
  -H "X-Api-Key: $REKA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"reka-flash","messages":[{"role":"user","content":"ping"}]}'
```

### 5. Hooks Status
- Are hook scripts present in .claude/scripts/?
- Are they executable?
- Do they have syntax errors? (run with --check if applicable)

### 6. Disk Usage
```bash
du -sh ai/ .claude/ node_modules/ 2>/dev/null
df -h . | tail -1
```

## Output Format

```
🔍 Harness Diagnostics — [timestamp]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 Structure:    [✅ OK | ❌ Issues]
🧠 Memory:       [✅ Active | ⚠️ Stale | ❌ Missing]
🌿 Git:          [branch] — [clean | N changes]
🔌 APIs:         [N/N connected]
🪝 Hooks:        [✅ OK | ❌ Issues]
💾 Disk:         [usage summary]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
