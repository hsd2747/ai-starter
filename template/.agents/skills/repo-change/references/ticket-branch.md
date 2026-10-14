# Ticket branch procedure

When to start this procedure is defined in `AGENTS.md`. `<base>` is `git.baseBranch` and `<branch>` is `git.branchPattern`
with `{KEY}` replaced, both from `.ai/config.json`.

## Building the question

Read the current state before asking; options built without it are wrong.

```
git branch --show-current
git status --short
git branch -a
```

Put only the relevant items below into the question.

## Base

- Offer branching from the current branch or from `<base>`.
- From `<base>`, run `git fetch origin <base>` and branch from `origin/<base>`. If the local `<base>` is behind, say so.
- If the current branch belongs to another ticket, say so. Stacking on another ticket's commits is rarely intended.

## Upstream

Always pass `--no-track` when branching from a remote-tracking branch.

```
git switch -c <branch> --no-track origin/<base>
git branch -vv   # the new branch must show no upstream
```

Without `--no-track`, `branch.autoSetupMerge` sets the upstream to `origin/<base>`, and a plain `git push` then
pushes **straight to `<base>`, skipping review**. Undoing that needs a force push to a shared branch (L3), so prevent it at creation.
If `git branch -vv` shows `[origin/...]` on the new branch, run `git branch --unset-upstream`.
Set the upstream on the first push with `git push -u origin <branch>`.

## A branch with the same name exists

- If `<branch>` exists locally or on the remote, do not create it again.
- Show the remote tip with `git log --oneline -1 origin/<branch>`. If it is behind `<base>` or points at another ticket's commits, the user needs that to choose.
- Offer three options: check out that branch, create a differently named branch, or stay on the current branch.
- A new local branch that diverges from an old remote tip will be rejected as non-fast-forward on push. Say so now; resolve it when a push is requested.

## Dirty worktree

Show staged, unstaged, and untracked changes separately and offer:

- **Carry over**: if the current branch is the base, `git switch -c <branch>` keeps the index and worktree as they are. No stash needed.
- **Carry over from a different base**: `git stash push -u`, `git switch -c <branch> --no-track origin/<base>`, `git stash pop`. If the pop conflicts, keep the stash, stop, and report.
- **Leave behind**: `git stash push -u -m <KEY>` on the current branch so the new branch starts clean; the key in the message makes it findable.
- **Discard**: irreversible, so L3. List the files that would be lost and get separate approval. Never run `git restore`, `git reset --hard`, or `git clean` without it.
- If the current changes look unrelated to the ticket, say so in the question. Dragging someone else's changes onto the new branch also needs undoing later.
- If one file mixes ticket and unrelated changes, separating them needs a hunk-level stash. State the cost and let the user choose to carry the whole file.

## After creating the branch

- Commit and push only when the user asks. Approval to branch is not approval to commit.
- Never commit on the base branch.
- Report the base and the upstream of the new branch. If the upstream points at the base, the push target is wrong and the user must know.
