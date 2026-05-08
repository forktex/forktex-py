# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""AOP-style write proxy for ForkTex's on-disk footprint.

Every write that targets a ``.forktex/`` directory (project-local or the
global ``~/.forktex/``) routes through :func:`tracked_write`. The proxy:

1. Validates the destination against :mod:`forktex.graph.structure` —
   unknown paths are rejected (legal/integrity), unless the caller opts
   into lenient mode or the ``FORKTEX_STRUCTURE_LENIENT=1`` env var is set.
2. Performs an atomic write (tempfile + ``os.replace``) so partial writes
   never appear on disk.
3. Records the touch in :mod:`forktex.graph.registry` so the host-OS
   graph and ``forktex graph purge`` know about it.

A complementary :func:`install_audit_hook` adds a ``sys.audit``-based
safety net that *logs* (does not intercept) any unsanctioned ``open``
call into a ``.forktex/`` path. Use it from the CLI entry point so missed
call sites surface in dev.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

from forktex_cloud import paths as _cloud_paths

from forktex.graph import registry as _registry
from forktex.graph.structure import EntrySpec, Scope, validate_path


_log = logging.getLogger("forktex.graph.io_proxy")

PROJECT_DIRNAME = _cloud_paths.PROJECT_DIRNAME

_LENIENT_ENV = "FORKTEX_STRUCTURE_LENIENT"


# ── Path classification ───────────────────────────────────────────────────


class StructureViolation(RuntimeError):
    """Raised when a write targets a non-canonical path inside ``.forktex/``."""


def _is_lenient(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    return os.environ.get(_LENIENT_ENV, "").lower() in {"1", "true", "yes"}


def _classify(path: Path) -> tuple[Scope, Path, str] | None:
    """Return ``(scope, base, rel_path_str)`` if *path* is inside a
    ``.forktex/`` directory, otherwise ``None``."""

    abs_path = path.resolve()
    parts = abs_path.parts

    # Global scope first (more specific path).
    global_dir = _cloud_paths.global_dir().resolve()
    try:
        rel = abs_path.relative_to(global_dir)
        return ("os", global_dir, rel.as_posix())
    except ValueError:
        pass

    # Project scope: walk up looking for an enclosing ``.forktex`` segment.
    for i, part in enumerate(parts):
        if part == PROJECT_DIRNAME:
            base = Path(*parts[: i + 1])
            rel = Path(*parts[i + 1 :])
            return ("project", base, rel.as_posix())
    return None


# ── Shared validation / recording helpers ────────────────────────────────


_Classified = tuple[Scope, Path, str]


def _validate_classified(
    target: Path, *, writer: str | None, lenient: bool | None
) -> _Classified | None:
    """Classify *target* and validate against the structure spec.

    Returns the ``(scope, base, rel_path)`` tuple when the path is under
    a ``.forktex/`` directory, ``None`` otherwise. Raises
    :class:`StructureViolation` for unsanctioned paths unless lenient
    mode is in effect, in which case it logs a warning and returns the
    classified tuple anyway. Also emits a debug log when ``writer`` is
    not in the spec's declared writer list.
    """
    classified = _classify(target)
    if classified is None:
        return None
    scope, _base, rel_path = classified
    match = validate_path(scope, rel_path)
    if not match.ok:
        msg = (
            f"refusing to write {rel_path!r} under {scope}-scope .forktex/: "
            f"{match.reason}"
        )
        if _is_lenient(lenient):
            _log.warning("%s — proceeding (lenient mode)", msg)
        else:
            raise StructureViolation(msg)
    spec: EntrySpec | None = match.spec
    if (
        spec is not None
        and spec.writers
        and writer is not None
        and writer not in spec.writers
    ):
        _log.debug(
            "writer %s not in declared writers for %s (%s)",
            writer,
            spec.pattern,
            ", ".join(spec.writers),
        )
    return classified


def _record_classified(
    classified: _Classified | None, *, kind: str, writer: str | None
) -> None:
    """Record a touch for a previously-classified path. No-op when the
    write was outside ``.forktex/``."""
    if classified is None:
        return
    scope, base, rel_path = classified
    if scope == "project":
        _registry.record_touch(
            project_root=base.parent,
            rel_path=rel_path,
            kind=kind,
            writer=writer,
        )
    elif rel_path != _registry.REGISTRY_FILENAME:
        # Skip recursive recording when writing the registry itself.
        _registry.record_touch(
            project_root=None,
            rel_path=rel_path,
            kind=kind,
            writer=writer,
        )


def _atomic_write(path: Path, content: str | bytes, *, encoding: str) -> None:
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        if isinstance(content, bytes):
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
        else:
            with os.fdopen(fd, "w", encoding=encoding) as fh:
                fh.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ── Public API ────────────────────────────────────────────────────────────


def tracked_write(
    path: Path | str,
    content: str | bytes,
    *,
    kind: str,
    writer: str | None = None,
    encoding: str = "utf-8",
    lenient: bool | None = None,
) -> Path:
    """Atomically write *content* to *path*, validating the structure spec.

    ``kind`` is a free-form short label (e.g. ``"graph_export"``,
    ``"settings"``) recorded in the registry. ``writer`` is the dotted name
    of the calling module — used for blame/audit and the structure spec's
    ``writers`` field.

    Writes outside any ``.forktex/`` directory pass through without
    registry side-effects (this helper is general but only enforces inside
    the canonical footprint).
    """
    target = Path(path)
    classified = _validate_classified(target, writer=writer, lenient=lenient)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, content, encoding=encoding)
    _record_classified(classified, kind=kind, writer=writer)
    return target


# ── Async + append helpers ────────────────────────────────────────────────


async def tracked_write_async(
    path: Path | str,
    content: str | bytes,
    *,
    kind: str,
    writer: str | None = None,
    encoding: str = "utf-8",
    lenient: bool | None = None,
) -> Path:
    """Async parity of :func:`tracked_write`.

    Uses ``aiofiles`` for the actual write so it's safe to call from inside
    an event loop without blocking. Validation + registry recording use the
    same code path as the sync variant.
    """
    import aiofiles  # type: ignore[import-not-found]

    target = Path(path)
    classified = _validate_classified(target, writer=writer, lenient=lenient)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(fd)
    try:
        if isinstance(content, bytes):
            async with aiofiles.open(tmp_name, "wb") as fh:
                await fh.write(content)
        else:
            async with aiofiles.open(tmp_name, "w", encoding=encoding) as fh:
                await fh.write(content)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    _record_classified(classified, kind=kind, writer=writer)
    return target


def tracked_append(
    path: Path | str,
    line: str,
    *,
    kind: str,
    writer: str | None = None,
    encoding: str = "utf-8",
    lenient: bool | None = None,
) -> Path:
    """Append one line of text to a file (e.g. JSONL) under structure-spec
    enforcement.

    Atomicity is per-line: a tempfile re-writes the existing content + the
    new line, then renames. Slower than a raw append but consistent with
    the rest of ``tracked_write``'s safety contract for files small enough
    to fit in memory (agent history JSONLs typically tens of KB).
    """
    target = Path(path)
    classified = _validate_classified(target, writer=writer, lenient=lenient)
    target.parent.mkdir(parents=True, exist_ok=True)

    if not line.endswith("\n"):
        line = line + "\n"
    existing = ""
    if target.is_file():
        try:
            existing = target.read_text(encoding=encoding)
        except OSError:
            existing = ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
    _atomic_write(target, existing + line, encoding=encoding)

    _record_classified(classified, kind=kind, writer=writer)
    return target


# ── Audit safety net ──────────────────────────────────────────────────────


_AUDIT_INSTALLED = False


def install_audit_hook() -> None:
    """Install a one-shot ``sys.audit`` hook that *logs* uncategorised writes.

    Idempotent. Safe to call from the CLI entry point.

    The hook is observation-only: it never blocks IO, it just produces a
    warning when a write into a ``.forktex/`` path was not made by
    :func:`tracked_write`. Use the warnings to convert remaining direct
    writers to ``tracked_write``.
    """

    global _AUDIT_INSTALLED
    if _AUDIT_INSTALLED:
        return
    _AUDIT_INSTALLED = True

    def _hook(event: str, args: tuple) -> None:  # pragma: no cover
        if event != "open":
            return
        if not args:
            return
        target = args[0]
        if isinstance(target, bytes):
            try:
                target = target.decode("utf-8", errors="replace")
            except (UnicodeDecodeError, AttributeError):  # fmt: skip
                return
        if not isinstance(target, (str, os.PathLike)):
            return
        try:
            target_path = Path(os.fspath(target))
        except (TypeError, ValueError):  # fmt: skip
            return
        # ``open`` with mode flag in args[1]; only flag writes.
        mode = args[1] if len(args) > 1 else "r"
        if isinstance(mode, str) and not any(c in mode for c in "wax+"):
            return
        try:
            classified = _classify(target_path)
        except (OSError, ValueError):  # fmt: skip
            return
        if classified is None:
            return
        _scope, _base, rel_path = classified
        if not rel_path or rel_path == ".":
            # Bare ``.forktex/`` directory mention (e.g., mkdir target);
            # not a file write inside the canonical footprint.
            return
        # Skip our own atomic-rename tempfiles (prefix '.<name>.').
        if target_path.name.startswith(".") and target_path.name.endswith(".tmp"):
            return
        _log.warning(
            "untracked .forktex write: %s (consider routing through "
            "forktex.graph.io_proxy.tracked_write)",
            target_path,
        )

    sys.addaudithook(_hook)
