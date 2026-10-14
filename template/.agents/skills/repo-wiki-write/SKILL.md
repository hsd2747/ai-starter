---
name: repo-wiki-write
description: Propose and write durable project knowledge into the wiki after a task, under the approval gate in AGENTS.md. Use when a completed change produced a rule that will change future decisions, or when the user asks to record something in the wiki; do not use for querying, and never write without approval.
---

# Wiki write

A healthy wiki holds a few dozen durable pages for a year of work. That ratio is the point: most tasks produce nothing durable.
Default to proposing nothing, and let a candidate earn its place against the tests below.

Read `wiki/README.md` for layout, kinds, and slug rules before writing. This skill decides **what** is worth storing; that file defines **where** and **how**.

## 1. Approval gate

- The user asking for a wiki update is itself the approval.
- Otherwise finish the main task first, then present candidates and wait. Never write to the wiki on your own initiative.
- Present each candidate as one line: target path, one-sentence rule or fact, why it will be needed again. If nothing passes section 2, say so and stop.
  "No durable knowledge this time" is the expected outcome, not a failure.

## 2. Candidate tests: all five must pass

Ask these about the explanation or rule itself, not about the task that produced it.

1. **Reuse.** Will someone apply it to a different feature within a few months? A rule that only fits the code you just touched fails.
2. **Non-obvious.** Would a competent developer reading the relevant code reach the same conclusion within five minutes? If yes, the code is the source.
3. **Decision-changing.** Does not knowing it produce work that gets reverted in review? "Useful to know" fails; "you will redo the work" passes.
4. **Durable.** Would one ordinary refactor delete it? A one-off observation belongs in `notes/`.
5. **Not covered.** Does an existing leaf already decide this? If so, **update that leaf instead of creating a new one.** Search first; a near-duplicate is worse than no page.

## 3. Reject on sight

- Directory trees, class lists, and inventories that one nearby file already shows.
- How a third-party package works. Its documentation is the source.
- What a bug was and how it was fixed. Git history is the source.
- Endpoint or field lists from an API specification. The specification is the source.
- Task narrative: what was tried, what failed, what the ticket asked for.
- Preferences with no failure mode behind them.
- Secrets, credentials, personal data, or raw payloads of any kind.

## 4. Placement

- Cross-cutting verified implementation truth: `wiki/facts/<category>/<slug>.md` with `kind: current`.
- Stable prescription: `wiki/facts/<category>/<slug>.md` with `kind: rule` and an explicit `adoption`.
- Observed once, ticket-specific, a decision record, or a handover: `wiki/notes/<slug>.md`.
- An exception or refinement to an existing rule: edit that leaf. Hubs carry links only.
- One leaf holds one decision. Aim for 30-60 lines; over 80 means it should be two pages.

## 5. Write

1. Frontmatter as defined in `wiki/README.md`, with absolute dates and real `sources`.
2. A rule starts with one bold `**Rule:**` line, then a table or checklist of scope and exceptions, then at most one concrete case.
   A current page states verified behavior without prescriptions and names the important code paths. Both end with a `## Related` line of wikilinks.
3. Write in the wiki language set in `.ai/config.json` and match neighboring pages.
4. The slug must be unique across the whole wiki.
5. A new facts page must be linked from at least one existing page (its hub or the closest related leaf) in the same edit.

## 6. Synchronize

Every write updates, in the same change: the page, one line in `wiki/index.md` under the right category, and a new dated entry at the bottom of `wiki/log.md`.
Never rewrite an existing log entry. Run `python3 tool/ai.py wiki lint` (or `verify`) before reporting.

## 7. Report

State what you wrote, what you updated instead of creating, and what you deliberately did not store. Rejected candidates are worth one line each; they show the filter ran.
