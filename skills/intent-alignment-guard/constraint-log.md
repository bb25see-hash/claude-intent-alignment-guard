---
name: constraint-log
description: "Session-capture quality memory for intent-alignment-guard. Append-only log of constraints learned from REVISE/BLOCK/rejection events. Entries graduate to memory/feedback_*.md after being confirmed in 2 distinct tasks."
type: reference
---

# Constraint Log

This is the **quality memory** for the intent-alignment-guard skill. Every time an output is rejected, revised, or blocked for a quality reason, the gap is recognized, articulated as a portable rule, and encoded here. On future tasks, matching constraints are loaded back into the Step-2 context summary so the same mistake is caught before it ships. Constraints that prove themselves (confirmed in 2 distinct tasks) graduate to `memory/feedback_*.md`, which is durable institutional knowledge. This file is the fast, draft-grade capture layer that feeds it.

## How to read this file

- At Step 2 (Context Summary), scan every entry. Match on the `[domain]` in the heading and on the `How to apply` line against the current task's domain, files, or systems.
- Surface the `Constraint` text of each match in the `• Constraints:` bullet. If nothing matches, show "none loaded."
- A match means: this rule has fired before on work like this. Treat it as an active quality check at the Action Gate, not background reading.

## How to write to this file

- **Append-only. Never overwrite or delete an existing entry.** Add new entries at the bottom of the entry list, above `## Graduated`.
- Use the capture template from SKILL.md verbatim. Convert relative dates to absolute (e.g., "today" → 2026-06-06).
- When a constraint catches something on a new task, increment its `Confirmed` count in place (this is the one permitted in-place edit).
- When `Confirmed` reaches 2: copy the rule to a `memory/feedback_*.md` file (do not reword), set `Status: graduated` here, and move a pointer line into `## Graduated`.

---

## Entries

### vault-writes — Recently Added & Amended entry is mandatory on every vault mutation
Date:        2026-06-06
Trigger:     Wrote a new research doc into the Vive La Memory vault but did not log the add in Recently Added & Amended.md; the change was invisible to the changelog and to "What's new this week."
Constraint:  Any add/amend/move/rename/delete inside a tracked Obsidian vault must add a top-of-file entry to that vault's Recently Added & Amended.md, with an ISO timestamp, a separate **References:** section linking every touched doc, and a separate **Cross-refs:** line. Blank line between every descriptor bullet.
Why:         The vault's auto-changelog and "Where to Start" surfaces read from Recently Added & Amended entries; a mutation without an entry silently breaks freshness tracking and leaves the vault state undiscoverable.
How to apply:Fires before completing any Tier 2 write whose destination is under Vault\Mega_Vault\. Check that the entry exists before reporting the write as done.
Confirmed:   0
Status:      draft

---

## Graduated

_(empty — promoted entries are listed here with a pointer to their memory/feedback_*.md file once Confirmed reaches 2)_
