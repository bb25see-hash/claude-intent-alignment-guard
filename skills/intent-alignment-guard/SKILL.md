---
name: intent-alignment-guard
description: "MANDATORY SELF-CHECK before any write, external, or high-risk action. Invoke when about to Edit, Write, Bash, push, send, delete, or execute anything that affects state outside the immediate read task."
---

# Intent Alignment Guard

## Task-Start — Interactive Multiple Choice

Run at the start of every non-conversational task. Skip for purely conversational turns ("thanks", "ok", "what does X mean").

---

### Step 1 — All Questions (single call)

Use `AskUserQuestion` with **five questions in a single call**. Generate options from what you understand about the task and codebase — do not use generic placeholders.

**Q1 — Task** (`header`: `"Task"`, 12 chars max)
Generate 2–3 options that represent the plausible interpretations of what the user wants:
- First option: your most confident interpretation (label it like an action: "Edit SKILL.md", "Update tracker", "Add auth endpoint")
- Second option: a narrower or broader variant if genuinely ambiguous
- Third option: only if a third distinct reading is plausible
- Last option (always): "Skip IAG" — bypasses all guard checks; proceed immediately without context summary
- "Other" is added automatically — do not add it yourself

**Q2 — Scope** (`header`: `"Scope"`)
Generate 2–4 options based on what files, vaults, or systems are mentioned or implied:
- Specific paths you've inferred (e.g., `scripts/sync-lego-tracker.ps1`)
- "Project-wide" if multiple systems are in play
- A narrower option ("Single file only") if a scoped interpretation is realistic

**Q3 — Risk** (`header`: `"Risk"`)
Use these fixed options:
- "No external actions" — Tier 1/2 only (read, edit, local write)
- "Includes Tier 3/4" — push, send, delete, external API call, visible to others
- "Not sure yet"

**Q4 — Data Routing** (`header`: `"Data Routing"`)
Generate 2–4 options based on where the task output will land and what role it plays there. Capture both the destination and the relationship (input-to, stored-in, replaces, augments, triggers):
- "Stays local" — output lives only in this project/repo/vault; no downstream consumers
- "Feeds another system" — output is consumed by a separate system (e.g., Slack message, Google Drive, external API, email); describe the relationship in the option description
- "Logged / persisted" — output is appended to a ledger, memory file, or audit trail as a record
- "Multiple placements" — output propagates to 2+ downstream locations with distinct relationships; list them
- Only include options that are genuinely plausible given the task; omit options that clearly don't apply

**Q5 — Pathway** (`header`: `"Pathway"`)
- "Proceed on context" *(Recommended)* — start work based on what was just confirmed
- "Proposal first" — generate 5-field formal proposal; wait for approval before doing anything
- "Skip guard" — proceed without further checks (hook still logs tier)

**If Q1 = "Skip IAG":** skip the context summary entirely and proceed immediately. Hook still logs tier. Ignore Q2–Q5 answers.

---

### Step 2 — Context Summary (always shown unless Q1 = "Skip IAG")

Always display this block before starting work:

```
• Task:   [one sentence — the confirmed task from Q1]
• Scope:  [what was confirmed in Q2]
• Data:   [where output lands + its relationship to each destination (input-to / stored-in / replaces / augments / triggers)]
• Risks:  [Tier 3/4 actions identified, or "none identified"]
• Mode:   [proposal first / proceed / guard off]
```

Then follow through:
- **Proceed on context** → start; surface action-gate bullets before each Tier 2+ action
- **Proposal first** → generate formal proposal (see below); wait for explicit confirmation before doing anything
- **Skip guard** → proceed without further checks (hook still logs tier)
- **Other** → treat written text as authoritative scope; confirm interpretation before starting

---

## Action Gate — Tier 2–4 only

Before any Tier 2–4 action during task execution, use `AskUserQuestion` (single question):

**Header:** `"Action Gate"`
**Question:** `"[Tier N] About to [exact action]. Is this within what you authorized?"`
**Options** (context-derived, 2–3):
- "Yes — proceed"
- "Yes — but show proposal first"
- "No — stop"

Always show action bullets regardless of answer:

```
• Action:     [exact action — Tier N label]
• Authorized: [what in this conversation justifies it]
• Skipped:    [lower-risk alternatives considered and rejected]
• Mode:       [proposal / proceed]
```

**If "No" or Other with blocking intent → BLOCK.** Do not proceed until authorization is explicit. Silence is not consent.

---

## Tier Classification

| Tier | Examples |
|------|----------|
| **1 — Read-only** (no gate needed) | Read, Grep, Glob, git status/log/diff, WebSearch, WebFetch |
| **2 — Reversible local write** | Edit, Write, git commit, mkdir, pip install, local config |
| **3 — External / visible to others** | git push, gh pr create/merge, Slack/Gmail/Drive MCP, external APIs |
| **4 — Destructive / irreversible** | rm -rf, force push, DROP TABLE, delete data, change permissions |

**Tier 4 rule:** Requires **explicit written authorization** in this conversation. No implicit consent. No "they didn't say to stop." BLOCK without it.

---

## Formal Proposal (when "Proposal first" is selected)

```
ACTION TYPE:     [Tier 1/2/3/4 + label]
PROPOSED ACTION: [exact action — verbatim]
TASK SCOPE:      [what the user authorized]
EVIDENCE:        [what context in this conversation justifies it]
ALTERNATIVES:    [lower-risk paths considered and why rejected]
```

Wait for explicit confirmation before proceeding.

---

## Outcomes

| Outcome | When | What to do |
|---------|------|------------|
| **ALLOW** | Authorization clear; action within scope | Proceed |
| **BLOCK** | No clear authorization; Tier 4 without explicit approval | Stop; explain why |
| **REVISE** | Partial alignment | Execute a safer form (draft vs. send, read vs. write) |
| **ESCALATE** | Requires human decision before any action | Ask; do not infer |

---

## Sub-Skills

**`action-permissions`** — Look up, grant, or revoke permissions for a specific action (git push, Slack send, rm -rf, etc.) across skills, cron jobs, scheduled routines, and settings.json. Invoke via `Skill("action-permissions")`.

---

## Architecture (when building multi-agent systems)

- **Actor** optimizes for task completion
- **Judge** (separate frontier model) optimizes only for user intent — never the same model as the actor
- Judge sits at the **action boundary**, not at end of task
- Four required outcomes: ALLOW / BLOCK / REVISE / ESCALATE
- Scope boundaries documented: what can this agent touch, write, delete?
