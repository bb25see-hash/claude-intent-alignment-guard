# Claude Intent Alignment Guard

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)
![Platform: Claude Code](https://img.shields.io/badge/Platform-Claude%20Code-blueviolet.svg)

> **Did the user actually authorize this?**
>
> IAG answers that question before every write, push, delete, or external action — in under 10ms, with no LLM call.

---

## The problem it solves

Claude Code is powerful enough to push code, send Slack messages, delete files, and call external APIs — all in a single session. Without a guard, *ambiguous intent becomes unintended action*.

IAG inserts a structured consent layer between intent and execution. Routine read-only work passes silently. Consequential actions surface a gate. Destructive actions are blocked outright until you say so explicitly.

---

## How it works

```
  User message
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  /intent-alignment-guard  (task-start)                  │
│                                                         │
│  5 questions · 1 AskUserQuestion call · no round-trip   │
│                                                         │
│  Q1 Task ── Q2 Scope ── Q3 Risk ── Q4 Routing ── Q5 Go  │
│       └─ "Skip IAG" → bypass all checks immediately     │
└──────────────────────────┬──────────────────────────────┘
                           │  context summary always shown
                           ▼
                      Claude works
                           │
              ┌────────────┴────────────┐
              │                         │
        Tier 1–2                    Tier 3–4
        (local)                  (external / destructive)
              │                         │
        hook: silent            hook: STOP directive
        or T2 reminder               │
              │                   ┌───┴────────────────────┐
              │                   │  Action Gate           │
              │                   │  • What exactly        │
              │                   │  • What authorized it  │
              │                   │  • Alternatives tried  │
              │                   └───┬────────────────────┘
              │                       │
              │              ┌────────┴────────┐
              │              │                 │
              │           ALLOW             BLOCK / ESCALATE
              │              │
              └──────────────┘
                    Done
```

---

## Tier classification

The hook (`hooks/pretool_intent_guard.py`) classifies every `Bash`, `PowerShell`, `Edit`, and `Write` call before it executes. No LLM call — pure regex pattern matching in <10ms.

| Tier | Label | Examples | Hook response |
|:----:|-------|----------|---------------|
| **1** | Read-only | `git status`, `grep`, `Read`, `WebSearch` | Silent pass |
| **2** | Reversible local write | `Edit`, `Write`, `git commit`, `mkdir` | Reminder + proceed |
| **3** | External / visible | `git push`, `gh pr`, Slack, external APIs | **STOP** — invoke IAG |
| **4** | Destructive / irreversible | `rm -rf`, force push, `DROP TABLE` | **Blocked** (exit 2) |

**Three escalation paths beyond basic tier:**
- **Sensitive paths** — `.env`, `.ssh/`, `settings.json` → auto-escalate to Tier 3
- **Credential content** — API keys, JWTs, PEM keys in write payloads → auto-escalate to Tier 3
- **Chain analysis** — `cmd1 && cmd2 ; cmd3` → highest tier across all segments wins

---

## Task-start protocol

Every non-trivial task opens with a **single 5-question `AskUserQuestion` call** — no back-and-forth:

```
┌─ Q1: Task ──────────────────────────────────────────────┐
│  2–3 context-derived interpretations of what you want   │
│  + "Skip IAG" as a one-click bypass option              │
├─ Q2: Scope ─────────────────────────────────────────────┤
│  Specific files / vaults / systems inferred from context│
├─ Q3: Risk ──────────────────────────────────────────────┤
│  No external actions  /  Includes Tier 3/4  /  Not sure │
├─ Q4: Data Routing ──────────────────────────────────────┤
│  Where output lands + its relationship to each dest.    │
└─ Q5: Pathway ───────────────────────────────────────────┘
   Proceed on context  /  Proposal first  /  Skip guard
```

A context summary block is always shown before work begins:

```
• Task:   [confirmed task]
• Scope:  [confirmed files/systems]
• Data:   [destination + relationship — input-to / stored-in / triggers]
• Risks:  [Tier 3/4 flags, or "none identified"]
• Mode:   [proceed / proposal first / guard off]
```

---

## Permission planes

`/action-permissions` manages what's authorized across four planes — from most to least privileged:

```
  ┌─────────────────────────────────────────────┐  broadest
  │  ~/.claude/settings.json  allow[]           │  all skills · all projects
  ├─────────────────────────────────────────────┤
  │  .claude/settings.json  allow[]             │  this project only
  ├─────────────────────────────────────────────┤
  │  SKILL.md  ## Authorized Actions            │  that skill only  ← preferred
  ├─────────────────────────────────────────────┤
  │  ~/.claude/cron-permissions.json            │  that cron only   ← preferred
  └─────────────────────────────────────────────┘  narrowest
```

**Always grant at the narrowest scope that works.**  
A skill-declared authorization only fires when that skill is active — it never bleeds into unrelated work.

---

## Outcomes

| Outcome | Condition | Action |
|---------|-----------|--------|
| `ALLOW` | Authorization clear; action within scope | Proceed |
| `BLOCK` | Tier 4 without explicit written approval | Stop; explain why |
| `REVISE` | Partial alignment | Execute a safer form (draft vs. send; read vs. write) |
| `ESCALATE` | Requires human decision | Ask — never infer |

> **Tier 4 rule:** explicit written authorization required in this conversation.  
> No implicit consent. No "they didn't say to stop." **Silence is not consent.**

---

## Repo contents

```
claude-intent-alignment-guard/
├── skills/
│   ├── intent-alignment-guard/
│   │   └── SKILL.md          ← task-start protocol + action gate
│   └── action-permissions/
│       └── SKILL.md          ← permission lookup / grant / revoke
├── hooks/
│   └── pretool_intent_guard.py   ← PreToolUse enforcement hook (<10ms, stdlib only)
├── skill-permissions.template.json   ← per-skill auth registry template
├── settings-hook-snippet.json        ← hook registration snippet
└── LICENSE
```

---

## Installation

**1. Copy the skill files**

```sh
mkdir -p ~/.claude/skills/intent-alignment-guard
mkdir -p ~/.claude/skills/action-permissions
mkdir -p ~/.claude/scripts

cp skills/intent-alignment-guard/SKILL.md ~/.claude/skills/intent-alignment-guard/
cp skills/action-permissions/SKILL.md     ~/.claude/skills/action-permissions/
cp hooks/pretool_intent_guard.py          ~/.claude/scripts/
```

**2. Register the hook in `~/.claude/settings.json`**

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

**3. (Optional) Seed the permissions registry**

```sh
cp skill-permissions.template.json ~/.claude/skill-permissions.json
```

Or skip this — `/action-permissions` will create and manage it for you on first use.

---

## Usage

| Invoke | When |
|--------|------|
| `/intent-alignment-guard` | Start of any non-trivial task |
| `/action-permissions` | Lookup, grant, or revoke a permission across any plane |

---

## Multi-agent note

When building multi-agent systems:

- **Actor** — optimizes for task completion
- **Judge** — separate frontier model; optimizes *only* for user intent; never the same model as the actor
- Judge sits at the **action boundary**, not end of task
- Scope boundaries must be explicit: what can this agent touch, write, delete?

---

## Requirements

- [Claude Code](https://claude.ai/code)
- Python 3.8+ (hook has no dependencies beyond stdlib)
- `gh` CLI (optional — used by `/action-permissions` for cron plane lookups)
