# Harness

This repository was created by ai-starter. It carries the same working rules, a verification CLI, and a wiki that accumulates
knowledge task by task. Architecture and tooling are not baked in: the first agent session interviews you, researches current
practice for your stack on the web, and writes the result into the harness after you approve it.

## What is inside

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Single policy source: risk levels L0-L3, controls, routing, verification, tests, comments, security, completion reports |
| `CLAUDE.md` | `@AGENTS.md` import for Claude Code |
| `REVIEW.md` | Review order and finding criteria |
| `.ai/` | Data the CLI reads: `config.json` (project settings, toolchain, checks), `schemas/`, `harness.json` (which starter version installed which files), gitignored `runs/` (receipts, logs, handoff notes) |
| `.agents/skills/` | The only copy of each skill (Agent Skills format) |
| `.claude/` | Skill links, the isolated wiki-query subagent, permissions, and the PreToolUse guard hook |
| `.gemini/settings.json` | Points Gemini CLI at `AGENTS.md` |
| `tool/ai.py` | Harness CLI, Python 3.10+ standard library only |
| `wiki/` | Project knowledge: `current` facts, `rule` contracts with adoption levels, notes, index, and log |
| `.githooks/pre-commit` | Runs `verify` before every commit; `python3 tool/ai.py hooks install` connects it once per clone |

Skills: `repo-onboard`, `repo-change`, `repo-review`, `repo-verify`, `repo-wiki-query`, `repo-wiki-write`.

Three places, three roles: `AGENTS.md` holds the gates that always apply, skills hold procedures loaded only when a task needs them,
and `.ai/` holds data that the CLI reads. Approval briefs happen in the conversation, and an unfinished task leaves a short `.ai/runs/<id>/handoff.md`.

## First session

Open this repository in your agent (Claude Code, Codex, Cursor, Gemini CLI, Copilot) and ask it to onboard the project.
`AGENTS.md` sends every agent to `repo-onboard` while `.ai/config.json` says `"onboarded": false`. Onboarding writes the settings and checks
in `.ai/config.json`, the repository map in `AGENTS.md`, and the first architecture pages in `wiki/`, then runs `doctor` and `verify --all`.

`.ai/harness.json` records the starter commit and a hash of every file it installed. Keep it: `python3 tool/starter.py upgrade`, run in the starter,
uses that commit as the base of a 3-way merge per harness file, so both your edits and the starter's arrive. It writes only harness files that are
committed and unmodified, and leaves conflict markers where both sides changed the same lines. Text between `project:<name>` markers
is yours: the merge keeps it as it is. JSON files merge by key, and where both sides changed a key your value stays.

## CLI

```bash
python3 tool/ai.py doctor                 # toolchain, harness files, skills, adapters
python3 tool/ai.py verify                 # checks selected from files changed since the base branch; receipt in .ai/runs/adhoc/
python3 tool/ai.py verify --all --id X    # whole repository
python3 tool/ai.py verify --check lint    # also run a declared check that no changed file selected
python3 tool/ai.py verify --dry-run       # show the selection only
python3 tool/ai.py wiki lint
python3 tool/ai.py adapters sync          # create missing .claude/skills links after adding a skill
python3 tool/ai.py hooks install          # connect the pre-commit hook in this clone
```

Built-in checks run for every project: whitespace and conflict markers, secret scan (`.env` files, signing keys, and credential files that git tracks or does not ignore, plus key patterns),
harness configuration, JSON syntax, Markdown link targets, wiki lint, and the harness self-test.
Everything language-specific comes from `checks` in `.ai/config.json`, which only onboarding (or an approved L2 change) edits.
`--check` accepts only ids declared there, so no command reaches the verifier from outside that file.

## Pre-commit hook

`.githooks/pre-commit` runs `python3 tool/ai.py verify --id pre-commit` before every commit and stops the commit when a check fails.
Git does not share `core.hooksPath` through a clone, so run `python3 tool/ai.py hooks install` once after cloning; `doctor` warns until you do.
If the repository already runs hooks from another tool (husky, lefthook, pre-commit, or files in `.git/hooks`), `hooks install` leaves them
in place, and you add the same verify call to that tool's pre-commit hook. Commands of your own go between the `project:pre-commit` markers.
`verify` checks the working tree, so changes you leave unstaged are checked too. For a file staged in part, the secret scan and the
whitespace and conflict-marker check also read the staged copy, because a commit can take either one; a leaked key cannot be taken back.
Project checks (format, lint, tests) run on the working tree only, so staging in part stays possible and they never move your files.
Verification receipts collect in `.ai/runs/pre-commit/`.

## Guard hook

`.claude/settings.json` registers `python3 tool/ai.py hook pre-tool-use`. It blocks force pushes, pushes that delete remote branches or tags,
`git reset --hard`, `git clean -f`, worktree-discarding `git restore`/`git checkout`/`git switch`, force branch deletion, stash drops,
skipping the pre-commit hook (`git commit --no-verify`, changing `core.hooksPath`), recursive `rm` or `find -delete` on broad targets, and reading, copying, or printing `.env` files (including through git history and `<`
redirection) and secret-looking environment variables. Listing the commits that touched an env file (`git log -- '.env*'`) stays allowed. Commands are parsed with shell quoting:
global git options, `sudo`, `bash -c`, and heredocs fed to a shell are seen through, while text in a commit message or a heredoc written
to a file is not a command. Instructions in `AGENTS.md` are context; the hook is enforcement. When a blocked action is really intended,
the user runs it with the `!` prefix. The guard reduces accidents; it is not a security boundary.

## Tool support

| Tool | Policy | Skills |
| --- | --- | --- |
| Claude Code | `CLAUDE.md` imports `AGENTS.md` | `.claude/skills/<name>` symlinks |
| Codex | reads `AGENTS.md` | reads `.agents/skills/` |
| Cursor | reads `AGENTS.md` | reads `.agents/skills/` |
| GitHub Copilot | reads `AGENTS.md` | reads `.agents/skills/` |
| Gemini CLI | `.gemini/settings.json` → `AGENTS.md` | reads `.agents/skills/` |

The skill links are symlinks. On Windows, enable `core.symlinks` (developer mode) or run `python3 tool/ai.py adapters sync` after cloning.
