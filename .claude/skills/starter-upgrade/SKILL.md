---
name: starter-upgrade
description: Bring starter changes into a workspace root and the managed repositories in it, or into one repository with the harness whether or not a workspace lists it, by running tool/starter.py upgrade or harness upgrade, which merge each harness file three ways against the starter commit the target recorded. Use when the user asks to upgrade, update, or sync existing repositories or a workspace with the latest starter or harness (for example "기존 레포들 하네스 최신으로 올려줘", "be에 스타터 변경 반영해줘").
---

# Upgrade

The generator plans and merges by itself and writes nothing when a check fails. Do not re-implement its checks; run it and relay its answer.

## 1. Locate

- One repository given by path, or one that no workspace lists: use `harness upgrade --repo <path>`. It needs no workspace and writes only inside the repository.
- Otherwise choose the workspace with [choose-workspace.md](../starter-workspace/references/choose-workspace.md) and use `upgrade --workspace`.
  Without a named repository it covers the workspace root and every listed `managed` repository; with `--name` only those repositories.
- A `registered` repository has no harness; offer `starter-install-harness` instead.

## 2. Plan

Run from this starter's root, one of:

```bash
python3 tool/starter.py upgrade --workspace <path> [--name <name> ...] --dry-run
python3 tool/starter.py harness upgrade --repo <path> --dry-run
```

- `"ok": false` about the starter: it has uncommitted changes under `template/` or `workspace-template/`, or no commit. Tell the user;
  commit only when they ask.
- Per target, summarize `updated`, `merged`, `added`, `conflicts`, `kept`, `skipped` with reasons, and `removedUpstream`. Say `upToDate` targets in one line.
- `blockers` list files that are uncommitted in a target. Show them and recommend committing or stashing in that repository first, so the
  upgrade arrives as its own reviewable change. Do neither yourself unless the user asks.

## 3. Apply

State in one line which targets will change, then run the same command without `--dry-run`. Report every entry in `warnings`.

## 4. Conflicts and leftovers

A conflict means a repository and the starter changed the same lines. Resolving one is work **inside that repository**:

- Read `<repo>/AGENTS.md` and follow it. Harness files such as `AGENTS.md` and `.ai/config.json` are L2 there.
- Propose a resolution per conflict that keeps the project's decisions and the starter's intent, and write it after approval.
- A conflict that has `project:` or `workspace:` markers on the starter side usually means the target filled that section before the
  starter marked it. Resolve it by moving the target's text between the markers and dropping the placeholder; later upgrades then keep it.
- `kept` lists JSON keys that both the target and the starter changed; the target's value stayed and the file is valid JSON. Show the
  starter's value from `template/<path>` in this starter and ask whether to adopt it.
- `removedUpstream` files are no longer shipped by the starter. Deleting them is the user's decision; never delete them yourself.
- `skipped` files were not touched. Explain each reason and offer to merge it by hand.

## 5. Verify and finish

- Run `cd <repo> && python3 tool/ai.py verify` in every upgraded repository. Leftover conflict markers fail `git-diff-check`.
- Run `cd <repo> && python3 tool/ai.py doctor` too. Upgrade adds harness files but never changes git config, so a warning that commits are not verified
  is answered with `python3 tool/ai.py hooks install`, after telling the user that every commit will run `verify` from then on.
- Nothing is committed. Show `git -C <target> status --short` for each target, and commit only when the user asks.
- Recommend opening the next session in each repository so that the upgraded hook and skills load.
