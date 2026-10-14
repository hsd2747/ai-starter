# Onboarding an existing codebase

Onboarding documents and guards an existing codebase; it does not restructure it.

- **Describe first.** Before proposing anything, map the real top-level structure, module or package boundaries, entry points,
  and the dependency directions the imports actually show. These become `current` pages with `verified` dates.
- **Prescribe gently.** A target architecture that the code does not follow yet becomes `rule` pages with `adoption: on-touch`
  (new and modified code must follow it) or `adoption: target` (approved destination, no work scheduled). Use `enforced` only for rules the code already satisfies.
- **No moves during onboarding.** Do not rename, move, or reformat source files. Propose restructuring as a separate task with its own risk level.
- **Reuse existing tooling.** If the project already has a formatter, linter, or test command, wire those into the checks in `.ai/config.json` as they are,
  even if research suggests a newer tool. Record the newer option as a refresh candidate instead.
- **Baseline legacy violations.** A new boundary or lint check runs with `required: false`, or with the tool's own baseline or freeze feature,
  until the user decides to enforce it. Say which in the proposal.
- **Respect existing agent files.** If the repository already has `AGENTS.md`, `CLAUDE.md`, or tool rule files of its own, stop and ask how to merge them before writing.
- **Existing CI stays.** Add the verify workflow next to existing pipelines; do not replace them.
