# Claude Intent Alignment Guard

A Claude Code skill system that enforces intent alignment before every write, external action, or high-risk operation — without slowing down routine work.

## What it does

Before any consequential action, the guard asks: *did the user actually authorize this?* It does this at two layers:

1. **The hook** (`hooks/pretool_intent_guard.py`) — a pattern-based `PreToolUse` hook that runs in <10ms before every `Bash`, `PowerShell`, `Edit`, and `Write` call. No LLM call. Classifies commands into four tiers and emits a directive.

2. **The skills** — interactive Claude Code skills that run the full task-start protocol and manage permissions across four authorization planes.

---

## Components

```
├── skills/
│   ├── intent-alignment-guard/SKILL.md   # Task-start protocol + action gate
│   └── action-permissions/SKILL.md       # Permission lookup / grant / revoke
├── hooks/
│   └── pretool_intent_guard.py           # PreToolUse enforcement hook
├── skill-permissions.template.json       # Per-skill authorization registry (template)
└── settings-hook-snippet.json            # Hook registration for settings.json
```

---

## Tier Classification

| Tier | Type | Hook behavior |
|------|------|---------------|
| 1 — Read-only | `git status`, `grep`, `Read`, `WebSearch` | Silent pass |
| 2 — Reversible local write | `Edit`, `Write`, `git commit`, `mkdir` | Reminder emitted; proceed |
| 3 — External / visible | `git push`, `gh pr`, Slack, external APIs | STOP directive; invoke IAG skill |
| 4 — Destructive / irreversible | `rm -rf`, force push, `DROP TABLE` | **Blocked** (exit 2) |

The hook also classifies by **file path** (sensitive paths like `.env`, `.ssh/`, `settings.json` escalate to Tier 3) and **content** (credential patterns in `new_string`/`content` escalate to Tier 3).

Chain analysis splits `&&` / `;` / `||` and takes the **highest tier** across all segments.

---

## How it works

### Task-start (per task)

`/intent-alignment-guard` runs a 5-question interactive protocol in a **single `AskUserQuestion` call**:

- **Q1 Task** — 2–3 interpretations of what the user wants; includes a "Skip IAG" escape hatch
- **Q2 Scope** — which files/systems are in scope
- **Q3 Risk** — Tier 1/2 only vs. includes Tier 3/4
- **Q4 Data Routing** — where output lands and its relationship to each destination
- **Q5 Pathway** — Proceed / Proposal first / Skip guard

If Q1 = "Skip IAG", the guard is bypassed entirely (hook still logs tier). Otherwise a context summary block is always shown before work begins.

### Action gate (per Tier 2–4 action)

Before each consequential action during execution, an inline gate surfaces:

```
• Action:     [exact action — Tier N label]
• Authorized: [what in this conversation justifies it]
• Skipped:    [lower-risk alternatives considered and rejected]
• Mode:       [proposal / proceed]
```

### Permission planes (`/action-permissions`)

The `action-permissions` sub-skill manages authorizations across four planes:

| Plane | Source | Scope |
|-------|--------|-------|
| Global settings | `~/.claude/settings.json allow[]` | All skills, all projects |
| Project settings | `.claude/settings.json allow[]` | This project only |
| Skill-declared | `SKILL.md ## Authorized Actions` | That skill only |
| Cron-scoped | `~/.claude/cron-permissions.json` | That cron job only |

**Prefer skill-declared or cron-scoped grants** — they are least-privilege and don't bleed into unrelated contexts.

### Skill-level authorization overrides

Commands in `skill-permissions.json` matching an active skill's authorization are **silently passed** by the hook before the Tier 3/4 sweep runs. This lets you pre-authorize predictable actions (e.g. `git push origin main` for an automated sync skill) without touching the global allowlist.

---

## Installation

### 1. Copy skill files

```
~/.claude/skills/intent-alignment-guard/SKILL.md
~/.claude/skills/action-permissions/SKILL.md
```

### 2. Copy the hook

```
~/.claude/scripts/pretool_intent_guard.py
```

### 3. Register the hook in `~/.claude/settings.json`

Merge the contents of `settings-hook-snippet.json` into your settings, updating the path:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "python \"/home/you/.claude/scripts/pretool_intent_guard.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### 4. Create the permissions registry (optional)

Copy `skill-permissions.template.json` to `~/.claude/skill-permissions.json` and populate it, or let `/action-permissions` create and manage it for you.

---

## Usage

| Command | When to use |
|---------|-------------|
| `/intent-alignment-guard` | Start of any non-trivial task — runs the 5-question protocol |
| `/action-permissions` | Lookup what's authorized; grant or revoke a permission for a specific skill, cron, or globally |

---

## Outcomes

| Outcome | When |
|---------|------|
| **ALLOW** | Authorization clear; action within scope |
| **BLOCK** | No clear authorization; Tier 4 without explicit written approval |
| **REVISE** | Partial alignment — execute a safer form |
| **ESCALATE** | Requires human decision before any action |

**Tier 4 rule:** requires explicit written authorization in the conversation. No implicit consent. Silence is not consent.

---

## Multi-agent architecture note

When building multi-agent systems with IAG:

- The **Actor** optimizes for task completion
- The **Judge** (separate frontier model) optimizes only for user intent — never the same model as the actor
- Judge sits at the **action boundary**, not at end of task
- Scope boundaries must be documented: what can this agent touch, write, delete?

---

## Requirements

- [Claude Code](https://claude.ai/code)
- Python 3.8+ (for the hook — no dependencies beyond stdlib)
- `gh` CLI (for `/action-permissions` cron plane lookups)
