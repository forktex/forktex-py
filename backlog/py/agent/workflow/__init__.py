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

"""Typed contracts for the agentic workflow (plan-mode + sub-agents).

The shapes here are the public surface a Phase B plan-mode loop and a
sub-agent spawner depend on. Defining them up-front (Phase A) means
the implementation work can land independently without breaking the
agreed-upon vocabulary.

Modules:
- ``plan`` — ``Plan``, ``PlanStep``, ``Approval`` + typed payload union.
- ``sub_agent`` — ``SubAgentSpec``, ``SubAgentResult``, ``Artifact``,
  ``spawn_sub_agent``.
"""

from forktex.agent.workflow.plan import (
    Approval,
    FileEditStep,
    Plan,
    PlanStep,
    PlanStepKind,
    ShellStep,
    SubAgentStep,
    ToolCallStep,
)
from forktex.agent.workflow.sub_agent import (
    Artifact,
    ArtifactKind,
    SubAgentResult,
    SubAgentSpec,
    SubAgentStatus,
    spawn_sub_agent,
)

__all__ = [
    # plan
    "Approval",
    "FileEditStep",
    "Plan",
    "PlanStep",
    "PlanStepKind",
    "ShellStep",
    "SubAgentStep",
    "ToolCallStep",
    # sub_agent
    "Artifact",
    "ArtifactKind",
    "SubAgentResult",
    "SubAgentSpec",
    "SubAgentStatus",
    "spawn_sub_agent",
]
