---
name: starter-help
description: Explain how to use this starter: what it creates, the workspace and harness concepts, which request or skill fits each task, and the generator commands behind them, tailored to the user's saved workspaces. Use when the user asks for help, a usage guide, what this repository or starter does, what they can ask for, or where to begin (for example "사용법 알려줘", "help", "뭐부터 하면 돼?", "이 저장소로 뭘 할 수 있어?").
---

# Help

Answer only what was asked, in the user's language. A general question gets the overview below; a question about one task gets that row and its next step.
Keep it short: tables and one-line answers, no internals the user did not ask about. Read nothing beyond step 1 unless the question needs it.

## 1. Current state

Run `python3 tool/starter.py workspace list` from this starter's root. Use it to end the answer with one concrete next step:

- No saved workspace: start with "create a repository" (`starter-new-repo`) or "bring in an existing one" (`starter-adopt-repo`).
- A workspace whose `managed` repositories exist: name them, and suggest onboarding one that is not onboarded yet (its `.ai/config.json` has `"onboarded": false`),
  or upgrading when the user asks about starter changes.
- `"ok": false`: say the list is unreadable and that every task still works when the user gives a path.

## 2. Overview

Present these three parts.

**What it is.** A generator for repositories that are developed with AI agents. Each repository gets the same working rules,
a verification CLI (`python3 tool/ai.py verify`) that a pre-commit hook runs before every commit, and a wiki. Architecture and tooling are chosen at onboarding, after an interview, not baked in.

**Two things it manages.**

| | What | Lives in |
| --- | --- | --- |
| Workspace | A folder that groups one product's repositories (`be`, `web`, `app`) with their roles and contracts | `workspace.json`, the workspace `AGENTS.md` |
| Harness | The starter files inside one repository: rules, skills, checks, wiki | that repository, recorded in `.ai/harness.json` |

A repository in a workspace is `managed` when it has the harness and `registered` when it is only listed.

**What to ask for.**

| Goal | Ask, for example | Skill |
| --- | --- | --- |
| Create new repositories | "Create be and web in ~/work/shop" | `starter-new-repo` |
| List an existing repository in a workspace | "Add the existing admin repository" | `starter-adopt-repo` |
| Add the harness to an existing repository | "Install the harness in admin" | `starter-install-harness` |
| Set up a repository's architecture and tooling | "Onboard be" | `starter-onboard-repo` |
| Bring starter changes into repositories | "Upgrade my workspace" | `starter-upgrade` |
| Record roles and contracts between repositories | "Record the API contract between be and app" | `starter-workspace` |
| Take a repository out of a workspace | "Remove admin from the workspace" | `starter-unregister-repo` |

## 3. Guarantees

Mention these when the user is about to run something, or asks whether it is safe:

- Nothing is committed or pushed unless the user asks.
- The generator writes only inside the workspace or repository it is given, never into this starter. Creating or installing never
  overwrites an existing file, and a failed check writes nothing.
- Existing agent instructions in a repository (`AGENTS.md`, `.cursorrules`, ...) are reported before an install, and merged only after approval.
- `upgrade` merges three ways and keeps the project's own edits; files it cannot merge are listed, not overwritten.

## 4. Commands, only when asked

The skills run these from this starter's root; show them only to a user who wants the command line. `python3 tool/starter.py help` prints the full reference.

| Area | Command |
| --- | --- |
| Both | `new --workspace PATH --name NAME [--role TEXT]`, `upgrade --workspace PATH [--name NAME] [--dry-run]` |
| Workspace | `adopt --workspace PATH --path REL [--install]`, `unregister --workspace PATH --name NAME`, `sync --workspace PATH`, `workspace list \| add \| remove` |
| Harness | `harness install \| upgrade \| status --repo PATH` |

For details beyond this, point to the matching section of `README.md` instead of reciting it.
