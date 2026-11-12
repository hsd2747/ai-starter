# Workspace

<!-- workspace:readme:start -->
This repository groups the repositories of one product so that every team works from the same folder with the same agent rules.
Replace this paragraph with one or two lines about the product and who uses this workspace.
<!-- workspace:readme:end -->

It holds only the workspace's own files: the repository list (`workspace.json`), the agent rules (`AGENTS.md`), workspace skills,
and a small tool (`.ai/workspace.py`). The repositories themselves are cloned next to these files and are never committed here.

## Getting started

You need:

- **Access** to the repositories listed in `workspace.json`: read access on each remote, granted per repository. Ask for what your team uses.
- **git and Python 3.9 or later.** On macOS, `xcode-select --install` installs both. Developers who commit in repositories with the harness need Python 3.10 or later.
- **Git access to the remotes**, for example an SSH key registered on the host. `git ls-remote <remote>` tells you whether it works.
- **Claude Code**, or another agent that reads `AGENTS.md`.

Then:

```bash
git clone <this repository> <folder> && cd <folder>
python3 .ai/workspace.py clone --team <team>   # clone every listed repository, record your team (see "teams" in workspace.json)
python3 .ai/workspace.py check --access        # what is still missing: team, tools, repositories, access, skills
claude                                         # then ask: "온보딩 해줘" or "help me get set up"
```

The `workspace-onboard` skill walks you through the rest, including the steps below. A repository you cannot access is listed under
`failed`; ask for access and run `clone` again. Developers set up each repository from its own README and open agent sessions inside it for work there.

<!-- workspace:setup:start -->
Steps that only this workspace needs, such as connectors, accounts, or whom to ask for access, go here.
<!-- workspace:setup:end -->

## Day to day

- `git pull`, then `python3 .ai/workspace.py clone` to get repositories added since.
- `CLAUDE.local.md` is yours: your team and your own preferences for agents. Git ignores it. Rules for everyone belong in `AGENTS.md`.
- Workspace skills live in `.agents/skills/<name>/SKILL.md`. To add one, write that file, run `python3 .ai/workspace.py skills sync`
  so that Claude Code sees it (`.claude/skills/<name>`), check it with `python3 .ai/workspace.py check`, and commit both.
  They load in sessions opened at this folder, not in sessions opened inside a repository. Names starting with `workspace-` are reserved for skills that ship with the workspace.
