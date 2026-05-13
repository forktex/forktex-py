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

"""Live-instance registry.

Every ``forktex`` invocation that does real work writes a record at
``~/.forktex/instances/<run_id>.json`` (host) and, when a project is
involved, a mirror at ``<project>/.forktex/instances/<run_id>.json``.
Long-running commands additionally heartbeat the record every 30s.
Stale records (no heartbeat for 5 min, or PID gone for one-shots) are
garbage-collected at every new invocation.

The records are written through :mod:`forktex.graph.io_proxy` so they
flow through the structure spec and the host-wide registry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re as _re
import secrets
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from forktex_cloud import paths as _cloud_paths


_log = logging.getLogger("forktex.runtime.instance")

INSTANCE_DIRNAME = "instances"
HEARTBEAT_INTERVAL_SECS = 30.0
HEARTBEAT_STALE_AFTER_SECS = 300.0  # 5 minutes
ONESHOT_STALE_AFTER_SECS = 3600.0  # 1 hour
STOPPED_KEEP_SECS = 86400.0  # 24 hours


InstanceStatus = Literal["running", "stopping", "stopped"]


# ── Data model ────────────────────────────────────────────────────────────


@dataclass
class InstanceRecord:
    run_id: str
    command: list[str]
    kind: str  # "serve" | "repl" | "cloud-up" | "one-shot" | …
    pid: int
    ppid: int
    started_at: str
    last_heartbeat_at: str
    project_root: str | None = None
    stopped_at: str | None = None
    status: InstanceStatus = "running"
    long_running: bool = False
    extra: dict = field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def new_run_id() -> str:
    return secrets.token_hex(4)


def global_instances_dir() -> Path:
    return _cloud_paths.global_dir() / INSTANCE_DIRNAME


def project_instances_dir(project_root: Path) -> Path:
    return _cloud_paths.project_dir(project_root) / INSTANCE_DIRNAME


def _record_filename(run_id: str) -> str:
    return f"{run_id}.json"


# ── Read ──────────────────────────────────────────────────────────────────


def _load_record(path: Path) -> InstanceRecord | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # fmt: skip
        return None
    try:
        return InstanceRecord(
            run_id=data["run_id"],
            command=list(data.get("command", [])),
            kind=data.get("kind", "one-shot"),
            pid=int(data.get("pid", 0)),
            ppid=int(data.get("ppid", 0)),
            started_at=data.get("started_at", _now_iso()),
            last_heartbeat_at=data.get("last_heartbeat_at", _now_iso()),
            project_root=data.get("project_root"),
            stopped_at=data.get("stopped_at"),
            status=data.get("status", "running"),
            long_running=bool(data.get("long_running", False)),
            extra=dict(data.get("extra", {})),
        )
    except (KeyError, TypeError, ValueError):  # fmt: skip
        return None


def iter_running_instances() -> Iterator[InstanceRecord]:
    """Yield every host-wide instance record currently on disk.

    Includes stopped records until they're GC'd. Callers should filter
    by ``status``/age as needed.
    """
    base = global_instances_dir()
    if not base.is_dir():
        return iter([])
    records: list[InstanceRecord] = []
    for entry in sorted(base.glob("*.json")):
        rec = _load_record(entry)
        if rec is not None:
            records.append(rec)
    return iter(records)


# ── Write ─────────────────────────────────────────────────────────────────


def _write_record(rec: InstanceRecord) -> None:
    """Write the record to the global dir and (if known) the project mirror."""
    from forktex.graph.io_proxy import tracked_write

    payload = json.dumps(asdict(rec), indent=2, sort_keys=True) + "\n"
    rel = f"{INSTANCE_DIRNAME}/{_record_filename(rec.run_id)}"

    # Global mirror (always).
    _cloud_paths.ensure_global_dir()
    global_path = global_instances_dir() / _record_filename(rec.run_id)
    tracked_write(
        global_path,
        payload,
        kind="instance",
        writer="forktex.runtime.instance",
    )

    # Project mirror (when known).
    if rec.project_root:
        project_root = Path(rec.project_root)
        if project_root.is_dir():
            _cloud_paths.ensure_project_dirs(project_root)
            project_path = project_instances_dir(project_root) / _record_filename(
                rec.run_id
            )
            tracked_write(
                project_path,
                payload,
                kind="instance",
                writer="forktex.runtime.instance",
            )
            _ = rel  # silence linters; rel only used for documentation


# ── Argv redaction (SECURITY.md §F) ───────────────────────────────────────


_REDACT_KEY_RE = _re.compile(
    r"^(--?(?:api[-_]?key|token|password|secret|access[-_]?token|"
    r"client[-_]?secret|jwt|bearer|auth))(=|$)",
    flags=_re.IGNORECASE,
)
_REDACT_VALUE_PLACEHOLDER = "***REDACTED***"


def redact_argv(argv: list[str]) -> list[str]:
    """Mask credential-bearing flags in *argv* before persisting them.

    Catches both forms:

    * ``--api-key=ftx-abc123`` → ``--api-key=***REDACTED***``
    * ``--api-key`` ``ftx-abc123`` → ``--api-key`` ``***REDACTED***``

    Conservative on purpose: matches a small list of well-known flag
    names (api-key, token, password, secret, access-token,
    client-secret, jwt, bearer, auth) plus their underscore variants.
    Full case-insensitive. Anything not matching passes through.
    """
    out: list[str] = []
    redact_next = False
    for arg in argv:
        if redact_next:
            out.append(_REDACT_VALUE_PLACEHOLDER)
            redact_next = False
            continue
        match = _REDACT_KEY_RE.match(arg)
        if match is None:
            out.append(arg)
            continue
        sep = match.group(2)
        if sep == "=":
            out.append(f"{match.group(1)}={_REDACT_VALUE_PLACEHOLDER}")
        else:
            out.append(arg)
            redact_next = True
    return out


# ── Lifecycle ─────────────────────────────────────────────────────────────


def create_instance(
    *,
    kind: str = "one-shot",
    project_root: Path | None = None,
    long_running: bool = False,
    command: list[str] | None = None,
    extra: dict | None = None,
) -> InstanceRecord:
    """Create and persist a new instance record.

    Sensitive flags in ``command`` (``--api-key``, ``--token`` etc.) are
    redacted before the record is written to disk. See
    :func:`redact_argv` and ``SECURITY.md §F`` for the full policy.
    """
    now = _now_iso()
    raw_argv = list(command if command is not None else sys.argv)
    rec = InstanceRecord(
        run_id=new_run_id(),
        command=redact_argv(raw_argv),
        kind=kind,
        pid=os.getpid(),
        ppid=os.getppid(),
        started_at=now,
        last_heartbeat_at=now,
        project_root=str(project_root.resolve()) if project_root else None,
        long_running=long_running,
        extra=dict(extra or {}),
    )
    try:
        _write_record(rec)
    except Exception as exc:  # pragma: no cover - non-fatal
        _log.debug("failed to write instance record: %s", exc)
    return rec


def heartbeat_instance(rec: InstanceRecord) -> None:
    """Update ``last_heartbeat_at`` on an existing record."""
    rec.last_heartbeat_at = _now_iso()
    try:
        _write_record(rec)
    except Exception as exc:  # pragma: no cover
        _log.debug("failed to update heartbeat for %s: %s", rec.run_id, exc)


def close_instance(rec: InstanceRecord, *, status: InstanceStatus = "stopped") -> None:
    """Mark an instance stopped and persist."""
    rec.status = status
    rec.stopped_at = _now_iso()
    try:
        _write_record(rec)
    except Exception as exc:  # pragma: no cover
        _log.debug("failed to close instance %s: %s", rec.run_id, exc)


async def heartbeat_loop(
    rec: InstanceRecord,
    *,
    interval_secs: float = HEARTBEAT_INTERVAL_SECS,
) -> None:
    """Async heartbeat task; cancel to stop. Catches CancelledError so the
    surrounding ``finally`` can write a clean close record."""
    try:
        while True:
            await asyncio.sleep(interval_secs)
            heartbeat_instance(rec)
    except asyncio.CancelledError:
        return


# ── Garbage collection ────────────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # We can't signal it but it definitely exists.
        return True
    except OSError:
        return False
    return True


def _is_stale(rec: InstanceRecord, *, now: datetime) -> bool:
    started = _parse_iso(rec.started_at) or now
    if rec.status == "stopped":
        stopped = _parse_iso(rec.stopped_at) or started
        return (now - stopped).total_seconds() > STOPPED_KEEP_SECS

    # status == "running" or "stopping"
    if rec.long_running:
        last = _parse_iso(rec.last_heartbeat_at) or started
        return (now - last).total_seconds() > HEARTBEAT_STALE_AFTER_SECS

    age = (now - started).total_seconds()
    if age > ONESHOT_STALE_AFTER_SECS:
        return True
    return age > 60 and not _pid_alive(rec.pid)


def gc_stale_instances() -> int:
    """Delete stale instance records (host + project mirrors). Returns the
    number deleted."""
    deleted = 0
    now = datetime.now(timezone.utc)
    base = global_instances_dir()
    if not base.is_dir():
        return 0
    for entry in list(base.glob("*.json")):
        rec = _load_record(entry)
        if rec is None:
            try:
                entry.unlink()
                deleted += 1
            except OSError:
                pass
            continue
        if not _is_stale(rec, now=now):
            continue
        try:
            entry.unlink()
            deleted += 1
        except OSError:
            pass
        if rec.project_root:
            mirror = (
                Path(rec.project_root)
                / _cloud_paths.PROJECT_DIRNAME
                / INSTANCE_DIRNAME
                / _record_filename(rec.run_id)
            )
            try:
                mirror.unlink()
            except OSError:
                pass
    return deleted
