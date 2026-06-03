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

"""Craft a structured :class:`Plan` from a natural-language task.

The model is asked to emit a plan as JSON in the shape ``Plan.from_dict``
expects. We try the Intelligence structured-output endpoint first (clean JSON
against a schema) and fall back to a streaming completion parsed with
``Plan.from_llm_output`` — both reach the same default model, so crafting works
wherever the agent loop does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forktex.agent.workflow.plan import Plan
from forktex.agent.workflow.sub_agent import DEFAULT_TOOL_SUBSETS

# Permissive schema — the per-kind payload is a discriminated union that strict
# JSON-schema struggles to express, so payload stays a generic object and the
# documented shape lives in the prompt. Enough to coerce valid JSON.
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "rationale": {"type": "string"},
        "expected_outcome": {"type": "string"},
        "requires_approval": {"type": "boolean"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["tool_call", "file_edit", "shell", "sub_agent"],
                    },
                    "payload": {"type": "object"},
                    "rollback": {"type": ["string", "null"]},
                },
                "required": ["kind", "payload"],
            },
        },
    },
    "required": ["intent", "rationale", "expected_outcome", "steps"],
}

_CRAFT_INSTRUCTIONS = """\
You are forktex's planner. Produce a concrete, minimal plan to accomplish the \
task, then STOP. Respond with a single JSON object (no prose, no code fences) \
of this exact shape:

{
  "intent": "<one line>",
  "rationale": "<why these steps>",
  "expected_outcome": "<what 'done' looks like>",
  "requires_approval": true,
  "steps": [ <step>, ... ]
}

Each step is {"kind": <k>, "payload": {...}, "rollback": <string|null>} where k is one of:
- "sub_agent": delegate to a specialist. payload = {"role": "researcher"|"editor"|"auditor", "intent": "<self-contained task>", "max_rounds": 5, "timeout_s": 60}
- "tool_call": payload = {"tool": "<tool name>", "arguments": {...}}
- "shell":     payload = {"command": "<cmd>", "timeout_s": 30}
- "file_edit": payload = {"path": "<rel path>", "operation": "create"|"modify"|"delete", "body": "<content or diff>"}

`kind` is ALWAYS one of the four literal values above — never a role name. To \
delegate, use kind "sub_agent" and pick the specialist with payload.role \
("researcher" to investigate, "editor" to make edits, "auditor" to review). \
CRITICAL: any step that produces content derived from earlier findings MUST be \
a sub_agent with role "editor" (it reads the repo and writes live) — do NOT use \
a static "file_edit" for derived content, because file_edit bodies are literal \
text fixed at planning time and cannot reference prior step outputs. Reserve \
"file_edit" for content you can write out in full right now. Keep the plan \
short (2-5 steps). Paths are relative to the project root."""


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Expand ergonomic ``sub_agent`` payloads (``role`` → ``name``+``tool_subset``)
    into the shape ``_payload_from_dict`` expects."""
    steps = data.get("steps")
    if not isinstance(steps, list):
        return data
    for step in steps:
        if not isinstance(step, dict):
            continue
        # Defensive: models sometimes use a role name as the step kind
        # ("editor") instead of kind "sub_agent" + payload.role. Coerce it.
        if step.get("kind") in DEFAULT_TOOL_SUBSETS:
            payload = step.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            payload.setdefault("role", step["kind"])
            if "intent" not in payload and isinstance(step.get("intent"), str):
                payload["intent"] = step["intent"]
            step["payload"] = payload
            step["kind"] = "sub_agent"
        if step.get("kind") != "sub_agent":
            continue
        payload = step.get("payload")
        if not isinstance(payload, dict):
            continue
        role = payload.get("role")
        if role and "name" not in payload:
            payload["name"] = role
        if role and "tool_subset" not in payload and role in DEFAULT_TOOL_SUBSETS:
            payload["tool_subset"] = sorted(DEFAULT_TOOL_SUBSETS[role])
    return data


async def craft_plan(
    task: str,
    *,
    intelligence: Any,
    project_root: str | Path,
    base_prompt: str | None = None,
) -> Plan:
    """Craft a :class:`Plan` for *task* using the configured model."""
    from forktex.agent.intelligence.grounding import build_system_prompt

    system = build_system_prompt(project_root, base_prompt=base_prompt or _CRAFT_INSTRUCTIONS)

    data = await _craft_structured(task, intelligence, system)
    if data is None:
        data = await _craft_streaming(task, intelligence, system)
    return Plan.from_dict(_normalize(data))


async def _craft_structured(task: str, intelligence: Any, system: str) -> dict[str, Any] | None:
    """Try the structured-output endpoint; return None to fall back."""
    try:
        from forktex_intelligence import Inputs

        model_id = await _structured_model(intelligence)
        if not model_id:
            return None
        out = await intelligence.invoke(
            model_id,
            Inputs(text=task, system=system, response_schema=PLAN_SCHEMA),
        )
        structured = getattr(out, "structured", None)
        return structured if isinstance(structured, dict) and structured else None
    except Exception:
        return None


async def _structured_model(intelligence: Any) -> str | None:
    """First chat model advertising the 'structured' capability, else None."""
    try:
        models = await intelligence.models()
    except Exception:
        return None
    for m in models:
        caps = getattr(m, "capabilities", None) or []
        if "chat" in caps and "structured" in caps:
            return getattr(m, "id", None)
    return None


async def _craft_streaming(task: str, intelligence: Any, system: str) -> dict[str, Any]:
    """Stream a completion (default model) and parse the JSON object out."""
    from forktex_intelligence.streams import SSEEventType, parse_sse_stream

    text = ""
    async for ev in parse_sse_stream(
        intelligence.chat_stream([{"role": "user", "content": task}], system=system)
    ):
        if ev.event == SSEEventType.DELTA:
            text += ev.delta_text
        elif ev.event == SSEEventType.ERROR:
            raise RuntimeError(f"plan crafting failed: {ev.error_message}")
    # Plan.from_llm_output tolerates fences/prose; re-extract to a dict here so
    # the caller can normalize sub_agent payloads before validation.
    from forktex.agent.workflow.plan import _extract_json_object

    return json.loads(_extract_json_object(text))


__all__ = ["craft_plan", "PLAN_SCHEMA"]
