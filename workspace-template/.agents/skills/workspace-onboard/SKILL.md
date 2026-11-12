---
name: workspace-onboard
description: Get a new member of this workspace ready to work, whatever their team (developers, PMs, designers): record their team, clone the repositories they can access, check tools and access, explain personal settings and the workspace skills, and walk through this workspace's own setup steps. Use when someone is new here, has just cloned the workspace, asks how to get set up or what is missing, or a check reports problems (for example "온보딩 해줘", "처음 왔어", "세팅 도와줘", "뭐 설치해야 해?", "help me get set up").
---

# Workspace onboarding

Talk in the user's language, one step at a time, and show each command before running it. Run everything from the workspace root.
Change nothing outside this workspace without asking: global git config, SSH keys, shell profiles, and installs are the user's to approve.
Never ask for, print, or store a token or password; credentials go into the user's credential store, not into any file here.

## 1. Where things stand

Run `python3 .ai/workspace.py check`. If `python3` is missing, explain how to get it (on macOS `xcode-select --install`, which also installs git) and stop there.
Summarize `problems` first, then `warnings`, in plain words. Use the rest of this skill only for what the report shows is missing.

## 2. Team

With no team recorded, read `teams` in `workspace.json`, ask which one the user is on, and run `python3 .ai/workspace.py local --team <team>`.
Explain that `CLAUDE.local.md` is theirs alone, ignored by git and loaded in every session here, and that rules marked with a team in `AGENTS.md` follow it.

## 3. Repositories and access

- For `missing` repositories, run `python3 .ai/workspace.py clone` and report `cloned`, `skipped`, and `failed`.
- For a failure, run `python3 .ai/workspace.py check --access` and list each repository without access with its remote. Access is granted on the remote,
  per repository; say whom to ask if the workspace steps below name someone. Never work around a repository the user cannot read.
- A failure on every remote usually means git cannot authenticate at all. Suggest `! ssh -T git@<host>` or `! git ls-remote <remote>` so the user sees the answer, and point to the host's guide for adding an SSH key.

## 4. Personal settings

Offer to add the user's own preferences to the Preferences section of `CLAUDE.local.md`, such as the language for answers or the level of detail.
Shared rules are not edited for one person; if the user wants a rule changed for everyone, it goes into `AGENTS.md` as a separate, reviewed change.

## 5. This workspace's steps

Follow the steps between the markers below and the setup section of `README.md`. Mark each one done or not done in the summary.

<!-- workspace:onboarding:start -->
No workspace-specific steps yet. Write them here, one numbered line each: connectors to enable, accounts to request, and whom to ask for access.
<!-- workspace:onboarding:end -->

## 6. By team

- **Developers:** each repository has its own setup; point to its README instead of running it unasked. Work in a repository by opening a session inside it,
  so that its own `AGENTS.md`, checks, and skills apply. A `check` warning about Python below 3.10 matters for them: the harness's `verify` and commit hook need it.
- **Everyone else:** work from this workspace root. The repositories are here to read: for planning, reviews, and answering questions about how things work.
  Changing one follows that repository's own rules and the access its remote grants.

## 7. Skills

List the workspace skills from `skills` in the check report, one line each from their descriptions, and say they load only in sessions opened at this root.
Mention that the team can add skills under `.agents/skills/`, as `README.md` describes.

## 8. Finish

Run `python3 .ai/workspace.py check` again. Report what is done, what is left with the next action for each, and suggest a first task that fits the user's team.
