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

"""Generate and sync Makefiles from the atom catalog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forktex.fsd.models import Atom, FSDStandard
from forktex.fsd.profiles import resolve_applicable_atoms
from forktex.manifest.models import AtomOverride, ForktexManifest


def _custom_atoms(
    manifest: ForktexManifest,
    standard: FSDStandard,
    *,
    package_manifest: ForktexManifest | None = None,
) -> list[tuple[Atom, AtomOverride]]:
    """Resolve custom (non-standard) atoms declared in forktex.json.

    A custom atom is any entry under ``fsd.atoms`` whose id is NOT in the
    FSD standard catalog and which provides ``commands``. It is rendered as
    a regular Make target with the override's commands and description.
    """
    config = (
        package_manifest.fsd
        if package_manifest and package_manifest.fsd
        else manifest.fsd
    )
    if not config:
        return []
    standard_ids = set(standard.atoms_by_id.keys())
    result: list[tuple[Atom, AtomOverride]] = []
    for atom_id, override in config.atoms.items():
        if atom_id in standard_ids:
            continue
        if not override.commands:
            continue
        synthetic = Atom(
            id=atom_id,
            name=atom_id,
            description=override.description or f"Custom atom: {atom_id}",
        )
        result.append((synthetic, override))
    return result


@dataclass(frozen=True)
class GeneratedMakefile:
    unit_name: str
    unit_path: Path
    content: str


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _normalize_profile_atom_ids(
    standard: FSDStandard,
    manifest: ForktexManifest,
    *,
    package_manifest: ForktexManifest | None = None,
) -> list[str]:
    applicable, disabled = resolve_applicable_atoms(
        manifest, package_manifest=package_manifest
    )
    config = (
        package_manifest.fsd
        if package_manifest and package_manifest.fsd
        else manifest.fsd
    )
    override_disabled = {
        atom_id
        for atom_id, override in (config.atoms.items() if config else [])
        if override.disabled
    }
    disabled |= override_disabled

    atoms = []
    for atom in standard.atoms:
        override = (
            config.atoms.get(atom.id) if config and atom.id in config.atoms else None
        )
        explicitly_enabled = bool(
            override
            and not override.disabled
            and (
                override.commands
                or override.targets
                or override.aliases
                or override.description
            )
        )
        if (
            applicable is not None
            and atom.id not in applicable
            and not explicitly_enabled
        ):
            continue
        if atom.id in disabled and not explicitly_enabled:
            continue
        # Skip atoms that don't use the `make` resolve strategy: they're
        # satisfied by filesystem paths, manifest fields, or file content,
        # so a Make target for them is meaningless noise.
        if not atom.make_targets:
            continue
        atoms.append(atom.id)
    return atoms


def _get_atom_override(
    manifest: ForktexManifest,
    atom_id: str,
    *,
    package_manifest: ForktexManifest | None = None,
) -> AtomOverride | None:
    config = (
        package_manifest.fsd
        if package_manifest and package_manifest.fsd
        else manifest.fsd
    )
    if not config:
        return None
    return config.atoms.get(atom_id)


def _make_target_names(
    atom: Atom, override: AtomOverride | None
) -> tuple[str, list[str]]:
    canonical = atom.make_targets or [atom.id]
    if override and override.targets:
        primary = override.targets[0]
        aliases = _dedupe(override.aliases)
        return primary, aliases
    return canonical[0], (override.aliases if override else [])


def _make_target_comment(
    atom: Atom, target: str, override: AtomOverride | None = None
) -> str:
    """Pick the description rendered into the Makefile help comment.

    A manifest override's description takes precedence over the standard
    atom's description, so authors can retitle a built-in atom (e.g.
    relabel ``codegen`` to "Not applicable" for projects that don't ship
    generated code) without forking the FSD catalog.
    """
    description = (
        override.description if override and override.description else atom.description
    )
    return f"{target}: ## {description}"


def _package_paths(manifest: ForktexManifest) -> tuple[list[str], list[str]]:
    publishable = [
        pkg.path
        for pkg in manifest.packages
        if pkg.publishable and pkg.language == "python"
    ]
    root_paths = [p for p in publishable if p == "."]
    subpaths = [p for p in publishable if p != "."]
    return root_paths, subpaths


def _deps_lines(manifest: ForktexManifest) -> list[str]:
    _, subpaths = _package_paths(manifest)
    editable_paths = subpaths + ["."]
    editable_args = " ".join(f"-e {path}" for path in editable_paths)
    return [
        f"pip install --break-system-packages {editable_args} 2>/dev/null || \\",
        f"\tpip install {editable_args}",
    ]


def _loop_lines(
    command: str, paths: list[str], *, prefix: str = "", tolerate_failure: bool = False
) -> list[str]:
    if not paths:
        return []
    suffix = " 2>/dev/null || true" if tolerate_failure else ""
    return [
        "@for pkg in $(SUBPACKAGES); do \\",
        f'\t\techo "  {prefix}$$pkg..."; \\',
        f"\t\tcd $$pkg && {command} && cd ..{suffix}; \\",
        "\tdone",
    ]


def _root_atom_commands(atom_id: str, manifest: ForktexManifest) -> list[str]:
    root_paths, subpaths = _package_paths(manifest)
    has_python = bool(root_paths) or bool(subpaths)

    # Python-shaped defaults only make sense when the manifest actually
    # declares python packages. For non-python root manifests (e.g. a
    # KnowledgeDirectory), emit a TODO stub and let `fsd.atoms[*].commands`
    # in the manifest supply the real body via _override_commands().
    python_specific = {
        "deps",
        "format",
        "lint",
        "typecheck",
        "test",
        "security-audit",
        "build",
        "publish",
        "publish-check",
        "publish-test",
    }
    if not has_python and atom_id in python_specific:
        return [f'@echo "TODO: configure {atom_id} for $(PROJECT_NAME)"']

    if atom_id == "deps":
        return _deps_lines(manifest)
    if atom_id == "format":
        return [
            "ruff format src/ tests/",
            "@for pkg in $(SUBPACKAGES); do \\",
            '\t\techo "  Formatting $$pkg..."; \\',
            "\t\truff format $$pkg/src/ $$pkg/tests/ 2>/dev/null || true; \\",
            "\tdone",
        ]
    if atom_id == "lint":
        return [
            "ruff check src/ tests/",
            "@for pkg in $(SUBPACKAGES); do \\",
            '\t\techo "  Linting $$pkg..."; \\',
            "\t\truff check $$pkg/src/ $$pkg/tests/ 2>/dev/null || true; \\",
            "\tdone",
        ]
    if atom_id == "typecheck":
        return ["python -m pyright src/ 2>/dev/null || python -m mypy src/"]
    if atom_id == "test":
        lines = ["poetry run pytest tests/ -x -q"]
        for pkg in subpaths:
            lines.append(
                f"cd {pkg} && poetry run pytest tests/ -x -q 2>/dev/null || true"
            )
        return lines
    if atom_id == "security-audit":
        return ['pip-audit 2>/dev/null || echo "pip-audit not installed, skipping"']
    if atom_id == "start":
        return [
            "@$(MAKE) deps",
            '@echo ""',
            '@echo "$(PROJECT_NAME) runtime ready."',
            '@echo "  Run: forktex --version"',
            '@echo "  Run: make test"',
            '@echo ""',
        ]
    if atom_id == "stop":
        return ['@echo "$(PROJECT_NAME) has no managed long-running runtime to stop."']
    if atom_id == "logs":
        return ['@echo "$(PROJECT_NAME) has no managed runtime logs to stream."']
    if atom_id == "build":
        return [
            "@for pkg in $(PUBLISHABLE_PACKAGES); do \\",
            '\t\techo "Building $$pkg..."; \\',
            "\t\tcd $$pkg && rm -rf dist/ && python3 -m build && cd ..; \\",
            "\tdone",
            '@echo "All packages built."',
        ]
    if atom_id == "publish":
        return [
            "@for pkg in $(PUBLISHABLE_PACKAGES); do \\",
            '\t\techo "Publishing $$pkg..."; \\',
            "\t\tcd $$pkg && rm -rf dist/ && python3 -m build && twine upload dist/* && cd ..; \\",
            "\tdone",
            '@echo "All packages published."',
        ]
    if atom_id == "publish-check":
        return [
            "@for pkg in $(PUBLISHABLE_PACKAGES); do \\",
            '\t\techo "Checking $$pkg..."; \\',
            "\t\t$(MAKE) -C $$pkg publish-check; \\",
            "\tdone",
        ]
    if atom_id == "publish-test":
        return [
            "@for pkg in $(PUBLISHABLE_PACKAGES); do \\",
            '\t\techo "Test-publishing $$pkg..."; \\',
            "\t\t$(MAKE) -C $$pkg publish-test; \\",
            "\tdone",
        ]
    if atom_id == "ci":
        return [
            "@$(MAKE) format-check lint test",
            '@echo "CI passed for $(PROJECT_NAME)"',
        ]
    if atom_id == "clean":
        return [
            "find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name dist -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name build -exec rm -rf {} + 2>/dev/null; true",
            'find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null; true',
            "find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null; true",
            "find . -type f -name .coverage -delete 2>/dev/null; true",
        ]
    if atom_id == "help":
        return [
            "@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \\",
            '\t\tawk \'BEGIN {FS = ":.*?## "}; {printf "  \\033[36m%-22s\\033[0m %s\\n", $$1, $$2}\'',
        ]
    return [f'@echo "TODO: implement {atom_id} for $(PROJECT_NAME)"']


def _package_atom_commands(atom_id: str, src_dir: str = "src") -> list[str]:
    if atom_id == "deps":
        return [
            "pip install --break-system-packages -e . 2>/dev/null || \\",
            "\tpip install -e .",
        ]
    if atom_id == "format":
        return [f"ruff format {src_dir}/ tests/ 2>/dev/null || ruff format {src_dir}/"]
    if atom_id == "lint":
        return [f"ruff check {src_dir}/ tests/ 2>/dev/null || ruff check {src_dir}/"]
    if atom_id == "typecheck":
        return [
            f"python -m pyright {src_dir}/ 2>/dev/null || python -m mypy {src_dir}/"
        ]
    if atom_id == "test":
        return ["poetry run pytest tests/ -x -q 2>/dev/null || poetry run pytest -x -q"]
    if atom_id == "security-audit":
        return ['pip-audit 2>/dev/null || echo "pip-audit not installed, skipping"']
    if atom_id == "build":
        return ["rm -rf dist/ && python3 -m build"]
    if atom_id == "publish":
        return ["twine upload dist/*"]
    if atom_id == "publish-check":
        return [
            '@echo "Checking publish readiness..."',
            "@test -f README.md || (echo 'ERROR: README.md missing' && exit 1)",
            "@test -f LICENSE || (echo 'ERROR: LICENSE missing' && exit 1)",
            "python3 -m build 2>/dev/null && twine check dist/* && rm -rf dist/",
            '@echo "Ready to publish."',
        ]
    if atom_id == "publish-test":
        return [
            "rm -rf dist/ && python3 -m build",
            "twine upload --repository testpypi dist/*",
        ]
    if atom_id == "ci":
        return [
            "@$(MAKE) format-check lint test",
            '@echo "CI passed for $(PROJECT_NAME)"',
        ]
    if atom_id == "clean":
        return [
            "find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name dist -exec rm -rf {} + 2>/dev/null; true",
            "find . -type d -name build -exec rm -rf {} + 2>/dev/null; true",
            'find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null; true',
            "find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null; true",
            "find . -type f -name .coverage -delete 2>/dev/null; true",
        ]
    if atom_id == "help":
        return [
            "@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \\",
            '\t\tawk \'BEGIN {FS = ":.*?## "}; {printf "  \\033[36m%-18s\\033[0m %s\\n", $$1, $$2}\'',
        ]
    return [f'@echo "TODO: implement {atom_id} for $(PROJECT_NAME)"']


def _override_commands(default: list[str], override: AtomOverride | None) -> list[str]:
    if override and override.commands:
        return override.commands
    return default


def _render_target(
    atom: Atom,
    *,
    target: str,
    aliases: list[str],
    commands: list[str],
    override: AtomOverride | None = None,
) -> list[str]:
    lines = [_make_target_comment(atom, target, override)]
    lines.extend(
        f"\t{line}" if not line.startswith("\t") else line for line in commands
    )
    # Aliases declared as separate no-op rules AFTER the target's commands.
    # Putting them before the commands would make Make attach the commands
    # to the alias rule instead of the target itself.
    for alias in aliases:
        lines.append("")
        lines.append(f"{alias}: {target}")
    return lines


def _declared_target_names(
    atoms: list[Atom],
    custom: list[tuple[Atom, AtomOverride]],
    *,
    manifest: ForktexManifest,
    package_manifest: ForktexManifest | None = None,
) -> set[str]:
    names: set[str] = set()
    for atom in atoms:
        target, aliases = _make_target_names(
            atom,
            _get_atom_override(manifest, atom.id, package_manifest=package_manifest),
        )
        names.add(target)
        names.update(aliases)
    for synthetic, override in custom:
        target, aliases = _make_target_names(synthetic, override)
        names.add(target)
        names.update(aliases)
    return names


def _root_secondary_targets(
    manifest: ForktexManifest,
    *,
    existing_targets: set[str],
) -> tuple[list[str], list[str]]:
    root_paths, subpaths = _package_paths(manifest)
    has_root_python = bool(root_paths)
    has_workspace_runtime = bool(root_paths or subpaths)
    if not has_workspace_runtime:
        # Non-python root manifests (e.g. KnowledgeDirectory) don't need
        # ruff/pytest/poetry secondaries, and their start/stop/logs atoms
        # are typically disabled by the profile so the alias rules would
        # dangle. Emit nothing.
        return [], []

    lines: list[str] = []
    phony: list[str] = []

    if has_root_python and "format-check" not in existing_targets:
        lines.extend(
            [
                "format-check: ## Check formatting without rewriting files",
                "\truff format --check src/ tests/",
                "\t@for pkg in $(SUBPACKAGES); do \\",
                "\t\truff format --check $$pkg/src/ $$pkg/tests/ 2>/dev/null || true; \\",
                "\tdone",
                "",
            ]
        )
        phony.append("format-check")

    if has_root_python and "lint-fix" not in existing_targets:
        lines.extend(
            [
                "lint-fix: ## Lint and auto-fix where possible",
                "\truff check --fix src/ tests/",
                "\t@for pkg in $(SUBPACKAGES); do \\",
                "\t\truff check --fix $$pkg/src/ $$pkg/tests/ 2>/dev/null || true; \\",
                "\tdone",
                "",
            ]
        )
        phony.append("lint-fix")

    if has_root_python and "test-cov" not in existing_targets:
        lines.extend(
            [
                "test-cov: ## Run tests with coverage",
                "\tpoetry run pytest tests/ --cov=src --cov-report=term-missing",
                "",
            ]
        )
        phony.append("test-cov")

    if has_root_python and "deps-lock" not in existing_targets:
        lines.extend(
            [
                "deps-lock: ## Lock dependencies",
                "\tpoetry lock",
                "",
            ]
        )
        phony.append("deps-lock")

    for alias in ("local", "local-down", "local-logs"):
        if alias in existing_targets:
            continue
        target = {
            "local": "start",
            "local-down": "stop",
            "local-logs": "logs",
        }[alias]
        lines.extend([f"{alias}: {target}", ""])
        phony.append(alias)

    return lines, phony


def generate_root_makefile(standard: FSDStandard, manifest: ForktexManifest) -> str:
    atom_ids = _normalize_profile_atom_ids(standard, manifest)
    atoms = [
        standard.atoms_by_id[atom_id]
        for atom_id in atom_ids
        if atom_id in standard.atoms_by_id
    ]
    _, subpaths = _package_paths(manifest)
    publishable_paths = [
        pkg.path
        for pkg in manifest.packages
        if pkg.publishable and pkg.language == "python"
    ]

    lines = [
        "# Generated by `forktex fsd makefile sync`",
        "# Unit: root project",
        ".DEFAULT_GOAL := help",
        f"PROJECT_NAME := {manifest.project_name or manifest.name or 'project'}",
        f"SUBPACKAGES := {' '.join(subpaths)}" if subpaths else "SUBPACKAGES :=",
        f"PUBLISHABLE_PACKAGES := {' '.join(publishable_paths)}"
        if publishable_paths
        else "PUBLISHABLE_PACKAGES :=",
        "",
    ]

    # Resolve custom atoms first so the standard-atom loop can skip any
    # atom whose primary make-target collides with a custom override.
    # Without this, the standard's ``license`` atom (make_targets =
    # ['license-check', 'license-fix']) and a custom ``license-check``
    # override would both emit a ``license-check:`` rule, leaving two
    # definitions in the generated Makefile.
    custom = _custom_atoms(manifest, standard)
    custom_target_collisions: set[str] = set()
    for synthetic, override in custom:
        ctarget, caliases = _make_target_names(synthetic, override)
        custom_target_collisions.add(ctarget)
        custom_target_collisions.update(caliases)

    for atom in atoms:
        override = _get_atom_override(manifest, atom.id)
        target, aliases = _make_target_names(atom, override)
        if target in custom_target_collisions:
            continue
        commands = _override_commands(_root_atom_commands(atom.id, manifest), override)
        lines.extend(
            _render_target(
                atom,
                target=target,
                aliases=aliases,
                commands=commands,
                override=override,
            )
        )
        lines.append("")

    for synthetic, override in custom:
        target, aliases = _make_target_names(synthetic, override)
        lines.extend(
            _render_target(
                synthetic,
                target=target,
                aliases=aliases,
                commands=override.commands,
                override=override,
            )
        )
        lines.append("")

    declared_targets = _declared_target_names(atoms, custom, manifest=manifest)
    secondary_lines, secondary_phony = _root_secondary_targets(
        manifest, existing_targets=declared_targets
    )
    lines.extend(secondary_lines)
    custom_target_names = [_make_target_names(s, o)[0] for s, o in custom]
    root_paths, subpaths = _package_paths(manifest)
    has_root_python = bool(root_paths)
    extra_targets: list[str] = []
    if has_root_python and "install-global" not in declared_targets:
        extra_targets.extend(
            [
                "install-global: ## Install the latest local forktex CLI globally in editable mode",
                "\tpip install --break-system-packages -e .",
                "",
            ]
        )
        secondary_phony.append("install-global")
    extra_targets.append(
        ".PHONY: "
        + " ".join(
            _dedupe(
                [
                    _make_target_names(atom, _get_atom_override(manifest, atom.id))[0]
                    for atom in atoms
                ]
                + custom_target_names
                + secondary_phony
            )
        )
    )
    lines.extend(extra_targets)
    return "\n".join(lines).rstrip() + "\n"


def _package_secondary_targets(
    src_dir: str = "src",
    *,
    existing_targets: set[str],
) -> tuple[list[str], list[str]]:
    """Secondary targets emitted in every package Makefile.

    These are not FSD atoms, but they're load-bearing for `make ci` (which
    calls `make format-check`) and for everyday package development.
    """
    lines: list[str] = []
    phony: list[str] = []
    if "format-check" not in existing_targets:
        lines.extend(
            [
                "format-check: ## Check formatting without rewriting files",
                f"\truff format --check {src_dir}/ tests/ 2>/dev/null || ruff format --check {src_dir}/",
                "",
            ]
        )
        phony.append("format-check")
    if "lint-fix" not in existing_targets:
        lines.extend(
            [
                "lint-fix: ## Lint and auto-fix where possible",
                f"\truff check --fix {src_dir}/ tests/ 2>/dev/null || ruff check --fix {src_dir}/",
                "",
            ]
        )
        phony.append("lint-fix")
    return lines, phony


def generate_package_makefile(
    standard: FSDStandard,
    manifest: ForktexManifest,
    package_manifest: ForktexManifest,
    *,
    package_dir: Path | None = None,
) -> str:
    atom_ids = _normalize_profile_atom_ids(
        standard, manifest, package_manifest=package_manifest
    )
    atoms = [
        standard.atoms_by_id[atom_id]
        for atom_id in atom_ids
        if atom_id in standard.atoms_by_id
    ]

    # Detect package layout: prefer `app/` (FastAPI convention) when present,
    # fall back to `src/` (Python library convention).
    src_dir = "src"
    if (
        package_dir is not None
        and (package_dir / "app").is_dir()
        and not (package_dir / "src").is_dir()
    ):
        src_dir = "app"

    lines = [
        "# Generated by `forktex fsd makefile sync`",
        "# Unit: package",
        ".DEFAULT_GOAL := help",
        f"PROJECT_NAME := {package_manifest.project_name or package_manifest.name or 'package'}",
        "",
    ]

    custom = _custom_atoms(manifest, standard, package_manifest=package_manifest)
    custom_target_collisions: set[str] = set()
    for synthetic, override in custom:
        ctarget, caliases = _make_target_names(synthetic, override)
        custom_target_collisions.add(ctarget)
        custom_target_collisions.update(caliases)

    for atom in atoms:
        override = _get_atom_override(
            manifest, atom.id, package_manifest=package_manifest
        )
        target, aliases = _make_target_names(atom, override)
        if target in custom_target_collisions:
            continue
        commands = _override_commands(
            _package_atom_commands(atom.id, src_dir), override
        )
        lines.extend(
            _render_target(
                atom,
                target=target,
                aliases=aliases,
                commands=commands,
                override=override,
            )
        )
        lines.append("")

    for synthetic, override in custom:
        target, aliases = _make_target_names(synthetic, override)
        lines.extend(
            _render_target(
                synthetic,
                target=target,
                aliases=aliases,
                commands=override.commands,
                override=override,
            )
        )
        lines.append("")

    declared_targets = _declared_target_names(
        atoms,
        custom,
        manifest=manifest,
        package_manifest=package_manifest,
    )
    secondary_lines, secondary_phony = _package_secondary_targets(
        src_dir, existing_targets=declared_targets
    )
    lines.extend(secondary_lines)

    custom_target_names = [_make_target_names(s, o)[0] for s, o in custom]
    phony_targets = _dedupe(
        [
            _make_target_names(
                atom,
                _get_atom_override(
                    manifest, atom.id, package_manifest=package_manifest
                ),
            )[0]
            for atom in atoms
        ]
        + custom_target_names
        + secondary_phony
    )
    lines.append(".PHONY: " + " ".join(phony_targets))
    return "\n".join(lines).rstrip() + "\n"


def generate_makefiles(
    project_root: Path,
    standard: FSDStandard,
    manifest: ForktexManifest,
    *,
    package: str | None = None,
    all_packages: bool = False,
) -> list[GeneratedMakefile]:
    """Generate one or more Makefiles for the current project."""

    generated = [
        GeneratedMakefile(
            unit_name=manifest.project_name or manifest.name or project_root.name,
            unit_path=project_root,
            content=generate_root_makefile(standard, manifest),
        )
    ]

    if not (package or all_packages):
        return generated

    selected_paths: set[str] | None = None
    if package:
        selected_paths = {package}

    for pkg in manifest.packages:
        if pkg.path == ".":
            continue
        if (
            selected_paths
            and pkg.path not in selected_paths
            and pkg.name not in selected_paths
        ):
            continue
        manifest_path = project_root / pkg.path / "forktex.json"
        if not manifest_path.is_file():
            continue
        package_manifest = ForktexManifest.load(manifest_path)
        generated.append(
            GeneratedMakefile(
                unit_name=package_manifest.project_name
                or package_manifest.name
                or pkg.name,
                unit_path=project_root / pkg.path,
                content=generate_package_makefile(
                    standard,
                    manifest,
                    package_manifest,
                    package_dir=project_root / pkg.path,
                ),
            )
        )
    return generated
