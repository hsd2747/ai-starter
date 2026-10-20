"""Reading the template trees, and writing files only through Staging so that a failure leaves targets as they were."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from .paths import StarterError

SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_PATHS = {".ai/runs"}


def _skipped(relative: str) -> bool:
    parts = relative.split("/")
    return any(part in SKIP_NAMES for part in parts) or relative.endswith(".pyc") or any(
        relative == p or relative.startswith(p + "/") for p in SKIP_PATHS)


def tree_files(source: Path) -> list[str]:
    """Files and symlinks under `source` as sorted relative paths. Symlinked directories stay links."""
    found = []
    for directory, dirnames, filenames in os.walk(source):
        base = Path(directory)
        for name in list(dirnames):
            if (base / name).is_symlink():
                dirnames.remove(name)
                filenames.append(name)
        for name in filenames:
            relative = (base / name).relative_to(source).as_posix()
            if not _skipped(relative):
                found.append(relative)
        dirnames[:] = [d for d in dirnames if not _skipped((base / d).relative_to(source).as_posix())]
    return sorted(found)


def file_hash(path: Path) -> str:
    data = b"link:" + os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


class Staging:
    """Collects writes as temporary files beside their destinations and moves them into place only on a clean exit.

    A failure while collecting removes the temporary files and leaves every destination as it was. Moving in is one
    rename per file, so it can only stop between two files, and the error then names the files already replaced.
    """

    def __init__(self) -> None:
        self._pending: list[tuple[Path, Path]] = []
        self._new_dirs: list[Path] = []

    def __enter__(self) -> Staging:
        return self

    def __exit__(self, kind, error, trace) -> bool:
        if kind is None:
            self._commit()
        else:
            self._discard()
        return False

    def _temp(self, dest: Path) -> Path:
        missing = []
        for directory in [dest.parent, *dest.parent.parents]:
            if os.path.lexists(directory):
                break
            missing.append(directory)
        for directory in reversed(missing):
            directory.mkdir()
            self._new_dirs.append(directory)
        temp = dest.with_name(f".{dest.name}.{uuid.uuid4().hex[:12]}.starter-tmp")
        self._pending.append((temp, dest))
        return temp

    def write(self, dest: Path, data: bytes, mode_from: Path | None = None) -> None:
        """`mode_from` gives the permission bits; by default an existing regular file at `dest` keeps its own."""
        mode_from = mode_from or (dest if dest.is_file() and not dest.is_symlink() else None)
        temp = self._temp(dest)
        with open(temp, "xb") as handle:
            handle.write(data)
        if mode_from is not None:
            shutil.copymode(mode_from, temp)

    def link(self, dest: Path, target: str) -> None:
        os.symlink(target, self._temp(dest))

    def copy(self, source: Path, dest: Path) -> None:
        if source.is_symlink():
            self.link(dest, os.readlink(source))
        else:
            shutil.copy2(source, self._temp(dest))

    def _discard(self) -> None:
        for temp, _ in self._pending:
            if os.path.lexists(temp):
                temp.unlink()
        for directory in reversed(self._new_dirs):
            with contextlib.suppress(OSError):
                directory.rmdir()
        self._pending, self._new_dirs = [], []

    def _commit(self) -> None:
        done: list[str] = []
        try:
            for temp, dest in self._pending:
                if dest.is_dir() and not dest.is_symlink():
                    raise IsADirectoryError(f"{dest} is a directory")
                os.replace(temp, dest)
                done.append(str(dest))
        except OSError as error:
            left = [str(dest) for _, dest in self._pending[len(done):]]
            self._pending = self._pending[len(done):]
            self._discard()
            raise StarterError(f"Stopped while moving files into place ({error}). Replaced: {done or 'none'}. "
                               f"Not replaced: {left}. The replaced files are complete; nothing else was changed.") from None
        self._pending, self._new_dirs = [], []


def write_atomic(path: Path, data: bytes) -> None:
    with Staging() as stage:
        stage.write(path, data)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StarterError(f"Cannot read {path}: {error}") from None


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
