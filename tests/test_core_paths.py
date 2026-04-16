from forktex.core.paths import (
    FORKTEX_MANIFEST,
    find_project_root,
    get_manifest_path,
    has_manifest,
    require_project_root,
)


def test_require_project_root_from_test_file():
    root = require_project_root(__file__)
    assert root.name == "forktex-py"
    assert (root / FORKTEX_MANIFEST).is_file()


def test_find_project_root_from_nested_path():
    root = require_project_root(__file__)
    nested = root / "src" / "forktex" / "fsd" / "models.py"
    root = find_project_root(nested)
    assert root is not None
    assert root.name == "forktex-py"


def test_manifest_helpers_use_canonical_name():
    root = require_project_root(__file__)
    assert get_manifest_path(root) == root / FORKTEX_MANIFEST
    assert has_manifest(root)
