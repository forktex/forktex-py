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
        if applicable is not None and atom.id not in applicable:
            continue
        if atom.id in disabled:
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


def _make_target_comment(atom: Atom, target: str) -> str:
    return f"{target}: ## {atom.description}"


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
    _, subpaths = _package_paths(manifest)

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
        lines = ["pytest tests/ -x -q"]
        for pkg in subpaths:
            lines.append(f"cd {pkg} && pytest tests/ -x -q 2>/dev/null || true")
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
        return ["pytest tests/ -x -q 2>/dev/null || pytest -x -q"]
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
) -> list[str]:
    lines = [_make_target_comment(atom, target)]
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


def _root_secondary_targets() -> list[str]:
    return [
        "format-check: ## Check formatting without rewriting files",
        "\truff format --check src/ tests/",
        "\t@for pkg in $(SUBPACKAGES); do \\",
        "\t\truff format --check $$pkg/src/ $$pkg/tests/ 2>/dev/null || true; \\",
        "\tdone",
        "",
        "lint-fix: ## Lint and auto-fix where possible",
        "\truff check --fix src/ tests/",
        "\t@for pkg in $(SUBPACKAGES); do \\",
        "\t\truff check --fix $$pkg/src/ $$pkg/tests/ 2>/dev/null || true; \\",
        "\tdone",
        "",
        "test-cov: ## Run tests with coverage",
        "\tpytest tests/ --cov=src --cov-report=term-missing",
        "",
        "deps-lock: ## Lock dependencies",
        "\tpoetry lock",
        "",
        "local: start",
        "",
        "dev: start",
        "",
        "local-down: stop",
        "",
        "dev-down: stop",
        "",
        "local-logs: logs",
        "",
        "dev-logs: logs",
        "",
    ]


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
        f"PROJECT_NAME := {manifest.project_name or manifest.name or 'project'}",
        f"SUBPACKAGES := {' '.join(subpaths)}" if subpaths else "SUBPACKAGES :=",
        f"PUBLISHABLE_PACKAGES := {' '.join(publishable_paths)}"
        if publishable_paths
        else "PUBLISHABLE_PACKAGES :=",
        "",
    ]

    for atom in atoms:
        override = _get_atom_override(manifest, atom.id)
        target, aliases = _make_target_names(atom, override)
        commands = _override_commands(_root_atom_commands(atom.id, manifest), override)
        lines.extend(
            _render_target(atom, target=target, aliases=aliases, commands=commands)
        )
        lines.append("")

    custom = _custom_atoms(manifest, standard)
    for synthetic, override in custom:
        target, aliases = _make_target_names(synthetic, override)
        lines.extend(
            _render_target(
                synthetic, target=target, aliases=aliases, commands=override.commands
            )
        )
        lines.append("")

    lines.extend(_root_secondary_targets())
    custom_target_names = [_make_target_names(s, o)[0] for s, o in custom]
    extra_targets = [
        "install-global: ## Install the latest local forktex CLI globally in editable mode",
        "\tpip install --break-system-packages -e .",
        "",
        ".PHONY: "
        + " ".join(
            _dedupe(
                [
                    _make_target_names(atom, _get_atom_override(manifest, atom.id))[0]
                    for atom in atoms
                ]
                + custom_target_names
                + [
                    "local",
                    "dev",
                    "local-down",
                    "dev-down",
                    "local-logs",
                    "dev-logs",
                    "format-check",
                    "lint-fix",
                    "test-cov",
                    "deps-lock",
                    "install-global",
                ]
            )
        ),
    ]
    lines.extend(extra_targets)
    return "\n".join(lines).rstrip() + "\n"


def _package_secondary_targets(src_dir: str = "src") -> list[str]:
    """Secondary targets emitted in every package Makefile.

    These are not FSD atoms, but they're load-bearing for `make ci` (which
    calls `make format-check`) and for everyday package development.
    """
    return [
        "format-check: ## Check formatting without rewriting files",
        f"\truff format --check {src_dir}/ tests/ 2>/dev/null || ruff format --check {src_dir}/",
        "",
        "lint-fix: ## Lint and auto-fix where possible",
        f"\truff check --fix {src_dir}/ tests/ 2>/dev/null || ruff check --fix {src_dir}/",
        "",
    ]


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
        f"PROJECT_NAME := {package_manifest.project_name or package_manifest.name or 'package'}",
        "",
    ]

    for atom in atoms:
        override = _get_atom_override(
            manifest, atom.id, package_manifest=package_manifest
        )
        target, aliases = _make_target_names(atom, override)
        commands = _override_commands(
            _package_atom_commands(atom.id, src_dir), override
        )
        lines.extend(
            _render_target(atom, target=target, aliases=aliases, commands=commands)
        )
        lines.append("")

    custom = _custom_atoms(manifest, standard, package_manifest=package_manifest)
    for synthetic, override in custom:
        target, aliases = _make_target_names(synthetic, override)
        lines.extend(
            _render_target(
                synthetic, target=target, aliases=aliases, commands=override.commands
            )
        )
        lines.append("")

    lines.extend(_package_secondary_targets(src_dir))

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
        + ["format-check", "lint-fix"]
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
