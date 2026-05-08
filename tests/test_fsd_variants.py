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

"""Variant-qualifier parser tests."""

from forktex.fsd.variants import ParsedAtom, make_target_for, parse_atom_key


SERVICES = {"api", "web", "sdk-py", "sdk-js", "client"}
ENVS = {"local", "staging", "production", "docker-sandbox"}


def test_bare_atom_no_qualifiers():
    p = parse_atom_key("apply", services=SERVICES, envs=ENVS)
    assert p == ParsedAtom(base_id="apply")
    assert p.make_target == "apply"


def test_single_env_qualifier():
    p = parse_atom_key("apply@local", services=SERVICES, envs=ENVS)
    assert p.base_id == "apply"
    assert p.env == "local"
    assert p.service is None
    assert p.custom == ()
    assert p.make_target == "apply-local"


def test_single_service_qualifier():
    p = parse_atom_key("build@api", services=SERVICES, envs=ENVS)
    assert p.service == "api"
    assert p.env is None
    assert p.make_target == "build-api"


def test_combined_service_and_env_canonical_order():
    p = parse_atom_key("apply@web@local", services=SERVICES, envs=ENVS)
    assert p.service == "web"
    assert p.env == "local"
    assert p.make_target == "apply-web-local"


def test_combined_axes_input_order_normalised():
    """`apply@local@web` should canonicalise to `apply-web-local`."""
    p = parse_atom_key("apply@local@web", services=SERVICES, envs=ENVS)
    assert p.service == "web"
    assert p.env == "local"
    assert p.make_target == "apply-web-local"


def test_free_form_qualifier_unrecognised_axis():
    p = parse_atom_key("test@is-interesting", services=set(), envs=set())
    assert p.custom == ("is-interesting",)
    assert p.make_target == "test-is-interesting"


def test_free_form_with_canonical_service():
    """Mixed: service matches, free-form lands at the leaf."""
    p = parse_atom_key("apply@web@experimental", services=SERVICES, envs=set())
    assert p.service == "web"
    assert p.custom == ("experimental",)
    assert p.make_target == "apply-web-experimental"


def test_free_form_preserves_declared_order():
    """`test@experimental@is-interesting` and the reversed key must produce
    DIFFERENT make targets — free-form is opaque, order matters."""
    a = parse_atom_key("test@experimental@is-interesting", services=set(), envs=set())
    b = parse_atom_key("test@is-interesting@experimental", services=set(), envs=set())
    assert a.make_target == "test-experimental-is-interesting"
    assert b.make_target == "test-is-interesting-experimental"
    assert a.make_target != b.make_target


def test_axis_collision_first_value_wins_rest_to_custom():
    """If two qualifiers both match the env axis, the first value claims the
    slot and the rest cascade to custom (don't silently drop)."""
    p = parse_atom_key("smoke@local@staging", services=SERVICES, envs=ENVS)
    assert p.env == "local"
    assert p.custom == ("staging",)
    assert p.make_target == "smoke-local-staging"


def test_three_qualifiers_full_canonical():
    p = parse_atom_key("apply@api@production@chaos", services=SERVICES, envs=ENVS)
    assert p.service == "api"
    assert p.env == "production"
    assert p.custom == ("chaos",)
    assert p.make_target == "apply-api-production-chaos"


def test_format_check_variant_canonical_target():
    """`format@check` is a free-form 'check mode' qualifier in projects
    that don't declare it as a canonical axis."""
    p = parse_atom_key("format@check", services=SERVICES, envs=ENVS)
    assert p.custom == ("check",)
    assert p.make_target == "format-check"


def test_make_target_for_function_style():
    p = parse_atom_key("publish@test", services=SERVICES, envs=ENVS)
    assert make_target_for(p) == p.make_target == "publish-test"


def test_empty_qualifier_segments_dropped():
    """`apply@@local` should ignore the empty segment, not crash."""
    p = parse_atom_key("apply@@local", services=SERVICES, envs=ENVS)
    assert p.env == "local"
    assert p.make_target == "apply-local"


def test_pathological_no_head():
    """A key starting with `@` is treated as opaque (no atom prefix)."""
    p = parse_atom_key("@orphan", services=SERVICES, envs=ENVS)
    assert p.base_id == "@orphan"


def test_qualifier_in_neither_axis_falls_through_to_custom():
    """Service-name-shaped value that doesn't match a known service stays
    free-form."""
    p = parse_atom_key("build@unknown-service", services=SERVICES, envs=ENVS)
    assert p.service is None
    assert p.custom == ("unknown-service",)
    assert p.make_target == "build-unknown-service"
