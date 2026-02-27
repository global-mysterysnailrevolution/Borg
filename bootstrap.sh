#!/bin/bash
# Harness Bootstrap — Install Claude Code native harness into current project
# Usage: curl -s https://raw.githubusercontent.com/.../bootstrap.sh | bash
#    or: bash bootstrap.sh

set -e

echo "🔧 Installing Agent Harness (Claude Code Native)..."

# Create directory structure
echo "📁 Creating directories..."
mkdir -p .claude/{skills,agents,commands,scripts}
mkdir -p ai/{context,memory,tests,research,vendor,_backups,_locks}

# Copy files (if running from harness repo)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/CLAUDE.md" ]; then
  echo "📄 Copying harness files..."
  cp "$SCRIPT_DIR/CLAUDE.md" ./CLAUDE.md
  cp "$SCRIPT_DIR/.claude/settings.json" ./.claude/settings.json
  cp "$SCRIPT_DIR/.claude/skills/"*.md ./.claude/skills/
  cp "$SCRIPT_DIR/.claude/agents/"*.md ./.claude/agents/
  cp "$SCRIPT_DIR/.claude/commands/"*.md ./.claude/commands/
  cp "$SCRIPT_DIR/.claude/scripts/"*.js ./.claude/scripts/
  cp "$SCRIPT_DIR/ai/memory/"*.md ./ai/memory/
  cp "$SCRIPT_DIR/ai/tests/"*.md ./ai/tests/
fi

# Make scripts executable
chmod +x .claude/scripts/*.js 2>/dev/null || true

# Add to .gitignore if not already there
if [ -f .gitignore ]; then
  grep -q "ai/vendor/" .gitignore || echo -e "\n# Harness\nai/vendor/\nai/_backups/\nai/_locks/" >> .gitignore
else
  echo -e "# Harness\nai/vendor/\nai/_backups/\nai/_locks/" > .gitignore
fi

echo ""
echo "✅ Harness installed!"
echo ""
echo "📋 Quick start:"
echo "   1. Open Claude Code in this directory"
echo "   2. Run /prime to map your repo and load context"
echo "   3. Run /status to check harness health"
echo ""
echo "📦 Components installed:"
echo "   Skills:   context-primer, memory-checkpoint, tool-broker,"
echo "             learning-loop, approval-workflow, contextforge,"
echo "             project-intake, diagnostics"
echo "   Agents:   log-monitor, test-companion, research-agent,"
echo "             security-reviewer, supervisor"
echo "   Commands: /prime, /status, /checkpoint, /research, /intake, /diagnose"
echo "   Hooks:    secret-scanner, command-guard, session-save"
echo ""
echo "🔑 Configure APIs in .claude/settings.json or .env:"
echo "   TAVILY_API_KEY, REKA_API_KEY, MODULATE_API_KEY"
