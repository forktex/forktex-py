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
