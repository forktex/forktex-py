# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of forktex-core.
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

"""Heartbeat refresh during long-running steps.

A running step must update ``step_run.heartbeat_at`` periodically so
the driver's stalled-step reclaim doesn't race ahead and reset a
healthy step. This test forces a step to sleep longer than the
heartbeat interval, then asserts the row's ``heartbeat_at`` advanced.
"""

from __future__ import annotations

import asyncio

import pytest

from forktex_core.flow import Ctx, Flow, step

from .conftest import wait_for_status

pytestmark = pytest.mark.asyncio


async def test_heartbeat_refreshes_during_long_step(db_url: str, fresh_schema: str):
    # Tight heartbeat interval so the test doesn't take forever; the
    # step body sleeps 1.5 intervals so we observe at least one refresh.
    flow = Flow(
        database_url=db_url,
        schema=fresh_schema,
        heartbeat_interval=0.3,
        stale_threshold=10.0,  # don't reclaim during the test
    )
    try:
        await flow.init()

        captured = {"first_heartbeat": None, "second_heartbeat": None}

        @step
        async def long_running(ctx: Ctx, state: dict) -> dict:
            # Inspect own step_run row mid-flight (without going via
            # public Flow API which lazy-loads — direct ORM read).
            from forktex_core.flow.persist.models import StepRun
            from sqlalchemy import select

            await asyncio.sleep(0.4)  # past first heartbeat tick
            async with flow.session() as session:
                row = (
                    await session.execute(
                        select(StepRun).where(
                            StepRun.run_id == ctx.run_id,
                            StepRun.status == "running",
                        )
                    )
                ).scalar_one()
                captured["first_heartbeat"] = row.heartbeat_at
            await asyncio.sleep(0.5)  # past second heartbeat tick
            async with flow.session() as session:
                row = (
                    await session.execute(
                        select(StepRun).where(
                            StepRun.run_id == ctx.run_id,
                            StepRun.status == "running",
                        )
                    )
                ).scalar_one()
                captured["second_heartbeat"] = row.heartbeat_at
            return {**state, "r": "done"}

        @flow.pipeline("heartbeat_test", version=1)
        class HeartbeatTest:
            steps = [long_running]

        await flow.start_driver()
        run_id = await flow.start("heartbeat_test")
        await wait_for_status(flow, run_id, until={"completed"}, timeout=15)

        first = captured["first_heartbeat"]
        second = captured["second_heartbeat"]
        assert first is not None
        assert second is not None
        # The second snapshot must show a strictly-later heartbeat than
        # the first — proves the heartbeat task actually fired during
        # the long step body.
        assert second > first, f"heartbeat did not advance: first={first} second={second}"
    finally:
        await flow.close()


async def test_reclaimed_step_does_not_execute_twice(db_url: str, fresh_schema: str):
    """A step whose heartbeat merely lags — not one that actually died — must still
    run exactly once.

    ``heartbeat_interval`` is set far longer than ``stale_threshold`` so the driver's
    own reclaim sweep legitimately finds the step's heartbeat stale while the step is
    genuinely still executing (no clock manipulation needed — the configuration alone
    reproduces the race). Before the driver-level in-flight guard, this reclaim would
    flip the run back to `pending`, and the very next tick would dispatch a second
    `execute_run` for the same run while the first was still inside the same step body.
    """
    flow = Flow(
        database_url=db_url,
        schema=fresh_schema,
        heartbeat_interval=100.0,  # far longer than the sleep below: never refreshes
        stale_threshold=0.5,  # short enough that the driver reclaims mid-sleep
        poll_interval=0.2,
    )
    try:
        await flow.init()

        executions: list[float] = []

        @step
        async def slow_step(ctx: Ctx, state: dict) -> dict:
            executions.append(asyncio.get_running_loop().time())
            await asyncio.sleep(2.0)  # spans several reclaim-eligible ticks
            return {**state, "done": True}

        @flow.pipeline("reclaim_no_double_exec", version=1)
        class ReclaimNoDoubleExec:
            steps = [slow_step]

        await flow.start_driver()
        run_id = await flow.start("reclaim_no_double_exec")
        await wait_for_status(flow, run_id, until={"completed", "failed"}, timeout=15)

        info = await flow.get(run_id)
        assert info.status == "completed", f"run did not complete cleanly: {info}"
        assert len(executions) == 1, f"step body ran {len(executions)} times, expected exactly 1"
    finally:
        await flow.close()
