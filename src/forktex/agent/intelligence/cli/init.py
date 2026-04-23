"""forktex intelligence init — Configure Intelligence API connection."""

from __future__ import annotations

import sys
from pathlib import Path

import asyncclick as click
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from forktex.agent.ui.console import console, info, error, success, spinner


@click.group()
async def intelligence():
    """ForkTex Intelligence — AI-powered development via the Intelligence API."""
    pass


@intelligence.command(name="init")
@click.option("--project", "-d", default=None, help="Project directory")
@click.option("--global", "save_global", is_flag=True, help="Save to global config")
async def init_cmd(project, save_global):
    """Set up Intelligence API connection.

    Register or provide an existing API key to get started.
    """
    from forktex_intelligence.config import IntelligenceSettings
    from forktex_intelligence.client.client import ForktexIntelligenceClient

    project_root = project or str(Path.cwd().absolute())

    console.print(
        Panel.fit(
            "[bold]Intelligence API Setup[/bold]\n\n"
            "Connect to the ForkTex Intelligence API.\n"
            "This is required for: forktex chat, forktex ask, forktex run",
            border_style="blue",
        )
    )
    console.print()

    # 1. Endpoint
    endpoint = Prompt.ask(
        "[bold]API endpoint[/bold]",
        default="https://intelligence.forktex.com/api",
    ).strip()

    # 2. Auth method
    has_key = Confirm.ask("Do you already have an API key?", default=False)

    if has_key:
        # Existing API key flow
        api_key = Prompt.ask("[bold]API key[/bold]", password=True).strip()
        if not api_key:
            error("API key cannot be empty.")
            sys.exit(1)
    else:
        # Register/login flow
        is_new = Confirm.ask("Create a new account?", default=True)
        email = Prompt.ask("[bold]Email[/bold]").strip()
        password = Prompt.ask("[bold]Password[/bold]", password=True).strip()

        if not email or not password:
            error("Email and password are required.")
            sys.exit(1)

        client = ForktexIntelligenceClient(endpoint)
        try:
            if is_new:
                with spinner("Creating account..."):
                    result = await client.register(email, password)
                # register() returns JWT, not API key — create one
                orgs = await client.list_orgs()
                if not orgs:
                    error("Account created but no organizations found.")
                    await client.close()
                    sys.exit(1)
                org_id = orgs[0]["id"]
                client.set_org(org_id)
                key_result = await client.create_api_key("forktex-cli")
                api_key = key_result.get("raw_key", "")
                org_slug = orgs[0].get("slug", org_id)
                success(f"Account created! Org: {org_slug}")
            else:
                with spinner("Logging in..."):
                    result = await client.login(email, password)
                # After login, need to get/create an API key
                # First, get orgs
                orgs = await client.list_orgs()
                if not orgs:
                    error("No orgs found. Create one first.")
                    await client.close()
                    sys.exit(1)
                org_id = orgs[0]["id"]
                client.set_org(org_id)
                # Create API key for the org
                key_result = await client.create_api_key("forktex-cli")
                api_key = key_result.get("raw_key", "")
                success(f"Logged in! Org: {orgs[0].get('slug', org_id)}")

            await client.close()
        except Exception as e:
            await client.close()
            error(f"Auth failed: {e}")
            sys.exit(1)

        if not api_key:
            error("Failed to obtain API key.")
            sys.exit(1)

    # 3. Build settings (no org_id — auto-resolved from API key)
    settings = IntelligenceSettings(endpoint=endpoint, api_key=api_key)

    # 4. Validate
    try:
        client = ForktexIntelligenceClient(endpoint, api_key)
        with spinner("Validating..."):
            health = await client.health()
            whoami = await client.whoami()
        await client.close()
        success(
            f"Connected! API v{health.version}, org: {whoami.get('org_id', 'unknown')[:8]}..."
        )
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Validation failed: {e}")
        info("Config saved anyway.")

    # 5. Save
    from forktex.agent.intelligence.settings import (
        save_intelligence_global,
        save_intelligence_project,
    )
    from forktex.core.paths import get_global_config_dir

    if save_global:
        save_intelligence_global(settings)
        info(f"Saved to {get_global_config_dir()}/intelligence.json")
    else:
        save_intelligence_project(settings, project_root)
        info(f"Saved to {project_root}/.forktex/intelligence.json")

    console.print()
    info('Ready! Try: [bold]forktex ask "Hello!"[/bold]')


@intelligence.command(name="status")
@click.option("--project", "-d", default=None, help="Project directory")
async def status_cmd(project):
    """Show Intelligence API connection status."""
    from forktex.agent.intelligence.settings import get_intelligence_settings
    from forktex_intelligence.client.client import ForktexIntelligenceClient

    project_root = project or str(Path.cwd().absolute())
    settings = get_intelligence_settings(project_root=project_root)

    console.print(f"[bold]Endpoint:[/bold] {settings.endpoint}")
    console.print(
        f"[bold]API Key:[/bold] {'***' + settings.api_key[-4:] if settings.api_key else 'not set'}"
    )

    if settings.is_configured:
        try:
            client = ForktexIntelligenceClient(settings.endpoint, settings.api_key)
            with spinner("Checking..."):
                health = await client.health()
                whoami = await client.whoami()
            await client.close()
            console.print(
                f"[bold green]Status:[/bold green] Connected (v{health.version})"
            )
            console.print(f"[bold]Org:[/bold]    {whoami.get('org_id', 'unknown')}")
        except Exception as e:
            console.print(f"[bold red]Status:[/bold red] Failed ({e})")
    else:
        info("Not configured. Run: forktex intelligence init")
