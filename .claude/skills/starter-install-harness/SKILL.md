---
name: starter-install-harness
description: Install the starter harness into an existing git repository, inside a workspace or not, by running tool/starter.py harness install, after proposing how the repository's own agent instructions (AGENTS.md, CLAUDE.md, .cursorrules, copilot instructions, its own .claude entries) will be merged. Also checks a repository's harness with harness status. Use when the user wants to add, install, or set up the harness or the agent rules in a repository that does not have them yet, or asks whether a repository has the harness or which starter version it recorded (for example "admin 레포에 하네스 깔아줘", "이 레포 하네스 버전 확인해줘").
---

# Install the harness

Harness commands work on one repository and write nothing outside it. They need no workspace; listing the repository in one is `starter-adopt-repo`.

## 1. Locate

- When the user gives a path, use it. When they name a repository, find it with `python3 tool/starter.py workspace list`
  (see [choose-workspace.md](../starter-workspace/references/choose-workspace.md)); a `registered` entry is one without the harness.
- The folder must already be a git repository outside this starter. If it lives only on a remote, propose `git clone <url> <path>` and run it only after the user confirms.
- Run `python3 tool/starter.py harness status --repo <path>`. `"installed": true` means the harness is already there: offer `starter-upgrade` instead.
- Run `git -C <repo> status --porcelain`. If the worktree is dirty, recommend committing or stashing first so that the harness arrives as its own
  reviewable change; do neither yourself unless the user asks.

## 2. Plan the merge of existing instructions

`harness status` lists two kinds of existing instructions. Neither is ever changed by the generator.

- `conflicts`: files at a harness path (`AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, ..., in any capitalization). The install refuses to run while any exists.
- `existingInstructions`: other agent tools' rule files, files set aside earlier (`*.pre-harness.*`), and the repository's own entries under `.claude/`, `.agents/`, and `.gemini/`.
  They do not block the install, but left alone they keep steering agents next to the harness.

When both lists are empty, say so in one line and go to step 3. Otherwise, before installing:

1. Read each listed file; for a folder, list it and read the files that hold rules. Never open `.env` files. In `.claude/settings.local.json`, read only
   permissions and hooks, and never repeat a value that looks like a token or a password. Check `git ls-files` to tell tracked files from personal ones.
2. Present one table: path, tool, what it instructs in one line, and a proposed disposition:
   - **Set aside, merge in onboarding**: required for every `conflicts` entry. Before the install, `git mv <file> <stem>.pre-harness<ext>`
     (plain `mv` for an untracked file; for example `AGENTS.pre-harness.md`); onboarding moves its rules into the harness and deletes it once the user agrees.
   - **Merge in onboarding, then point to AGENTS.md**: another tool's rules that should bind every agent (`.cursorrules`, `.cursor/rules/`,
     `.github/copilot-instructions.md`, `AGENT.md`, `GEMINI.md`). After the merge the file shrinks to a pointer to `AGENTS.md`, so every tool reads one set of rules.
   - **Keep as is**: the repository's own skills, commands, or agents under `.claude/` that do not contradict the harness, and personal untracked files
     such as `CLAUDE.local.md` or `.claude/settings.local.json`.
3. Name every rule that contradicts the harness, for example on commits and pushes, approvals, or verification, and ask which one wins.
4. Wait for approval. Do not merge content now: until onboarding finishes, the installed `AGENTS.md` allows no other tracked change, so the merge happens there.
5. Run only the approved moves, then `harness status` again: `conflicts` must be empty.

## 3. Run

From this starter's root:

```bash
python3 tool/starter.py harness install --repo <path>
```

- If the user also wants the repository listed in a workspace and it is not listed yet, run `adopt --install` through `starter-adopt-repo` instead; it does both.
- On `"ok": false` nothing was written. A conflict that appears now goes back to step 2.
- On success, report `merged`, `existingInstructions`, and every entry in `warnings`, and summarize `git -C <repo> status --short` by top-level folder.

## 4. Next

- If a workspace already lists the repository, run `python3 tool/starter.py sync --workspace <path>` so that its table shows the harness.
- Nothing is committed. The repository is not onboarded yet: offer `starter-onboard-repo` and hand it the approved dispositions from step 2.
  Onboarding in another session finds the same files, because they stay in the repository until they are merged.
