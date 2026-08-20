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

"""
forktex.agent.tools.web - Web search and fetch tools.

web_search uses the `ddgs` package (DuckDuckGo) -- no browser needed.
web_fetch uses Playwright for full JS-rendered page extraction.

Both tools are provider-independent (no LLM API required).
"""

from __future__ import annotations

from typing import List

from forktex.agent.tools.base import Tool, ToolResult


# ── Web search (ddgs-based, no browser) ─────────────────────────────────────


async def _web_search(query: str, max_results: int = 10) -> ToolResult:
    """Search the web using DuckDuckGo via the ddgs package."""
    try:
        from ddgs import DDGS
    except ImportError:
        return ToolResult(
            content="ddgs package required. Install with: pip install ddgs",
            is_error=True,
        )

    try:
        import asyncio

        def _search():
            return list(DDGS().text(query, max_results=max_results))

        raw = await asyncio.to_thread(_search)

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in raw
        ]

        data = {"results": results, "query": query}

        if results:
            content = f"Search results for: {query}\n\n"
            for i, r in enumerate(results, 1):
                content += f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}\n\n"
        else:
            content = f"No results found for: {query}"

        return ToolResult(content=content, data=data)

    except Exception as exc:
        return ToolResult(content=f"Search error: {exc}", is_error=True)


# ── Web fetch (Playwright for JS rendering) ─────────────────────────────────


class _BrowserManager:
    """Lazy Playwright browser -- only starts when web_fetch is first called."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        if self._browser is not None:
            return self._browser

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "playwright package required. Install with: pip install playwright && playwright install"
            )

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def get_page(self):
        browser = await self._ensure_browser()
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        return await context.new_page()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


_browser_manager = _BrowserManager()


async def _web_fetch(url: str) -> ToolResult:
    """Fetch a web page and extract text content (Playwright, JS-rendered)."""
    try:
        page = await _browser_manager.get_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            title = await page.title()
            content = await page.evaluate("""
                () => {
                    const remove = document.querySelectorAll('script, style, nav, footer, header, aside');
                    remove.forEach(el => el.remove());
                    return document.body ? document.body.innerText.substring(0, 50000) : '';
                }
            """)
            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .slice(0, 50)
                    .map(a => a.href)
                    .filter(h => h.startsWith('http'))
            """)

            data = {"title": title, "content": content, "links": links}
            return ToolResult(
                content=f"# {title}\n\n{content[:5000]}",
                data=data,
            )
        finally:
            await page.context.close()
    except RuntimeError as exc:
        return ToolResult(content=str(exc), is_error=True)
    except Exception as exc:
        return ToolResult(content=f"Fetch error: {exc}", is_error=True)


# ── Tool factory ────────────────────────────────────────────────────────────


def create_web_tools() -> List[Tool]:
    """Create web browsing tools (provider-independent)."""
    return [
        Tool(
            name="web_search",
            description="Search the web for information using DuckDuckGo",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
            handler=lambda query, max_results=10: _web_search(query, max_results),
        ),
        Tool(
            name="web_fetch",
            description="Fetch and extract content from a web page (supports JavaScript rendering)",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
            handler=lambda url: _web_fetch(url),
        ),
    ]
