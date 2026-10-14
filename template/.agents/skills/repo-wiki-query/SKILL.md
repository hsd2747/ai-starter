---
name: repo-wiki-query
description: Query the project wiki for architecture, conventions, decisions, and implementation knowledge. Use for every L2 or L3 task before tracked writes or an L3 approval brief, and whenever a question or lower-risk change needs project-specific context; reads only what it needs and never modifies the wiki.
---

# Wiki query

1. Start at `wiki/index.md` and identify the smallest relevant category.
2. Read the category hub, then only the leaves needed. Do not preload the wiki. Use `grep -rl` over `wiki/` for terms the index does not surface.
3. Read the relevant `current` and `rule` leaves separately. Read notes only for historical or task-specific context. Follow sources only when a claim affects the decision.
4. Compare consequential claims with live code or configuration. A `current` mismatch is stale knowledge. A `rule` mismatch is an enforced violation, an on-touch legacy gap, or a target gap according to `adoption`; report it instead of silently choosing one.
5. For direct questions, answer naturally and cite repository-relative wiki paths. For L2 and L3 grounding, return only this structure, without creating a file:

   ```yaml
   current:
     - path: wiki/facts/<category>/<slug>.md
       why: <one line: the present state this task must respect>
   rules:
     - path: wiki/facts/<category>/<slug>.md
       why: <one line: why it applies to this task>
       adoption: <enforced | on-touch | target>
       constraints: [<up to three rules whose violation means rework>]
   notes:
     - path: wiki/notes/<slug>.md
       why: <one line: relevant precedent>
   caveats: [<stale pages, conflicts with live code, missing coverage>]
   ```

6. Omit empty entries inside `current`, `rules`, and `notes`, but always return all four top-level keys. Do not copy page bodies into the result.
7. Never edit pages, `wiki/index.md`, or `wiki/log.md`. Recording knowledge is `repo-wiki-write`'s job, after the task and after approval; report a gap as a caveat.
