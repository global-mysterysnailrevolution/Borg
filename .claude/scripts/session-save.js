#!/usr/bin/env node
/**
 * Stop hook: Saves session metadata to ai/memory/SESSION_LOG.md
 * This runs when a session ends. It appends a timestamped entry.
 * 
 * Note: The full WORKING_MEMORY save requires Claude's context
 * (what was being worked on, decisions made, etc.) which this script
 * can't access. This script handles the mechanical part — creating
 * the log entry. The /checkpoint command handles the rich content.
 */

const fs = require('fs');
const path = require('path');

const MEMORY_DIR = path.join(process.cwd(), 'ai', 'memory');
const SESSION_LOG = path.join(MEMORY_DIR, 'SESSION_LOG.md');

// Ensure directory exists
if (!fs.existsSync(MEMORY_DIR)) {
  fs.mkdirSync(MEMORY_DIR, { recursive: true });
}

const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);

// Get git info if available
let branch = 'unknown';
let lastCommit = '';
try {
  const { execSync } = require('child_process');
  branch = execSync('git branch --show-current 2>/dev/null', { encoding: 'utf8' }).trim();
  lastCommit = execSync('git log --oneline -1 2>/dev/null', { encoding: 'utf8' }).trim();
} catch (e) {
  // Not a git repo, that's fine
}

const entry = `
## Session End — ${timestamp}
- **Branch**: ${branch}
- **Last Commit**: ${lastCommit}
- **Note**: Run \`/prime\` at start of next session to restore full context
`;

// Append to session log
try {
  if (!fs.existsSync(SESSION_LOG)) {
    fs.writeFileSync(SESSION_LOG, '# Session Log\n\nChronological record of sessions.\n');
  }
  fs.appendFileSync(SESSION_LOG, entry);
} catch (e) {
  // Silently fail — don't block session end
}

// Exit cleanly — don't block the Stop event
process.exit(0);
