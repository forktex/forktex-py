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

"""Tests for the live-instance registry: create / heartbeat / close / GC."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from forktex.runtime import instance


pytestmark = pytest.mark.usefixtures("isolated_home")


def _backdate(rec_path, *, started_secs=0, heartbeat_secs=0, stopped_secs=None):
    """Rewrite a record on disk with backdated timestamps."""
    import json

    data = json.loads(rec_path.read_text())
    now = datetime.now(timezone.utc)
    if started_secs:
        data["started_at"] = (now - timedelta(seconds=started_secs)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    if heartbeat_secs:
        data["last_heartbeat_at"] = (now - timedelta(seconds=heartbeat_secs)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    if stopped_secs is not None:
        data["stopped_at"] = (now - timedelta(seconds=stopped_secs)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        data["status"] = "stopped"
    rec_path.write_text(json.dumps(data))


def test_create_instance_writes_record(project_root):
    rec = instance.create_instance(
        kind="serve",
        project_root=project_root,
        long_running=True,
    )
    files = list(instance.global_instances_dir().glob("*.json"))
    assert len(files) == 1
    assert files[0].stem == rec.run_id
    # Project mirror also written.
    proj_files = list(instance.project_instances_dir(project_root).glob("*.json"))
    assert len(proj_files) == 1


def test_close_instance_marks_stopped(project_root):
    rec = instance.create_instance(kind="serve", project_root=project_root)
    instance.close_instance(rec)
    file = instance.global_instances_dir() / f"{rec.run_id}.json"
    import json

    data = json.loads(file.read_text())
    assert data["status"] == "stopped"
    assert data["stopped_at"] is not None


def test_iter_running_instances(project_root):
    rec1 = instance.create_instance(kind="serve", project_root=project_root)
    rec2 = instance.create_instance(kind="repl", project_root=project_root)
    instance.close_instance(rec2)
    running = [r for r in instance.iter_running_instances() if r.status == "running"]
    run_ids = {r.run_id for r in running}
    assert rec1.run_id in run_ids
    assert rec2.run_id not in run_ids


def test_gc_stale_long_running(project_root):
    rec = instance.create_instance(
        kind="serve",
        project_root=project_root,
        long_running=True,
    )
    rec_path = instance.global_instances_dir() / f"{rec.run_id}.json"
    # Backdate heartbeat past the 5-minute stale threshold.
    _backdate(rec_path, heartbeat_secs=400, started_secs=400)
    deleted = instance.gc_stale_instances()
    assert deleted >= 1
    assert not rec_path.exists()


def test_gc_keeps_fresh_long_running(project_root):
    rec = instance.create_instance(
        kind="serve",
        project_root=project_root,
        long_running=True,
    )
    rec_path = instance.global_instances_dir() / f"{rec.run_id}.json"
    deleted = instance.gc_stale_instances()
    assert deleted == 0
    assert rec_path.exists()


def test_gc_old_stopped_records(project_root):
    rec = instance.create_instance(kind="serve", project_root=project_root)
    instance.close_instance(rec)
    rec_path = instance.global_instances_dir() / f"{rec.run_id}.json"
    _backdate(rec_path, stopped_secs=86500)  # > 24h
    deleted = instance.gc_stale_instances()
    assert deleted >= 1


def test_gc_oneshot_with_dead_pid(project_root):
    rec = instance.create_instance(
        kind="one-shot",
        project_root=project_root,
        long_running=False,
    )
    rec_path = instance.global_instances_dir() / f"{rec.run_id}.json"
    # Replace pid with a guaranteed-dead one and age out the 60s grace.
    import json

    data = json.loads(rec_path.read_text())
    data["pid"] = 999999  # Almost certainly not alive
    rec_path.write_text(json.dumps(data))
    _backdate(rec_path, started_secs=120)
    deleted = instance.gc_stale_instances()
    assert deleted >= 1


@pytest.mark.asyncio
async def test_heartbeat_loop_updates_record(project_root):
    rec = instance.create_instance(
        kind="serve",
        project_root=project_root,
        long_running=True,
    )
    initial_heartbeat = rec.last_heartbeat_at
    task = asyncio.create_task(instance.heartbeat_loop(rec, interval_secs=0.05))
    # Sleep long enough for the timestamp (1s granularity) to advance.
    await asyncio.sleep(1.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert rec.last_heartbeat_at != initial_heartbeat
