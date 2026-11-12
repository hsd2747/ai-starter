---
name: workspace-rules
description: Change this workspace's shared rules through conversation: rules for every team in the `workspace:rules` block of AGENTS.md, one team's rules in .ai/teams/<team>.md, adding a team, the contracts between repositories, and this workspace's onboarding steps. Use when someone asks to add, change, or remove a workspace or team rule, to add a team, or to record who owns an API or another contract between repositories (for example "우리 팀 규칙에 추가해줘", "pd팀 규칙 바꿔줘", "qa 팀 추가해줘", "be랑 app 사이 계약 정리해줘").
---

# Workspace rules

Talk in the user's language and run everything from the workspace root. Shared rules reach every member's sessions here, so propose each change
as text and write it only after the user approves it. Never write one person's values, such as names, account IDs, or personal paths, into a shared file;
they belong in that person's `CLAUDE.local.md` or in a lookup at run time.

## Where a rule goes

- **One team:** `.ai/teams/<team>.md`.
- **Every team, needed by most sessions:** between the `workspace:rules` markers of `AGENTS.md`. Never edit the sections around the markers;
  they come from ai-starter and change only through its upgrade.
- **A procedure only some tasks need:** a `.ai/<topic>.md` file with one line in the `workspace:rules` block saying when to read it, or a workspace skill.
- **One line in a shared file that only some teams follow:** a team mark such as "(dev)".
- `AGENTS.md` stays under 200 lines, because every session here loads it whole; `python3 .ai/workspace.py check` warns past the limit.
- Sessions opened inside a repository never load these rules. A rule a repository must obey has to live in that repository too:
  propose it there, and change it as work in that repository, under its own `AGENTS.md` and the user's team rules.

## A new team

Run `python3 .ai/workspace.py team add <name>`, which adds the team to `teams` in `workspace.json` and creates `.ai/teams/<name>.md`.
Ask for the team's first rules and write them in that file after approval. Members record the team with `python3 .ai/workspace.py local --team <name>`.

## Contracts between repositories

1. Read the repository table and, for each repository involved, its `AGENTS.md` or README. Look read-only for contract artifacts: API specs
   (`openapi.*`, `swagger.*`, `*.graphql`, `*.proto`), shared schema or type packages, generated clients, and environment variable names that point
   at another repository. Read variable names from `.env.example` only; never open `.env` files.
2. Ask only what the code did not answer: owner, consumers, source of truth, compatibility policy, and who must hear about a breaking change.
3. Propose one line per contract: `<owner> owns <contract>; source of truth: <path or URL>; consumers: <repos>; changes: <policy>`.
   After approval, replace only the text between the `workspace:contracts` markers.

## Onboarding steps

Steps only this workspace needs, such as connectors, accounts, and whom to ask for access, go between the `workspace:setup` markers of `README.md`
and the `workspace:onboarding` markers of `.agents/skills/workspace-onboard/SKILL.md`, the same steps in both.

## Finish

Run `python3 .ai/workspace.py check` and relay its problems and warnings. Show `git status --short` and a short summary of the change.
Commit only when the user asks.
