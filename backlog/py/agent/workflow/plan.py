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

"""Plan-mode typed contracts.

A ``Plan`` is the agent's proposed next-N steps to address a user's
goal. The flow is:

1. User submits a goal/prompt.
2. The plan-mode loop calls ``Intelligence.chat_stream(...)`` with a
   system prompt that requires a structured ``Plan`` artifact.
3. The streamed text is parsed via ``Plan.from_llm_output(text)``.
4. If ``plan.requires_approval`` is true, the UI renders the plan and
   awaits an ``Approval`` (approve / reject / edit).
5. On approval the loop executes the steps sequentially, surfacing
   progress.

The Phase A deliverable here is the **typed contract** + a JSON parser
+ a validator. The execution loop itself is Phase B.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal


__all__ = [
    "Approval",
    "ApprovalDecision",
    "FileEditStep",
    "Plan",
    "PlanParseError",
    "PlanStep",
    "PlanStepKind",
    "ShellStep",
    "SubAgentStep",
    "ToolCallStep",
]


PlanStepKind = Literal["tool_call", "file_edit", "shell", "sub_agent"]
ApprovalDecision = Literal["approve", "reject", "edit"]


class PlanParseError(ValueError):
    """Raised when an LLM output cannot be parsed as a valid ``Plan``."""


# ── Step payload types ────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolCallStep:
    """A request to invoke a tool registered with the local tool server."""

    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class FileEditStep:
    """A request to edit a file. The loop applies via the filesystem tools."""

    path: str
    operation: Literal["create", "modify", "delete"]
    # For 'modify': unified-diff or before/after snippets.
    # For 'create': full content.
    # For 'delete': empty.
    body: str = ""


@dataclass(frozen=True)
class ShellStep:
    """A request to run a shell command via the bash tool.

    Bounded by ``timeout_s`` so a hung command can't stall the plan.
    """

    command: str
    timeout_s: float = 30.0


@dataclass(frozen=True)
class SubAgentStep:
    """A request to spawn a sub-agent for a focused sub-task.

    Carries the full ``SubAgentSpec`` so the executor doesn't need to
    re-derive it. Imported lazily inside the dataclass body to avoid
    a top-level circular import between ``plan`` and ``sub_agent``.
    """

    # Forward-declared by string; resolved at execution time.
    spec_name: str
    spec_intent: str
    spec_tool_subset: tuple[str, ...]
    spec_system_prompt_addendum: str
    spec_max_rounds: int
    spec_timeout_s: float


# ── Plan / PlanStep / Approval ────────────────────────────────────────


PlanStepPayload = ToolCallStep | FileEditStep | ShellStep | SubAgentStep


@dataclass(frozen=True)
class PlanStep:
    """One step in a plan, typed by ``kind`` + a discriminated payload."""

    kind: PlanStepKind
    payload: PlanStepPayload
    rollback: str | None = None  # how to undo if a downstream step fails

    def __post_init__(self) -> None:
        # Lightweight sanity check — payload type must match declared kind.
        expected = _PAYLOAD_FOR_KIND[self.kind]
        if not isinstance(self.payload, expected):
            raise TypeError(
                f"PlanStep(kind={self.kind!r}) requires payload of "
                f"{expected.__name__}; got {type(self.payload).__name__}"
            )


_PAYLOAD_FOR_KIND: dict[PlanStepKind, type] = {
    "tool_call": ToolCallStep,
    "file_edit": FileEditStep,
    "shell": ShellStep,
    "sub_agent": SubAgentStep,
}


@dataclass(frozen=True)
class Plan:
    """The agent's proposed next-N steps to address a goal."""

    intent: str
    rationale: str
    steps: tuple[PlanStep, ...]
    expected_outcome: str
    requires_approval: bool = True

    @classmethod
    def from_llm_output(cls, text: str) -> Plan:
        """Parse a plan from LLM output.

        Expected format: a JSON object (possibly inside ```json fences).
        The parser tolerates leading/trailing prose and code fences but
        requires a valid JSON object with the right shape.
        """
        payload = _extract_json_object(text)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise PlanParseError(f"plan output is not valid JSON: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        """Build a ``Plan`` from a parsed dict (post JSON-decode)."""
        try:
            intent = str(data["intent"])
            rationale = str(data["rationale"])
            expected_outcome = str(data["expected_outcome"])
            requires_approval = bool(data.get("requires_approval", True))
            raw_steps = data["steps"]
        except KeyError as exc:
            raise PlanParseError(f"plan output missing required key: {exc}") from exc
        if not isinstance(raw_steps, list):
            raise PlanParseError("plan 'steps' must be a list")
        steps = tuple(_step_from_dict(s) for s in raw_steps)
        return cls(
            intent=intent,
            rationale=rationale,
            steps=steps,
            expected_outcome=expected_outcome,
            requires_approval=requires_approval,
        )


@dataclass(frozen=True)
class Approval:
    """User response to a proposed plan.

    For ``decision="edit"``, ``edits`` carries the user-revised steps to
    execute in place of the original plan; ``reason`` is optional but
    recommended for the agent's context.
    """

    decision: ApprovalDecision
    edits: tuple[PlanStep, ...] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.decision == "edit" and self.edits is None:
            raise ValueError("Approval(decision='edit') requires edits=...")
        if self.decision != "edit" and self.edits is not None:
            raise ValueError(
                "Approval edits only apply when decision='edit'; "
                f"got decision={self.decision!r}"
            )


# ── Parsing helpers ──────────────────────────────────────────────────


def _extract_json_object(text: str) -> str:
    """Pull the JSON object out of LLM output that may have prose + fences.

    Looks first inside ```json ... ``` blocks; otherwise takes the
    substring between the first ``{`` and the matching closing ``}``.
    """
    stripped = text.strip()
    fence = "```json"
    if fence in stripped:
        start = stripped.find(fence) + len(fence)
        end = stripped.find("```", start)
        if end == -1:
            raise PlanParseError("unterminated ```json fence in plan output")
        return stripped[start:end].strip()
    if stripped.startswith("{"):
        return stripped
    first_brace = stripped.find("{")
    if first_brace == -1:
        raise PlanParseError("plan output contains no JSON object")
    return stripped[first_brace:]


def _step_from_dict(raw: Any) -> PlanStep:
    if not isinstance(raw, dict):
        raise PlanParseError(f"plan step must be a dict; got {type(raw).__name__}")
    try:
        kind = raw["kind"]
    except KeyError as exc:
        raise PlanParseError("plan step missing 'kind' field") from exc
    if kind not in _PAYLOAD_FOR_KIND:
        raise PlanParseError(f"unknown plan step kind: {kind!r}")
    payload_dict = raw.get("payload")
    if not isinstance(payload_dict, dict):
        raise PlanParseError(
            f"plan step kind={kind!r} requires a dict 'payload'; got "
            f"{type(payload_dict).__name__}"
        )
    rollback = raw.get("rollback")
    payload = _payload_from_dict(kind, payload_dict)
    return PlanStep(kind=kind, payload=payload, rollback=rollback)


def _payload_from_dict(kind: PlanStepKind, payload: dict[str, Any]) -> PlanStepPayload:
    if kind == "tool_call":
        return ToolCallStep(
            tool=str(payload["tool"]),
            arguments=dict(payload.get("arguments", {})),
        )
    if kind == "file_edit":
        return FileEditStep(
            path=str(payload["path"]),
            operation=payload["operation"],  # type: ignore[arg-type]
            body=str(payload.get("body", "")),
        )
    if kind == "shell":
        return ShellStep(
            command=str(payload["command"]),
            timeout_s=float(payload.get("timeout_s", 30.0)),
        )
    if kind == "sub_agent":
        return SubAgentStep(
            spec_name=str(payload["name"]),
            spec_intent=str(payload["intent"]),
            spec_tool_subset=tuple(payload.get("tool_subset", ())),
            spec_system_prompt_addendum=str(payload.get("system_prompt_addendum", "")),
            spec_max_rounds=int(payload.get("max_rounds", 5)),
            spec_timeout_s=float(payload.get("timeout_s", 60.0)),
        )
    raise PlanParseError(f"unknown plan step kind: {kind!r}")
