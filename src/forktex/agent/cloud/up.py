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

"""forktex cloud up — start your project locally or deploy to your cloud."""

from __future__ import annotations

import subprocess
import sys

import asyncclick as click

from forktex_cloud import paths as cloud_paths
from forktex.agent.cloud.errors import translate_cloud_errors


@click.command()
@click.option(
    "--env",
    "environment",
    default=None,
    help="Environment overlay (e.g. local, staging, production)",
)
@click.option("--name", default=None, help="Override project name")
@click.option("--flavour", default=None, help="Override infrastructure flavour")
@click.option("--region", default=None, help="Override infrastructure region")
@click.option("--skip-dns", is_flag=True, help="Skip DNS setup")
@click.option("--skip-ssl", is_flag=True, help="Skip SSL provisioning")
@click.option(
    "-d", "--detach", is_flag=True, help="Run containers in background (local)"
)
@click.option("--build", is_flag=True, help="Rebuild images before starting (local)")
@click.option(
    "--down", "tear_down", is_flag=True, help="Stop and remove containers (local)"
)
@click.option("--logs", "tail_logs", is_flag=True, help="Tail logs (local)")
@click.option("--service", default=None, help="Filter logs by service (local)")
@click.option(
    "--since", default="10m", help="Log lookback window (local, default: 10m)"
)
@click.option("--raw", is_flag=True, help="Use docker compose logs directly (local)")
@click.option(
    "--no-observability", is_flag=True, help="Disable the local logs/metrics stack"
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.option(
    "--archive",
    "archive_delivery",
    is_flag=True,
    help="Upload images via docker save instead of registry pull (for locally-built images)",
)
@click.pass_context
@translate_cloud_errors
async def up(
    ctx,
    environment,
    name,
    flavour,
    region,
    skip_dns,
    skip_ssl,
    detach,
    build,
    tear_down,
    tail_logs,
    service,
    since,
    raw,
    no_observability,
    verbose,
    archive_delivery,
):
    """Deploy (remote) or start local mode (--env local)."""
    if environment == "local":
        _run_local(
            ctx,
            detach=detach,
            build=build,
            tear_down=tear_down,
            tail_logs=tail_logs,
            service=service,
            since=since,
            raw=raw,
            no_observability=no_observability,
        )
    else:
        _run_remote(
            ctx,
            environment=environment,
            name=name,
            flavour=flavour,
            region=region,
            skip_dns=skip_dns,
            skip_ssl=skip_ssl,
            verbose=verbose,
            archive_delivery=archive_delivery,
        )


def _run_remote(
    ctx,
    *,
    environment,
    name,
    flavour,
    region,
    skip_dns,
    skip_ssl,
    verbose,
    archive_delivery=False,
):
    """Deploy via the cloud controller API (POST /api/v1/up)."""
    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.require_connection()
    project_root = ctx.obj["project_root"]

    from forktex_cloud.client import ForktexCloudClient

    with ForktexCloudClient.from_context(cloud_ctx) as client:
        click.echo(f"  Dispatching deploy via {cloud_ctx.controller}...")
        # archive_delivery is implicitly always-on whenever project_dir is
        # provided — the SDK auto-tarballs local Dockerfile build contexts
        # in client.up(). The CLI flag is kept for forward-compat but is a
        # no-op against the current SDK signature.
        _ = archive_delivery
        result = client.up(
            name=name,
            flavour=flavour,
            region=region,
            env=environment,
            skip_dns=skip_dns,
            skip_ssl=skip_ssl,
            project_dir=project_root,
        )
        deployment_id = result.deployment_id
        run_id = result.job_id
        click.echo(f"  Deployment: {deployment_id}")
        click.echo(f"  Flow run:   {run_id}")
        click.echo()

        _stream_run(client, run_id=run_id, verbose=verbose)


def _stream_run(client, *, run_id: str, verbose: bool = False) -> None:
    """Poll the flow run via `client.flow_get` and print step transitions
    until the run terminates. Replaces the prior SSE-based version that
    relied on `client.stream_flow_run_events` (no longer exists) and a
    StepRunRead/RunRead event shape (no longer matches the API)."""
    import time as _time

    _COLOR = {
        "running": ("cyan", "▶"),
        "completed": ("green", "✓"),
        "failed": ("red", "✗"),
        "cancelled": ("yellow", "⊘"),
        "pending": ("white", "·"),
    }

    def _fmt(name: str, status: str) -> str:
        color, icon = _COLOR.get(status, ("white", "?"))
        return f"  {click.style(icon + ' ' + name, fg=color)}"

    seen: dict[str, str] = {}
    deadline = _time.monotonic() + 30 * 60  # 30 min safety cap
    while _time.monotonic() < deadline:
        try:
            run = client.flow_get(run_id)
        except Exception as exc:
            click.echo(f"  (poll error: {exc}) — retrying...")
            _time.sleep(5)
            continue
        for node in run.get("nodes") or []:
            name = node.get("name") or ""
            status = node.get("status") or ""
            if seen.get(name) != status:
                click.echo(_fmt(name, status))
                seen[name] = status
        run_status = run.get("status")
        if run_status in ("completed", "failed", "cancelled"):
            color = (
                "green"
                if run_status == "completed"
                else "red"
                if run_status == "failed"
                else "yellow"
            )
            click.echo()
            click.echo(f"  {click.style('Deploy ' + run_status, fg=color, bold=True)}")
            if run_status == "failed" and verbose:
                for node in run.get("nodes") or []:
                    if node.get("status") == "failed" and node.get("error"):
                        click.echo(
                            f"  {click.style('Error:', fg='red')} "
                            f"{node['name']}: {str(node['error'])[:400]}"
                        )
            return
        _time.sleep(2)
    click.echo(f"  poll deadline reached without terminal state for run {run_id}")


def _run_local(
    ctx,
    *,
    detach,
    build,
    tear_down,
    tail_logs,
    service,
    since,
    raw,
    no_observability,
):
    """Run the stack locally via docker compose."""
    project_root = ctx.obj["project_root"]
    compose_file = str(cloud_paths.compose_path(project_root, "local"))
    env_name = "local"

    if tear_down:
        # Resolve project name for compose isolation
        project_name = "forktex"
        try:
            from forktex.agent.cloud._manifest_cache import load_manifest

            manifest = load_manifest(project_root, env=env_name)
            project_name = manifest.name or "forktex"
        except (FileNotFoundError, ValueError, KeyError):  # fmt: skip
            click.echo(
                f"Warning: could not load manifest, using project name '{project_name}'",
                err=True,
            )
        _exec(
            [
                "docker",
                "compose",
                "-p",
                project_name,
                "-f",
                compose_file,
                "down",
                "-v",
                "--remove-orphans",
            ]
        )
        return

    if tail_logs:
        if raw or no_observability:
            # Resolve project name for compose isolation
            pname = "forktex"
            try:
                from forktex.agent.cloud._manifest_cache import load_manifest

                m = load_manifest(project_root, env=env_name)
                pname = m.name or "forktex"
            except (FileNotFoundError, ValueError, KeyError):  # fmt: skip
                click.echo(
                    f"Warning: could not load manifest, using project name '{pname}'",
                    err=True,
                )
            _exec(["docker", "compose", "-p", pname, "-f", compose_file, "logs", "-f"])
            return
        _tail_loki(project_root, service=service, since=since, env_name=env_name)
        return

    from forktex_cloud.bridge.local_compose import write_local_compose
    from forktex_cloud.manifest.loader import ManifestError

    from forktex.agent.cloud._manifest_cache import load_manifest

    try:
        manifest = load_manifest(project_root, env=env_name)
    except ManifestError as e:
        raise click.ClickException(str(e))

    secrets_provider = None
    try:
        from forktex_cloud.secrets.factory import get_secrets_provider

        secrets_provider = get_secrets_provider(project_root=project_root)
    except (ValueError, ImportError):  # fmt: skip
        pass

    obs_enabled = not no_observability
    manifest_obs_enabled = manifest.observability.get("enabled")
    if manifest_obs_enabled is False:
        obs_enabled = False

    from forktex.agent.ui.console import console
    from forktex.runtime.decorators import sdk_boundary

    # Wrap the SDK write so any unspec'd file it produces inside .forktex/
    # surfaces as a structure violation rather than a silent compose error.
    _wrapped_write = sdk_boundary(
        scope="project",
        project_root_arg="project_root",
        strict=False,
    )(write_local_compose)

    with console.status(
        f"[cyan]rendering compose for[/cyan] [bold]{env_name}[/bold]…",
        spinner="dots",
    ):
        compose_path = _wrapped_write(
            manifest,
            project_root,
            secrets_provider=secrets_provider,
            observability=obs_enabled,
        )
    compose_file = str(compose_path)

    project_name = manifest.name or "forktex"
    base_cmd = ["docker", "compose", "-p", project_name, "-f", compose_file]
    up_cmd = base_cmd + ["up"]
    if build:
        up_cmd.append("--build")
    if detach:
        up_cmd.append("-d")

    click.echo(f"compose file: {compose_path}")
    _print_port_table(manifest, observability=obs_enabled, env_name=env_name)
    if obs_enabled:
        click.echo("  Observability:")
        click.echo("    Loki:     http://localhost:3100 (log aggregation)")
        click.echo("    Logs:     forktex cloud up --env local --logs")
        click.echo()
    _exec(up_cmd)


def _print_port_table(manifest, *, observability: bool = True, env_name: str = "local"):
    from forktex.agent.cloud._local_constants import (
        OBSERVABILITY_PORTS,
        allocate_host_ports,
    )

    local_services = manifest.services_for_env(env=env_name)
    reserved = OBSERVABILITY_PORTS if observability else set()
    ports = allocate_host_ports(local_services, reserved=reserved)
    click.echo()
    click.echo(f"  {'Service':<16} {'Type':<14} {'Port':<8} {'Host'}")
    click.echo(f"  {'─' * 52}")
    for svc in local_services:
        sid = svc["id"]
        svc_type = svc.get("type", "compute")
        container_port = svc.get("port", 80)
        host_col = f"localhost:{ports[sid]}" if sid in ports else "(internal)"
        click.echo(f"  {sid:<16} {svc_type:<14} {container_port:<8} {host_col}")
    click.echo()


def _parse_since(since: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600}
    if since and since[-1] in units:
        try:
            return int(since[:-1]) * units[since[-1]]
        except ValueError:
            pass
    return 600


def _tail_loki(project_root, *, service, since, env_name="local"):
    import time
    from forktex_cloud.bridge.loki import loki_ready, build_logql, tail
    from forktex_cloud.bridge.log_formatter import assign_colors, format_line, COLORS

    # Cloud's stack publishes Loki on a non-default host port (3110)
    # so it can coexist with other forktex stacks that also default to
    # 3100. Read the canonical constant from the SDK so the two stay
    # in lock-step. Older SDK builds without this symbol fall back
    # to 3100.
    try:
        from forktex_cloud.bridge.local_compose import loki_host_port

        host_port = loki_host_port()
    except ImportError:
        host_port = 3100

    compose_file = str(cloud_paths.compose_path(project_root, "local"))
    base_url = f"http://localhost:{host_port}"
    if not loki_ready(base_url):
        click.echo(
            f"  Loki not reachable on {base_url} — falling back to docker compose logs"
        )
        _exec(["docker", "compose", "-f", compose_file, "logs", "-f"])
        return

    services: list[str] | None = None
    if service:
        services = [s.strip() for s in service.split(",") if s.strip()]

    logql = build_logql(services)
    since_secs = _parse_since(since)
    start_ns = int((time.time() - since_secs) * 1_000_000_000)

    if services:
        all_ids = services
    else:
        try:
            from forktex.agent.cloud._manifest_cache import load_manifest

            manifest = load_manifest(project_root, env=env_name)
            all_ids = [s["id"] for s in manifest.services_for_env(env=env_name)]
        except Exception:
            all_ids = []

    color_map = assign_colors(all_ids) if all_ids else {}
    max_name_len = max((len(s) for s in all_ids), default=8)

    try:
        for ts_ns, svc_name, line in tail(base_url, logql, start_ns):
            if svc_name not in color_map:
                color_map[svc_name] = COLORS[len(color_map) % len(COLORS)]
                if len(svc_name) > max_name_len:
                    max_name_len = len(svc_name)
            click.echo(
                format_line(ts_ns, svc_name, line, color_map[svc_name], max_name_len)
            )
    except KeyboardInterrupt:
        click.echo()


def _exec(cmd: list[str]) -> None:
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)
