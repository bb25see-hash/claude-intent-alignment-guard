"""
pretool_intent_guard.py — Comprehensive PreToolUse intent + tier classifier.

Runs before Edit / Write / Bash / PowerShell tool calls. No LLM call —
purely pattern-based for <10ms latency. Classifies actions by risk tier
using command patterns, file-path inspection, content inspection, and
chain analysis (splits && / ; segments and takes the highest tier).

Tier mapping:
  1 — Read-only (git status, grep, ls, cat, pytest)          -> silent pass
  2 — Reversible local write (edit file, git commit)          -> directive reminder
  3 — External / cross-system / sensitive (git push, gh pr)   -> invoke-skill directive
  4 — Destructive / irreversible (rm -rf, DROP TABLE)         -> BLOCKED (exit 2)

Hook output (stdout JSON hookSpecificOutput):
  Tier 1: nothing
  Tier 2: [IAG T2] reminder + invoke-skill-if-ambiguous directive
  Tier 3: [IAG T3] STOP — invoke Skill("intent-alignment-guard") NOW
  Tier 4: stderr [IAG] BLOCKED ... + exit 2

Skill-level authorization overrides:
  ~/.claude/skill-permissions.json — written by /action-permissions Grant flow.
  Any command matching an entry there is silently passed (Tier 1 override) before
  the Tier 4/3 sweep runs. This allows per-skill pre-authorization without touching
  the global settings.json allow[].
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Tier 4 — block outright (no legitimate automated use case)
# ---------------------------------------------------------------------------
_TIER4_PATTERNS: list[tuple[str, str]] = [
    # Filesystem destruction
    (r"\brm\s+-[rf]{1,3}\s+(/|~|\./?$|\$HOME|\$env:USERPROFILE|\$\{?HOME\}?)", "rm -rf on root/home/cwd"),
    (r"\brm\s+-[rf]{1,3}\s+\*", "rm -rf glob (all files)"),
    # Force push
    (r"\bgit\s+push\b.*--force(-with-lease)?\b", "force push"),
    (r"\bgit\s+push\b.*-[fF]\b(?!ile)", "force push shorthand"),
    # Push directly to protected branch
    (r"\bgit\s+push\b.*\b(origin|upstream)\s+(main|master|production|prod|release)\b", "push to protected branch"),
    # Database destruction
    (r"\bdrop\s+(table|database|schema)\b", "DROP TABLE/DATABASE/SCHEMA"),
    (r"\btruncate\s+table\b", "TRUNCATE TABLE"),
    # Disk / recursive Windows delete
    (r"format\s+[a-zA-Z]:\s*[/\\]", "disk format command"),
    (r"\bdel\s+/[sS]\b", "recursive Windows del /S"),
    (r"\brmdir\s+/[sS]\b", "recursive Windows rmdir /S"),
    (r"\bRemove-Item\b.*-Recurse\b.*-Force\b", "PS recursive force-delete"),
    (r"\bRemove-Item\b.*-Force\b.*-Recurse\b", "PS force-delete recursive (reversed flags)"),
    # Git history rewriting
    (r"\bgit\s+filter-branch\b", "git filter-branch (history rewrite)"),
    (r"\bgit\s+filter-repo\b", "git filter-repo (history rewrite)"),
]

# ---------------------------------------------------------------------------
# Tier 3 — external / cross-system / sensitive (must invoke IAG skill)
# ---------------------------------------------------------------------------
_TIER3_PATTERNS: list[tuple[str, str]] = [
    # --- Git: external / history-affecting ---
    (r"\bgit\s+push\b", "git push"),
    (r"\bgit\s+merge\b", "git merge"),
    (r"\bgit\s+rebase\b", "git rebase"),
    (r"\bgit\s+commit\s+--amend\b", "git commit --amend (history rewrite)"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard (discard all changes)"),
    (r"\bgit\s+clean\s+-[fdxXn]{1,4}\b", "git clean (discard untracked files)"),
    (r"\bgit\s+stash\s+(drop|clear)\b", "git stash drop/clear (permanent discard)"),
    (r"\bgit\s+branch\s+-[Dd]\b", "delete git branch"),
    (r"\bgit\s+tag\s+-[dD]\b", "delete git tag"),
    (r"\bgit\s+checkout\s+--\s", "git checkout -- (discard working-tree changes)"),
    (r"\bgit\s+restore\b", "git restore (discard changes)"),
    # --- GitHub CLI ---
    (r"\bgh\s+pr\s+(create|merge|close|comment|edit|review)\b", "GitHub PR action"),
    (r"\bgh\s+issue\s+(create|comment|close|edit|delete)\b", "GitHub issue action"),
    (r"\bgh\s+release\b", "GitHub release"),
    (r"\bgh\s+repo\b", "GitHub repo action"),
    (r"\bgh\s+workflow\s+run\b", "GitHub Actions trigger"),
    (r"\bgh\s+secret\b", "GitHub secret management"),
    # --- HTTP / external APIs ---
    (r"\bcurl\b.*https?://", "curl to external URL"),
    (r"\bwget\b.*https?://", "wget to external URL"),
    (r"\bInvoke-WebRequest\b", "PS web request"),
    (r"\bInvoke-RestMethod\b", "PS REST call"),
    (r"\bSend-MailMessage\b", "PS email send"),
    # --- Publishing / deployment ---
    (r"\bnpm\s+(publish|deploy)\b", "npm publish/deploy"),
    (r"\btwine\s+upload\b|\bpip\s+upload\b", "PyPI publish"),
    (r"\bcargo\s+publish\b", "crates.io publish"),
    (r"\bdocker\s+push\b", "docker push to registry"),
    (r"\bdocker\s+deploy\b", "docker deploy"),
    (r"\bvercel\s+(deploy|--prod)\b", "Vercel deploy"),
    (r"\bnetlify\s+deploy\b", "Netlify deploy"),
    (r"\bheroku\s+\w", "Heroku command"),
    (r"\bfly\s+(deploy|launch|secrets)\b", "Fly.io deploy/secrets"),
    # --- Cloud CLIs (mutating verbs only) ---
    (r"\baws\s+\S+\s+(create|delete|update|put|set|attach|detach|terminate|stop|start|deploy|publish|revoke)\b", "AWS mutating CLI"),
    (r"\baz\s+\S+\s+(create|delete|update|set|assign|deploy|publish|revoke)\b", "Azure mutating CLI"),
    (r"\bgcloud\s+\S+\s+(create|delete|update|deploy|publish|set|revoke)\b", "GCloud mutating CLI"),
    (r"\bterraform\s+(apply|destroy|import|push)\b", "Terraform apply/destroy"),
    (r"\bpulumi\s+(up|destroy|cancel)\b", "Pulumi up/destroy"),
    (r"\bkubectl\s+(apply|delete|patch|scale|rollout|exec|cp|replace|create|run)\b", "kubectl mutating command"),
    # --- Remote execution ---
    (r"\bssh\b.+@.+\b(rm|sudo|systemctl|reboot|shutdown|drop|delete|truncate|kill)\b", "SSH remote destructive cmd"),
    (r"\bscp\b", "SCP file transfer"),
    (r"\brsync\b.*--delete\b", "rsync --delete"),
    # --- Safety bypass flags ---
    (r"--no-verify\b", "--no-verify (bypass hooks)"),
    (r"--skip-hooks?\b", "--skip-hooks"),
    (r"--no-gpg-sign\b", "--no-gpg-sign (bypass signing)"),
    (r"--allow-empty\b", "--allow-empty commit"),
    (r"--force\b", "--force flag (scope depends on command)"),
    # --- Secrets / credentials in command args ---
    (r"(?i)(export|set)\s+\w*(SECRET|API_KEY|TOKEN|PASSWORD|CREDENTIAL|PRIVATE_KEY)\w*\s*=", "secret env var assignment"),
    (r"\$env:\w*(SECRET|API_KEY|TOKEN|PASSWORD|CREDENTIAL|PRIVATE_KEY)\w*\s*=", "PS secret env var assignment"),
    # --- Production environment targeting ---
    (r"\b(production|prod|staging)\b.*\b(deploy|release|migrate|rollback|restart|stop|start)\b", "mutating op on prod/staging"),
    # --- System service / process management ---
    (r"\b(systemctl|service)\s+(start|stop|restart|enable|disable|mask)\b", "system service management"),
    (r"\bkill\s+-9\b|\bkillall\b|\bpkill\b", "force process kill"),
    (r"\bStop-Process\b.*-Force\b", "PS force stop process"),
    (r"\bStop-Service\b", "PS stop service"),
    # --- Privilege escalation ---
    (r"\bsudo\b", "sudo (privilege escalation)"),
    (r"\brunas\.exe\b|\bRunAs\b.*\/user:", "Windows RunAs"),
    (r"\bStart-Process\b.*-Verb\s+RunAs\b", "PS RunAs elevation"),
    # --- Scheduled task / persistence creation ---
    (r"\bcrontab\s+-[el]\b", "crontab edit/list"),
    (r"\bschtasks\s+/create\b", "Windows scheduled task create"),
    (r"\bNew-ScheduledTask\b|\bRegister-ScheduledTask\b", "PS scheduled task create"),
    # --- Dependency installation (changes environment) ---
    (r"\bpip\s+install\b(?!.*--dry-run)", "pip install"),
    (r"\bnpm\s+install\b(?!.*--dry-run)", "npm install"),
    (r"\byarn\s+add\b", "yarn add"),
    (r"\bpnpm\s+add\b", "pnpm add"),
    (r"\bcargo\s+add\b", "cargo add"),
    (r"\buv\s+(add|install)\b", "uv add/install"),
]

# ---------------------------------------------------------------------------
# Tier 1 — clearly read-only (silent, no reminder)
# ---------------------------------------------------------------------------
_TIER1_PATTERNS: list[str] = [
    # Git read-only
    r"^\s*git\s+(status|log|diff|show|stash\s+list|remote\s+-v|branch(-a)?|describe|shortlog|reflog|ls-files|ls-tree|blame|cat-file|rev-parse|rev-list|name-rev|for-each-ref|check-ignore)\b",
    r"^\s*git\s+(fetch|pull)\b",
    # Shell navigation / inspection
    r"^\s*(ls|dir|type|cat|head|tail|echo|printf|where|which|pwd|whoami|hostname|uname|date|cal|env|printenv|id)\b",
    r"^\s*(grep|rg|find|locate|ack|ag)\b",
    # Testing / static analysis
    r"^\s*(python|py)\s+.*\b(test|pytest|spec|lint|mypy|flake8|ruff|check|typecheck|type-check|typecheck)\b",
    r"^\s*pytest\b",
    r"^\s*(mypy|flake8|ruff|pylint|pyright|bandit|semgrep)\b",
    r"^\s*black\s+--check\b",
    r"^\s*isort\s+--check\b",
    r"^\s*(npm|yarn|pnpm)\s+(test|run\s+test|run\s+lint|run\s+check|run\s+typecheck|run\s+type-check|audit)\b",
    r"^\s*(cargo\s+test|cargo\s+check|cargo\s+clippy|go\s+test|go\s+vet|go\s+build)\b",
    # File metadata / hashing
    r"^\s*(wc|du|df|stat|file|md5sum|sha256sum|sha1sum|xxd|hexdump|strings)\b",
    # Python introspection / read-only project scripts
    r"^\s*python\s+-c\s+['\"]?import\b",
    r"^\s*(ast\.parse|python\s+-m\s+py_compile|python\s+-m\s+json\.tool)\b",
    r"^\s*python\s+.*\b(scan|report|summary|check|verify|validate|audit|inspect|analyze|analyse|rebuild|rebuild-ledger|scan-session|fetch-lego|fetch-polymarket)\b",
    # PowerShell read-only cmdlets
    r"^\s*(Get-Content|Get-ChildItem|Get-Item|Get-ItemProperty|Get-Location|Get-Process|Get-Service|Get-Variable|Get-Command|Get-Help|Get-Member|Get-History|Get-Date|Get-Host|Get-FileHash|Test-Path|Split-Path|Join-Path|Resolve-Path|Get-Acl|Get-EventLog|Get-WinEvent|Get-NetAdapter|Get-NetIPAddress|Get-Disk|Get-Volume)\b",
    r"^\s*(Write-Host|Write-Output|Write-Verbose|Write-Debug|Write-Information)\b",
    r"^\s*(Select-Object|Where-Object|ForEach-Object|Sort-Object|Group-Object|Measure-Object|Format-List|Format-Table|Format-Wide|ConvertTo-Json|ConvertFrom-Json|ConvertTo-Csv|Compare-Object|Tee-Object)\b",
    r"^\s*(Import-Module|Get-Module)\b",
    # Package managers — read-only queries
    r"^\s*(npm|yarn|pnpm)\s+(list|ls|info|view|outdated|audit)\b",
    r"^\s*(pip|pip3)\s+(list|show|check|freeze|inspect)\b",
    r"^\s*cargo\s+(search|info|tree|metadata)\b",
    # Docker — read-only
    r"^\s*docker\s+(ps|images|inspect|logs|stats|top|diff|history|search|info|version)\b",
    r"^\s*docker\s+compose\s+(ps|logs|config)\b",
]

# ---------------------------------------------------------------------------
# Sensitive file path fragments -> escalate Edit/Write to Tier 3
# ---------------------------------------------------------------------------
_SENSITIVE_PATH_FRAGMENTS: list[str] = [
    "/.env",
    "\\.env",
    "/secrets/",
    "\\secrets\\",
    "/credentials",
    "/.ssh/",
    "\\.ssh\\",
    ".claude/settings",
    "\\claude\\settings",
    ".aws/credentials",
    ".aws/config",
    "\\aws\\credentials",
    "/kubeconfig",
    "\\kubeconfig",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "id_rsa",
    "id_ed25519",
    "_rsa.pem",
    "private_key",
    "client_secret",
]

# ---------------------------------------------------------------------------
# Credential / secret content patterns (inspect new_string / content)
# ---------------------------------------------------------------------------
_SECRET_CONTENT_PATTERNS: list[str] = [
    r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|password|passwd|credential)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
    r"(?i)(AKIA|ASIA)[A-Z0-9]{16}",                                   # AWS access key ID
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",  # JWT token
    r"postgresql://[^:]+:[^@]+@",                                      # Postgres DSN with creds
    r"mysql://[^:]+:[^@]+@",                                           # MySQL DSN with creds
    r"mongodb(\+srv)?://[^:]+:[^@]+@",                                 # MongoDB DSN with creds
    r"redis://:[^@]+@",                                                # Redis DSN with auth
    r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",               # PEM private key
]


# ---------------------------------------------------------------------------
# Skill-level authorization overrides
# ---------------------------------------------------------------------------

_SKILL_PERMS_PATH = pathlib.Path.home() / ".claude" / "skill-permissions.json"


def _load_skill_authorizations() -> list[dict]:
    """Load per-skill pre-authorized action patterns from skill-permissions.json."""
    if not _SKILL_PERMS_PATH.exists():
        return []
    try:
        data = json.loads(_SKILL_PERMS_PATH.read_text(encoding="utf-8"))
        return data.get("authorizations", [])
    except Exception:
        return []


def _is_skill_authorized(cmd: str, authorizations: list[dict]) -> tuple[bool, str]:
    """
    Return (True, skill_name) if cmd matches any skill-level authorization,
    (False, '') otherwise.

    match_type values:
      "contains" (default) — pattern string is a substring of cmd (case-insensitive)
      "exact"              — cmd.strip() == pattern.strip()
      "regex"              — re.search(pattern, cmd, IGNORECASE)
    """
    for auth in authorizations:
        pattern = auth.get("pattern", "").strip()
        if not pattern:
            continue
        match_type = auth.get("match_type", "contains")
        matched = False
        if match_type == "exact":
            matched = cmd.strip().lower() == pattern.lower()
        elif match_type == "regex":
            matched = bool(re.search(pattern, cmd, re.IGNORECASE))
        else:  # "contains"
            matched = pattern.lower() in cmd.lower()
        if matched:
            return True, auth.get("skill", "unknown-skill")
    return False, ""


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------

def _classify_segment(cmd: str) -> tuple[int, str]:
    """Classify a single command segment (no chain operators)."""
    for pat, reason in _TIER4_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return 4, reason

    for pat, reason in _TIER3_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return 3, reason

    for pat in _TIER1_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return 1, "read-only"

    return 2, "local write"


def _classify_cmd(cmd: str) -> tuple[int, str]:
    """
    Classify a Bash/PowerShell command string.
    Splits && / ; / || chains and returns the highest tier across all segments.
    """
    segments = re.split(r"\s*(?:&&|;|\|\|)\s*", cmd)
    max_tier, max_reason = 1, "read-only"

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        tier, reason = _classify_segment(segment)
        if tier > max_tier:
            max_tier, max_reason = tier, reason
        if max_tier == 4:
            break

    return max_tier, max_reason


def _inspect_content(content: str) -> Optional[str]:
    """Scan Edit/Write content for credential patterns. Returns reason or None."""
    for pat in _SECRET_CONTENT_PATTERNS:
        if re.search(pat, content):
            return "content appears to contain a credential or secret"
    return None


def _classify_file_path(file_path: str) -> tuple[int, str]:
    """Classify an Edit/Write target file path."""
    path_norm = file_path.lower().replace("\\", "/")
    for frag in _SENSITIVE_PATH_FRAGMENTS:
        if frag.lower().replace("\\", "/") in path_norm:
            return 3, f"sensitive path fragment: {frag.strip('/\\')}"
    return 2, "file write"


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _emit_context(msg: str) -> None:
    payload = {
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": msg,
        }
    }
    print(json.dumps(payload))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    tool_input = (
        payload.get("tool_input")
        or payload.get("toolInput")
        or payload.get("input")
        or {}
    )

    # Read-only tools — never need the guard
    if tool_name in ("Read", "Glob", "Grep", "WebSearch", "WebFetch",
                     "ListMcpResourcesTool", "ReadMcpResourceTool", "ToolSearch"):
        return 0

    # -----------------------------------------------------------------------
    # Edit / Write — classify by file path + optionally inspect content
    # -----------------------------------------------------------------------
    if tool_name in ("Edit", "Write"):
        file_path = str(tool_input.get("file_path", "") or tool_input.get("path", ""))
        tier, reason = _classify_file_path(file_path)

        # Inspect content for secrets (Write = full content; Edit = new_string)
        content_to_check = str(
            tool_input.get("content", "")
            or tool_input.get("new_string", "")
        )
        if content_to_check:
            secret_reason = _inspect_content(content_to_check)
            if secret_reason and tier < 3:
                tier, reason = 3, secret_reason

        if tier == 2:
            _emit_context(
                f"[IAG T2] File write -> {file_path or 'unknown'}. "
                "Verify this is within the authorized task scope. "
                "If scope is ambiguous or this affects state outside the immediate task, "
                "STOP and invoke Skill(\"intent-alignment-guard\") before proceeding. "
                "This reminder does not substitute for the full skill."
            )
        else:
            _emit_context(
                f"[IAG T3] Sensitive path or credential write detected ({reason}) -> {file_path}. "
                "STOP — invoke Skill(\"intent-alignment-guard\") NOW. "
                "Run the full 6-step protocol and surface the 5-field action proposal "
                "to the user before this write executes. Ambiguity is not consent."
            )
        return 0

    # -----------------------------------------------------------------------
    # Bash / PowerShell — classify by command content with chain analysis
    # -----------------------------------------------------------------------
    if tool_name in ("Bash", "PowerShell"):
        cmd = str(tool_input.get("command", ""))

        # Check skill-level authorizations BEFORE tier sweep.
        # If the command matches an entry in skill-permissions.json, pass silently —
        # the user explicitly pre-authorized this action for that skill.
        _auths = _load_skill_authorizations()
        authorized, auth_skill = _is_skill_authorized(cmd, _auths)
        if authorized:
            return 0  # silent pass — covered by skill-level authorization

        tier, reason = _classify_cmd(cmd)

        if tier == 1:
            return 0  # silent

        if tier == 2:
            _emit_context(
                f"[IAG T2] {reason} — verify this is within the authorized task scope. "
                "If scope is ambiguous, STOP and invoke Skill(\"intent-alignment-guard\") "
                "before proceeding. This reminder does not substitute for the full skill."
            )
            return 0

        if tier == 3:
            _emit_context(
                f"[IAG T3] External or sensitive action detected ({reason}). "
                "STOP — invoke Skill(\"intent-alignment-guard\") NOW before this command executes. "
                "The hook reminder does not substitute for the full skill. "
                "Ambiguity is not consent."
            )
            return 0

        if tier == 4:
            print(
                f"[IAG] BLOCKED - Tier 4 destructive action: {reason}. "
                "This requires explicit written user authorization. "
                "Re-state what you are about to do and ask the user to confirm.",
                file=sys.stderr,
            )
            return 2

    # All other tools (Agent, Skill, etc.) — pass through
    return 0


if __name__ == "__main__":
    sys.exit(main())
