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

"""Execute a crafted :class:`Plan` across steps + delegated sub-agents.

Two tiers behind one interface (:class:`PlanExecutor`):

- :class:`InProcessExecutor` — sequential, in-process, DB-free. The default.
- ``FlowExecutor`` (``flow_backend``) — durable/parallel via ``forktex_core.flow``,
  selected when a flow DB is configured. *Planned, not yet built*:
  ``select_executor`` currently degrades to the in-process tier.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional, Protocol

from forktex.agent.workflow.plan import (
    FileEditStep,
    Plan,
    PlanStep,
    ShellStep,
    SubAgentStep,
    ToolCallStep,
)
from forktex.agent.workflow.sub_agent import SubAgentSpec, spawn_sub_agent

StepEventCallback = Optional[Callable[[str, str, dict[str, Any]], None]]


@dataclass
class StepResult:
    """Outcome of one executed plan step."""

    kind: str
    status: str  # "completed" | "failed" | "skipped"
    summary: str = ""
    error: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanRunResult:
    """Aggregate outcome of executing a plan."""

    status: str  # "completed" | "failed"
    steps: list[StepResult] = field(default_factory=list)
    failed_index: Optional[int] = None
    rollback_hint: Optional[str] = None


class PlanExecutor(Protocol):
    async def execute(
        self, plan: Plan, *, on_step_event: StepEventCallback = None
    ) -> PlanRunResult: ...


class InProcessExecutor:
    """Run a plan's steps sequentially in the current process.

    Sub-agent steps delegate via :func:`spawn_sub_agent`; tool/shell/file steps
    go through the parent ``ToolServer``. A failing step stops the run and
    surfaces its ``rollback`` hint (no auto-rollback in v1).
    """

    def __init__(
        self,
        intelligence: Any,
        tool_server: Any,
        *,
        on_tool_event: StepEventCallback = None,
    ) -> None:
        self._intelligence = intelligence
        self._tool_server = tool_server
        self._on_tool_event = on_tool_event

    async def execute(
        self, plan: Plan, *, on_step_event: StepEventCallback = None
    ) -> PlanRunResult:
        results: list[StepResult] = []
        # Plans are crafted up-front, so a later step (e.g. an editor) can't know
        # what an earlier step (e.g. a researcher) discovered unless we feed it
        # forward. Accumulate each step's load-bearing summary and hand it to
        # subsequent sub-agents as context.
        context: list[str] = []
        for i, step in enumerate(plan.steps):
            if on_step_event:
                on_step_event("plan_step", f"{i + 1}/{len(plan.steps)} {step.kind}", {})
            result = await self._run_step(step, context)
            results.append(result)
            if result.summary:
                context.append(f"Step {i + 1} ({result.kind}): {result.summary}")
            if result.status == "failed":
                return PlanRunResult(
                    status="failed",
                    steps=results,
                    failed_index=i,
                    rollback_hint=step.rollback,
                )
        return PlanRunResult(status="completed", steps=results)

    async def _run_step(self, step: PlanStep, context: list[str]) -> StepResult:
        payload = step.payload
        try:
            if isinstance(payload, SubAgentStep):
                return await self._run_sub_agent(payload, context)
            if isinstance(payload, ToolCallStep):
                return await self._run_tool(payload.tool, payload.arguments)
            if isinstance(payload, ShellStep):
                return await self._run_tool(
                    "bash_execute", {"command": payload.command}
                )
            if isinstance(payload, FileEditStep):
                return await self._run_file_edit(payload)
            return StepResult(
                kind=step.kind, status="failed", error="unknown step kind"
            )
        except Exception as exc:  # a step failure must not crash the run
            return StepResult(kind=step.kind, status="failed", error=str(exc))

    async def _run_sub_agent(self, p: SubAgentStep, context: list[str]) -> StepResult:
        addendum = p.spec_system_prompt_addendum
        if context:
            addendum = (
                addendum
                + "\n\nFindings from earlier plan steps (use these — do not re-derive):\n"
                + "\n".join(context)
            ).strip()
        spec = SubAgentSpec(
            name=p.spec_name,
            intent=p.spec_intent,
            tool_subset=frozenset(p.spec_tool_subset),
            system_prompt_addendum=addendum,
            max_rounds=p.spec_max_rounds,
            timeout_s=p.spec_timeout_s,
        )
        # Degrade gracefully to the tools the parent actually exposes.
        available = {s["name"] for s in self._tool_server.get_schemas()}
        spec = replace(spec, tool_subset=frozenset(spec.tool_subset) & available)
        res = await spawn_sub_agent(
            spec,
            parent_intelligence=self._intelligence,
            parent_tool_server=self._tool_server,
            on_tool_event=self._on_tool_event,
        )
        return StepResult(
            kind="sub_agent",
            status="completed" if res.status == "completed" else "failed",
            summary=res.summary,
            error=res.error,
            data={
                "tokens": res.tokens_used,
                "rounds": res.rounds_used,
                "name": res.name,
            },
        )

    async def _run_tool(self, tool: str, arguments: dict[str, Any]) -> StepResult:
        if self._on_tool_event:
            self._on_tool_event("call", tool, arguments)
        result = await self._tool_server.call(tool, **arguments)
        if self._on_tool_event:
            self._on_tool_event("result", tool, result.to_dict())
        return StepResult(
            kind="tool_call",
            status="failed" if result.is_error else "completed",
            summary=result.content[:200],
            error=result.content if result.is_error else None,
        )

    async def _run_file_edit(self, p: FileEditStep) -> StepResult:
        if p.operation == "delete":
            res = await self._run_tool("delete_file", {"path": p.path})
        else:  # create | modify → write the full body
            res = await self._run_tool(
                "write_file", {"path": p.path, "content": p.body}
            )
        res.kind = "file_edit"
        return res


def resolve_flow_db() -> Optional[str]:
    """The flow database URL, or None (in-process tier). Env first; config later."""
    return os.environ.get("FORKTEX_FLOW_DB") or None


def select_executor(
    intelligence: Any,
    tool_server: Any,
    *,
    on_tool_event: StepEventCallback = None,
    flow_db: Optional[str] = None,
) -> PlanExecutor:
    """Pick the durable ``@flow`` tier when a flow DB is configured + available,
    else the in-process default. Mirrors the graceful-degrade grounding pattern.

    The durable ``FlowExecutor`` (``flow_backend``, on ``forktex_core.flow``) is
    not yet implemented, so a configured flow DB currently degrades cleanly to
    the in-process tier. Wire the backend here when it lands.
    """
    url = flow_db or resolve_flow_db()
    if url:
        # Durable @flow tier not yet built — fall back to in-process.
        pass
    return InProcessExecutor(intelligence, tool_server, on_tool_event=on_tool_event)


__all__ = [
    "PlanExecutor",
    "InProcessExecutor",
    "StepResult",
    "PlanRunResult",
    "select_executor",
    "resolve_flow_db",
]
