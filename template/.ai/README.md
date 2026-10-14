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
| `.github/workflows/verify.yml` | CI running the same selector as local `verify` |

Skills: `repo-onboard`, `repo-change`, `repo-review`, `repo-verify`, `repo-wiki-query`, `repo-wiki-write`.

Three places, three roles: `AGENTS.md` holds the gates that always apply, skills hold procedures loaded only when a task needs them,
and `.ai/` holds data that the CLI reads. Approval briefs happen in the conversation, and an unfinished task leaves a short `.ai/runs/<id>/handoff.md`.

## First session

Open this repository in your agent (Claude Code, Codex, Cursor, Gemini CLI, Copilot) and ask it to onboard the project.
`AGENTS.md` sends every agent to `repo-onboard` while `.ai/config.json` says `"onboarded": false`. Onboarding writes the settings and checks
in `.ai/config.json`, the repository map in `AGENTS.md`, the first architecture pages in `wiki/`, and the CI toolchain step, then runs `doctor` and `verify --all`.

`.ai/harness.json` records the starter commit and a hash of every file it installed. Keep it: a later harness upgrade compares against it
to tell files you changed from files the starter changed.

## CLI

```bash
python3 tool/ai.py doctor                 # toolchain, harness files, skills, adapters
python3 tool/ai.py verify                 # checks selected from files changed since the base branch; receipt in .ai/runs/adhoc/
python3 tool/ai.py verify --all --id X    # whole repository
python3 tool/ai.py verify --check lint    # also run a declared check that no changed file selected
python3 tool/ai.py verify --dry-run       # show the selection only
python3 tool/ai.py wiki lint
python3 tool/ai.py adapters sync          # create missing .claude/skills links after adding a skill
```

Built-in checks run for every project: whitespace and conflict markers, secret scan (`.env` files, signing keys, and credential files that git tracks or does not ignore, plus key patterns),
harness configuration, JSON syntax, Markdown link targets, wiki lint, and the harness self-test.
Everything language-specific comes from `checks` in `.ai/config.json`, which only onboarding (or an approved L2 change) edits.
`--check` accepts only ids declared there, so no command reaches the verifier from outside that file.

## Guard hook

`.claude/settings.json` registers `python3 tool/ai.py hook pre-tool-use`. It blocks force pushes, pushes that delete remote branches or tags,
`git reset --hard`, `git clean -f`, worktree-discarding `git restore`/`git checkout`/`git switch`, force branch deletion, stash drops,
recursive `rm` or `find -delete` on broad targets, and reading, copying, or printing `.env` files (including through git history and `<`
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
