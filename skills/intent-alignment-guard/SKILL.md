---
name: intent-alignment-guard
description: "MANDATORY SELF-CHECK before any write, external, or high-risk action. Invoke when about to Edit, Write, Bash, push, send, delete, or execute anything that affects state outside the immediate read task."
---

# Intent Alignment Guard

Two distinct functions, checked separately at the action boundary:

- **Authorization** — did the user permit this action? (Tiers 1–4 below.)
- **Quality** — does this output meet the encoded bar? (Constraint Library below.)

Consent and quality are never blurred: an authorized action can still FAIL quality, and a high-quality output can still be unauthorized. Both must pass.

## Task-Start — Interactive Multiple Choice

Run at the start of every non-conversational task. Skip for purely conversational turns ("thanks", "ok", "what does X mean").

---

### Step 1 — All Questions (single call)

Use `AskUserQuestion` with **four questions in a single call** (tool maximum is 4). Generate options from what you understand about the task and codebase — do not use generic placeholders.

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

**Q3 — Risk + Data Routing** (`header`: `"Risk"`)
Combine risk tier and output destination into one question. Generate 2–4 options that capture both where output lands AND whether any external actions are involved:
- "Local only, no external actions" — Tier 1/2; output stays in repo/vault; no push/send/delete
- "Local + logged/persisted" — Tier 1/2; output appended to ledger or memory file in addition to primary destination
- "Includes Tier 3/4 action" — push, send, delete, external API, visible to others; describe the external action
- "Multiple placements" — output goes to 2+ destinations with distinct relationships; list them
- Only include options that are genuinely plausible; omit options that clearly don't apply

**Q4 — Pathway** (`header`: `"Pathway"`)
- "Proceed on context" *(Recommended)* — start work based on what was just confirmed
- "Proposal first" — generate 5-field formal proposal; wait for approval before doing anything
- "Skip guard" — proceed without further checks (hook still logs tier)

**Option description format** — the `description` field for every option must use **bullet points**, not prose. Separate bullets with `\n`:
```
- [what this option does]
- [what it affects / where output lands]
- [key constraint, trade-off, or caveat]
```
2–3 bullets per option is the target. Never write a single prose sentence as a description — bullets make the trade-offs scannable at a glance.

**If Q1 = "Skip IAG":** skip the context summary entirely and proceed immediately. Hook still logs tier. Ignore Q2–Q4 answers.

---

### Step 2 — Context Summary (always shown unless Q1 = "Skip IAG")

Before starting work, scan `constraint-log.md` for entries whose `[domain]` or `How to apply` matches the current task; load their `Constraint` text into the summary. Then display this block:

```
• Task:        [one sentence — the confirmed task from Q1]
• Scope:       [what was confirmed in Q2]
• Data:        [where output lands + its relationship to each destination (input-to / stored-in / replaces / augments / triggers)]
• Risks:       [Tier 3/4 actions identified, or "none identified"]
• Constraints: [matching constraint text from constraint-log.md, or "none loaded"]
• Mode:        [proposal first / proceed / guard off]
```

Scan `constraint-log.md` for entries matching the current task domain; surface the constraint text. If none match, show "none loaded."

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

Always show action bullets regardless of answer. The first three bullets check **authorization**; the `Quality` bullet checks the output against the **Constraint Library** — two separate checks, both must pass:

```
• Action:     [exact action — Tier N label]
• Authorized: [what in this conversation justifies it]
• Skipped:    [lower-risk alternatives considered and rejected]
• Quality:    passes  /  FAILS — constraint violated: "[constraint text]"
• Mode:       [proposal / proceed]
```

**If "No" or Other with blocking intent → BLOCK.** Do not proceed until authorization is explicit. Silence is not consent.

**If `Quality` FAILS → outcome is REVISE or BLOCK → immediately run Constraint Capture** (below) before retrying the action.

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
| **ALLOW** | Authorization clear; action within scope; quality passes | Proceed |
| **BLOCK** | No clear authorization; Tier 4 without explicit approval; or hard quality violation | Stop; explain why; run Constraint Capture if quality-driven |
| **REVISE** | Partial alignment, or quality FAILS a loaded constraint | Execute a safer/corrected form; run Constraint Capture |
| **ESCALATE** | Requires human decision before any action | Ask; do not infer |

---

## Constraint Capture

Run after any **REVISE** or **BLOCK** driven by quality, or whenever the user rejects an output. Every rejection is a knowledge-creation moment — capture it so the constraint persists instead of evaporating.

1. **Recognize** — state the specific gap between "looks right" and "is correct." Name what was actually wrong, not that something felt off.
2. **Articulate** — rewrite the gap as a domain-portable constraint. Strip out task-specific nouns; phrase it so it fires on the next analogous task, not just this one.
3. **Encode** — append the constraint to `constraint-log.md` (append-only; never overwrite an existing entry) using this template verbatim:

```
### [domain] — [constraint title]
Date:        YYYY-MM-DD
Trigger:     [action or output that caused the rejection]
Constraint:  [the rule — portable, not task-specific]
Why:         [underlying reason — domain logic, past incident, business requirement]
How to apply:[when/where this fires in future tasks]
Confirmed:   0  ← increment on each future task where this constraint catches something
Status:      draft
```

**Auto-graduation:** Each future task where a constraint catches something, increment its `Confirmed` count. When `Confirmed` reaches **2** (confirmed in 2 distinct tasks), auto-promote the entry to a `memory/feedback_*.md` file using the existing feedback schema (`rule → **Why:** → **How to apply:**`). The promotion is a **copy** — do not reword or translate the constraint text. Then set `Status: graduated` in `constraint-log.md` and add it to that file's `## Graduated` section with a pointer to the new feedback file.

---

## Constraint Library

The Constraint Library is the quality memory that the authorization tiers cannot provide. Lifecycle:

- **Load** — at Step 2, matching constraints are surfaced in the `• Constraints:` bullet.
- **Capture** — at the Action Gate, a quality FAIL triggers Constraint Capture, which appends a new entry.
- **Graduate** — at `Confirmed: 2`, the entry is copied into durable memory and marked `graduated`.

File path: `.claude/skills/intent-alignment-guard/constraint-log.md` — this is **session-capture**: fast, append-only, draft-grade. `memory/feedback_*.md` is **durable institutional knowledge** — load-bearing across all projects. A constraint earns its way from one to the other by catching real errors twice.

---

## Sub-Skills

**`action-permissions`** — Look up, grant, or revoke permissions for a specific action (git push, Slack send, rm -rf, etc.) across skills, cron jobs, scheduled routines, and settings.json. Invoke via `Skill("action-permissions")`.

---

## Architecture (when building multi-agent systems)

- **Actor** optimizes for task completion
- **Judge** (separate frontier model) optimizes only for user intent — never the same model as the actor
- Judge sits at the **action boundary**, not at end of task
- Four required outcomes: ALLOW / BLOCK / REVISE / ESCALATE
- Quality layer (constraint library) sits alongside authorization — both checked at action boundary; neither substitutes for the other
- Scope boundaries documented: what can this agent touch, write, delete?
