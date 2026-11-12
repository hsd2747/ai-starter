---
name: workspace-repos
description: List or unlist a repository in this workspace, or change its role or remote, with `.ai/workspace.py register`, `unregister`, and `sync`, which change only workspace.json and the repository table in AGENTS.md. Use when someone wants to add a repository cloned here to the workspace, take one off the list, or change what the table says about it (for example "admin 레포 워크스페이스에 등록해줘", "이 레포 목록에서 빼줘", "be 역할 설명 바꿔줘").
---

# Workspace repositories

Talk in the user's language and run everything from the workspace root. These commands change only `workspace.json` and the table between
the `workspace:repos` markers of `AGENTS.md`, never a file inside a repository. Installing the harness in a repository needs ai-starter;
if the user asks for it, say so and leave it there.

## Register

1. Get the folder. It must already be a git repository inside this workspace; `--path` is relative to the root.
   A repository that lives elsewhere or only on a remote: propose `git clone <url> <folder>` here and run it only after the user confirms.
2. Ask for its role in one line, what the repository is for, if the user did not say. The remote defaults to the repository's origin;
   ask for one only when it has none.
3. State in one line what will be written, then run:

   ```bash
   python3 .ai/workspace.py register --path <folder> [--name <name>] --role "<role>" [--remote <url>]
   ```

4. Report `registered`, `kind`, and every warning. Without a remote, teammates cannot clone the repository: ask for its URL, never one with a token or password in it.

## Unregister

1. Find the entry by name, or by `path` when the user named a folder. A folder without an entry is not registered; say so and stop.
2. Before running, say in two or three lines: `workspace.json` loses the entry and the table loses its row; the folder and every file in it stay as they are,
   a harness included. List every line between the `workspace:contracts` markers of `AGENTS.md` that names the repository; the command does not change them.
   Wait for the user to confirm.
3. Run `python3 .ai/workspace.py unregister --name <name>` and report `removed` and every warning.
4. Propose new text for the contract lines that named the repository and edit them after approval, as `workspace-rules` describes.
   Deleting or moving the folder is the user's decision; never do it yourself.

## Role or remote

Edit the entry in `workspace.json`, then run `python3 .ai/workspace.py sync`. Never edit between the `workspace:repos` markers by hand.
A remote is never a URL with a token or password in it.

## Finish

On `"ok": false` nothing was written; relay the error in plain words. A warning about missing table markers means `workspace.json` changed but the table did not:
offer to restore the markers and run `sync`. Nothing is committed: show `git status --short`, and commit `workspace.json` and `AGENTS.md` together only when the user asks.
