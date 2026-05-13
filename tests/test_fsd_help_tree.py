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

from forktex.fsd.help_tree import build_help_tree, render_help_text
from forktex.fsd.loader import load_standard
from forktex.manifest.models import ForktexManifest


def _manifest():
    return ForktexManifest.model_validate(
        {
            "manifestVersion": "1.1.0",
            "name": "demo",
            "fsd": {
                "version": "1.3.0",
                "profiles": ["workspace/python-monorepo"],
                "atoms": {
                    "apply@local@web": {
                        "description": "Apply web locally",
                        "commands": ["echo apply"],
                    },
                    "publish@test": {
                        "description": "Publish to test registry",
                        "commands": ["echo publish"],
                    },
                },
            },
            "packages": [
                {
                    "name": "web",
                    "path": "web",
                    "version": "0.1.0",
                    "language": "python",
                    "publishable": True,
                }
            ],
            "cloud": {"environments": [{"name": "local"}, {"name": "prod"}]},
        }
    )


def test_help_tree_contains_declared_targets_and_suggestions():
    standard = load_standard()
    tree = build_help_tree(standard, _manifest(), cli_atoms={"apply", "publish"})

    by_target = {entry.target: entry for entry in tree.entries}

    assert by_target["apply-web-local"].kind == "custom"
    assert by_target["apply-web-local"].make_invocation == "make apply-web-local"
    assert by_target["publish-test"].kind == "custom"
    assert "monitor-local-logs" in by_target
    assert by_target["monitor-local-logs"].kind == "suggested"
    assert by_target["monitor-local-logs"].runnable is False


def test_plain_renderer_is_deterministic_and_marks_surfaces():
    standard = load_standard()
    tree = build_help_tree(standard, _manifest(), cli_atoms={"apply"})

    text = render_help_text(tree, atom_id="apply")

    assert "demo help: apply" in text
    assert "apply-web-local" in text
    assert "make apply" in text
    assert "forktex apply" in text
    assert "suggest:" in text
