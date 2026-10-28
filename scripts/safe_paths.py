"""Filesystem boundary helpers for explicitly selected local evaluation paths."""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path


class UnsafePathError(ValueError):
    """A path contains traversal, a link/reparse point, or an unexpected type."""


def _absolute_path(value: str | os.PathLike[str]) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise UnsafePathError("A filesystem path must be a string or Path.") from exc
    if not isinstance(raw, str) or not raw or "\0" in raw:
        raise UnsafePathError("A filesystem path must be a non-empty text path.")
    candidate = Path(raw).expanduser()
    if ".." in candidate.parts:
        raise UnsafePathError("Parent-directory traversal ('..') is not allowed in evaluation paths.")
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = Path(os.path.abspath(candidate))
    if os.name == "nt" and any(":" in part for part in candidate.parts[1:]):
        raise UnsafePathError("Alternate data stream path components are not allowed.")
    return candidate


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


def _reject_link_components(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if _is_link_or_reparse_point(current):
            raise UnsafePathError("Symlinks and filesystem reparse points are not allowed in evaluation paths.")


def checked_path(value: str | os.PathLike[str]) -> Path:
    """Normalize an explicit path after rejecting traversal and linked components."""
    candidate = _absolute_path(value)
    _reject_link_components(candidate)
    resolved = candidate.resolve(strict=False)
    if resolved != candidate:
        raise UnsafePathError("The evaluation path resolves through an unexpected filesystem target.")
    return resolved


def ensure_directory(value: str | os.PathLike[str], *, create: bool) -> Path:
    """Validate a chosen directory, creating missing ordinary directories if requested."""
    directory = checked_path(value)
    if directory == Path(directory.anchor):
        raise UnsafePathError("A filesystem root cannot be used as an evaluation directory.")
    if create:
        directory.mkdir(parents=True, exist_ok=True)
        directory = checked_path(directory)
    if not directory.exists() or not directory.is_dir():
        raise UnsafePathError("The selected evaluation directory does not exist or is not a directory.")
    return directory.resolve(strict=True)


def safe_read_text(value: str | os.PathLike[str], *, encoding: str = "utf-8") -> str:
    """Read an ordinary file selected by the operator or discovered under a safe root."""
    path = checked_path(value)
    if not path.exists() or not path.is_file():
        raise UnsafePathError("The selected evaluation input is not a regular file.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        current = path.lstat()
        if not stat.S_ISREG(opened.st_mode) or stat.S_ISLNK(current.st_mode):
            raise UnsafePathError("The selected evaluation input changed or is not a regular file.")
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise UnsafePathError("The selected evaluation input changed during validation.")
        with os.fdopen(descriptor, "r", encoding=encoding) as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def safe_write_text(
    value: str | os.PathLike[str], content: str, *, overwrite: bool = False,
    encoding: str = "utf-8",
) -> Path:
    """Write a regular file without following links; replace output atomically if requested."""
    target = checked_path(value)
    parent = ensure_directory(target.parent, create=False)
    target = checked_path(target)
    if target.exists() and target.is_dir():
        raise UnsafePathError("An evaluation output file cannot replace a directory.")

    if not overwrite:
        with target.open("x", encoding=encoding, newline="") as handle:
            handle.write(content)
        return target

    temporary = parent / f".{target.name}.{secrets.token_hex(12)}.tmp"
    temporary = checked_path(temporary)
    try:
        with temporary.open("x", encoding=encoding, newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        checked_path(target)
        os.replace(temporary, target)
    finally:
        if temporary.exists() and not _is_link_or_reparse_point(temporary):
            temporary.unlink()
    return target
