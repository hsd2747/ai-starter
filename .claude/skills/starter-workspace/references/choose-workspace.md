# Choose the workspace

Every starter skill resolves its workspace this way before asking anything else.

Run from this starter's root:

```bash
python3 tool/starter.py workspace list
```

It prints the saved workspace list (`~/.claude/ai-starter/workspaces.json`), most recent first. The generator adds a workspace there on every
successful `new`, `adopt`, `sync`, or `workspace add`. Each entry says whether the folder `exists`, whether it is `initialized`
(has `workspace.json`), and its repositories.

| Situation | Do |
| --- | --- |
| The request names a workspace path or a saved workspace by folder name | Use it. |
| Exactly one saved workspace exists | Use it. Say in one line which one and its repositories, so the user can redirect. |
| Several saved workspaces exist | Ask which one, most recent first, with "a new workspace" as the last option. |
| None is saved, or the user wants a new one | Explain first, then ask for the path (below). |
| A saved folder no longer exists | Tell the user and offer `workspace remove --path <path>`, which only forgets the entry. |
| `"ok": false` (unreadable list) | Show the error and ask the user for the path directly; the generator still works without the list. |

## When no workspace is saved

Before asking about repositories, explain in two or three sentences:

- A workspace is a folder outside this starter that groups the repositories of one product, for example `be`, `web`, and `app`.
- Its `AGENTS.md` lists each repository's role and the contracts between them, and the folder is a small git repository of its own.
- Every repository inside it stays an independent git repository.

Then ask for the path, suggesting `<parent of this starter>/<product name>`. When the user answers, save it:

```bash
python3 tool/starter.py workspace add --path <path>
```

`add` only records the path; the folder and its files are created with the first repository. On `"ok": false` (for example a path inside this starter),
show the error and ask again.
