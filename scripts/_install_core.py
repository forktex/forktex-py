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

"""Shared installer logic for the forktex CLI.

Inlined into `install.sh` and `install.ps1` by `build_installers.py` at
publish time so the hosted one-liners remain self-contained.

Flow:
    1. Verify Python >= 3.14.
    2. Pick install strategy in this order:
         (a) `pipx install forktex`                              [preferred]
         (b) `python -m pip install --user forktex`              [fallback]
         (c) `python -m pip install --user --break-system-packages forktex`
                                                                 [PEP 668 consent]
    3. Invoke `forktex info` to seed `~/.forktex/` / `%APPDATA%/forktex/` via
       `forktex_cloud.paths.ensure_global_dir()`.
    4. Print a short "what's next" footer.

The script is intentionally stdlib-only — it runs *before* forktex is
installed, so it cannot import anything from it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional

MIN_PY = (3, 12)
PACKAGE = "forktex"
INDEX_URL_HINT = os.environ.get("FORKTEX_INDEX_URL")  # let users point at TestPyPI for now


class InstallError(RuntimeError):
    pass


# ── pretty output (no rich here — stdlib only) ──────────────────────────────


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb"


_COLOR = _supports_color()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def ok(msg: str) -> None:
    print(_c("32", "✓"), msg)


def info(msg: str) -> None:
    print(_c("36", "·"), msg)


def warn(msg: str) -> None:
    print(_c("33", "⚠"), msg, file=sys.stderr)


def fail(msg: str) -> None:
    print(_c("31", "✗"), msg, file=sys.stderr)


# ── checks ──────────────────────────────────────────────────────────────────


def check_python() -> None:
    if sys.version_info < MIN_PY:
        ver = f"{MIN_PY[0]}.{MIN_PY[1]}"
        raise InstallError(
            f"forktex requires Python >= {ver}; "
            f"found {sys.version_info.major}.{sys.version_info.minor}.\n"
            f"  macOS:    brew install python@{ver}\n"
            f"  Ubuntu:   sudo apt install python{ver} python{ver}-venv  "
            f"(or: sudo add-apt-repository ppa:deadsnakes/ppa  for older Ubuntu)\n"
            f"  Debian:   sudo apt install -t bookworm-backports python{ver}\n"
            f"  Fedora:   sudo dnf install python{ver}\n"
            f"  Arch:     sudo pacman -S python\n"
            f"  Windows:  winget install Python.Python.{ver}"
        )
    ok(f"python {sys.version_info.major}.{sys.version_info.minor} ok")


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    info(" ".join(cmd))
    return subprocess.run(cmd, check=check, text=True, capture_output=False)


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


# ── install strategies ──────────────────────────────────────────────────────


def _in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def try_pipx() -> bool:
    pipx = _which("pipx")
    if not pipx:
        return False
    args = [pipx, "install", "--force"]
    if INDEX_URL_HINT:
        # pipx expects --pip-args as a SINGLE shell-quoted argument.
        args += [
            "--pip-args",
            f"--index-url={INDEX_URL_HINT} --extra-index-url=https://pypi.org/simple/",
        ]
    args.append(PACKAGE)
    try:
        _run(args)
        return True
    except subprocess.CalledProcessError as exc:
        warn(f"pipx install failed (exit {exc.returncode}); trying pip next")
        return False


def try_pip(break_system: bool = False) -> bool:
    args = [sys.executable, "-m", "pip", "install", "--upgrade"]
    if not _in_venv():
        # Only use --user when we're on system python; inside a venv pip
        # rejects --user because user site-packages aren't on the venv's path.
        args.append("--user")
    if break_system:
        args.append("--break-system-packages")
    if INDEX_URL_HINT:
        args += ["--index-url", INDEX_URL_HINT, "--extra-index-url", "https://pypi.org/simple/"]
    args.append(PACKAGE)
    try:
        _run(args)
        return True
    except subprocess.CalledProcessError as exc:
        # PEP 668: "externally-managed-environment" → retry with --break-system-packages once.
        if not break_system and exc.returncode != 0:
            warn("pip blocked by PEP 668; retrying with --break-system-packages")
            return try_pip(break_system=True)
        return False


def offer_pipx_bootstrap() -> bool:
    """Ask the user to install pipx first, then retry."""
    if not sys.stdin.isatty():
        return False  # non-interactive → skip the prompt, fall through to pip
    info("pipx not found — install it? (recommended: isolates forktex + its deps)")
    try:
        answer = input("  install pipx now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if answer and answer not in ("y", "yes", ""):
        return False
    try:
        _run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "pipx"])
        _run([sys.executable, "-m", "pipx", "ensurepath"])
        return True
    except subprocess.CalledProcessError:
        warn("pipx bootstrap failed; falling back to pip --user")
        return False


def install() -> None:
    if try_pipx():
        return
    if offer_pipx_bootstrap() and try_pipx():
        return
    if try_pip():
        return
    raise InstallError("all install strategies failed. See https://forktex.com/install for manual steps.")


# ── post-install ────────────────────────────────────────────────────────────


def seed_forktex_dir() -> None:
    """Invoke `forktex info` so `ensure_global_dir()` runs and the on-disk
    layout is created. Best-effort — failures here are non-fatal."""
    ft = _which("forktex")
    if not ft:
        warn("forktex not on PATH yet — restart your shell or run `source ~/.bashrc`")
        return
    try:
        subprocess.run([ft, "info"], check=False, capture_output=True, timeout=10)
        ok("seeded ~/.forktex/")
    except Exception as exc:
        warn(f"could not seed ~/.forktex/ ({exc}); `forktex info` will do it on first run")


def footer() -> None:
    print()
    print(_c("1;36", "forktex is installed."))
    print()
    print("  next:")
    print(f"    {_c('32', 'forktex')}                 # interactive (chat + menu)")
    print(f"    {_c('32', 'forktex cloud connect')}   # connect to the cloud controller")
    print(f"    {_c('32', 'forktex --help')}          # full command tree")
    print()
    print(f"  docs: https://forktex.com/docs")
    print()


# ── entry ────────────────────────────────────────────────────────────────────


def main() -> int:
    try:
        check_python()
        install()
        seed_forktex_dir()
        footer()
        return 0
    except InstallError as exc:
        fail(str(exc))
        return 2
    except KeyboardInterrupt:
        fail("aborted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
