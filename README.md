# ai-starter

A generator for repositories that are developed together with AI coding agents. Each repository it creates gets the same working
rules, a verification CLI, and a wiki that accumulates knowledge task by task. Architecture and tooling are not baked in:
the first agent session in a new repository interviews you, researches current practice for its stack, and writes the result after you approve it.

Repositories live in a **workspace**: a folder that groups the repositories of one product (for example `be`, `web`, `app`)
and describes their roles in one `AGENTS.md`. The starter itself is never modified by the generator.

Requirements: git and Python 3.10 or newer.

## Create a repository

```bash
python3 tool/starter.py new --workspace ~/work/my-product --name be --role "Backend API"
python3 tool/starter.py new --workspace ~/work/my-product --name web --role "Web frontend" --remote git@example.com:team/web.git
```

The first call initializes the workspace. Each call copies `template/` into `<workspace>/<name>`, runs `git init` there,
records the starter version in `.ai/harness.json`, and adds a row to the workspace table. Nothing is committed.
Then open an agent session **in the new repository** and ask it to onboard the project; harness details are in `template/.ai/README.md`.

## Bring in a repository that was not created here

```bash
python3 tool/starter.py adopt --workspace ~/work/my-product --path admin --role "Legacy admin web"
python3 tool/starter.py adopt --workspace ~/work/my-product --path admin --install
```

Without `--install` the repository is only **registered**: listed with its role, and no file in it is touched.
With `--install` the harness is copied in. Any existing harness file (`AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, ...)
stops the command before it writes anything; only `.gitignore` and `.gitattributes` are merged by appending missing lines.
The folder must already be a git repository inside the workspace.
A repository registered without `--install` can get the harness later with the second command; its role is kept.

After editing roles or remotes in `workspace.json`, rewrite the table in the workspace `AGENTS.md`:

```bash
python3 tool/starter.py sync --workspace ~/work/my-product
```

## Through conversation

Open an agent session in this starter and ask in plain words. Claude Code picks the matching skill from `.claude/skills/`:

| Skill | Ask for example | Does |
| --- | --- | --- |
| `starter-new-repo` | "Create be and web in ~/work/my-product" | Checks the starter commit, collects names and roles, runs `new` |
| `starter-onboard-repo` | "Onboard be" | Runs the repository's own `repo-onboard` under its `AGENTS.md`, from this session |
| `starter-adopt-repo` | "Add the existing admin repository" | Chooses register or install, runs `adopt` |
| `starter-workspace` | "Record the contracts between be and app" | Edits roles and the contracts section, proposes per-repository rules |

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
| `tool/starter.py` | The generator |
| `tool/ai.py` | Guard hook for sessions in this starter |
| `tests/` | Generator tests |
| `.claude/skills/starter-*` | Conversational skills for the generator |

Maintenance rules for this starter are in `AGENTS.md`.

## Not decided yet

- TODO(owner): an `upgrade` command that brings starter changes into existing repositories. `.ai/harness.json` already records
  the starter commit and a hash per installed file, so an upgrade can tell files a project changed from files the starter changed.
- TODO(owner): decide whether to add optional local search (for example qmd) once a project wiki grows past a few hundred pages; `index.md` and grep are enough until then.
