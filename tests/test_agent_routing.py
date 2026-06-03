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

# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.

"""forktex auto-selects its own agent from the task — no manual `-t` needed."""

from __future__ import annotations

import pytest

from forktex.agent.engine import route_agent_type


@pytest.mark.parametrize(
    "task,expected",
    [
        ("Add error handling to src/app.py", "developer"),
        ("fix the failing test in the parser", "developer"),
        ("refactor the auth module", "developer"),
        ("What testing patterns does this project use?", "researcher"),
        ("find where the config is loaded and explain it", "researcher"),
        ("review the documentation repository and report findings", "researcher"),
        ("review the current diff", "reviewer"),
        ("do a code review of the PR", "reviewer"),
        ("audit the security of the auth code", "reviewer"),
        ("help me with this", "assistant"),
        ("", "assistant"),
    ],
)
def test_route_agent_type(task, expected):
    assert route_agent_type(task) == expected


def test_build_verb_beats_review_word():
    # An explicit change verb wins (implies write access) even with "review".
    assert route_agent_type("implement the changes from the code review") == "developer"
