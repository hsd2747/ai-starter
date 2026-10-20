"""`upgrade`: bring starter changes into a workspace root and its managed repositories.

Every target is planned without writing; only when no target has a blocker are all writes staged and moved in together.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path

from . import paths
from .files import Staging, file_hash, tree_files
from .gitutil import git_ok, starter_version
from .install import MERGED_ON_ADOPT, pattern_lines, with_lines
from .manifests import load_manifest, manifest_bytes, manifest_errors
from .merge import merge_json, merge_text, merge_with_blocks
from .paths import GUARD_DIR, HARNESS_RECORD, WORKSPACE_FILE, StarterError, resolve_workspace
from .registry import remember_workspace
from .workspace import guard_files, load_workspace

# Seeds: installed once, then written by the repository. upgrade replaces only an untouched copy and never merges into one.
PROJECT_OWNED = {"wiki/index.md", "wiki/log.md"}


Content = tuple  # ("file", bytes) or ("link", bytes of the link target)


def _disk(path: Path) -> Content | None:
    if path.is_symlink():
        return ("link", os.readlink(path).encode())
    return ("file", path.read_bytes()) if path.is_file() else None


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


def _blob(listing: dict[str, tuple[str, str]], source: str) -> Content | None:
    if source not in listing:
        return None
    mode, blob = listing[source]
    data = subprocess.run(["git", "cat-file", "blob", blob], cwd=paths.STARTER, capture_output=True, check=True).stdout
    return ("link" if mode == "120000" else "file", data)


def plan_upgrade(root: Path, label: str, owned: set[str], sources: dict[str, str], base_source, listing: dict,
                 append_only: set[str] = frozenset()) -> dict:
    """What an upgrade does to one target, computed without writing.

    `owned` are the destination paths the starter installed at the recorded commit, `sources` maps every destination path
    the starter ships now to its starter path, and `base_source` maps a destination path to its starter path at that commit.
    """
    plan: dict = {"writes": {}, "owned": set(), "updated": [], "merged": [], "conflicts": [], "kept": [], "added": [], "skipped": [],
                  "removedUpstream": []}
    for rel in sorted(owned | sources.keys()):
        ours = _disk(root / rel)
        if rel not in sources:
            if ours is not None:
                plan["removedUpstream"].append(rel)
            continue
        theirs = _disk(paths.STARTER / sources[rel])
        base = _blob(listing, base_source(rel)) if rel in owned else None
        if rel in owned or ours == theirs:
            plan["owned"].add(rel)
        if ours == theirs or (base is not None and base == theirs):
            continue
        if rel not in owned:
            if ours is None:
                plan["writes"][rel] = (theirs, sources[rel])
                plan["added"].append(rel)
                plan["owned"].add(rel)
            else:
                plan["skipped"].append({"path": rel, "reason": "new in the starter but a different file already exists here; merge by hand"})
            continue
        if base is None:
            plan["skipped"].append({"path": rel, "reason": "not in the recorded starter commit, so there is no base to merge from"})
        elif ours is None:
            plan["skipped"].append({"path": rel, "reason": "deleted here but changed in the starter; restore it by hand if it is still wanted"})
        elif ours == base:
            plan["writes"][rel] = (theirs, sources[rel])
            plan["updated"].append(rel)
        elif rel in PROJECT_OWNED:
            plan["skipped"].append({"path": rel, "reason": "the target writes this file after install; compare it with the starter's copy by hand"})
        elif "link" in (ours[0], base[0], theirs[0]) or any(b"\0" in c[1] for c in (ours, base, theirs)):
            plan["skipped"].append({"path": rel, "reason": "changed both here and in the starter, and it is a link or binary; merge by hand"})
        elif rel in append_only:
            present = {line.strip() for line in ours[1].decode().splitlines()}
            installed = {line.strip() for line in base[1].decode().splitlines()}
            missing = [line for line in pattern_lines(theirs[1].decode()) if line.strip() not in installed | present]
            if missing:
                plan["writes"][rel] = (("file", with_lines(ours[1].decode(), missing).encode()), sources[rel])
                plan["merged"].append(rel)
        elif rel.endswith(".json") and (outcome := merge_json(rel, ours[1], base[1], theirs[1])) is not None:
            if isinstance(outcome, str):
                plan["skipped"].append({"path": rel, "reason": outcome})
                continue
            data, kept = outcome
            if data is not None:
                plan["writes"][rel] = (("file", data), sources[rel])
                plan["merged"].append(rel)
            if kept:
                plan["kept"].append({"path": rel, "keys": kept})
        else:
            outcome = merge_with_blocks(ours[1], base[1], theirs[1], label) or merge_text(ours[1], base[1], theirs[1], label)
            if isinstance(outcome, str):
                plan["skipped"].append({"path": rel, "reason": outcome})
                continue
            merged, conflicts = outcome
            plan["writes"][rel] = (("file", merged), sources[rel])
            plan["conflicts" if conflicts else "merged"].append(rel)
    return plan


def _dirty(root: Path, paths: list[str]) -> list[str]:
    output = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", *paths], cwd=root,
                            capture_output=True, text=True).stdout
    return sorted(line[3:] for line in output.splitlines())


def _stage_writes(stage: Staging, root: Path, writes: dict[str, tuple[Content, str]]) -> None:
    for rel, ((kind, data), source) in writes.items():
        if kind == "link":
            stage.link(root / rel, data.decode())
        else:
            stage.write(root / rel, data, mode_from=paths.STARTER / source)


def _guard_dest(source: str) -> str | None:
    """Destination in the workspace root of a starter path, for the files a workspace copies."""
    if source.startswith("workspace-template/"):
        return source.removeprefix("workspace-template/")
    if source == "template/tool/ai.py" or source.startswith("template/tool/ai_harness/"):
        return f"{GUARD_DIR}/{source.removeprefix('template/tool/')}"
    return None


def _workspace_source(rel: str) -> str:
    return f"template/tool/{rel.removeprefix(GUARD_DIR + '/')}" if rel.startswith(GUARD_DIR + "/") else f"workspace-template/{rel}"


def _target_report(name: str, root: Path, commit: str | None) -> dict:
    return {"target": name, "path": str(root), "from": commit, "blockers": []}


def _check_base(report: dict, commit: str | None, version: dict) -> bool:
    if not commit:
        report["blockers"].append("no starter commit is recorded, so there is no base to merge from; upgrade it by hand")
    elif not git_ok(paths.STARTER, "cat-file", "-e", f"{commit}^{{commit}}"):
        report["blockers"].append(f"the recorded starter commit {commit[:12]} is not in this starter's history")
    elif not git_ok(paths.STARTER, "merge-base", "--is-ancestor", commit, version["commit"]):
        report["blockers"].append(f"the recorded starter commit {commit[:12]} is not an ancestor of the starter HEAD")
    else:
        report["upToDate"] = commit == version["commit"]
        return not report["upToDate"]
    return False


def _finish_plan(report: dict, root: Path, plan: dict, record: str) -> None:
    for key in ("updated", "merged", "conflicts", "kept", "added", "skipped", "removedUpstream"):
        report[key] = plan[key]
    dirty = _dirty(root, [*plan["writes"], record])
    if dirty:
        report["blockers"].append(f"commit or stash these first so the upgrade arrives as its own reviewable change: {dirty}")


def _plan_repository(workspace: Path, repo: dict, version: dict, listings: dict) -> tuple[dict, dict | None]:
    root = workspace / repo["path"]
    record_path = root / HARNESS_RECORD
    report = _target_report(repo["name"], root, None)
    if not record_path.is_file():
        report["blockers"].append(f"{HARNESS_RECORD} is missing")
        return report, None
    try:
        record = load_manifest(record_path, "harness")
    except StarterError as error:
        report["blockers"].append(str(error))
        return report, None
    commit = report["from"] = record["starter"]["commit"]
    if not _check_base(report, commit, version):
        return report, None
    if record["starter"]["dirty"]:
        report["warning"] = "it was installed from a starter with uncommitted template changes; review the merged files closely"
    listing = listings.setdefault(commit, _starter_listing(commit))
    sources = {rel: f"template/{rel}" for rel in tree_files(paths.TEMPLATE)}
    append_only = MERGED_ON_ADOPT if record["mode"] == "adopt" else set()
    plan = plan_upgrade(root, repo["name"], set(record["files"]), sources, lambda rel: f"template/{rel}", listing, append_only)
    _finish_plan(report, root, plan, HARNESS_RECORD)
    record = {**record, "starter": version, "upgradedAt": date.today().isoformat(),
              "files": {rel: file_hash(paths.TEMPLATE / rel) for rel in sorted(plan["owned"])}}
    return report, {"root": root, "plan": plan, "record_path": record_path, "record_kind": "harness", "record": record}


def _plan_workspace(workspace: Path, manifest: dict, version: dict, listings: dict) -> tuple[dict, dict | None]:
    commit = manifest["starter"]["commit"]
    report = _target_report("workspace", workspace, commit)
    if not _check_base(report, commit, version):
        return report, None
    listing = listings.setdefault(commit, _starter_listing(commit))
    owned = {dest for dest in map(_guard_dest, listing) if dest}
    sources = {rel: f"workspace-template/{rel}" for rel in tree_files(paths.WORKSPACE_TEMPLATE)}
    sources.update({f"{GUARD_DIR}/{rel}": f"template/tool/{rel}" for rel in guard_files()})
    plan = plan_upgrade(workspace, "workspace", owned, sources, _workspace_source, listing)
    _finish_plan(report, workspace, plan, WORKSPACE_FILE)
    return report, {"root": workspace, "plan": plan, "record_path": workspace / WORKSPACE_FILE, "record_kind": "workspace",
                    "record": {**manifest, "starter": version}}


def run(workspace_path: str, names: list[str], dry_run: bool) -> dict:
    """Upgrades the workspace root and every managed repository, or only the repositories in `names`."""
    workspace = resolve_workspace(workspace_path)
    manifest = load_workspace(workspace)
    if manifest is None:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE}.")
    version = starter_version()
    if version["commit"] is None or version["dirty"]:
        raise StarterError("Commit the starter first: an upgrade records the starter commit as the base of the next one, "
                           "so template/ and workspace-template/ must match it.")
    repos = {r["name"]: r for r in manifest["repos"]}
    for name in names:
        if name not in repos:
            raise StarterError(f"The workspace does not register {name!r}.")
        if repos[name]["kind"] != "managed":
            raise StarterError(f"{name!r} is registered without the harness; install it with `adopt --install` instead.")

    listings: dict = {}
    planned = [_plan_workspace(workspace, manifest, version, listings)] if not names else []
    targets = names or [r["name"] for r in manifest["repos"] if r["kind"] == "managed"]
    planned += [_plan_repository(workspace, repos[name], version, listings) for name in targets]
    for report, work in planned:
        if work:
            report["blockers"] += [f"the updated {work['record_path'].name} would be invalid: {error}"
                                   for error in manifest_errors(work["record_kind"], work["record"])]
    reports = [report for report, _ in planned]
    blocked = [f"{r['target']}: {b}" for r in reports for b in r["blockers"]]
    if blocked and not dry_run:
        raise StarterError("Nothing was written. " + " | ".join(blocked))

    if not dry_run:
        with Staging() as stage:
            for _, work in planned:
                if work:
                    _stage_writes(stage, work["root"], work["plan"]["writes"])
                    stage.write(work["record_path"], manifest_bytes(work["record_path"], work["record_kind"], work["record"]))
    conflicts = [f"{r['path']}/{c}" for r in reports for c in r.get("conflicts", [])]
    result = {"ok": True, "dryRun": dry_run, "starter": version, "targets": reports,
              "warnings": [f"{r['target']}: {r['warning']}" for r in reports if r.get("warning")]}
    if not dry_run:
        result["warnings"] += remember_workspace(workspace)
        kept = [f"{r['path']}/{k['path']}" for r in reports for k in r.get("kept", [])]
        result["next"] = ("Resolve the conflict markers in: " + ", ".join(conflicts) + ". " if conflicts else "") + \
            ("Each target kept its own value for the JSON keys under kept; compare them with the starter's in: " + ", ".join(kept) + ". "
             if kept else "") + \
            "Run `python3 tool/ai.py verify` in each upgraded repository and review the diff there; nothing was committed."
    return result
