---
name: starter-onboard-repo
description: Onboard a repository that this starter created or adopted, without leaving this session, by following that repository's own repo-onboard skill and AGENTS.md. Use when the user asks to onboard a generated repository, or to set up or refresh its architecture and tooling (for example "be 온보딩해줘").
---

# Onboard a generated repository

Onboarding is defined inside the target repository, not here. This skill only sets up the context so that it can run from a session opened in the starter.

## 1. Find the repository

- When the user gives a path, use it. Otherwise run `python3 tool/starter.py workspace list` and match the named repository against the `managed` entries
  of the saved workspaces; ask only when the name matches more than one or none (then follow [choose-workspace.md](../starter-workspace/references/choose-workspace.md)).
  A `registered` entry has no harness: offer `starter-adopt-repo` with install first.
- Confirm that `<repo>/.ai/config.json` and `<repo>/.agents/skills/repo-onboard/SKILL.md` exist. If `onboarded` is already true, this is the skill's refresh mode; say so.
- The repository lies outside this project, so file tools may ask for permission on each access. If that gets in the way, suggest that the user run `/add-dir <workspace>` once.

## 2. Work under the repository's rules

Until onboarding is finished:

- Read `<repo>/AGENTS.md` in full and follow it for everything inside the repository: risk levels, approvals, security, verification, and the completion report.
  The starter rule that template policy does not govern starter work does not apply: this is work in the generated repository.
- Read `<repo>/.agents/skills/repo-onboard/SKILL.md` and follow it step by step. Resolve its relative links from that file's folder, and read each linked reference when the skill says to.
- Run every harness command from the repository root, for example `cd <repo> && python3 tool/ai.py doctor`. The CLI finds its root from the current directory.
- Write only inside `<repo>`. When a problem belongs to the template itself, report it as a starter change instead of patching `template/` for one project.
- This session does not load `<repo>/.claude/settings.json`, so the repository's permission list does not apply. Ask before any command its `AGENTS.md` requires approval for.

## 3. Finish

Report what step 6 of `repo-onboard` requires. Then:

- Nothing is committed. Show `git -C <repo> status --short` and commit only when the user asks.
- If the workspace has two or more managed repositories, offer `starter-workspace` to record the contracts between them.
- Recommend opening later sessions in the repository itself, where its hook, permissions, and skills load automatically.
