#!/usr/bin/env node
/**
 * PreToolUse hook: Gates dangerous bash commands behind user approval.
 * Receives tool input on stdin, outputs decision on stdout.
 */

let input = '';
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    const command = data.tool_input?.command || '';

    // Patterns that ALWAYS block (deny)
    const BLOCKED = [
      /rm\s+-rf\s+[\/~]/,           // rm -rf / or ~
      /mkfs/,                        // Format disk
      /dd\s+if=.*of=\/dev/,          // Write to device
      /:(){ :\|:& };:/,              // Fork bomb
      /curl.*\|\s*(?:ba)?sh/,        // Pipe curl to shell
      /wget.*\|\s*(?:ba)?sh/,        // Pipe wget to shell
    ];

    for (const pattern of BLOCKED) {
      if (pattern.test(command)) {
        console.log(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'deny',
            permissionDecisionReason: `🚫 Blocked dangerous command: ${command.substring(0, 80)}`
          }
        }));
        return;
      }
    }

    // Patterns that require user confirmation (ask)
    const RISKY = [
      { pattern: /git\s+push/, label: 'git push' },
      { pattern: /git\s+reset\s+--hard/, label: 'git reset --hard' },
      { pattern: /git\s+clean\s+-[fd]/, label: 'git clean' },
      { pattern: /drop\s+(?:table|database)/i, label: 'DROP statement' },
      { pattern: /truncate\s+table/i, label: 'TRUNCATE statement' },
      { pattern: /rm\s+-rf?\s+/, label: 'recursive delete' },
      { pattern: /sudo\s+/, label: 'sudo command' },
      { pattern: /npm\s+publish/, label: 'npm publish' },
      { pattern: /docker\s+push/, label: 'docker push' },
      { pattern: /kubectl\s+(?:delete|apply)/, label: 'kubectl modify' },
      { pattern: /chmod\s+777/, label: 'chmod 777' },
    ];

    for (const { pattern, label } of RISKY) {
      if (pattern.test(command)) {
        console.log(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'ask_user',
            permissionDecisionReason: `⚠️  Risky operation (${label}): ${command.substring(0, 100)}`
          }
        }));
        return;
      }
    }

    // Safe — allow
    process.exit(0);
  } catch (e) {
    process.exit(0); // Don't block on parse errors
  }
});
