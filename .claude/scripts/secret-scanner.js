#!/usr/bin/env node
/**
 * PreToolUse hook: Scans file content for exposed secrets before writing.
 * Receives tool input on stdin, outputs decision on stdout.
 */

const fs = require('fs');

const SECRET_PATTERNS = [
  // API Keys
  { pattern: /(?:api[_-]?key|apikey)\s*[:=]\s*['"]?[A-Za-z0-9\-_]{20,}['"]?/gi, label: 'API Key' },
  // AWS
  { pattern: /AKIA[0-9A-Z]{16}/g, label: 'AWS Access Key' },
  // Generic secrets
  { pattern: /(?:secret|password|passwd|token)\s*[:=]\s*['"][^'"]{8,}['"]/gi, label: 'Secret/Password' },
  // Private keys
  { pattern: /-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----/g, label: 'Private Key' },
  // Slack tokens
  { pattern: /xox[bporas]-[0-9]{10,}/g, label: 'Slack Token' },
  // GitHub tokens
  { pattern: /gh[pousr]_[A-Za-z0-9_]{36,}/g, label: 'GitHub Token' },
  // Generic long hex strings (potential keys)
  { pattern: /['"][0-9a-f]{40,}['"]/gi, label: 'Potential Secret (hex)' },
];

// Files that are EXPECTED to contain secrets
const ALLOWED_FILES = [
  '.env.example',
  '.env.template',
  '.claude/settings.json', // Our own config
  'ai/memory/',            // Memory files may reference keys by name
];

let input = '';
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    const content = data.tool_input?.content || data.tool_input?.file_text || '';
    const filePath = data.tool_input?.path || data.tool_input?.file_path || '';

    // Skip allowed files
    if (ALLOWED_FILES.some(f => filePath.includes(f))) {
      process.exit(0); // Allow
    }

    // Scan for secrets
    const findings = [];
    for (const { pattern, label } of SECRET_PATTERNS) {
      const matches = content.match(pattern);
      if (matches) {
        findings.push({ label, count: matches.length });
      }
    }

    if (findings.length > 0) {
      const reasons = findings.map(f => `${f.label} (${f.count} match${f.count > 1 ? 'es' : ''})`);
      console.log(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'ask_user',
          permissionDecisionReason: `⚠️  Potential secrets detected in ${filePath}: ${reasons.join(', ')}. Review before writing.`
        }
      }));
    }
    // If no findings, exit 0 (allow)
  } catch (e) {
    // On error, don't block — just allow
    process.exit(0);
  }
});
