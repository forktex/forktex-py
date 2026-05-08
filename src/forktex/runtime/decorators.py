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

"""AOP-style decorators for compliance + lifecycle.

Four decorators, each stamps a metadata attribute on the wrapped function
so tests (and a future linter) can introspect coverage:

* ``@tracked_writer(spec_pattern, kind, scope='project')`` — declares a
  function as a structured writer. The wrapped function returns
  ``(Path, str | bytes)``; the decorator validates the path against the
  structure spec at decoration time AND at call time, then routes the
  write through :func:`forktex.graph.io_proxy.tracked_write`.

* ``@sdk_boundary(scope='project', project_root_arg='project_root')`` —
  wraps a sibling-SDK call that may write into ``.forktex/``. Snapshots
  the directory before, runs the call, walks the diff after, and
  validates each new/changed file against the structure spec. Records
  every write in the registry.

* ``@needs_project`` — auto-resolves a project root via
  :func:`forktex.core.paths.find_project_root` and calls
  :func:`forktex.runtime.lifecycle.ensure_runtime`. Errors fast (with
  the helpful message) if invoked outside a project.

* ``@long_running(label)`` — for commands that don't return promptly
  (``serve``, REPL). Spawns the heartbeat task at entry, registers
  signal handlers, writes the close record on exit.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
from pathlib import Path
from typing import Any, Callable

from forktex.graph.io_proxy import StructureViolation, _classify, tracked_write
from forktex.graph.registry import record_touch
from forktex.graph.structure import GLOBAL_SPEC, PROJECT_SPEC, Scope, validate_path
from forktex.runtime import instance as _instance
from forktex.runtime import lifecycle as _lifecycle


# ── @tracked_writer ───────────────────────────────────────────────────────


def _spec_known(scope: Scope, pattern: str) -> bool:
    spec = PROJECT_SPEC if scope == "project" else GLOBAL_SPEC
    return any(e.pattern == pattern for e in spec)


def tracked_writer(
    *,
    spec_pattern: str,
    kind: str,
    scope: Scope = "project",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare a function as a structured writer.

    The wrapped function must return ``(path, content)`` where ``path`` is
    a :class:`pathlib.Path` (absolute or relative — relative is resolved
    against cwd) and ``content`` is ``str`` or ``bytes``.

    Usage::

        @tracked_writer(spec_pattern="cloud.json", kind="cloud_settings")
        def save_cloud_context_global(ctx) -> tuple[Path, str]:
            return path, json.dumps(...)

    The function gains a ``__forktex_spec__`` attribute carrying
    ``(spec_pattern, kind, scope)`` for test introspection.
    """

    if not _spec_known(scope, spec_pattern):
        raise ValueError(
            f"@tracked_writer references unknown {scope}-scope spec entry "
            f"{spec_pattern!r}; add it to forktex.graph.structure first."
        )

    def _decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if not (isinstance(result, tuple) and len(result) == 2):
                raise TypeError(
                    f"@tracked_writer-wrapped {fn.__qualname__} must return "
                    f"(Path, str|bytes); got {type(result).__name__}"
                )
            path, content = result
            if not isinstance(path, Path):
                path = Path(path)
            return tracked_write(
                path,
                content,
                kind=kind,
                writer=fn.__qualname__,
            )

        _wrapper.__forktex_spec__ = (spec_pattern, kind, scope)  # type: ignore[attr-defined]
        return _wrapper

    return _decorate


# ── @sdk_boundary ─────────────────────────────────────────────────────────


def _snapshot(forktex_dir: Path) -> dict[str, tuple[float, str]]:
    """Snapshot ``.forktex/`` as ``{rel: (mtime, sha256_short)}``.

    Hash is computed only for files. Returns empty dict if dir doesn't exist.
    """
    out: dict[str, tuple[float, str]] = {}
    if not forktex_dir.is_dir():
        return out
    for path in forktex_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()[:12]
            rel = path.relative_to(forktex_dir).as_posix()
            out[rel] = (stat.st_mtime, digest)
        except OSError:
            continue
    return out


def sdk_boundary(
    *,
    scope: Scope = "project",
    project_root_arg: str = "project_root",
    strict: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a sibling-SDK call that may write into ``.forktex/``.

    Snapshots ``.forktex/`` before, runs the call, walks the diff after,
    and validates each new/changed file against the structure spec. Each
    new/changed file is also recorded via :func:`record_touch` so the
    host-wide registry stays consistent.

    ``strict=True`` (default) raises :class:`StructureViolation` for any
    unspec'd path the SDK produced. ``strict=False`` warns but proceeds.
    """

    def _decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def _wrapper(*args, **kwargs):
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            project_root_value = bound.arguments.get(project_root_arg)
            if project_root_value is None:
                # Nothing to monitor; pass through.
                return fn(*args, **kwargs)
            project_root = Path(project_root_value).resolve()
            forktex_dir = (
                project_root / ".forktex"
                if scope == "project"
                else _root_global_forktex_dir()
            )

            before = _snapshot(forktex_dir)
            result = fn(*args, **kwargs)
            after = _snapshot(forktex_dir)

            for rel, after_meta in after.items():
                before_meta = before.get(rel)
                if before_meta == after_meta:
                    continue  # unchanged
                match = validate_path(scope, rel)
                if not match.ok:
                    msg = (
                        f"@sdk_boundary detected an unspec'd write to "
                        f"{rel!r} from {fn.__qualname__}: {match.reason}"
                    )
                    if strict:
                        raise StructureViolation(msg)
                    import logging

                    logging.getLogger("forktex.runtime.decorators").warning(msg)
                # Record the touch in the registry regardless of strict mode.
                full = forktex_dir / rel
                classified = _classify(full)
                if classified is None:
                    continue
                rec_scope, base, rel_path = classified
                record_touch(
                    project_root=base.parent if rec_scope == "project" else None,
                    rel_path=rel_path,
                    kind="sdk_write",
                    writer=fn.__qualname__,
                )
            return result

        _wrapper.__forktex_role__ = ("sdk_boundary", scope, fn.__qualname__)  # type: ignore[attr-defined]
        return _wrapper

    return _decorate


def _root_global_forktex_dir() -> Path:
    from forktex_cloud import paths as _cloud_paths

    return _cloud_paths.global_dir()


# ── Shared project resolution ────────────────────────────────────────────


def _resolve_project(hint: str | None) -> Path | None:
    """Walk upward from *hint* (or cwd) looking for a ``forktex.json``.

    Returns the resolved root or ``None`` when not found. Both
    :func:`needs_project` (which raises) and :func:`long_running`
    (which falls back to host scope) call this single helper.
    """
    from forktex.core.paths import find_project_root

    start = Path(hint).resolve() if hint else Path.cwd().resolve()
    return find_project_root(start)


def _resolve_project_required(hint: str | None) -> Path:
    """Like :func:`_resolve_project`, but raise a helpful CLI error when
    no ``forktex.json`` is found."""
    import asyncclick as click  # type: ignore[import-not-found]

    root = _resolve_project(hint)
    if root is None:
        start = Path(hint).resolve() if hint else Path.cwd().resolve()
        raise click.ClickException(
            f"no forktex.json found at or above {start}.\n"
            "Run from a project directory, pass --project /path/to/project, "
            "or use a host-scope command instead."
        )
    return root


# ── @needs_project ────────────────────────────────────────────────────────


def needs_project(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Auto-resolve a project root for a Click command.

    Looks for a ``project`` keyword argument; falls back to cwd. Walks
    upward via :func:`find_project_root`. Raises :class:`click.ClickException`
    with a helpful message if no ``forktex.json`` is found.

    Calls :func:`lifecycle.ensure_runtime` and stores the resulting
    ``InstanceRecord`` on the wrapped function's local context. The wrapped
    function receives the resolved project root as ``project_root`` keyword
    if its signature accepts it; otherwise it's only used internally.
    """

    sig = inspect.signature(fn)
    accepts_project_root = "project_root" in sig.parameters
    is_async = inspect.iscoroutinefunction(fn)

    def _maybe_register(root):
        # If an outer decorator (e.g. @long_running) already created an
        # instance record for this invocation, don't double-register.
        if _lifecycle._active_instances:
            return None
        return _lifecycle.ensure_runtime(
            needs_project=True,
            kind=fn.__name__.replace("_cmd", "").replace("_", "-"),
            project_hint=str(root),
        )

    if is_async:

        @functools.wraps(fn)
        async def _async_wrapper(*args, **kwargs):
            root = _resolve_project_required(kwargs.get("project"))
            rec = _maybe_register(root)
            try:
                if accepts_project_root:
                    kwargs.setdefault("project_root", root)
                return await fn(*args, **kwargs)
            finally:
                if rec is not None and not rec.long_running:
                    _lifecycle.deactivate(rec)

        _async_wrapper.__forktex_role__ = ("needs_project", fn.__qualname__)  # type: ignore[attr-defined]
        return _async_wrapper

    @functools.wraps(fn)
    def _sync_wrapper(*args, **kwargs):
        root = _resolve_project_required(kwargs.get("project"))
        rec = _maybe_register(root)
        try:
            if accepts_project_root:
                kwargs.setdefault("project_root", root)
            return fn(*args, **kwargs)
        finally:
            if rec is not None and not rec.long_running:
                _lifecycle.deactivate(rec)

    _sync_wrapper.__forktex_role__ = ("needs_project", fn.__qualname__)  # type: ignore[attr-defined]
    return _sync_wrapper


# ── @long_running ─────────────────────────────────────────────────────────


def long_running(*, label: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark an async Click command as long-running.

    On entry: spawns a heartbeat task that updates the instance record
    every 30s. Composes with ``@needs_project`` (apply ``@long_running``
    above ``@needs_project`` so the long-running flag propagates into
    ``ensure_runtime``).
    """

    def _decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(
                f"@long_running expects an async function; {fn.__qualname__} is sync."
            )

        @functools.wraps(fn)
        async def _wrapper(*args, **kwargs):
            project_root = _resolve_project(kwargs.get("project"))
            if project_root is None:
                # Fallback: still register a host-scope long-running record.
                rec = _lifecycle.ensure_runtime(
                    needs_project=False,
                    long_running=True,
                    kind=label,
                )
            else:
                rec = _lifecycle.ensure_runtime(
                    needs_project=True,
                    long_running=True,
                    kind=label,
                    project_hint=str(project_root),
                )

            heartbeat_task: asyncio.Task | None = None
            if rec is not None:
                heartbeat_task = asyncio.create_task(
                    _instance.heartbeat_loop(rec), name=f"forktex-heartbeat-{label}"
                )
            try:
                return await fn(*args, **kwargs)
            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except (asyncio.CancelledError, Exception):  # fmt: skip
                        pass
                if rec is not None:
                    _lifecycle.deactivate(rec)

        _wrapper.__forktex_role__ = ("long_running", label, fn.__qualname__)  # type: ignore[attr-defined]
        return _wrapper

    return _decorate
