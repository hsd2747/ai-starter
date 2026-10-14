---
name: repo-change
description: Implement or modify code under the repository risk policy. Use for bug fixes, features, UI changes, API integration, routing, shared state, refactoring, and other requested writes; do not use for review-only or wiki-query-only requests.
---

# Change

1. Read `AGENTS.md` and classify risk before writing. Follow its L2 notice and L3 approval gate exactly. If `.ai/config.json` is not onboarded, run `repo-onboard` first.
2. If the request carries a ticket key matching `git.ticketKeyPattern`, follow the ticket-branch rule in `AGENTS.md`; the cases are in [references/ticket-branch.md](references/ticket-branch.md).
3. If `.ai/runs/<id>/handoff.md` exists for this work, read it and continue from its next actions.
4. For L2 and L3, run `repo-wiki-query` before the first tracked write unless its result already exists in the current task. Combine its current state, rules, notes, and caveats with the request, external contracts, and live code. For L0 and L1, query only when project knowledge is needed.
5. For L3, present the approval brief from `AGENTS.md` in the conversation and wait. Ask only for missing information that would materially change the result; record safe, reversible assumptions instead.
6. Implement the smallest complete change. Preserve the dependency rule and public contracts; do not mix unrelated cleanup into the task.
   Delegate writes to subagents only under the conditions in `AGENTS.md`, and settle every judgement in their prompts.
7. If the task grows into L2, announce the promotion before the next write. If it reaches L3, stop writing and present the approval brief.
8. Run `python3 tool/ai.py verify` (or `repo-verify` when something fails). Use `--all` only for an intentionally repository-wide subject, and `--check <id>` when a declared check must run although no changed file selects it.
9. Report with the completion format in `AGENTS.md`. Distinguish passing, failing, skipped, and pre-existing failures.
   If the work is unfinished and someone else continues, write the handoff note described in `AGENTS.md`.
10. Then judge whether the task produced knowledge worth keeping, using the candidate tests in `repo-wiki-write`. Most tasks produce none, and saying so is a complete answer. Never write to the wiki before approval.
