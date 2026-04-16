from pathlib import Path

from forktex.fsd.loader import load_standard
from forktex.fsd.makefile import generate_makefiles
from forktex.fsd.profiles import resolve_applicable_atoms
from forktex.manifest.models import ForktexManifest


PROJECT_ROOT = Path("/home/samanu/Desktop/forktex/forktex-py")


def test_workspace_profile_limits_applicable_atoms():
    manifest = ForktexManifest.load(PROJECT_ROOT / "forktex.json")
    applicable, disabled = resolve_applicable_atoms(manifest)

    assert applicable is not None
    assert "deps" in applicable
    assert "build" in applicable
    assert "codegen" not in applicable
    assert "deploy" not in disabled


def test_generate_root_makefile_contains_expected_targets():
    manifest = ForktexManifest.load(PROJECT_ROOT / "forktex.json")
    standard = load_standard()
    generated = generate_makefiles(
        project_root=PROJECT_ROOT,
        standard=standard,
        manifest=manifest,
    )

    content = generated[0].content
    assert "PROJECT_NAME := forktex-py" in content
    assert "install-global: ## Install the latest local forktex CLI globally in editable mode" in content
    assert "format-check: ## Check formatting without rewriting files" in content
    assert "deps-lock: ## Lock dependencies" in content
