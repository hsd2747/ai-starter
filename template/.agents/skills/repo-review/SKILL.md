---
name: repo-review
description: Review diffs or pull requests for actionable defects, contract violations, regressions, security issues, and missing verification. Use when the user asks for code review, PR review, diff inspection, or risk assessment without implementation.
---

# Review

1. Read `AGENTS.md` and `REVIEW.md`.
2. Establish the intended result and the changed surface. If the change is L2 or L3, run `repo-wiki-query` unless the task already has its result, and use the returned rules and caveats as review evidence.
3. Trace affected consumers and failure states. Prioritize behavior, compatibility, the dependency rule, security, concurrency, lifecycle, and verification coverage.
4. Report only actionable findings caused or exposed by the change, each with severity, narrow location, impact, triggering conditions, and a safe correction direction.
5. Separate pre-existing issues from regressions. Do not raise findings for formatter-only concerns or subjective style.
6. If there are no findings, say so and list only material verification gaps or remaining uncertainty.

Review is read-only unless the user separately asks for fixes.
