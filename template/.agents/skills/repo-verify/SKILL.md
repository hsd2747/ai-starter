---
name: repo-verify
description: Verify changes with checks proportional to their affected contracts and record truthful evidence. Use after code changes, when asked to test or validate work, when diagnosing verification failures, or before handoff and completion.
---

# Verify

1. Read the changed files and determine which contracts the change affects. For L2 and L3, reuse the task's `repo-wiki-query` result or run it, and include applicable rules in the verification scope.
2. Run `python3 tool/ai.py verify` for the current changes: everything that differs from the merge base with `git.baseBranch`, including committed work on the branch (the receipt's `baseRef` names it; `HEAD` means no base branch was found, so only uncommitted work was checked). Use `--all` only when the whole repository is the subject. `--dry-run` shows the selection without running it.
3. Every language-specific command comes from `checks` in `.ai/config.json`. When the default selection cannot prove the result, add `--check <id>` for a declared check (repeatable). If the needed check is not declared, propose adding it (an L2 change to the verification contract) instead of presenting an ad-hoc command as evidence. Write tests only under the rules in `AGENTS.md`.
4. Do not sequence code generation by hand. `generate`-stage checks run after `early` and before `late`. If `verification-subject-stable` fails after a generator ran, the committed generated code was stale: keep the regenerated output and run verify again rather than reverting it.
5. Read failures from the printed summary first, then from the log path in the receipt. Built-in checks:
   - `git-diff-check`: whitespace errors and conflict markers in changed and untracked files.
   - `secret-scan`: `.env` files, signing keys, and credential files that are tracked or not ignored, and high-confidence key patterns (including connection strings with a real password). Findings never show the value. A false positive on a line can be marked with `secret-scan: allow`; every suppressed hit is still listed under `warnings` for a reviewer. A real hit means the secret must be removed and rotated, not suppressed. The scan reads files, not git history.
   - `harness-config`: `.ai/config.json`, skill frontmatter, and `.claude/skills` adapters (`python3 tool/ai.py adapters sync` fixes missing links).
   - `json-syntax`, `doc-links`, `wiki-lint`, and `harness-test`.
6. Do not rerun unrelated expensive checks to produce more evidence. For L3, gather two independent kinds of evidence when feasible.
7. When subagents wrote parts of the change, verify the merged worktree once rather than per subagent.
8. Receipts are written to `.ai/runs/<id>/verification-<timestamp>.json` (`--id` defaults to `adhoc`). Before trusting a receipt someone else produced, confirm its scope, base, HEAD, worktree digest, and file list still match the repository, and compare its `toolchain`. Preserve failed evidence; a later run creates a new receipt.
9. Report each check as pass, fail, or skipped, with the reason for skips and whether failures predate the task.
10. A commit that the pre-commit hook stopped left its receipt in `.ai/runs/pre-commit/`. Fix the failure and commit again; never bypass the hook.
    A pre-existing failure that blocks the commit is reported to the user, who decides how to proceed.

Verification never authorizes deploys, external writes, production data changes, deletion, or cost-incurring actions.
