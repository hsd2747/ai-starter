# Starter maintenance

This repository is ai-starter, a generator. It is never onboarded and holds no product code.

## Layout

- `template/`: everything copied into a new or adopted repository. Its `AGENTS.md`, skills, and `.claude/` are the policy of
  **generated** repositories. They do not govern work on this starter, even when a tool loads them while you edit files under
  `template/` (for example the `template:repo-*` skills or the onboarding gate in `template/AGENTS.md`).
- `workspace-template/`: files for a workspace root: `AGENTS.md` with a generated repository table, `CLAUDE.md`, a whitelist `.gitignore`, and the guard hook settings.
- `tool/starter.py`: the generator (`new`, `adopt`). Python 3.10+, standard library only.
- `tool/ai.py`: the guard hook entry for sessions in this starter; it delegates to `template/tool/ai_harness/guard.py`.
- `tests/`: generator tests.
- `.claude/skills/starter-*`: conversational wrappers around the generator (`starter-new-repo`, `starter-onboard-repo`, `starter-adopt-repo`,
  `starter-workspace`). When one of them works inside a generated repository, that repository's `AGENTS.md` rules there.

## Rules

- `template/.ai/config.json` stays un-onboarded: `"onboarded": false`, empty project fields, no toolchain, no checks.
  Nothing project-specific or language-specific goes into `template/`.
- A change under `template/` or `workspace-template/` reaches every repository created afterwards. Before writing one,
  state in one line what generated repositories will see differently, then proceed.
- The generator writes only inside the workspace it is given, plus the saved workspace list `~/.claude/ai-starter/workspaces.json`
  that the starter skills read. It never writes into this starter, never overwrites an existing file, and validates everything before
  its first write. `tests/` pins these rules and redirects the list with `AI_STARTER_REGISTRY`; keep them passing.
- Generated repositories record the starter commit in `.ai/harness.json`. Commit starter changes before creating repositories that will be kept.
- Commit and push only when the user asks. Never hardcode secrets, tokens, or connection strings.

## Verification

```bash
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s template/tool/tests -t template/tool -q
```

This root has no `verify`. For an end-to-end check, create a workspace in a temporary folder with `python3 tool/starter.py new`
and run `python3 tool/ai.py verify --all` inside the generated repository. Report which of these ran and their results.
