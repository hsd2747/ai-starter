# Architecture research guide

This guide holds no stack presets on purpose. Recommended layouts and tools change faster than a template is updated:
lint plugins get archived, official guides add or drop layers, and popular "standard" layouts turn out to be unofficial.
What does not change is below; everything else is looked up for the specific stack at onboarding time.

## Principles that do not age

1. **The dependency rule is the architecture.** Source dependencies point toward policy (domain rules) and away from details
   (frameworks, databases, UI, transport). Folder names are not the architecture; the allowed import directions are.
2. **Boundaries follow what changes together.** Prefer feature or domain modules at the top level and layer inside them only as much as needed.
   A top level of `domain/`, `data/`, `presentation/` says nothing about what the system does.
3. **Layers are earned.** Start with the fewest layers the project's domain complexity justifies. A use-case or domain layer, ports, and adapters
   are added when there is logic to protect, a dependency to replace, or a test seam to create; not because a diagram has four circles.
4. **Language-enforced boundaries beat conventions.** Modules, packages, crates, projects, targets, and visibility rules the compiler checks come first.
   Lint rules or architecture tests come second. A documented convention with no check comes last.
5. **Data crossing a boundary is plain.** Pass simple data structures across boundaries; do not leak framework or database types inward.
6. **Composition happens at the edge.** Wiring, configuration, and dependency injection live in the outermost entry point.
7. **Existing code is described before it is prescribed.** Record what is there as `current`; introduce targets as `on-touch` or `target` rules.

## Choosing a style

Use the interview answers as signals. These are tendencies, not presets; confirm each with current sources.

| Signals | Usually fits |
| --- | --- |
| Small, short-lived, mostly CRUD, one developer | Feature folders with thin internal structure; no separate domain layer |
| Rich business rules, long-lived, several developers | Clean or onion style inside feature modules |
| Many external systems that are swapped or faked in tests | Ports and adapters (hexagonal) at those boundaries |
| Many independent requests or commands, frequent feature additions | Vertical slices, refactoring toward shared domain code only when duplication appears |
| Large frontend with many contributors | A feature-sliced layering of app, pages, features, entities, shared (or the framework's current equivalent) |
| Library or SDK | Stable public API surface over internal modules; no application layering |
| Monorepo | Package or module boundaries first, then per-package structure |

## Research procedure

Run these searches for the concrete stack, replacing the placeholders. Run independent searches together.

1. **Official guidance**: `<framework> official architecture guide`, `<language> official project layout`, `<platform> app architecture recommendations`.
2. **Maintained reference projects**: `<framework> clean architecture template`, `<framework> example app official`.
   For each candidate repository, check whether it is archived, when it last changed, and whether its maintainers are the framework's authors.
3. **Boundary enforcement**: `<language> enforce import boundaries`, `<language> architecture test library`, `<build tool> module dependency rules`.
4. **Everyday toolchain**: `<language> formatter default <current year>`, `<language> linter recommended <current year>`, `<language> test runner`,
   `<framework> code generation`.
5. **Currency of every chosen tool**: `<tool> archived`, `<tool> deprecated`, `<tool> successor`, and its release notes for compatibility with the pinned language version.

Rank sources in this order: official documentation and maintainer repositories, then widely used and actively maintained projects,
then articles and posts. Prefer sources from the last two years; label anything older. When sources disagree, present both sides in the proposal instead of picking silently.

## Currency checks before proposing a tool

A tool goes into the checks in `.ai/config.json` only if all of these hold, or the proposal states which one fails and why it is still chosen:

- Not archived, and a release or meaningful commit within roughly the last 12 months.
- Compatible with the language and framework versions the project pins.
- Runs non-interactively with a non-zero exit code on failure, and has a check-only mode that does not rewrite files.
- License acceptable for the project.
- Installable from the ecosystem's standard registry by a known publisher.

Examples of drift observed when this guide was written (2026-10): a widely used Dart lint plugin framework was archived in favor of the
analyzer's official plugin system, and a popular .NET architecture-test library had gone two years without changes while a port of a Java
library stayed active. Expect similar drift for any stack.

## What research produces

- The proposal table described in the skill, with a source link per decision.
- One wiki `rule` leaf per architecture decision, citing `url:<link> (accessed YYYY-MM-DD)` sources and an adoption level.
- `.ai/config.json` entries for the toolchain, the boundary check, and the everyday checks.
- A short `setup` entry in `wiki/log.md` listing rejected options and why.

## Pitfalls

- Treating an unofficial community layout as a standard because it is popular.
- Copying a template's entire stack (database, queue, auth provider) when only its structure was wanted.
- Adding every layer on day one; empty layers become the default place for code that does not belong there.
- Choosing a boundary tool without checking that it still works with the pinned toolchain.
- Letting a boundary check fail every task in a legacy codebase; start with a baseline or warn-only mode.
