---
name: starter-workspace
description: Maintain a workspace's root files through conversation: repository roles in workspace.json and the generated table, the contracts between repositories in the workspace AGENTS.md, and the workspace's own commit. Use when the user asks to record or update contracts, ownership, or roles between repositories such as be, web, and app, to change a repository's role, or to tidy up or commit a workspace.
---

# Workspace upkeep

The workspace `AGENTS.md` is read only by sessions opened at the workspace root. CI and a teammate who clones a single repository never see it.

First choose the workspace with [choose-workspace.md](references/choose-workspace.md). The saved list itself is managed with
`python3 tool/starter.py workspace list | add --path <path> | remove --path <path>`; `remove` only forgets the entry.

## Roles

- Roles and remotes live in `workspace.json`; whether a repository has the harness does not, because the table reads it from each repository's `.ai/harness.json`.
  Edit the entry in `workspace.json`, then run `python3 tool/starter.py sync --workspace <path>` from this starter's root to rewrite the table.
  Never edit between the `workspace:repos` markers by hand.
- Turning a registered repository into a managed one goes through `starter-install-harness`, then `sync`, not through an edit.
- Taking a repository out of the workspace goes through `starter-unregister-repo`, not through an edit. It only unlists the repository; never delete its folder.

## Contracts

1. Read the workspace `AGENTS.md` and `workspace.json`. For each managed repository, read the repository map in its `AGENTS.md` and its `wiki/index.md`,
   then only the pages about interfaces. For a registered repository, read its README.
2. Look read-only for contract artifacts: API specs (`openapi.*`, `swagger.*`, `*.graphql`, `*.proto`), shared schema or type packages,
   generated clients, auth configuration, and environment variable names that point at another repository. Read variable names from `.env.example` only; never open `.env` files.
3. Ask only what the code did not answer: owner, consumers, source of truth, compatibility policy, and who must hear about a breaking change.
4. Propose the new text of the "Contracts between repositories" section, one line per contract:
   `<owner> owns <contract>; source of truth: <path or URL>; consumers: <repos>; changes: <policy>`. Wait for approval, then replace only the text between the `workspace:contracts` markers.
5. A rule that a repository must obey also has to live in that repository. For each affected managed repository, propose a candidate:
   a wiki `rule` page following its `wiki/README.md`, or a line between the `project:rules` markers of its `AGENTS.md` (L2 there). Write it only after approval, under that repository's `AGENTS.md`
   and its `repo-wiki-write` skill, then run `cd <repo> && python3 tool/ai.py verify`. A registered repository gets no harness file; mention the gap instead.

## Commit

The workspace is its own git repository and tracks only its root files; repository folders are ignored and committed in their own repositories.
Show `git -C <workspace> status --short` and a short diff summary. Commit only when the user asks.
