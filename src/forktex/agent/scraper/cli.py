"""forktex scrape — Agentic scraper with persistent browser.

Launches a stateful Playwright browser, creates a SCRAPER agent,
and streams the Intelligence API agent loop as it navigates and
extracts data from the target URL.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

import asyncclick as click

from forktex.agent.ui.console import console, info, error


def _get_project_root() -> str:
    return str(Path.cwd().absolute())


@click.command()
@click.argument("url")
@click.option("--goal", "-g", required=True, help="Scraping goal description")
@click.option("--output", "-o", default=None, help="Output filename for extracted data")
@click.option("--project", "-d", default=None, help="Project directory")
@click.option("--max-rounds", default=40, help="Maximum agent loop rounds")
@click.option("--client-cert", default=None, help="Path to client certificate PEM file")
@click.option("--client-key", default=None, help="Path to client private key PEM file")
@click.option(
    "--client-pfx", default=None, help="Path to PKCS#12 (.p12/.pfx) certificate bundle"
)
@click.option(
    "--client-passphrase",
    default=None,
    help="Passphrase for the PFX/P12 file (or set FORKTEX_PFX_PASSPHRASE)",
)
@click.option("--client-ca", default=None, help="Path to CA certificate PEM file")
@click.option(
    "--head",
    "headed",
    is_flag=True,
    default=False,
    help="Run browser in headed mode (visible window)",
)
async def scrape(
    url,
    goal,
    output,
    project,
    max_rounds,
    client_cert,
    client_key,
    client_pfx,
    client_passphrase,
    client_ca,
    headed,
):
    """Scrape a website using an AI-driven browser agent.

    Launches a persistent browser, navigates to URL, and uses the
    Intelligence API to drive extraction based on the goal.

    For sites requiring client certificate authentication, use either
    PEM files (--client-cert + --client-key) or a PKCS#12 bundle (--client-pfx).

    Examples:
        forktex scrape "https://example.com" -g "Extract product listings"

        forktex scrape "https://e-licitatie.ro:8881/su/home" -g "Extract IT offers" \\
            --client-pfx licitatii.p12 --client-passphrase "secret"
    """
    from forktex.agent.intelligence.settings import get_intelligence_settings
    from forktex_intelligence.client.client import ForktexIntelligenceClient
    from forktex_intelligence.streams import SSEEventType
    from forktex.agent.manager import AgentManager
    from forktex.agent.tools.scraper import StatefulBrowser
    from forktex.agent.scraper.truths import TruthsStore

    project_root = project or _get_project_root()
    settings = get_intelligence_settings(project_root=project_root)

    if not settings.is_configured:
        error("Intelligence API not configured.")
        info("Run [bold]forktex intelligence login[/bold] to set up.")
        sys.exit(1)

    client = ForktexIntelligenceClient.from_settings(settings)
    if not client._org_id:
        await client.whoami()

    # Set up browser and truths
    screenshots_dir = str(Path(project_root) / ".forktex" / "scraper" / "screenshots")
    browser = StatefulBrowser()
    truths_store = TruthsStore(project_root)

    try:
        # Derive cert origin from URL (scheme + host + port)
        cert_origin = None
        has_client_cert = client_pfx or (client_cert and client_key)
        if has_client_cert:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            cert_origin = f"{parsed.scheme}://{parsed.netloc}"

        # Allow passphrase from env var
        if client_pfx and not client_passphrase:
            import os

            client_passphrase = os.environ.get("FORKTEX_PFX_PASSPHRASE")

        info("Starting browser...")
        await browser.start(
            screenshots_dir,
            headless=not headed,
            client_cert=client_cert,
            client_key=client_key,
            client_pfx=client_pfx,
            client_passphrase=client_passphrase,
            client_ca=client_ca,
            cert_origin=cert_origin,
        )
        if has_client_cert:
            info(f"Browser ready (client cert for {cert_origin})")
        else:
            info("Browser ready (cert bypass enabled)")

        from forktex.agent.ui.display import handle_tool_event

        manager = AgentManager(
            project_root,
            client,
            on_tool_event=handle_tool_event,
            browser=browser,
            truths_store=truths_store,
        )

        session = manager.create_session()

        # Build the task prompt with context
        task = (
            f"Navigate to {url} and accomplish this goal: {goal}\n\n"
            f"Start by checking truths for any known selectors for this domain. "
            f"Then navigate to the URL, inspect the page, and extract the requested data. "
            f"Save all verified selectors to truths and output structured JSON with the results."
        )
        if output:
            task += f"\n\nSave the output to filename: {output}"

        try:
            process = manager.create_agent(
                session,
                "scraper",
                task=task,
            )
        except ValueError as e:
            error(str(e))
            await client.close()
            sys.exit(1)

        console.print(f"\n[bold]Goal:[/bold] {goal}")
        console.print(f"[bold]URL:[/bold] {url}")
        console.print(
            f"[dim]Session: {session.id} | Agent: {process.id} (scraper)[/dim]"
        )
        console.print()

        # Stream the response
        console.print("[bold green]Scraper Agent:[/bold green]")
        full_text = ""

        async for event in process.chat_stream(task):
            if event.event == SSEEventType.DELTA:
                console.print(event.delta_text, end="")
                full_text += event.delta_text
            elif event.event == SSEEventType.USAGE:
                pass
            elif event.event == SSEEventType.ERROR:
                error(event.error_message)
                break
            elif event.event == SSEEventType.DONE:
                pass

        if full_text:
            console.print()

        # Finalize
        from forktex.agent.process import AgentStatus

        if process.status != AgentStatus.FAILED:
            process.status = AgentStatus.COMPLETED
            process.completed_at = time.time()

        manager.persist_state(process)

        console.print()
        info(f"Scraping completed. Agent: {process.id[:8]}...")

    except Exception as e:
        error(f"Scraper failed: {e}")
    finally:
        info("Closing browser...")
        await browser.close()
        await client.close()
