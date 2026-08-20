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

"""``mark_step_running`` is a compare-and-swap, not a blind write.

The end-to-end double-execution scenario (a reclaim racing a still-alive
executor) is covered in ``test_heartbeat.py::test_reclaimed_step_does_not_execute_twice``,
which exercises the driver's in-flight dedup guard. This module tests the
narrower, lower-level guarantee directly: two callers racing to claim the
exact same ``pending`` row must produce exactly one winner, never two.
"""

from __future__ import annotations

import asyncio

import pytest
from uuid import uuid7

from forktex_core.flow.persist import runs as _runs
from forktex_core.flow.persist import steps as _steps

pytestmark = pytest.mark.asyncio


async def test_only_one_concurrent_claim_wins(flow):
    run_id = uuid7()
    await _runs.insert_run(
        flow,
        run_id=run_id,
        workflow_name="claim_race_test",
        workflow_version=1,
        input={},
        metadata={},
    )
    step_id, status, _ = await _steps.upsert_pending_step(
        flow,
        run_id=run_id,
        step_name="s",
        step_qualname="s",
        step_index=0,
        args_hash="fixed",
        max_attempts=1,
    )
    assert status == "pending"

    results = await asyncio.gather(
        *[_steps.mark_step_running(flow, step_id) for _ in range(5)],
        return_exceptions=True,
    )

    successes = [r for r in results if r is None]
    losses = [r for r in results if isinstance(r, _steps.StepClaimLost)]
    other = [r for r in results if r is not None and not isinstance(r, _steps.StepClaimLost)]

    assert other == [], f"unexpected exception type(s): {other}"
    assert len(successes) == 1, f"expected exactly one winner, got {len(successes)}"
    assert len(losses) == 4, f"expected the other 4 to lose the race, got {len(losses)}"
