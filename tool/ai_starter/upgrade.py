"""`upgrade` and `harness upgrade`: bring starter changes into a workspace root and its managed repositories, or into one repository.

Every target is planned without writing; only when no target has a blocker are all writes staged and moved in together.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import paths
from .files import Staging, file_hash, tree_files
from .gitutil import git_ok, starter_version
from .manifests import load_manifest, manifest_bytes, manifest_errors
from .merge import merge_file
from .paths import GUARD_DIR, HARNESS_RECORD, WORKSPACE_FILE, StarterError, resolve_repo, resolve_workspace
from .policy import policy_for
from .registry import remember_workspace
from .workspace import guard_files, load_workspace, repo_kind


@dataclass(frozen=True)
class Content:
    kind: str
    """"file" or "link"."""
    data: bytes
    """The file's bytes, or the link target."""

    @property
    def mergeable(self) -> bool:
        return self.kind == "file" and b"\0" not in self.data


@dataclass
class Write:
    content: Content
    source: str
    """Starter path whose permission bits the written file takes."""


@dataclass
class Plan:
    """What an upgrade does to one target's files, computed without writing."""

    writes: dict[str, Write] = field(default_factory=dict)
    owned: set[str] = field(default_factory=set)
    """Paths the starter has installed once the plan is applied; the new version record lists them."""
    updated: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    kept: list[dict] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    removed_upstream: list[str] = field(default_factory=list)

    def skip(self, rel: str, reason: str) -> None:
        self.skipped.append({"path": rel, "reason": reason})

    def report(self) -> dict:
        return {"updated": self.updated, "merged": self.merged, "conflicts": self.conflicts, "kept": self.kept,
                "added": self.added, "skipped": self.skipped, "removedUpstream": self.removed_upstream}


@dataclass
class Target:
    """A workspace root or a repository: why it cannot be upgraded, or its plan and the version record to write with it."""

    name: str
    root: Path
    record_path: Path
    record_kind: str
    commit: str | None = None
    blockers: list[str] = field(default_factory=list)
    warning: str | None = None
    up_to_date: bool | None = None
    plan: Plan | None = None
    record: dict | None = None

    def report(self) -> dict:
        report = {"target": self.name, "path": str(self.root), "from": self.commit, "blockers": self.blockers}
        if self.up_to_date is not None:
            report["upToDate"] = self.up_to_date
        if self.warning:
            report["warning"] = self.warning
        if self.plan is not None:
            report.update(self.plan.report())
        return report


def _disk(path: Path) -> Content | None:
    if path.is_symlink():
        return Content("link", os.readlink(path).encode())
    return Content("file", path.read_bytes()) if path.is_file() else None


def _starter_listing(commit: str) -> dict[str, tuple[str, str]]:
    """{starter path: (mode, blob)} of template/ and workspace-template/ at `commit`."""
    process = subprocess.run(["git", "ls-tree", "-r", "-z", commit, "--", "template", "workspace-template"],
                             cwd=paths.STARTER, capture_output=True)
    if process.returncode != 0:
        raise StarterError(f"Cannot list starter commit {commit}: {process.stderr.decode(errors='replace').strip()}")
    listing = {}
    for item in process.stdout.split(b"\0"):
        if item:
            meta, path = item.split(b"\t", 1)
            mode, _, blob = meta.decode().split()
            listing[path.decode()] = (mode, blob)
    return listing


def _listing(listings: dict, commit: str) -> dict[str, tuple[str, str]]:
    if commit not in listings:
        listings[commit] = _starter_listing(commit)
    return listings[commit]


def _blob(listing: dict[str, tuple[str, str]], source: str) -> Content | None:
    if source not in listing:
        return None
    mode, blob = listing[source]
    data = subprocess.run(["git", "cat-file", "blob", blob], cwd=paths.STARTER, capture_output=True, check=True).stdout
    return Content("link" if mode == "120000" else "file", data)


def plan_upgrade(root: Path, label: str, mode: str, owned: set[str], sources: dict[str, str],
                 base_source: Callable[[str], str], listing: dict) -> Plan:
    """What an upgrade does to one target, computed without writing.

    `mode` is how the target got its harness (see policy_for). `owned` are the destination paths the starter installed at the
    recorded commit, `sources` maps every destination path the starter ships now to its starter path, and `base_source` maps
    a destination path to its starter path at that commit.
    """
    plan = Plan()
    for rel in sorted(owned | sources.keys()):
        ours = _disk(root / rel)
        if rel not in sources:
            if ours is not None:
                plan.removed_upstream.append(rel)
            continue
        source = sources[rel]
        theirs = _disk(paths.STARTER / source)
        base = _blob(listing, base_source(rel)) if rel in owned else None
        if rel in owned or ours == theirs:
            plan.owned.add(rel)
        if ours == theirs or (base is not None and base == theirs):
            continue
        if rel not in owned:
            if ours is None:
                plan.writes[rel] = Write(theirs, source)
                plan.added.append(rel)
                plan.owned.add(rel)
            else:
                plan.skip(rel, "new in the starter but a different file already exists here; merge by hand")
            continue
        if base is None:
            plan.skip(rel, "not in the recorded starter commit, so there is no base to merge from")
        elif ours is None:
            plan.skip(rel, "deleted here but changed in the starter; restore it by hand if it is still wanted")
        elif ours == base:
            plan.writes[rel] = Write(theirs, source)
            plan.updated.append(rel)
        elif not (ours.mergeable and base.mergeable and theirs.mergeable):
            plan.skip(rel, "changed both here and in the starter, and it is a link or binary; merge by hand")
        else:
            result = merge_file(policy_for(rel, mode), rel, ours.data, base.data, theirs.data, label)
            if result.skip:
                plan.skip(rel, result.skip)
                continue
            if result.data is not None:
                plan.writes[rel] = Write(Content("file", result.data), source)
                (plan.conflicts if result.conflicts else plan.merged).append(rel)
            if result.kept:
                plan.kept.append({"path": rel, "keys": result.kept})
    return plan


def _dirty(root: Path, rels: list[str]) -> list[str]:
    output = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", *rels], cwd=root,
                            capture_output=True, text=True).stdout
    return sorted(line[3:] for line in output.splitlines())


def _stage_writes(stage: Staging, root: Path, writes: dict[str, Write]) -> None:
    for rel, write in writes.items():
        if write.content.kind == "link":
            stage.link(root / rel, write.content.data.decode())
        else:
            stage.write(root / rel, write.content.data, mode_from=paths.STARTER / write.source)


def _guard_dest(source: str) -> str | None:
    """Destination in the workspace root of a starter path, for the files a workspace copies."""
    if source.startswith("workspace-template/"):
        return source.removeprefix("workspace-template/")
    if source == "template/tool/ai.py" or source.startswith("template/tool/ai_harness/"):
        return f"{GUARD_DIR}/{source.removeprefix('template/tool/')}"
    return None


def _workspace_source(rel: str) -> str:
    return f"template/tool/{rel.removeprefix(GUARD_DIR + '/')}" if rel.startswith(GUARD_DIR + "/") else f"workspace-template/{rel}"


def _check_base(target: Target, version: dict) -> bool:
    """Whether the recorded commit can serve as the merge base and the target is behind the starter HEAD."""
    commit = target.commit
    if not commit:
        target.blockers.append("no starter commit is recorded, so there is no base to merge from; upgrade it by hand")
    elif not git_ok(paths.STARTER, "cat-file", "-e", f"{commit}^{{commit}}"):
        target.blockers.append(f"the recorded starter commit {commit[:12]} is not in this starter's history")
    elif not git_ok(paths.STARTER, "merge-base", "--is-ancestor", commit, version["commit"]):
        target.blockers.append(f"the recorded starter commit {commit[:12]} is not an ancestor of the starter HEAD")
    else:
        target.up_to_date = commit == version["commit"]
        return not target.up_to_date
    return False


def _attach_plan(target: Target, plan: Plan) -> None:
    target.plan = plan
    dirty = _dirty(target.root, [*plan.writes, target.record_path.relative_to(target.root).as_posix()])
    if dirty:
        target.blockers.append(f"commit or stash these first so the upgrade arrives as its own reviewable change: {dirty}")


def _plan_repository(name: str, root: Path, version: dict, listings: dict) -> Target:
    target = Target(name, root, root / HARNESS_RECORD, "harness")
    if not target.record_path.is_file():
        target.blockers.append(f"{HARNESS_RECORD} is missing")
        return target
    try:
        record = load_manifest(target.record_path, "harness")
    except StarterError as error:
        target.blockers.append(str(error))
        return target
    target.commit = record["starter"]["commit"]
    if not _check_base(target, version):
        return target
    if record["starter"]["dirty"]:
        target.warning = "it was installed from a starter with uncommitted template changes; review the merged files closely"
    sources = {rel: f"template/{rel}" for rel in tree_files(paths.TEMPLATE)}
    plan = plan_upgrade(root, name, record["mode"], set(record["files"]), sources, lambda rel: f"template/{rel}",
                        _listing(listings, target.commit))
    _attach_plan(target, plan)
    target.record = {**record, "starter": version, "upgradedAt": date.today().isoformat(),
                     "files": {rel: file_hash(paths.TEMPLATE / rel) for rel in sorted(plan.owned)}}
    return target


def _plan_workspace(workspace: Path, manifest: dict, version: dict, listings: dict) -> Target:
    target = Target("workspace", workspace, workspace / WORKSPACE_FILE, "workspace", commit=manifest["starter"]["commit"])
    if not _check_base(target, version):
        return target
    listing = _listing(listings, target.commit)
    owned = {dest for dest in map(_guard_dest, listing) if dest}
    sources = {rel: f"workspace-template/{rel}" for rel in tree_files(paths.WORKSPACE_TEMPLATE)}
    sources.update({f"{GUARD_DIR}/{rel}": f"template/tool/{rel}" for rel in guard_files()})
    _attach_plan(target, plan_upgrade(workspace, "workspace", "workspace", owned, sources, _workspace_source, listing))
    target.record = {**manifest, "starter": version}
    return target


def run(workspace_path: str, names: list[str], dry_run: bool) -> dict:
    """Upgrades the workspace root and every repository in it that has the harness, or only the repositories in `names`."""
    workspace = resolve_workspace(workspace_path)
    manifest = load_workspace(workspace)
    if manifest is None:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE}.")
    version = _committed_starter()
    repos = {r["name"]: r for r in manifest["repos"]}
    for name in names:
        if name not in repos:
            raise StarterError(f"The workspace does not register {name!r}.")
        if repo_kind(workspace, repos[name]) != "managed":
            raise StarterError(f"{name!r} has no harness; install it with `harness install --repo {workspace / repos[name]['path']}` first.")

    listings: dict = {}
    targets = [_plan_workspace(workspace, manifest, version, listings)] if not names else []
    chosen = names or [r["name"] for r in manifest["repos"] if repo_kind(workspace, r) == "managed"]
    targets += [_plan_repository(name, workspace / repos[name]["path"], version, listings) for name in chosen]
    result = _apply(targets, version, dry_run)
    if not dry_run:
        result["warnings"] += remember_workspace(workspace)
    return result


def run_repository(repo_path: str, dry_run: bool) -> dict:
    """Upgrades one repository's harness, whether or not a workspace lists it. Nothing outside the repository is written."""
    repo = resolve_repo(repo_path)
    if not (repo / HARNESS_RECORD).is_file():
        raise StarterError(f"{repo} has no {HARNESS_RECORD}; install the harness with `harness install --repo {repo}` first.")
    version = _committed_starter()
    return _apply([_plan_repository(repo.name, repo, version, {})], version, dry_run)


def _committed_starter() -> dict:
    version = starter_version()
    if version["commit"] is None or version["dirty"]:
        raise StarterError("Commit the starter first: an upgrade records the starter commit as the base of the next one, "
                           "so template/ and workspace-template/ must match it.")
    return version


def _apply(targets: list[Target], version: dict, dry_run: bool) -> dict:
    """Writes every planned target together, or nothing when any target has a blocker."""
    for target in targets:
        if target.record is not None:
            target.blockers += [f"the updated {target.record_path.name} would be invalid: {error}"
                                for error in manifest_errors(target.record_kind, target.record)]
    blocked = [f"{t.name}: {blocker}" for t in targets for blocker in t.blockers]
    if blocked and not dry_run:
        raise StarterError("Nothing was written. " + " | ".join(blocked))

    if not dry_run:
        with Staging() as stage:
            for target in targets:
                if target.plan is not None:
                    _stage_writes(stage, target.root, target.plan.writes)
                    stage.write(target.record_path, manifest_bytes(target.record_path, target.record_kind, target.record))
    result = {"ok": True, "dryRun": dry_run, "starter": version, "targets": [t.report() for t in targets],
              "warnings": [f"{t.name}: {t.warning}" for t in targets if t.warning]}
    if not dry_run:
        planned = [t for t in targets if t.plan is not None]
        conflicts = [f"{t.root}/{rel}" for t in planned for rel in t.plan.conflicts]
        kept = [f"{t.root}/{entry['path']}" for t in planned for entry in t.plan.kept]
        result["next"] = ("Resolve the conflict markers in: " + ", ".join(conflicts) + ". " if conflicts else "") + \
            ("Each target kept its own value for the JSON keys under kept; compare them with the starter's in: " + ", ".join(kept) + ". "
             if kept else "") + \
            "Run `python3 tool/ai.py verify` in each upgraded repository and review the diff there; nothing was committed."
    return result
