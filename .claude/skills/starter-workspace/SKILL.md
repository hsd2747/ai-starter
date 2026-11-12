---
name: starter-workspace
description: Maintain a workspace's root files through conversation: repository roles and remotes in workspace.json and the generated table, the contracts between repositories in the workspace AGENTS.md, the workspace's own commit, and sharing it with the team or cloning a teammate's workspace with workspace clone. Use when the user asks to record or update contracts, ownership, or roles between repositories such as be, web, and app, to change a repository's role, to tidy up or commit a workspace, or to share a workspace or set up a teammate's one locally (for example "팀원 워크스페이스 받아줘", "워크스페이스 팀이랑 공유하고 싶어").
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

## Sharing

The workspace repository works like a manifest: teammates clone it and then every listed repository from its `remote`.

- **Share.** Show which entries in `workspace.json` have no `remote` (`sync` warns about them). Ask for each URL, never one with a token or password in it,
  edit the entries, and run `sync`. Adding a remote to the workspace repository and pushing it are outward-facing: do them only when the user asks,
  after showing the remote URL and the files that would be pushed (`git -C <workspace> ls-files`).
- **Separate personal values before sharing.** Read the tracked files (`git -C <workspace> ls-files`, skipping `.ai/guard/`) and list what belongs to one person:
  names, account IDs, personal paths, and preferences worded as one user's standing request. Ask whether each is personal or a team rule; mask the values in the
  list you show. A personal value that a tool can look up at run time (for example the current Jira user) becomes a lookup; the rest moves to that person's
  `CLAUDE.local.md`. A team rule that only some teams follow gets a team mark such as "(dev)". Record the team names in `workspace.json` as `teams`,
  then run `python3 <workspace>/.ai/workspace.py local --team <team>` for the user and `check`. Git history keeps removed values; say so, and rewrite history only if the user asks.
- **Clone a teammate's workspace.** Ask for the workspace repository URL, a local path, and the user's team, then run
  `python3 tool/starter.py workspace clone --path <path> --url <url> --team <team>` from this starter's root. For a workspace that is already there, for example after a pull
  that added a repository, omit `--url`; `--name <repo>` limits it to some repositories. Report `cloned`, `present`, `skipped`, and `failed` with their reasons, and warnings.
  A clone that fails on authentication means the user's git cannot reach that remote yet; suggest they check their access with `! git ls-remote <remote>`, never a URL with a token.
- Teammates do not need this starter: a workspace carries `.ai/workspace.py`, so `git clone <url> <folder>` and `python3 .ai/workspace.py clone` inside it do the same.
  A workspace made before that file existed gets it with `upgrade --workspace <path> --root-only` (`starter-upgrade`); commit and push it before teammates rely on it.
- Each cloned repository still needs its own local setup, such as dependencies and environment files made from their examples; point to its README instead of doing it unasked.

## Commit

The workspace is its own git repository and tracks only its root files; repository folders are ignored and committed in their own repositories.
Show `git -C <workspace> status --short` and a short diff summary. Commit only when the user asks.
