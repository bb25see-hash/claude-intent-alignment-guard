---
name: action-permissions
description: Use when you need to look up, grant, or revoke permissions for a specific action (git push, git pull, Slack send, rm -rf, etc.) across skills, cron jobs, scheduled routines, and settings.json. Also use when user asks "is X allowed", "what can my cron do", "add permission for Y", or "remove permission for Z".
---

# Action Permission Manager

Sub-skill of `intent-alignment-guard`. Surfaces and manages what actions are authorized across the four permission planes — with **scoped grants** so a permission can be given to one skill, cron, or routine without touching the global allowlist.

---

## Step 1 — Mode + Action + Planes (single AskUserQuestion call, 3 questions)

**Q1 — Mode** (`header: "Mode"`)
- "Lookup" — show permission matrix for one action across selected planes
- "Grant" — authorize an action for a specific skill, cron, routine, project, or globally
- "Revoke" — remove an authorization from any scope
- "Audit" — list all Tier 3/4 actions found across selected planes

**Q2 — Action** (`header: "Action"`)

Generate 2–4 options from what was mentioned or implied:
- Common Tier 3: `git push`, `Slack send`, `gh pr create`, `gh pr merge`
- Common Tier 2: `git pull`, `git commit`, `Edit`, `Write`
- Common Tier 4: `rm -rf`, `git push --force`
- "All Tier 3/4" — scan comprehensively

**Q3 — Planes** (`header: "Planes"`, `multiSelect: true`)
- "settings.json" — `~/.claude/settings.json` allow[]/deny[]
- "Skills" — grep `~/.claude/skills/*/SKILL.md`
- "Cron jobs" — `CronList` commands
- "Routines" — `/schedule` managed agents

---

## Step 2 — Proceed (second AskUserQuestion call)

**Q4 — Proceed** (`header: "Proceed"`)
- "Run now" *(Recommended)*
- "Show plan first"
- "Cancel"

---

## Step 3 — Context Summary (always shown before executing)

```
• Mode:    [Lookup / Grant / Revoke / Audit]
• Action:  [action name — Tier N — External / Local write / Destructive]
• Planes:  [which planes will be checked]
• Risk:    [Tier 1 read-only / Tier 2 local write / Tier 4 — needs explicit auth]
```

---

## Lookup — Execution

**Tier 1 — no gate needed.**

1. `Read ~/.claude/settings.json` → scan `allow[]` and `deny[]`
2. `CronList` → scan `command` fields for the action keyword
3. `Grep ~/.claude/skills/` → all SKILL.md files (including `## Authorized Actions` sections)
4. Read `~/.claude/cron-permissions.json` if it exists → scan for the action
5. Routines: check `/schedule` agent configs

**Output format:**
```
Action: git push  (Tier 3 — External)

Plane                    | Status      | Scope            | Where / Context
settings.json (global)   | not listed  | global           | Not in allow[] or deny[]
settings.json (project)  | not listed  | this project     | Not in .claude/settings.json
Skills                   | REFERENCED  | intent-align-guard | Tier 3 gate required
                         | AUTHORIZED  | polymarket-sync  | ## Authorized Actions: git push origin master*
Cron jobs                | EXECUTES    | polymarket-sync  | cron job-id abc123
cron-permissions.json    | not listed  | —                | File not found
Scheduled routines       | —           | —                | none found

Verdict: polymarket-sync has a skill-declared authorization. IAG will auto-allow when that skill is active.
```

**Status values:**

| Status | Meaning |
|--------|---------|
| `ALLOW` | In `allow[]` / explicitly approved |
| `DENY` | In `deny[]` / explicitly blocked |
| `AUTHORIZED` | In `## Authorized Actions` in a SKILL.md or `cron-permissions.json` |
| `EXECUTES` | A cron or routine runs this action |
| `REFERENCED` | A skill mentions this action — check for gate vs. blanket approval |
| `not listed` | No record; IAG default tiers apply |

---

## Grant — Execution

**Tier 2 — Reversible local write. Action Gate required before writing.**

### Sub-step A — Scope question (third AskUserQuestion call)

`header: "Scope"` — where should this permission live?

Generate options from context (which skill/cron/routine was mentioned):

- "Skill-declared — [skill-name]" — adds `## Authorized Actions` entry to that skill's SKILL.md; IAG reads it to auto-allow when that skill is active *(Recommended for skill-specific use)*
- "Cron-scoped — [job name/id]" — adds entry to `~/.claude/cron-permissions.json`; IAG reads it when that cron runs
- "Project-scoped — .claude/settings.json" — adds to the active project's local settings; applies to all tools in this project only
- "Global — ~/.claude/settings.json" — applies everywhere; use only when the action should be allowed from any context

**If user named a specific skill** (e.g., "polymarket-sync"), default the first option to that skill. Never default to Global.

### Sub-step B — Pattern question (fourth AskUserQuestion call, for skill-declared and cron-scoped)

`header: "Pattern"` — how specific should the authorization be?

Generate options from the action + what the skill/cron actually runs (grep the skill SKILL.md for the exact command used):
- Narrow: `git push origin master` or `git push origin HEAD` (exact branch)
- Broad: `git push origin *` (any branch on origin)
- Full: `git push *` — any remote/branch — **flag if broader than needed**
- "Enter custom" — user specifies

For `settings.json allow[]` (project or global scope), wrap in `Bash(...)`:
- `Bash(git push origin master*)`, `Bash(git push origin HEAD*)`, etc.

### Sub-step C — Action Gate

```
• Action:     [write target — Tier 2 — exact file + change]
• Authorized: [what in this conversation justifies it]
• Skipped:    [why broader/global scope was not used]
• Mode:       proceed
```

`AskUserQuestion` (`header: "Action Gate"`):
- "Yes — proceed"
- "Yes — show the exact diff first"
- "No — stop"

### Sub-step D — Write

**Skill-declared** — add to the skill's SKILL.md. If `## Authorized Actions` section already exists, append. If not, create it just before the final section:

```markdown
## Authorized Actions

These actions are pre-authorized for this skill. The intent-alignment-guard reads this section
and auto-allows matching actions when this skill is active.

| Action | Pattern | Authorized by | Date |
|--------|---------|---------------|------|
| git push | `git push origin master*` | [user — context] | YYYY-MM-DD |
```

**Cron-scoped** — write/update `~/.claude/cron-permissions.json`:

```json
{
  "polymarket-sync": {
    "job_id": "abc123",
    "authorized_actions": [
      {
        "action": "git push",
        "pattern": "git push origin master*",
        "authorized_by": "user",
        "date": "YYYY-MM-DD",
        "context": "automated sync run"
      }
    ]
  }
}
```

**Project-scoped / Global** — add to `allow[]` in the appropriate `settings.json`:

```json
"allow": ["Bash(git push origin master*)"]
```

### Sub-step E — Memory log

Append to `memory/permission_changes_log.md`:

```markdown
## [ISO timestamp] — GRANT [action]
- Scope:   [Skill-declared: polymarket-sync / Cron: job-id / Project / Global]
- Pattern: `[exact pattern added]`
- Target:  [file path edited]
- Context: [one sentence — why authorized]
```

---

## Revoke — Execution

**Tier 2.**

### Sub-step A — Scope + match confirmation (third AskUserQuestion call)

Show where the action is currently authorized (all scopes that have a record). Ask which to remove:
- "Skill-declared — polymarket-sync SKILL.md"
- "cron-permissions.json — job abc123"
- "Project settings.json — .claude/settings.json"
- "None — cancel"

Never remove partial matches. Confirm verbatim before editing.

### Sub-step B — Action Gate → Write → Memory log

Same pattern as Grant: gate → edit → log.

---

## Audit — Execution

**Tier 1 — no gate needed.**

Scan all selected planes. For each Tier 3/4 action found, report:

```
Plane: Skills
  polymarket-sync/SKILL.md
    ## Authorized Actions: git push origin master*  [Tier 3 — pre-authorized]
  intent-alignment-guard/SKILL.md
    REFERENCED: git push  [Tier 3 — gate required]

Plane: Cron jobs  (CronList)
  polymarket-sync (job-id: abc123)
    git push origin master  [Tier 3 — EXECUTES — covered by skill-declared auth]

Plane: settings.json (global)
  allow[]: none

Plane: settings.json (project)
  allow[]: none
```

---

## Four Permission Planes Reference

| Plane | Source | Scope |
|-------|--------|-------|
| **settings.json (global)** | `~/.claude/settings.json allow[]` | All skills, all projects |
| **settings.json (project)** | `.claude/settings.json allow[]` | This project only |
| **Skill-declared** | `~/.claude/skills/[name]/SKILL.md` `## Authorized Actions` | That skill only |
| **Cron-scoped** | `~/.claude/cron-permissions.json` keyed by job ID | That cron only |
| **Routines** | `/schedule` agent config | That routine only |

IAG reads all five scopes before deciding whether to gate. Skill-declared and cron-scoped authorizations are the least-privilege options — prefer them over project or global.

---

## Tier Quick Reference

| Action | Tier | Notes |
|--------|------|-------|
| `git push` | 3 | External; visible to remote |
| `git pull` | 2 | Local write; reversible |
| `git commit` | 2 | Local; reversible |
| `Slack send` | 3 | External; visible to channel |
| `rm -rf` | 4 | Destructive; requires explicit written auth |
| `gh pr create/merge` | 3 | External; visible on GitHub |
| `Edit` / `Write` | 2 | Local; reversible |
| `WebSearch` / `WebFetch` | 1 | Read-only |
| `Read` / `Grep` / `Glob` | 1 | Read-only |
| `CronList` / `CronCreate` | 1 / 2 | List = read-only; Create = local write |

---

## Memory Log Path

`~/.claude/projects/C--Users-csbuc-Research-Marketing-Strategist-Agent-Environment--main/memory/permission_changes_log.md`

Create the file if it does not exist.
