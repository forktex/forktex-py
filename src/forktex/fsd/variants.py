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

"""Atom-variant qualifier syntax parser.

Atom IDs accept ``@<qualifier>`` suffixes per the v1.1.0 schema. Two
canonical biased axes drive automatic Make-target generation:

- **service** — qualifier matches a name in ``packages[*].name``;
  generator wraps the recipe with ``cd packages/<service>`` and
  selects the per-language toolchain.
- **env** — qualifier matches a name in ``cloud.environments[*].name``;
  generator injects ``--env <env>`` and (where present) sources
  ``forktex.<env>.json`` overlay.

Anything else is **free-form** — opaque pass-through, no injection.

The canonical Make-target name uses order
``<atom>-<service>-<env>-<custom1>-<custom2>...``. The parser
accepts qualifiers in any input order (canonical axes are matched by
value, not position). Free-form qualifiers preserve their declared
order so two free-form-different atom keys never collide.

Examples
--------

Given ``packages = {"api", "web"}`` and ``envs = {"local", "prod"}``:

>>> parse_atom_key("apply", services={"api","web"}, envs={"local","prod"}).make_target
'apply'
>>> parse_atom_key("apply@local", services={"api","web"}, envs={"local","prod"}).make_target
'apply-local'
>>> parse_atom_key("apply@web@local", services={"api","web"}, envs={"local","prod"}).make_target
'apply-web-local'
>>> parse_atom_key("apply@local@web", services={"api","web"}, envs={"local","prod"}).make_target
'apply-web-local'
>>> parse_atom_key("test@is-interesting", services=set(), envs=set()).make_target
'test-is-interesting'
>>> parse_atom_key("apply@web@experimental", services={"api","web"}, envs=set()).make_target
'apply-web-experimental'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


__all__ = ["ParsedAtom", "parse_atom_key", "make_target_for"]


@dataclass(frozen=True)
class ParsedAtom:
    """Result of parsing an atom-variant key like ``apply@web@local``.

    ``base_id`` is the bare atom ID; ``service`` and ``env`` are
    populated when the qualifier matches a canonical axis value;
    ``custom`` keeps every other qualifier in its declared order.
    """

    base_id: str
    service: str | None = None
    env: str | None = None
    custom: tuple[str, ...] = ()

    @property
    def make_target(self) -> str:
        """Return the canonical Make-target name.

        Canonical order: ``<atom>-<service>-<env>-<custom1>-<custom2>...``.
        """
        parts: list[str] = [self.base_id]
        if self.service:
            parts.append(self.service)
        if self.env:
            parts.append(self.env)
        parts.extend(self.custom)
        return "-".join(parts)


def parse_atom_key(
    key: str,
    *,
    services: Iterable[str],
    envs: Iterable[str],
) -> ParsedAtom:
    """Parse an atom key (possibly ``@``-qualified) against the canonical axes.

    *services* is the set of recognised service names (typically
    ``{p.name for p in manifest.packages}`` plus their short aliases).
    *envs* is the set of recognised env names (typically
    ``{e.name for e in manifest.cloud.environments}``).

    A qualifier matching a service value populates ``service``; matching
    an env value populates ``env``; everything else lands in ``custom``
    in declared order. If two qualifiers both match the same axis (e.g.
    two services named for both packages), the **first** value wins and
    the rest cascade to ``custom`` so we don't silently lose them.
    """
    services_set = set(services)
    envs_set = set(envs)

    if "@" not in key:
        return ParsedAtom(base_id=key)

    head, *qualifiers = key.split("@")
    if not head:
        # Pathological `@something` with no head — treat the whole as custom.
        return ParsedAtom(base_id=key)

    service: str | None = None
    env: str | None = None
    custom: list[str] = []

    for q in qualifiers:
        if not q:
            continue
        if service is None and q in services_set:
            service = q
        elif env is None and q in envs_set:
            env = q
        else:
            custom.append(q)

    return ParsedAtom(
        base_id=head,
        service=service,
        env=env,
        custom=tuple(custom),
    )


def make_target_for(parsed: ParsedAtom) -> str:
    """Convenience: return the Make-target name for a parsed atom.

    Equivalent to ``parsed.make_target``; exposed as a free function for
    callers that prefer the function-style API.
    """
    return parsed.make_target
