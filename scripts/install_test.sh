#!/usr/bin/env bash

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

# Smoke-test the bundled installers across Linux distros via Docker.
#
#     bash scripts/install_test.sh                # all supported images
#     bash scripts/install_test.sh ubuntu-22.04   # one row
#
# Each row runs the built install.sh and asserts `forktex --version` works.
# Requires `python3 scripts/build_installers.py` to have been run first.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DIST="$ROOT/dist/install"

if [ ! -f "$DIST/install.sh" ]; then
    echo "build first:  python3 $HERE/build_installers.py" >&2
    exit 2
fi

# row:<label> image bootstrap
# Floor is Python 3.14. ubuntu-22.04 + python:3.11-slim are *expected-to-fail*
# (they verify the wrapper's "Python ≥ 3.14 required" rejection path renders).
ROWS=(
    "ubuntu-24.04|ubuntu:24.04|apt-get update -qq && apt-get install -y -qq curl python3 python3-venv pipx"
    "fedora-41|fedora:41|dnf install -y -q python3 python3-pip pipx"
    "archlinux|archlinux:latest|pacman -Sy --noconfirm python python-pip"
    "py314|python:3.14-slim|apt-get update -qq && apt-get install -y -qq pipx"
    "py313|python:3.13-slim|apt-get update -qq && apt-get install -y -qq pipx"
)

# Negative-path rows: must FAIL with exit 2 and print the upgrade hint.
NEGATIVE_ROWS=(
    "py311-reject|python:3.11-slim|true"
)

WANT="${1:-}"

pass=0 ; fail=0 ; failures=()

for row in "${ROWS[@]}"; do
    label="${row%%|*}"
    rest="${row#*|}"
    image="${rest%%|*}"
    bootstrap="${rest#*|}"

    if [ -n "$WANT" ] && [ "$WANT" != "$label" ]; then
        continue
    fi

    echo
    echo "── $label ($image) ──"

    # TestPyPI fallback for now — real PyPI once the package is published.
    env_flag="-e FORKTEX_INDEX_URL=https://test.pypi.org/simple/"

    if docker run --rm $env_flag \
        -v "$DIST:/dist:ro" \
        "$image" bash -c "
            set -e
            $bootstrap
            sh /dist/install.sh
            forktex --version
            forktex status --no-probe
            test -f \$HOME/.forktex/.version
        "; then
        pass=$((pass+1))
        echo "✓ $label"
    else
        fail=$((fail+1))
        failures+=("$label")
        echo "✗ $label"
    fi
done

# Negative-path checks: installer must reject Python < 3.14 cleanly.
for row in "${NEGATIVE_ROWS[@]}"; do
    label="${row%%|*}"
    rest="${row#*|}"
    image="${rest%%|*}"
    bootstrap="${rest#*|}"

    if [ -n "$WANT" ] && [ "$WANT" != "$label" ]; then
        continue
    fi

    echo
    echo "── $label ($image) [expected reject] ──"

    out=$(docker run --rm \
        -v "$DIST:/dist:ro" \
        "$image" bash -c "
            set -e
            $bootstrap
            sh /dist/install.sh 2>&1
            exit 99
        " 2>&1) && rc=$? || rc=$?

    if [ "$rc" = "2" ] && echo "$out" | grep -q "Python >= 3.14"; then
        pass=$((pass+1))
        echo "✓ $label (rejected with rc=2 + correct hint)"
    else
        fail=$((fail+1))
        failures+=("$label (got rc=$rc)")
        echo "✗ $label  expected rc=2 + 'Python >= 3.14' message"
        echo "$out" | tail -8
    fi
done

echo
echo "── summary: $pass passed, $fail failed ──"
if [ $fail -gt 0 ]; then
    printf '  failed: %s\n' "${failures[@]}"
    exit 1
fi
