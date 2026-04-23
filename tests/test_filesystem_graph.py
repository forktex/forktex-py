from forktex.core.paths import require_project_root
from forktex.filesystem.graph import build_project_graph


def test_build_project_graph_detects_root_packages_and_child_manifests():
    project_root = require_project_root(__file__)

    graph = build_project_graph(project_root)

    package_names = {pkg.name for pkg in graph.packages}
    assert "forktex" in package_names

    # forktex-py is now a single-package repo. The four ecosystem SDKs
    # (forktex-intelligence, forktex-cloud, forktex-core, forktex-documents)
    # live in their own repos and are consumed as ordinary dependencies.
    child_manifest_paths = {
        p.relative_to(project_root).as_posix() for p in graph.child_manifest_paths
    }
    assert child_manifest_paths == set() or all(
        not p.startswith(
            (
                "forktex-core/",
                "forktex-documents/",
                "forktex-intelligence/",
                "forktex-cloud/",
            )
        )
        for p in child_manifest_paths
    )


def test_build_project_graph_detects_main_forktex_domains():
    project_root = require_project_root(__file__)

    graph = build_project_graph(project_root)

    domain_names = {domain.name for domain in graph.domains}
    assert "fsd" in domain_names
    assert "architecture" in domain_names
    assert "manifest" in domain_names
    assert "agent" in domain_names
