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

"""Retry policy + terminal-failure type for the agent loop.

The loop retries a transient stream-open failure a few times with exponential
backoff. Retries are surfaced via the loop's ``on_tool_event`` callback (a
``"retry"`` event) — **never** by injecting text into the transcript — and the
exception is re-raised once attempts are exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple, Type


class AgentLoopExhausted(RuntimeError):
    """Raised when the agent loop exceeds its tool-round budget.

    A terminal control-flow signal (not a transcript event): consumers catch it
    — ``AgentLoop.run_task`` maps it to ``AgentResponse.error``; streaming
    consumers render it via their stream-error handler.
    """


@dataclass(frozen=True)
class RetryPolicy:
    """How transient stream failures are retried (exponential backoff)."""

    max_attempts: int = 3
    base_delay: float = 5.0
    transient: Tuple[Type[BaseException], ...] = field(default=(Exception,))

    def delay_for(self, attempt: int) -> float:
        """Backoff before the *next* attempt after a 0-indexed failed ``attempt``."""
        return self.base_delay * (2**attempt)

    def is_last(self, attempt: int) -> bool:
        """True if 0-indexed ``attempt`` is the final permitted one."""
        return attempt + 1 >= self.max_attempts


__all__ = ["RetryPolicy", "AgentLoopExhausted"]
