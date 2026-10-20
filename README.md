# ai-starter

A generator for repositories that are developed together with AI coding agents. Each repository it creates gets the same working
rules, a verification CLI, and a wiki that accumulates knowledge task by task. Architecture and tooling are not baked in:
the first agent session in a new repository interviews you, researches current practice for its stack, and writes the result after you approve it.

Two things are managed separately:

- A **workspace** is a folder that groups the repositories of one product (for example `be`, `web`, `app`) and describes their roles
  in one `AGENTS.md`. Workspace commands change only the workspace's own root files.
- The **harness** is the set of starter files inside one repository. Harness commands work on that repository alone, whether or not a workspace lists it.

`new`, `adopt --install`, and `upgrade` combine both. The starter itself is never modified by the generator.

Requirements: git and Python 3.10 or newer.

## Create a repository

```bash
python3 tool/starter.py new --workspace ~/work/my-product --name be --role "Backend API"
python3 tool/starter.py new --workspace ~/work/my-product --name web --role "Web frontend" --remote git@example.com:team/web.git
```

The first call initializes the workspace. Each call copies `template/` into `<workspace>/<name>`, runs `git init` there,
records the starter version in `.ai/harness.json`, connects the pre-commit hook that runs `verify` before every commit,
and adds a row to the workspace table. Nothing is committed.
Then open an agent session **in the new repository** and ask it to onboard the project; harness details are in `template/.ai/README.md`.

## Manage a workspace

```bash
python3 tool/starter.py adopt --workspace ~/work/my-product --path admin --role "Legacy admin web"   # list an existing repository
python3 tool/starter.py adopt --workspace ~/work/my-product --path admin --install                   # list it and install the harness
python3 tool/starter.py unregister --workspace ~/work/my-product --name admin                        # take it out of the list
python3 tool/starter.py sync --workspace ~/work/my-product                                           # rewrite the table
```

`adopt` lists a folder that is already a git repository inside the workspace; without `--install` no file in it is touched.
`unregister` removes the entry and its table row; the folder and every file in it, an installed harness included, stay as they are.
Run `sync` after editing roles or remotes in `workspace.json`, or after installing the harness in a listed repository.

`workspace.json` holds names, paths, roles, and remotes only. The table's Harness column is read from each repository:
**managed** when it has `.ai/harness.json`, **registered** otherwise.

## Manage the harness in one repository

```bash
python3 tool/starter.py harness status  --repo ~/work/my-product/admin             # installed? which starter commit?
python3 tool/starter.py harness install --repo ~/work/my-product/admin             # copy the harness in
python3 tool/starter.py harness upgrade --repo ~/work/my-product/admin --dry-run   # plan an upgrade, then run it without --dry-run
```

The repository can be anywhere outside this starter; nothing outside it is written. `install` stops before it writes anything when
any harness file (`AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, ...) already exists; only `.gitignore` and `.gitattributes`
are merged by appending missing lines. `harness status` lists those files under `conflicts` before an install, and lists other agent
instructions the harness would leave in place (`.cursorrules`, `.github/copilot-instructions.md`, the repository's own `.claude/` entries, ...)
under `existingInstructions`; the `starter-install-harness` skill proposes how to merge each one before it installs.

After the files are in place, `install` (and `adopt --install`) runs the repository's `python3 tool/ai.py hooks install`, which points
`core.hooksPath` at `.githooks` so that every commit runs `verify`. When the repository already runs hooks from another tool (husky, lefthook,
pre-commit, or files in `.git/hooks`), it leaves them in effect and the report's `hooks.problem` says where to add the verify call.
This is the only change outside the files, and it touches only the repository's local git config; a failure there is a warning, not a rollback.
`core.hooksPath` does not travel with a clone, and `upgrade` never changes git config: run `hooks install` in each clone, as `doctor` reminds you.

## Bring starter changes into existing repositories

```bash
python3 tool/starter.py upgrade --workspace ~/work/my-product --dry-run   # plan for the workspace root and every managed repository
python3 tool/starter.py upgrade --workspace ~/work/my-product             # apply
python3 tool/starter.py upgrade --workspace ~/work/my-product --name be   # one listed repository only
python3 tool/starter.py harness upgrade --repo ~/work/solo                # a repository no workspace lists
```

Each target recorded the starter commit it came from (`.ai/harness.json`, or `workspace.json` for the workspace root). For every harness file,
`upgrade` merges three versions with `git merge-file`: that commit's template, the current template, and the file in the target.
Onboarding edits and starter edits on different lines both survive; the same lines changed on both sides leave conflict markers,
which `verify` then reports until they are resolved. Files the starter removed are listed, never deleted.

Three kinds of content are not merged line by line:

- **Marked blocks.** Text between `project:<name>` (or `workspace:<name>`) start and end markers belongs to the target: the repository map
  and rules in `AGENTS.md`, the commands in `.githooks/pre-commit`, the project section of `.gitignore`, and the contracts in the workspace `AGENTS.md`.
  The merge covers only the text around the blocks, and each block keeps the target's text.
- **JSON files** merge by key, and lists of plain values merge by item. Where both sides changed the same key, the target's value stays
  and the key is listed under `kept`. A `schemaVersion` raised by the starter needs a migration step in `MIGRATIONS` in `tool/ai_starter/merge.py`.
- **Seeds** (`wiki/index.md`, `wiki/log.md`) are replaced only while the target has not changed them, and are otherwise left alone.

The starter must be committed, and every file `upgrade` would write must be committed and unmodified in its target;
otherwise nothing is written anywhere. The result arrives as an ordinary uncommitted diff in each repository.

Every command writes its files to temporary files first and moves them into place only once all of them are ready, so a full disk
or a permission error leaves every target as it was. `new` builds the repository under a temporary name and renames it at the end.
In the rare case that moving in stops partway, the error lists the files already replaced and the ones that were not.

## Saved workspaces

`new`, `adopt`, `unregister`, `sync`, and `upgrade` save their workspace in `~/.claude/ai-starter/workspaces.json`, most recent first, so the skills below
know where your workspaces are without asking each time.

```bash
python3 tool/starter.py workspace list                     # saved workspaces with their repositories
python3 tool/starter.py workspace add --path ~/work/next    # save a path before its first repository
python3 tool/starter.py workspace remove --path ~/work/old  # forget an entry; the folder is untouched
```

## Through conversation

Open an agent session in this starter and ask in plain words. Claude Code picks the matching skill from `.claude/skills/`.
Each skill starts from the saved workspace list; when it is empty, the skill explains what a workspace is and asks for its path first.


| Skill | Ask for example | Does |
| --- | --- | --- |
| `starter-help` | "How do I use this?" | Explains the starter, what to ask for, and a next step from your saved workspaces |
| `starter-new-repo` | "Create be and web in ~/work/my-product" | Checks the starter commit, collects names and roles, runs `new` |
| `starter-onboard-repo` | "Onboard be" | Runs the repository's own `repo-onboard` under its `AGENTS.md`, from this session |
| `starter-adopt-repo` | "Add the existing admin repository" | Lists it with its role, optionally with the harness, runs `adopt` |
| `starter-install-harness` | "Install the harness in admin" | Checks `harness status` and the worktree, runs `harness install` |
| `starter-unregister-repo` | "Take admin out of my-product" | Shows what stays and which contracts name it, runs `unregister` |
| `starter-workspace` | "Record the contracts between be and app" | Edits roles and the contracts section, proposes per-repository rules |
| `starter-upgrade` | "Bring the latest starter into my-product" | Shows the dry run, runs `upgrade` or `harness upgrade`, helps resolve conflicts, runs `verify` |

Onboarding from this session does not load the repository's own hook and permission settings. For daily work, open a session in the repository itself.

## Workspace layout

```text
my-product/                  # its own git repository; tracks only the files below
├── AGENTS.md                # repository roles (generated table) and contracts between repositories
├── CLAUDE.md                # @AGENTS.md
├── workspace.json           # source of the repository list
├── .gitignore               # ignores every repository folder
├── .claude/settings.json    # guard hook for sessions opened at the workspace root
├── .ai/guard/               # copy of the guard the hook runs
├── be/                      # managed: has the harness
└── admin/                   # registered: role only
```

Every repository stays self-contained. CI and a teammate who clones one repository never see the workspace, so rules a repository
needs belong in its own `AGENTS.md`. Run checks from inside a repository: `cd be && python3 tool/ai.py verify`.

## Starter layout

| Path | Purpose |
| --- | --- |
| `template/` | Files copied into every new or adopted repository |
| `workspace-template/` | Files for a workspace root |
| `tool/starter.py` | The generator's entry point |
| `tool/ai_starter/` | The generator's code, one module per concern |
| `tool/schemas/` | Schemas of `workspace.json`, `.ai/harness.json`, and the saved workspace list, checked on every read and write |
| `tool/ai.py` | Guard hook for sessions in this starter |
| `tests/` | Generator tests |
| `.claude/skills/starter-*` | Conversational skills for the generator |

Maintenance rules for this starter are in `AGENTS.md`.

## Not decided yet

- TODO(owner): decide whether to add optional local search (for example qmd) once a project wiki grows past a few hundred pages; `index.md` and grep are enough until then.
