"""forktex intelligence index-ecosystem — Index ecosystem knowledge for RAG.

Indexes AGENTS.md files, ecosystem.json, architecture data, and library
definitions into an Intelligence API collection for semantic search by agents.

This creates the "ecosystem brain" — agents can query it to understand
the full FORKTEX factory before taking action.

Usage:
    forktex intelligence index-ecosystem
    forktex intelligence index-ecosystem --collection forktex-ecosystem
    forktex intelligence index-ecosystem --dir ~/Desktop/forktex
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncclick as click

from forktex.agent.ui.console import console, info, error


COLLECTION_NAME = "forktex-ecosystem"

# Files to index, relative to ecosystem root
KNOWLEDGE_FILES = [
    # AGENTS.md files (ground knowledge)
    ("docs/AGENTS.md", "ecosystem-grounding"),
    ("forktex-py/AGENTS.md", "forktex-cli-agent"),
    ("network/AGENTS.md", "network-platform"),
    ("cloud/AGENTS.md", "cloud-platform"),
    ("intelligence/AGENTS.md", "intelligence-platform"),
    ("workflow/AGENTS.md", "workflow-engine"),
    ("contracts/AGENTS.md", "contracts-engine"),
    ("solar/AGENTS.md", "solar-platform"),
    ("corporate/AGENTS.md", "corporate-platform"),
    ("survey/AGENTS.md", "survey-platform"),
    # Ecosystem data
    ("docs/ecosystem.md", "ecosystem-overview"),
    ("docs/overview.md", "factory-overview"),
    ("docs/engineering/libraries.json", "library-graph"),
    # FSD standard
    ("docs/compliance/fsd/README.md", "fsd-standard"),
]


def _find_ecosystem_root(start: Path) -> Path | None:
    """Walk up to find parent with multiple forktex repos."""
    current = start
    for _ in range(5):
        parent = current.parent
        repos = [d for d in parent.iterdir() if d.is_dir() and (d / ".git").is_dir()]
        if len(repos) >= 3:
            return parent
        current = parent
    return None


def _discover_agents_md(root: Path) -> list[tuple[str, str]]:
    """Find all AGENTS.md files under the ecosystem root."""
    files = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        agents_md = d / "AGENTS.md"
        if agents_md.exists():
            rel = str(agents_md.relative_to(root))
            files.append((rel, f"{d.name}-agents"))
    return files


@click.command(name="index-ecosystem")
@click.option("--dir", "-d", "root_dir", default=None, help="Ecosystem root directory")
@click.option("--collection", "-c", default=COLLECTION_NAME, help="Collection name")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be indexed without uploading"
)
async def index_ecosystem(root_dir: str | None, collection: str, dry_run: bool):
    """Index ecosystem knowledge into Intelligence API for RAG queries.

    Creates a vector collection containing all AGENTS.md files, ecosystem
    metadata, and architecture data. Agents can then search this collection
    to understand the full FORKTEX factory.
    """
    if root_dir:
        root = Path(root_dir)
    else:
        root = _find_ecosystem_root(Path.cwd())

    if not root or not root.is_dir():
        error("Could not find ecosystem root. Use --dir to specify.")
        return

    info(f"Ecosystem root: {root}")

    # Discover all indexable files (dedup by path)
    seen_paths: set[str] = set()
    all_files: list[tuple[str, str]] = []

    for rel_path, label in _discover_agents_md(root):
        if rel_path not in seen_paths:
            seen_paths.add(rel_path)
            all_files.append((rel_path, label))

    for rel_path, label in KNOWLEDGE_FILES:
        full = root / rel_path
        if full.exists() and rel_path not in seen_paths:
            seen_paths.add(rel_path)
            all_files.append((rel_path, label))

    # Also discover architecture JSON
    arch_dir = root / ".forktex" / "architecture"
    if arch_dir.exists():
        arch_files = sorted(arch_dir.glob("arch-*.json"))
        if arch_files:
            latest = arch_files[-1]
            all_files.append((str(latest.relative_to(root)), "latest-architecture"))

    console.print(f"\n[bold]Files to index ({len(all_files)}):[/bold]\n")
    for rel_path, label in all_files:
        full = root / rel_path
        exists = full.exists()
        status_icon = "[green]OK[/green]" if exists else "[red]MISSING[/red]"
        size = full.stat().st_size if exists else 0
        console.print(f"  {status_icon} {rel_path:<60} [{label}] ({size:,} bytes)")

    existing = [(p, l) for p, l in all_files if (root / p).exists()]
    console.print(f"\n  [bold]{len(existing)}/{len(all_files)}[/bold] files found")

    if dry_run:
        info("Dry run — no files uploaded.")
        return

    # Connect to Intelligence API
    from forktex.intelligence import Intelligence

    try:
        async with Intelligence() as ai:
            info(f"Connected to Intelligence API")

            # Create or find collection
            collections_resp = await ai.list_collections()
            coll_list = collections_resp.get(
                "collections", collections_resp.get("data", [])
            )
            existing_coll = None
            for c in coll_list:
                if c.get("name") == collection:
                    existing_coll = c
                    break

            if existing_coll:
                coll_id = existing_coll["id"]
                info(f"Using existing collection: {collection} ({coll_id})")
                # Delete existing documents to refresh
                docs_resp = await ai.list_documents(coll_id)
                doc_list = docs_resp.get("documents", docs_resp.get("data", []))
                for doc in doc_list:
                    await ai.delete_document(coll_id, doc["id"])
                info(f"Cleared {len(doc_list)} old documents")
            else:
                result = await ai.create_collection(collection)
                coll_id = result["id"]
                info(f"Created collection: {collection} ({coll_id})")

            # Upload each file
            uploaded = 0
            for rel_path, label in existing:
                full = root / rel_path
                content = full.read_bytes()
                filename = f"{label}--{Path(rel_path).name}"

                content_type = (
                    "application/json"
                    if rel_path.endswith(".json")
                    else "text/markdown"
                )

                try:
                    await ai.upload_document(
                        coll_id,
                        content,
                        filename,
                        content_type=content_type,
                    )
                    uploaded += 1
                    console.print(f"  [green]Uploaded[/green] {filename}")
                except Exception as e:
                    console.print(f"  [red]Failed[/red] {filename}: {e}")

            console.print(
                f"\n[bold green]Indexed {uploaded}/{len(existing)} files into '{collection}'[/bold green]"
            )
            console.print(f"\nAgents can now search this knowledge:")
            console.print(
                f"  [cyan]forktex ask 'What database does the network platform use?'[/cyan]"
            )
            console.print(f"  [cyan]forktex ask 'How are workflows structured?'[/cyan]")

    except Exception as e:
        error(f"Intelligence API error: {e}")
        error("Make sure the Intelligence API is running: forktex intelligence status")
