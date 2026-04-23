"""forktex present — Auto-generate presentations for archetypes and blueprints.

Reads engineering/manifest.json + archetype/blueprint markdown files,
extracts structured data, and renders poster-style HTML presentations.

Works for both:
- Archetypes (technology-generic: forktex-api, forktex-db, forktex-cache...)
- Blueprints (platform-specific: network-api, cloud-api, intelligence-api...)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import asyncclick as click
from jinja2 import Environment, FileSystemLoader

from forktex.agent.fsd.standard import FSD_VERSION

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ── Color schemes per archetype ──────────────────────────────────────────────

ARCHETYPE_COLORS = {
    "forktex-api": {
        "primary": "#10b981",
        "primary_light": "#34d399",
        "accent": "#06b6d4",
        "primary_rgb": "16, 185, 129",
        "accent_rgb": "6, 182, 212",
    },
    "forktex-client": {
        "primary": "#8b5cf6",
        "primary_light": "#a78bfa",
        "accent": "#ec4899",
        "primary_rgb": "139, 92, 246",
        "accent_rgb": "236, 72, 153",
    },
    "forktex-web": {
        "primary": "#3b82f6",
        "primary_light": "#60a5fa",
        "accent": "#8b5cf6",
        "primary_rgb": "59, 130, 246",
        "accent_rgb": "139, 92, 246",
    },
    "forktex-db": {
        "primary": "#0ea5e9",
        "primary_light": "#38bdf8",
        "accent": "#06b6d4",
        "primary_rgb": "14, 165, 233",
        "accent_rgb": "6, 182, 212",
    },
    "forktex-cache": {
        "primary": "#ef4444",
        "primary_light": "#f87171",
        "accent": "#f97316",
        "primary_rgb": "239, 68, 68",
        "accent_rgb": "249, 115, 22",
    },
    "forktex-storage": {
        "primary": "#059669",
        "primary_light": "#34d399",
        "accent": "#0ea5e9",
        "primary_rgb": "5, 150, 105",
        "accent_rgb": "14, 165, 233",
    },
    "forktex-vector": {
        "primary": "#d946ef",
        "primary_light": "#e879f9",
        "accent": "#f97316",
        "primary_rgb": "217, 70, 239",
        "accent_rgb": "249, 115, 22",
    },
    "forktex-queue": {
        "primary": "#f59e0b",
        "primary_light": "#fbbf24",
        "accent": "#10b981",
        "primary_rgb": "245, 158, 11",
        "accent_rgb": "16, 185, 129",
    },
    "forktex-mail": {
        "primary": "#6366f1",
        "primary_light": "#818cf8",
        "accent": "#06b6d4",
        "primary_rgb": "99, 102, 241",
        "accent_rgb": "6, 182, 212",
    },
    "forktex-phone": {
        "primary": "#14b8a6",
        "primary_light": "#2dd4bf",
        "accent": "#8b5cf6",
        "primary_rgb": "20, 184, 166",
        "accent_rgb": "139, 92, 246",
    },
}

DEFAULT_COLORS = {
    "primary": "#10b981",
    "primary_light": "#34d399",
    "accent": "#06b6d4",
    "primary_rgb": "16, 185, 129",
    "accent_rgb": "6, 182, 212",
}


# ── Markdown extraction ──────────────────────────────────────────────────────


def _extract_tables(md: str, header_pattern: str) -> list[dict]:
    """Extract rows from the first markdown table under a heading matching pattern."""
    lines = md.split("\n")
    in_section = False
    headers = []
    rows = []
    for line in lines:
        if re.match(r"^#{1,3}\s+", line) and header_pattern.lower() in line.lower():
            in_section = True
            continue
        if in_section and line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not headers:
                headers = cells
            else:
                rows.append(dict(zip(headers, cells)))
        elif (
            in_section
            and not line.startswith("|")
            and line.strip()
            and not line.startswith("<!--")
        ):
            if headers:
                break
    return rows


def _extract_section_items(md: str, header_pattern: str) -> list[str]:
    """Extract bullet items from a markdown section."""
    lines = md.split("\n")
    in_section = False
    items = []
    for line in lines:
        if re.match(r"^#{1,3}\s+", line) and header_pattern.lower() in line.lower():
            in_section = True
            continue
        if in_section and line.strip().startswith(("- ", "* ")):
            items.append(re.sub(r"^[-*]\s+", "", line.strip()))
        elif in_section and re.match(r"^#{1,3}\s+", line):
            break
    return items


def _extract_front_matter(md: str) -> dict:
    """Extract YAML-like front matter from --- delimited block."""
    if not md.startswith("---"):
        # Try HTML comment header then ---
        match = re.search(r"---\n(.*?)\n---", md, re.DOTALL)
        if match:
            fm = {}
            for line in match.group(1).split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    val = val.strip().strip('"').strip("'")
                    if val.startswith("["):
                        val = [
                            v.strip().strip('"').strip("'")
                            for v in val.strip("[]").split(",")
                        ]
                    fm[key.strip()] = val
            return fm
    return {}


# ── Data builders ────────────────────────────────────────────────────────────


def _build_archetype_context(
    manifest_item: dict, md_content: str, colors: dict
) -> dict:
    """Build Jinja2 context for an archetype presentation."""
    slug = manifest_item.get("slug", "")
    stack = manifest_item.get("stack", [])
    title = manifest_item.get("title", slug)

    # Extract tech stack table
    tech_rows = _extract_tables(md_content, "stack") or _extract_tables(
        md_content, "technology"
    )
    tech_stack = []
    for row in tech_rows[:10]:
        name = (
            row.get("Component")
            or row.get("Technology")
            or row.get("component")
            or row.get("technology")
            or ""
        )
        version = row.get("Version") or row.get("version") or ""
        tech = row.get("Technology") or row.get("technology") or ""
        if name and name.strip("**"):
            tech_stack.append({"name": name.strip("*"), "version": version or tech})

    # Extract features/capabilities
    features = (
        _extract_section_items(md_content, "capabilit")
        or _extract_section_items(md_content, "feature")
        or _extract_section_items(md_content, "pattern")
        or _extract_section_items(md_content, "rule")
    )

    # Extract dependencies
    dep_rows = _extract_tables(md_content, "dependenc") or _extract_tables(
        md_content, "key package"
    )
    dependencies = []
    for row in dep_rows[:9]:
        name = (
            row.get("Drive")
            or row.get("Package")
            or row.get("name")
            or list(row.values())[0]
            if row
            else ""
        )
        desc = (
            row.get("Purpose")
            or row.get("description")
            or row.get("desc")
            or (list(row.values())[1] if len(row) > 1 else "")
        )
        if name and name.strip("*`"):
            dependencies.append({"name": name.strip("*`"), "desc": desc.strip("*`")})

    # Extract FSD atoms
    atom_rows = _extract_tables(md_content, "fsd atom") or _extract_tables(
        md_content, "atom"
    )
    fsd_atoms = []
    for row in atom_rows[:12]:
        name = row.get("Atom") or row.get("atom") or ""
        target = row.get("Target") or row.get("Make Target") or row.get("target") or ""
        iso = row.get("ISO") or row.get("ISO Control") or row.get("iso") or ""
        status = row.get("Status") or row.get("status") or ""
        if name and name.strip("`"):
            fsd_atoms.append(
                {
                    "name": name.strip("`"),
                    "target": target.strip("`"),
                    "iso": iso,
                    "status": "pass"
                    if "required" in status.lower() or "optional" in status.lower()
                    else status.lower(),
                }
            )

    # Subtitle from first paragraph after title
    subtitle_match = re.search(r"^>\s*(.+)$", md_content, re.MULTILINE)
    subtitle = (
        subtitle_match.group(1).strip()
        if subtitle_match
        else f"{'Technology blueprint' if True else 'Platform implementation guide'} for the FORKTEX ecosystem"
    )

    return {
        "kind": "archetype",
        "title": title,
        "display_name": slug.replace("forktex-", "").replace("-", " ").title()
        + " Stack",
        "subtitle": subtitle,
        "colors": colors,
        "header_badges": [{"value": s, "label": ""} for s in stack[:4]],
        "tech_stack": tech_stack[:8],
        "architecture_layers": [],
        "features": features[:8],
        "dependencies": dependencies[:9],
        "fsd_atoms": fsd_atoms,
        "stats": [],
        "platform": None,
        "year": datetime.now().year,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "fsd_version": FSD_VERSION,
    }


def _build_blueprint_context(
    manifest_item: dict, md_content: str, colors: dict
) -> dict:
    """Build Jinja2 context for a blueprint presentation."""
    slug = manifest_item.get("slug", "")
    title = manifest_item.get("title", slug)
    archetype = manifest_item.get("archetype", "")

    ctx = _build_archetype_context(manifest_item, md_content, colors)
    ctx["kind"] = "blueprint"
    ctx["display_name"] = (
        slug.replace("-api", "").replace("-client", "").replace("-", " ").title()
    )
    ctx["subtitle"] = (
        f"Development blueprint for {ctx['display_name']} — instantiation of {archetype}"
    )

    # Extract platform info from front matter or markdown
    fm = _extract_front_matter(md_content)
    ctx["platform"] = {
        "name": title,
        "path": f"/{slug.split('-')[0]}",
        "fsd_level": fm.get("fsd_level", "—"),
        "archetype": archetype,
    }

    # Extract engines from Engine/Module inventory section
    engines = _extract_tables(md_content, "engine") or _extract_tables(
        md_content, "module"
    )
    if engines:
        ctx["features"] = []
        for eng in engines[:10]:
            name = (
                eng.get("Engine")
                or eng.get("Module")
                or eng.get("engine")
                or list(eng.values())[0]
                if eng
                else ""
            )
            purpose = (
                eng.get("Purpose")
                or eng.get("purpose")
                or (list(eng.values())[1] if len(eng) > 1 else "")
            )
            if name and name.strip("*`"):
                ctx["features"].append(f"{name.strip('*`')} — {purpose.strip('*`')}")

    # Extract API routes
    routes = _extract_tables(md_content, "api route") or _extract_tables(
        md_content, "endpoint"
    )
    if routes and not ctx.get("architecture_layers"):
        ctx["architecture_layers"] = [
            {
                "boxes": [
                    {
                        "name": r.get("Prefix")
                        or r.get("Route")
                        or list(r.values())[0],
                        "highlight": i == 0,
                    }
                ]
                for i, r in enumerate(routes[:4])
                if r
            }
        ]

    return ctx


# ── Rendering ────────────────────────────────────────────────────────────────


def _render(context: dict) -> str:
    """Render the archetype/blueprint template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("archetype.html")
    return template.render(**context)


# ── CLI ──────────────────────────────────────────────────────────────────────


@click.group()
def present():
    """Generate presentations for archetypes and blueprints."""
    pass


@present.command()
@click.option("--output-dir", default=None, type=click.Path(), help="Output directory")
@click.option(
    "--docs-dir",
    default=None,
    type=click.Path(),
    help="Docs root (default: cwd/docs or cwd)",
)
@click.pass_context
async def archetypes(ctx, output_dir, docs_dir):
    """Generate HTML presentations for all archetypes."""
    docs = Path(docs_dir) if docs_dir else _find_docs()
    out = Path(output_dir) if output_dir else docs / "presentations"
    out.mkdir(parents=True, exist_ok=True)

    manifest_path = docs / "engineering" / "manifest.json"
    if not manifest_path.exists():
        raise click.ClickException(f"manifest.json not found at {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    items = [i for i in manifest.get("items", []) if i.get("kind") == "archetype"]

    click.echo(f"Generating archetype presentations: {len(items)} archetypes")
    click.echo("=" * 50)

    for item in items:
        slug = item["slug"]
        md_path = docs / "engineering" / "archetypes" / f"{slug}.md"
        if not md_path.exists():
            click.echo(f"  SKIP  {slug} (no markdown)")
            continue

        md_content = md_path.read_text()
        colors = ARCHETYPE_COLORS.get(slug, DEFAULT_COLORS)
        context = _build_archetype_context(item, md_content, colors)
        html = _render(context)

        html_path = out / f"{slug}-archetype.html"
        html_path.write_text(html)
        click.echo(f"  OK    {slug} → {html_path.name}")

    click.echo(f"\nOutput: {out}/")


@present.command()
@click.option("--output-dir", default=None, type=click.Path(), help="Output directory")
@click.option(
    "--docs-dir",
    default=None,
    type=click.Path(),
    help="Docs root (default: cwd/docs or cwd)",
)
@click.pass_context
async def blueprints(ctx, output_dir, docs_dir):
    """Generate HTML presentations for all blueprints."""
    docs = Path(docs_dir) if docs_dir else _find_docs()
    out = Path(output_dir) if output_dir else docs / "presentations"
    out.mkdir(parents=True, exist_ok=True)

    manifest_path = docs / "engineering" / "manifest.json"
    if not manifest_path.exists():
        raise click.ClickException(f"manifest.json not found at {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    items = [i for i in manifest.get("items", []) if i.get("kind") == "blueprint"]

    click.echo(f"Generating blueprint presentations: {len(items)} blueprints")
    click.echo("=" * 50)

    for item in items:
        slug = item["slug"]
        md_path = docs / "engineering" / "blueprints" / f"{slug}.md"
        if not md_path.exists():
            click.echo(f"  SKIP  {slug} (no markdown)")
            continue

        md_content = md_path.read_text()
        archetype = item.get("archetype", "")
        colors = ARCHETYPE_COLORS.get(archetype, DEFAULT_COLORS)
        context = _build_blueprint_context(item, md_content, colors)
        html = _render(context)

        html_path = out / f"{slug}-overview.html"
        html_path.write_text(html)
        click.echo(f"  OK    {slug} → {html_path.name}")

    click.echo(f"\nOutput: {out}/")


def _find_docs() -> Path:
    """Find the docs directory."""
    cwd = Path.cwd()
    if (cwd / "docs" / "engineering").exists():
        return cwd / "docs"
    if (cwd / "engineering").exists():
        return cwd
    return cwd / "docs"
