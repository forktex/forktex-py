"""Guard the build-context `root_prefix` derivation in `forktex cloud up`.

`_run_local` derives the SDK's `root_prefix` as the relative hop from the
generated compose file's directory up to the project root
(`os.path.relpath(project_root, compose_target.parent)`) instead of assuming a
fixed depth. The original `network/network` bug came from that hop being
hard-coded and silently drifting when the compose moved into `.forktex/cache/`.
This pins the invariant: for the standard layout the derived prefix is `../..`,
and it always points back at the project root.
"""

import os
from pathlib import Path

from forktex.substrate.paths import compose_path


def _derived_root_prefix(project_root: Path) -> str:
    compose_target = compose_path(project_root, "local")
    return os.path.relpath(project_root, compose_target.parent)


def test_derived_prefix_is_two_levels_for_cache_layout(tmp_path):
    # .forktex/cache/ is two directories below the project root.
    assert _derived_root_prefix(tmp_path) == os.path.join("..", "..")


def test_derived_prefix_round_trips_to_project_root(tmp_path):
    compose_dir = compose_path(tmp_path, "local").parent
    prefix = _derived_root_prefix(tmp_path)
    assert (compose_dir / prefix).resolve() == tmp_path.resolve()
