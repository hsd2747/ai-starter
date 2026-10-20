# Starter maintenance

This repository is ai-starter, a generator. It is never onboarded and holds no product code.

## Layout

- `template/`: everything copied into a new or adopted repository. Its `AGENTS.md`, skills, and `.claude/` are the policy of
  **generated** repositories. They do not govern work on this starter, even when a tool loads them while you edit files under
  `template/` (for example the `template:repo-*` skills or the onboarding gate in `template/AGENTS.md`).
- `workspace-template/`: files for a workspace root: `AGENTS.md` with a generated repository table, `CLAUDE.md`, a whitelist `.gitignore`, and the guard hook settings.
- `tool/starter.py`: the generator's entry point. Workspace commands (`adopt`, `unregister`, `sync`, `workspace`) change only a workspace's
  root files; harness commands (`harness install`, `harness upgrade`, `harness status`) work on one repository, listed in a workspace or not;
  `new`, `adopt --install`, and `upgrade` combine both. Python 3.10+, standard library only.
- `tool/ai_starter/`: the generator's code. `cli.py` parses commands and runs all of them except the upgrades in `upgrade.py`; `workspace.py`, `install.py`,
  and `registry.py` write workspaces, harness copies, and the saved list; `policy.py` decides how each harness file is treated and
  `merge.py` merges one file by that policy; `manifests.py` validates state files;
  `files.py`, `gitutil.py`, and `paths.py` hold the shared helpers. Read `paths.STARTER`, `paths.TEMPLATE`, and `paths.WORKSPACE_TEMPLATE`
  as attributes, never import them by name: tests point them at a throwaway copy of the starter.
- `tool/schemas/`: schemas of the files the generator keeps state in (`workspace.json`, `.ai/harness.json`, the saved workspace list).
  They are checked with `template/tool/ai_harness/schema.py`, so they use only the keywords it supports.
- `tool/ai.py`: the guard hook entry for sessions in this starter; it delegates to `template/tool/ai_harness/guard.py`.
- `tests/`: generator tests, one file per command (`test_new.py`, `test_upgrade.py`, ...). `support.py` holds the shared helpers and
  the two base cases: `WorkspaceCase` (a temporary workspace) and `UpgradeCase` (a throwaway starter copy whose template can change).
  Test files import the generator through `support`, which puts `tool/` on the path. `test_merge.py` tests policies and merges
  directly, without git repositories; cover a new merge rule there first.
- `.claude/skills/starter-*`: conversational wrappers around the generator (workspace: `starter-workspace`, `starter-adopt-repo`, `starter-unregister-repo`;
  harness: `starter-install-harness`, `starter-upgrade`, `starter-onboard-repo`; both: `starter-new-repo`; usage guide: `starter-help`). When one of them works inside a generated repository, that repository's `AGENTS.md` rules there.

## Rules

- `template/.ai/config.json` stays un-onboarded: `"onboarded": false`, empty project fields, no toolchain, no checks.
  Nothing project-specific or language-specific goes into `template/`.
- A change under `template/` or `workspace-template/` reaches every repository created afterwards. Before writing one,
  state in one line what generated repositories will see differently, then proceed.
- The generator writes only inside the workspace or repository it is given, plus the saved workspace list `~/.claude/ai-starter/workspaces.json`
  that the starter skills read. It never writes into this starter, never overwrites an existing file, and validates everything before
  its first write. `tests/` pins these rules and redirects the list with `AI_STARTER_REGISTRY`; keep them passing.
- Every file the generator writes goes through `files.Staging` (or `files.write_atomic` for a single file), never through a direct write,
  so that a failure leaves its targets as they were. Writes that belong together, such as the files of one command, share one `Staging`.
- Every read and write of `workspace.json`, `.ai/harness.json`, and the saved workspace list goes through the schemas in `tool/schemas/`.
  A field added to one of these files is added to its schema in the same change; files that existing workspaces already hold must stay valid.
- `upgrade` and `harness upgrade` are the only commands that change files the starter installed earlier: only those files, only when git shows every file
  they would write as committed and unmodified, and only by a 3-way merge against the recorded starter commit. They never delete a file.
  That recorded commit must stay in this starter's history, so never rewrite or force-push commits that repositories were created from.
- Content that a repository or workspace fills in after install goes between `project:<name>` or `workspace:<name>` start and end markers
  in `template/` and `workspace-template/`, so that `upgrade` keeps it. Never rename or remove a block that onboarding fills:
  `upgrade` skips a file whose filled block the starter no longer has. A template change that raises a JSON `schemaVersion` adds
  the migration steps to `MIGRATIONS` in `tool/ai_starter/merge.py` in the same commit.
- A harness file that needs its own handling in `upgrade` gets it through `policy_for` in `tool/ai_starter/policy.py` and, for a new
  kind of merge, a `Policy` member that `merge_file` runs. Never add a path-specific branch to `upgrade.py` or `install.py`.
- Whether a repository has the harness is decided by its `.ai/harness.json` alone; `workspace.json` never records it. Generated repositories record the starter commit there. Commit starter changes before creating repositories that will be kept.
- Commit and push only when the user asks. Never hardcode secrets, tokens, or connection strings.

## Verification

```bash
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s template/tool/tests -t template/tool -q
```

This root has no `verify`. For an end-to-end check, create a workspace in a temporary folder with `python3 tool/starter.py new`
and run `python3 tool/ai.py verify --all` inside the generated repository. Report which of these ran and their results.
