# Review playbook

A review checks whether the diff produced the intended result safely. Real defects and contract violations come before style preferences.

## Order

1. Read the user's request, the PR description, and any handoff note for the intended scope and settled decisions.
2. Follow the changed user flows and data flows; check consumers, failure states, and backward compatibility.
3. Check the related tests and verification receipts. Do not trust a passing record alone: confirm that its base, HEAD, worktree digest, and file list match the change under review.
4. Report findings in priority order, each with the triggering condition, impact, a safe correction direction, and the narrowest code location.

## Required perspectives

- Architecture: does the change respect the dependency rule in `AGENTS.md` and the architecture `rule` pages in the wiki?
- Contracts and serialization: missing or renamed fields, nullability, enums, mappers, pagination, error responses, existing consumers.
- State and UI (when the project has one): loading, empty, error, retry, duplicate actions, updates after disposal, accessibility state.
- Entry points: routes, commands, endpoints, arguments, guards, and deep links change only as intended.
- Security: credentials, tokens, and personal data stay out of logs, analytics, URLs, and plaintext storage.
- Concurrency and resources: cancellation, races, duplicate requests, exception translation, and cleanup are safe.
- Verification: the consumers of every changed contract and the regression surface were actually checked.

## Finding criteria

- Raise only problems with an observable effect on behavior or a contract.
- Do not state an uncertain possibility as fact; say what evidence would confirm it.
- Separate pre-existing problems from those this change introduced.
- A missing comment is not a finding. A comment that contradicts the code or is no longer true is.
- Newly added commented-out code and TODOs without a removal condition are findings.
- If you find nothing, say so, and list only checks you could not run and remaining uncertainty.
