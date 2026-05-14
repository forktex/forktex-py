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

"""Cross-facet auth-contract symmetry test.

The three platforms — cloud, intelligence, network — share a unified
auth surface (``forktex.agent.auth``). This test asserts each facet
honours the same contract:

- Listed in ``FACETS``.
- Has a connect impl (``connect_<facet>``) with the same kwargs.
- ``load_state(facet, project_root)`` returns an :class:`AuthState`.
- The credential file lives at the path declared by the structure
  spec, marked ``sensitivity="secret"``.
- A public Python shim (``forktex.<facet>``) re-exports the canonical
  client class.

If a facet drifts from the contract, this test catches it before
runtime.
"""

from __future__ import annotations

import inspect

import forktex.fsd  # noqa: F401  warm-up; circular-import dance

from forktex.agent.auth import (
    connect_cloud,
    connect_intelligence,
    connect_network,
)
from forktex.agent.auth.store import load_state
from forktex.agent.auth.types import FACETS, AuthState
from forktex.graph.structure import GLOBAL_SPEC

CONNECT_IMPLS = {
    "cloud": connect_cloud,
    "intelligence": connect_intelligence,
    "network": connect_network,
}

# The kwargs every connect impl must accept (unified surface so the
# Click command factory can build identical CLI commands per facet).
_REQUIRED_CONNECT_KWARGS = {
    "project",
    "save_global",
    "endpoint",
    "email",
    "password",
    "api_key",
    "new_account",
}


# ── FACETS shape ──────────────────────────────────────────────────────────


def test_facets_are_three_known_platforms():
    assert set(FACETS) == {"cloud", "intelligence", "network"}


def test_every_facet_has_a_connect_impl():
    for facet in FACETS:
        assert facet in CONNECT_IMPLS, f"facet {facet!r} missing a connect impl"
        impl = CONNECT_IMPLS[facet]
        assert inspect.iscoroutinefunction(impl), f"connect_{facet} must be `async def`"


def test_connect_impls_accept_the_same_kwargs():
    """All three connect_<facet> functions must accept the same kwargs so
    `build_facet_commands` can synthesise identical Click commands."""
    for facet, impl in CONNECT_IMPLS.items():
        sig = inspect.signature(impl)
        params = set(sig.parameters)
        missing = _REQUIRED_CONNECT_KWARGS - params
        assert not missing, (
            f"connect_{facet} is missing kwargs: {sorted(missing)} "
            f"(has: {sorted(params)})"
        )
        # All kwargs should be keyword-only — defensive: catches anyone who
        # adds a positional first arg by accident.
        for name in _REQUIRED_CONNECT_KWARGS:
            kind = sig.parameters[name].kind
            assert kind is inspect.Parameter.KEYWORD_ONLY, (
                f"connect_{facet}'s {name} must be keyword-only (found: {kind})"
            )


# ── load_state shape ──────────────────────────────────────────────────────


def test_load_state_returns_auth_state_per_facet(tmp_path):
    for facet in FACETS:
        state = load_state(facet, tmp_path)
        assert isinstance(state, AuthState)
        assert state.facet == facet
        # Empty project = nothing configured.
        assert state.configured is False


# ── structure-spec contract ───────────────────────────────────────────────


def test_each_facet_has_a_secret_credential_entry_in_global_spec():
    """Every facet's global credential file must be declared in
    ``GLOBAL_SPEC`` with ``sensitivity="secret"``. This binds the audit
    hook (no untracked writes) to the auth flow."""
    expected_patterns = {
        "cloud": "cloud.json",
        "intelligence": "intelligence.json",
        "network": "network.json",
    }
    by_pattern = {entry.pattern: entry for entry in GLOBAL_SPEC}
    for facet, pattern in expected_patterns.items():
        assert pattern in by_pattern, (
            f"{facet}: no EntrySpec for {pattern} in GLOBAL_SPEC"
        )
        entry = by_pattern[pattern]
        assert entry.sensitivity == "secret", (
            f"{facet}: {pattern} must be sensitivity='secret', "
            f"got {entry.sensitivity!r}"
        )


# ── Python shim symmetry ──────────────────────────────────────────────────


def test_each_facet_has_a_python_shim():
    """forktex.cloud, forktex.intelligence, forktex.network must all be
    importable and expose a canonical client class. The canonical names
    are Cloud / Intelligence / NetWork respectively (with back-compat
    fallbacks for older SDK floors)."""
    import importlib

    expected = {
        "cloud": "Cloud",
        "intelligence": "Intelligence",
        "network": "NetWork",
    }
    for facet, canonical_class in expected.items():
        shim_name = f"forktex.{facet}"
        try:
            shim = importlib.import_module(shim_name)
        except ImportError as exc:
            raise AssertionError(f"missing shim: {shim_name}") from exc
        assert hasattr(shim, canonical_class), (
            f"{shim_name} must export {canonical_class}; "
            f"current exports: {[n for n in dir(shim) if not n.startswith('_')]}"
        )


def test_each_shim_declares_all_with_canonical_name():
    """``__all__`` is the public API contract — must list the canonical
    class name."""
    import importlib

    expected = {
        "cloud": "Cloud",
        "intelligence": "Intelligence",
        "network": "NetWork",
    }
    for facet, canonical_class in expected.items():
        shim = importlib.import_module(f"forktex.{facet}")
        all_list = getattr(shim, "__all__", None)
        assert all_list is not None, f"forktex.{facet}.__all__ missing"
        assert canonical_class in all_list, (
            f"forktex.{facet}.__all__ must include {canonical_class!r}; "
            f"found: {all_list}"
        )


# ── auth/cli.py is free of long-form imports ───────────────────────────────


def test_auth_cli_imports_canonical_names_only():
    """`forktex.agent.auth.cli` must import the canonical SDK classes
    (Cloud / Intelligence / NetWork) via the forktex.* shims, not the
    long-form (`ForktexCloudClient`, `ForktexIntelligenceClient`,
    `NetworkClient`) directly. Drift would defeat the rename migration."""
    from forktex.core.paths import require_project_root

    src = require_project_root(__file__)
    auth_cli = (src / "src" / "forktex" / "agent" / "auth" / "cli.py").read_text()

    forbidden = [
        "from forktex_intelligence.client.client import ForktexIntelligenceClient",
        "from forktex_cloud.client import ForktexCloudClient",
        "from forktex_network import NetworkClient",
    ]
    for line in forbidden:
        assert line not in auth_cli, (
            f"auth/cli.py must not import the long-form SDK class:\n  {line}\n"
            f"Use the forktex.<facet> shim instead."
        )
