# Onboarding interview

Ask only what inspection could not answer. Group questions into at most three rounds of up to four, offer a recommended
default for each, and explain in one clause why the answer matters. Skip a question when an earlier answer makes it irrelevant.

## Round 1: what is being built

| Question | Why it matters | Default when unsure |
| --- | --- | --- |
| Project name and one-sentence purpose | Fills `.ai/config.json` and the wiki index heading | Directory name |
| Language, runtime, and framework | Drives every research query | Detected manifest |
| Project type: backend API, web frontend, mobile app, desktop app, CLI, library/SDK, worker/batch, monorepo of several | Libraries get a public/internal split instead of application layers; frontends and backends follow different guidance | Detected from dependencies |
| New project or existing code | Existing code is documented as `current` and never restructured during onboarding | Detected from the tree |

## Round 2: how much structure it deserves

| Question | Why it matters | Default when unsure |
| --- | --- | --- |
| Expected lifespan and scale: prototype, product, long-lived system | Short-lived or small projects start simple; heavy layering is a cost | Product |
| Domain complexity: mostly CRUD, or rules and calculations | Decides whether a domain/use-case layer exists at all | Add it later when needed |
| External integrations that may be replaced or faked in tests (databases, third-party APIs, messaging) | Decides whether ports and adapters are worth their indirection | Adapters only at real boundaries |
| Team size and familiarity with the chosen style | Unfamiliar styles need stricter enforcement or a simpler choice | Simpler choice |

## Round 3: how it is worked on

| Question | Why it matters | Default when unsure |
| --- | --- | --- |
| Top-level split: by feature, by layer, or hybrid | Features at the top with layers inside is the common current default | Feature-first |
| Boundary enforcement: language modules only, lint/architecture tests, or warn-only at first | Sets the boundary check's `required` flag and baseline | Enforced for new code, warn for legacy |
| Issue tracker key format and base branch | Fills `git.ticketKeyPattern` and `git.baseBranch` | No ticket keys, `main` |
| Wiki language | Pages are written in this language from now on | Same as these docs |

Record the answers as short lines; they become the `decisions` of the setup entry in `wiki/log.md` and the rationale in each architecture rule page.
