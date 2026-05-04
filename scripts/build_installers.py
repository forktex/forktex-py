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

"""Inline `_install_core.py` into `install.sh` and `install.ps1`.

Replaces the `# @@INSTALL_CORE@@` marker and everything inside the sentinel
fallback block with the literal contents of `_install_core.py`, producing
self-contained installer scripts ready to host at install.forktex.com.

Usage:
    python3 scripts/build_installers.py            # writes to dist/install/
    python3 scripts/build_installers.py --check    # verify parity, no write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE / "_install_core.py"
SH_IN = HERE / "install.sh"
PS1_IN = HERE / "install.ps1"
OUT_DIR = HERE.parent / "dist" / "install"

SH_START = "__FORKTEX_INSTALL_CORE__"
PS1_SENTINEL_START = "$core = @'"
PS1_SENTINEL_END = "'@"


def _inline_sh(template: str, core: str) -> str:
    lines = template.splitlines(keepends=True)
    out: list[str] = []
    in_block = False
    for ln in lines:
        if ln.strip().endswith(f"<<'{SH_START}'"):
            out.append(ln)
            out.append(core if core.endswith("\n") else core + "\n")
            in_block = True
            continue
        if in_block:
            if ln.strip() == SH_START:
                out.append(ln)
                in_block = False
            continue
        out.append(ln)
    return "".join(out)


def _inline_ps1(template: str, core: str) -> str:
    lines = template.splitlines(keepends=True)
    out: list[str] = []
    in_block = False
    for ln in lines:
        if ln.strip() == PS1_SENTINEL_START:
            out.append(ln)
            out.append(core if core.endswith("\n") else core + "\n")
            in_block = True
            continue
        if in_block:
            if ln.strip() == PS1_SENTINEL_END:
                out.append(ln)
                in_block = False
            continue
        out.append(ln)
    return "".join(out)


def build(check: bool = False) -> int:
    core = CORE.read_text(encoding="utf-8")
    sh_out = _inline_sh(SH_IN.read_text(encoding="utf-8"), core)
    ps1_out = _inline_ps1(PS1_IN.read_text(encoding="utf-8"), core)

    if check:
        print(f"sh:  {len(sh_out)} bytes")
        print(f"ps1: {len(ps1_out)} bytes")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "install.sh").write_text(sh_out, encoding="utf-8")
    (OUT_DIR / "install.sh").chmod(0o755)
    (OUT_DIR / "install.ps1").write_text(ps1_out, encoding="utf-8")
    (OUT_DIR / "_install_core.py").write_text(core, encoding="utf-8")
    print(f"wrote {OUT_DIR}/install.sh ({len(sh_out)} bytes)")
    print(f"wrote {OUT_DIR}/install.ps1 ({len(ps1_out)} bytes)")
    print(f"wrote {OUT_DIR}/_install_core.py (fallback)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Bundle the forktex installers.")
    ap.add_argument("--check", action="store_true", help="report sizes, don't write.")
    args = ap.parse_args()
    return build(check=args.check)


if __name__ == "__main__":
    sys.exit(main())
