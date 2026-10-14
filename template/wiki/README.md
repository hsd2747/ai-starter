# Wiki format

This directory is the project's durable knowledge. It does not depend on any AI tool or plugin; plain file reads and `grep` are enough.
This file defines **where** and **how** pages are written. **What** is worth writing is decided by
[.agents/skills/repo-wiki-write/SKILL.md](../.agents/skills/repo-wiki-write/SKILL.md). `python3 tool/ai.py wiki lint` enforces the structural rules below.

## Layout

- `facts/<category>/<slug>.md`: present state, target rules, and hubs, filed by the code area they concern.
- `notes/<slug>.md`: task records, decision records, comparisons, deferred ideas. Append-friendly.
- `index.md`: catalog of every page. `## Facts` has one `###` section per category with `Current`, `Rules`, and `Hubs` groups; `## Notes` is separate.
- `log.md`: append-only history of wiki writes, oldest first. After branches merge, an older entry may sit below a newer one; lint only warns.

## Knowledge kinds

Every facts page declares exactly one `kind`. When present state and target differ on the same topic, write two leaves and link them.

| kind | Meaning | Extra frontmatter | Body |
| --- | --- | --- | --- |
| `current` | Structure or behavior verified in code or configuration | `verified: YYYY-MM-DD` | Observation only. Instructions and targets go into a `rule`. |
| `rule` | Approved target contract for new work and reviews | `adoption: enforced \| on-touch \| target` | Rule, scope, exceptions, failure conditions. Cite current code only as short evidence. |
| `hub` | Entry point for a large topic | none | Neutral overview and links to `current` and `rule` leaves. No standalone rules. |

`adoption` means:

- `enforced`: any mismatch in scope is a defect now.
- `on-touch`: existing mismatches are tolerated, but new code and code being modified must follow the rule.
- `target`: an approved destination; a mismatch alone never widens a task's scope.

Notes are never the source of a current contract. Link a note from a rule or current page when its history matters,
but keep the present judgement complete in the rule or current page itself.

## Categories

The only filing axis is **which code area you are touching when you need the page**. Kind is expressed by `kind`, not by folder.
Onboarding creates the first categories from the project's real code areas (for example `architecture/`, `api/`, `persistence/`, `ui/`, `build/`).

- No catch-all folder. A rule that looks global (formatting, naming) still goes to the area it is applied in.
- When three or more pages fit no existing category, create a new one.
- `architecture/` holds layout, module and package boundaries, the dependency rule, and dependency policy.

## Pages

- **One page is one independently consumable unit with one kind.** Split when an agent would need part of it alone, or when present state and target are mixed.
- **Leaves aim for 30-60 lines.** Over 80 lines means split (lint warns).
- **Large topics use a hub plus leaves.** A hub holds an overview and links; new rules become new leaves with one link line added to the hub.
- **No long code samples.** At most one good/bad pair of up to 15 lines; otherwise point at real code with `Code: <path>`.

## Frontmatter

```yaml
---
kind: rule                # facts only: current | rule | hub
layer: facts              # facts | notes, matching the folder
adoption: on-touch        # rule only
verified: 2026-01-31      # current only
tags: [architecture]
sources:
  - code:src/app/main.ts
  - url:https://example.org/guide (accessed 2026-01-31)
  - ticket:ABC-123
  - manual:2026-01-31
created: 2026-01-31
updated: 2026-01-31
---
```

- Dates are absolute `YYYY-MM-DD`.
- Facts pages need at least one source. `sources` cite where the content came from; never a prompt, a raw payload, a secret, or personal data.
- Use block lists (`- item`) for values that contain commas.

## Body

- A rule starts with one bold `**Rule:**` line, then a scope and exceptions table or checklist, then at most one concrete case.
- A current page states verified behavior and the important code paths.
- Both end with `## Related` followed by wikilinks.

## Links and slugs

- Link pages with `[[slug]]`: the file name without folder or extension. `[[slug|label]]` and `[[slug#heading]]` also work.
- Slugs are unique across the whole wiki, regardless of folder. Facts slugs are lowercase kebab-case.
- Every page is listed in `index.md`. A new facts page is linked from at least one other page, usually its hub.
- Dangling wikilinks fail lint.

## Querying

- Start from the relevant category in `index.md` and read only the hubs and leaves you need. Never preload the wiki.
- Read `current` and `rule` pages separately; read notes only when history matters to the decision.
- A `current` page that disagrees with live code is stale. A `rule` mismatch is judged by its adoption: violation, legacy gap, or planned gap.
- Querying never edits the wiki.

## Editing

- When the user asks for a wiki change, it is approved. Otherwise propose candidates and wait (see `AGENTS.md`).
- Every write updates the page, `index.md`, and `log.md` in the same change. `.gitattributes` merges `index.md` and `log.md` with `merge=union`,
  so parallel branches keep both sides; after a merge, check `index.md` for a category heading that appears twice.
- When a change conflicts with a `current` page, check live code and update the page. When it conflicts with a `rule`, judge it by adoption; never let both claims stand silently.
