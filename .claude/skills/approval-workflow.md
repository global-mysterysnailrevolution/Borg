---
name: approval-workflow
description: >
  Implements human-in-the-loop approval gates for high-risk operations.
  Use this skill before deploying to production, making destructive changes,
  modifying security settings, sending external communications, or any
  operation the user has flagged as requiring approval. Triggers on
  /approve command and when operations match the approval-required list.
---

# Approval Workflow

Replaces the harness `APPROVAL_WORKFLOW.md` system.

## Operations Requiring Approval

### Always Require Approval
- `git push` to main/master/production branches
- Database migrations or schema changes
- Deployment commands (docker push, kubectl apply, etc.)
- Deleting files outside of `ai/` or `node_modules/`
- Modifying `.env`, secrets, or credential files
- External API calls that modify state (POST/PUT/DELETE to production)
- Publishing packages (npm publish, pip upload, etc.)

### Configurable (user can enable/disable)
- Creating new files outside the project structure
- Installing new dependencies
- Running commands with sudo/admin
- Modifying CI/CD pipelines

## Approval Flow

1. **Detect** — Identify operation matches approval-required list
2. **Present** — Show the user exactly what will happen:
   - Command or action to execute
   - Files affected
   - Risk assessment (low/medium/high)
   - Rollback plan
3. **Wait** — Do NOT proceed until explicit "approved", "yes", "go ahead"
4. **Log** — Record approval in `ai/memory/APPROVALS.md`:
   ```markdown
   ## [timestamp] — [Action]
   **Risk**: [low/medium/high]
   **Approved by**: user
   **Result**: [pending/success/failed]
   ```
5. **Execute** — Run the approved operation
6. **Report** — Confirm completion or failure

## Emergency Override

If the user says "skip approvals" or "auto-approve", acknowledge but warn:
- "I'll proceed without approval gates. You can re-enable with `/approve on`"
- Log that approvals were bypassed in SESSION_LOG.md
