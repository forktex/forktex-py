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

"""Deep-merge for ``ForktexManifest`` per-env overlays.

Overlay rules:

- Dicts merge recursively. Overlay scalars win over base scalars.
- Lists of records keyed by ``id`` or ``name`` merge by key: an overlay
  entry replaces the base entry with the same key; new entries append.
- Plain lists (no id/name key) replace the base list entirely. This
  prevents accidental concatenation when the user meant to *replace*
  (e.g. ``cloud.environments[]`` in a per-env overlay).

These rules mirror the cloud SDK's existing overlay semantics so a
single ``forktex.<env>.json`` file behaves the same across both tools.
"""

from __future__ import annotations

from typing import Any

__all__ = ["deep_merge"]


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict that is ``base`` with ``overlay`` deep-merged in."""
    result: dict[str, Any] = dict(base)
    for key, ov_value in overlay.items():
        if key in result:
            base_value = result[key]
            result[key] = _merge_values(base_value, ov_value)
        else:
            result[key] = ov_value
    return result


def _merge_values(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        return deep_merge(base, overlay)
    if isinstance(base, list) and isinstance(overlay, list):
        return _merge_lists(base, overlay)
    return overlay  # scalar or type-mismatch — overlay wins


def _record_key(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    for key_field in ("id", "name"):
        value = item.get(key_field)
        if isinstance(value, str) and value:
            return f"{key_field}:{value}"
    return None


def _merge_lists(base: list[Any], overlay: list[Any]) -> list[Any]:
    # If every entry on both sides is keyable, merge by key. Otherwise the
    # overlay replaces the base (predictable, matches user intent).
    base_keys = [_record_key(x) for x in base]
    overlay_keys = [_record_key(x) for x in overlay]
    if not base or not overlay:
        return list(overlay) if overlay else list(base)
    if any(k is None for k in base_keys + overlay_keys):
        return list(overlay)

    by_key: dict[str, Any] = {}
    order: list[str] = []
    for item, key in zip(base, base_keys, strict=True):
        assert key is not None  # narrowed above
        by_key[key] = item
        order.append(key)
    for item, key in zip(overlay, overlay_keys, strict=True):
        assert key is not None
        if key in by_key:
            existing = by_key[key]
            if isinstance(existing, dict) and isinstance(item, dict):
                by_key[key] = deep_merge(existing, item)
            else:
                by_key[key] = item
        else:
            by_key[key] = item
            order.append(key)
    return [by_key[k] for k in order]
