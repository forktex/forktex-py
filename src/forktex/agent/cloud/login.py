"""forktex cloud login — authenticate with email/password or API key."""

from __future__ import annotations

import asyncclick as click

from forktex.agent.cloud.settings import save_cloud_context_global


@click.command()
@click.option(
    "--url",
    prompt="Controller URL",
    default="https://cloud.forktex.com",
    help="Cloud controller URL",
)
@click.option("--api-key", default=None, help="API key for CI/CD mode (ftx-...)")
@click.pass_context
async def login(ctx, url, api_key):
    """Configure the cloud controller connection.

    Interactive mode: prompts for email/password, obtains a JWT token, and
    selects an org.

    CI/CD mode: pass --api-key to authenticate with an org-scoped API key
    instead of email/password.
    """
    from forktex_cloud.client import ForktexCloudClient

    cloud_ctx = ctx.obj["cloud_ctx"]
    cloud_ctx.controller = url.rstrip("/")

    if api_key:
        # CI/CD mode — store API key directly
        cloud_ctx.account_key = api_key
        cloud_ctx.access_token = None
        save_cloud_context_global(cloud_ctx)
        try:
            with ForktexCloudClient(
                cloud_ctx.controller, account_key=api_key
            ) as client:
                health = client.health()
            click.echo(
                f"Connected to {cloud_ctx.controller} (API key mode, status: {health.status})"
            )
        except Exception as e:
            import httpx
            from forktex_cloud import CloudAPIError

            if isinstance(e, CloudAPIError):
                click.echo(
                    f"Warning: authentication failed ({e.status_code}): {e.detail}",
                    err=True,
                )
            elif isinstance(e, (httpx.ConnectError, httpx.TimeoutException)):
                click.echo(f"Warning: could not reach controller: {e}", err=True)
            else:
                click.echo(f"Warning: could not verify connection: {e}", err=True)
            click.echo("Credentials saved. You can retry later.")
        return

    # Interactive mode — email/password login
    email = await click.prompt("Email")
    password = await click.prompt("Password", hide_input=True)

    try:
        with ForktexCloudClient(cloud_ctx.controller) as client:
            # Login to get JWT token
            token_resp = client.login(email, password)
            access_token = token_resp.access_token

            # Create an authed client to fetch orgs
            with ForktexCloudClient(
                cloud_ctx.controller, access_token=access_token
            ) as authed_client:
                orgs = authed_client.list_orgs()

            if not orgs:
                click.echo("Error: no organizations found for this account.", err=True)
                return

            # Select org
            if len(orgs) == 1:
                org = orgs[0]
            else:
                click.echo("\nAvailable organizations:")
                for i, o in enumerate(orgs, 1):
                    click.echo(f"  {i}. {o.name} ({o.slug})")
                choice = click.prompt(
                    "Select organization",
                    type=click.IntRange(1, len(orgs)),
                    default=1,
                )
                org = orgs[choice - 1]

            # Fetch region from health
            with ForktexCloudClient(cloud_ctx.controller) as client:
                health = client.health()
                region = health.region

            # Save to context
            cloud_ctx.access_token = access_token
            cloud_ctx.account_key = None
            cloud_ctx.org_id = str(org.id)
            cloud_ctx.region = region
            save_cloud_context_global(cloud_ctx)

            click.echo(
                f"Logged in to {cloud_ctx.controller} as {email}\n"
                f"  Organization: {org.name} ({org.slug})\n"
                f"  Region: {region or 'unknown'}"
            )

    except Exception as e:
        import httpx
        from forktex_cloud import CloudAPIError

        if isinstance(e, CloudAPIError):
            click.echo(f"Login failed ({e.status_code}): {e.detail}", err=True)
        elif isinstance(e, (httpx.ConnectError, httpx.TimeoutException)):
            click.echo(
                f"Login failed: could not reach {cloud_ctx.controller} ({e})", err=True
            )
        else:
            click.echo(f"Login failed: {e}", err=True)
