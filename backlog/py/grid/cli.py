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

"""``forktex grid`` — the dynamic virtual database studio + persistence runtime.

Commands:

- ``up`` / ``down`` / ``status`` — manage the Dockerized Postgres declared in
  ``forktex.json`` (reuses the cloud compose pipeline).
- ``serve`` — run the self-describing grid HTTP API + studio.

Heavy deps (forktex_core[grid], FastAPI, uvicorn, the cloud SDK, Docker) are
imported lazily inside each command so this group always loads — only the
command you run needs its extra.
"""

from __future__ import annotations

import asyncclick as click


@click.group("grid")
async def grid() -> None:
    """ForkTex Grid — fully-dynamic virtual database (persistence + studio)."""


@grid.command("up")
@click.option(
    "--attach", is_flag=True, help="Run in the foreground (default: detached)."
)
async def up_cmd(attach: bool) -> None:
    """Start the Dockerized Postgres backing the grid (from forktex.json)."""
    from forktex.grid import runtime

    try:
        database_url = runtime.compose_up(detach=not attach)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("grid runtime up.")
    if database_url:
        click.echo(f"DATABASE_URL={database_url}")
        click.echo("Run: forktex grid serve")


@grid.command("down")
@click.option(
    "--volumes", "-v", is_flag=True, help="Also remove the data volume (destructive)."
)
async def down_cmd(volumes: bool) -> None:
    """Stop the grid runtime containers."""
    from forktex.grid import runtime

    try:
        runtime.compose_down(volumes=volumes)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("grid runtime down.")


@grid.command("status")
async def status_cmd() -> None:
    """Show the grid runtime container status."""
    from forktex.grid import runtime

    try:
        runtime.compose_status()
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


@grid.command("serve")
@click.option("--host", default="127.0.0.1", help="Bind host.")
@click.option("--port", "-p", default=4445, help="Bind port.")
@click.option(
    "--database-url", default=None, help="Override DATABASE_URL (else derive/embedded)."
)
async def serve_cmd(host: str, port: int, database_url: str | None) -> None:
    """Serve the grid HTTP API + studio (OpenAPI at /docs)."""
    try:
        import uvicorn  # type: ignore[import-not-found]
    except ImportError as exc:
        raise click.ClickException(
            "grid serve needs the [api] extra: pip install 'forktex[api]'"
        ) from exc

    from forktex.grid import runtime
    from forktex.grid.app import build_app

    url = database_url or runtime.derive_database_url()
    app = build_app(database_url=url)
    click.echo(
        f"grid studio → http://{host}:{port}/docs  (db: {'manifest/env' if url else 'embedded pgserver'})"
    )
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))
    await server.serve()


@grid.command("projects")
async def projects_cmd() -> None:
    """List projects registered in the system namespace."""
    from forktex.grid.persistence import GridStore, list_projects

    store = await GridStore.open()
    try:
        rows = await list_projects(store)
    finally:
        await store.close()
    if not rows:
        click.echo("(no projects registered)")
        return
    for row in rows:
        click.echo(
            f"{row.get('fingerprint', '?'):16}  {row.get('name', ''):24}  {row.get('root', '')}"
        )


@grid.command("reconcile")
async def reconcile_cmd() -> None:
    """Reconcile registered projects (DB) against the live filesystem."""
    from forktex.grid.persistence import GridStore
    from forktex.grid.reconcile import reconcile_projects

    store = await GridStore.open()
    try:
        report = await reconcile_projects(store)
    finally:
        await store.close()
    click.echo(
        f"checked={report['checked']} healthy={report['healthy']} drifted={len(report['drifted'])}"
    )
    for drift in report["drifted"]:
        click.echo(
            f"  DRIFT [{drift['issue']}] {drift['fingerprint']}  {drift['root']}"
        )


__all__ = ["grid"]
