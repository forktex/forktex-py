#!/usr/bin/env sh

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

# forktex installer — POSIX (Linux / macOS)
#
# Usage:
#     curl -sSL install.forktex.com/sh | sh
#
# This wrapper finds a Python ≥ 3.12 and hands control to the inlined
# `_install_core.py`. The inlining is done by `scripts/build_installers.py`
# at publish time so the hosted script is self-contained.

set -eu

# Locate Python. Prefer python3; on some Macs only `python3` exists.
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    printf '\033[31m✗\033[0m forktex installer: Python is required (>= 3.12).\n' >&2
    printf '  macOS:   brew install python@3.12\n' >&2
    printf '  Ubuntu:  sudo apt install python3.12 python3.12-venv\n' >&2
    printf '  Debian:  sudo apt install -t bookworm-backports python3.12  (or use deadsnakes)\n' >&2
    printf '  Fedora:  sudo dnf install python3.12\n' >&2
    printf '  Arch:    sudo pacman -S python\n' >&2
    exit 2
fi

exec "$PY" - <<'__FORKTEX_INSTALL_CORE__'
# @@INSTALL_CORE@@
# Fallback when the inliner hasn't been run: fetch from the hosted installer.
import os, sys, urllib.request
url = os.environ.get("FORKTEX_INSTALL_CORE_URL", "https://install.forktex.com/_install_core.py")
exec(urllib.request.urlopen(url).read().decode("utf-8"))
__FORKTEX_INSTALL_CORE__
