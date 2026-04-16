"""forktex.agent.tools.scraper — StatefulBrowser + 12 scraper tools.

Provides a persistent Playwright browser and tools for navigating,
interacting with, and extracting data from web pages. The browser
persists across the entire agent session, enabling multi-step scraping
workflows driven by the Intelligence API agent loop.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from forktex.agent.tools.base import Tool, ToolResult
from forktex.agent.scraper.truths import TruthsStore


class StatefulBrowser:
    """Persistent Playwright browser context for scraper agents.

    Unlike the stateless web_fetch tool, this browser stays open
    across tool calls so the LLM can navigate step by step.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._screenshots_dir: Optional[Path] = None

    @property
    def page(self):
        """The single persistent page."""
        return self._page

    async def start(
        self,
        screenshots_dir: str,
        *,
        headless: bool = True,
        client_cert: Optional[str] = None,
        client_key: Optional[str] = None,
        client_pfx: Optional[str] = None,
        client_passphrase: Optional[str] = None,
        client_ca: Optional[str] = None,
        cert_origin: Optional[str] = None,
    ) -> None:
        """Launch Chromium with certificate bypass enabled.

        Args:
            screenshots_dir: Directory for saving screenshots.
            client_cert: Path to client certificate PEM file.
            client_key: Path to client private key PEM file.
            client_pfx: Path to PKCS#12 (.p12/.pfx) bundle.
            client_passphrase: Passphrase for the PFX/P12 file.
            client_ca: Path to CA certificate PEM file (optional).
            cert_origin: Origin to use the client cert for (e.g. "https://e-licitatie.ro:8881").
        """
        from playwright.async_api import async_playwright

        self._screenshots_dir = Path(screenshots_dir)
        self._screenshots_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)

        ctx_kwargs: Dict[str, Any] = {
            "ignore_https_errors": True,
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        if cert_origin and (client_pfx or (client_cert and client_key)):
            cert_entry: Dict[str, Any] = {"origin": cert_origin}
            if client_pfx:
                cert_entry["pfxPath"] = client_pfx
                if client_passphrase:
                    cert_entry["passphrase"] = client_passphrase
            else:
                cert_entry["certPath"] = client_cert
                cert_entry["keyPath"] = client_key
            if client_ca:
                cert_entry["caCerts"] = [client_ca]
            ctx_kwargs["client_certificates"] = [cert_entry]

        self._context = await self._browser.new_context(**ctx_kwargs)
        self._page = await self._context.new_page()

    async def close(self) -> None:
        """Clean shutdown of browser resources."""
        if self._context:
            await self._context.close()
            self._context = None
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


def _resolve_selector(selector: str) -> str:
    """Auto-prefix XPath selectors for Playwright."""
    if selector.startswith("//") or selector.startswith("/"):
        return f"xpath={selector}"
    return selector


def _auto_save_truth(
    truths_store: TruthsStore,
    browser: StatefulBrowser,
    selector: str,
    action: str,
) -> None:
    """Auto-persist a working selector to truths after a successful action."""
    try:
        page = browser.page
        if page is None:
            return
        from urllib.parse import urlparse
        domain = urlparse(page.url).hostname or "unknown"
        category = "xpaths" if selector.startswith("/") or selector.startswith("//") else "selectors"
        key = f"{action}:{selector}"
        truths_store.save_entry(domain, category, key, selector, confidence=0.9)
    except Exception:
        pass  # Never let auto-save break the tool


def create_scraper_tools(
    browser: StatefulBrowser,
    truths_store: TruthsStore,
    project_root: str,
) -> List[Tool]:
    """Create the 12 scraper tools bound to the given browser and truths store."""

    output_dir = Path(project_root) / ".forktex" / "scraper" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. scraper_navigate ─────────────────────────────────────────────

    async def _navigate(url: str, wait_until: str = "domcontentloaded") -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            resp = await page.goto(url, wait_until=wait_until, timeout=30000)
            status = resp.status if resp else "unknown"
            title = await page.title()
            return ToolResult(
                content=f"Navigated to {url} (status={status}, title={title})",
                data={"url": url, "status": status, "title": title},
            )
        except Exception as exc:
            return ToolResult(content=f"Navigate error: {exc}", is_error=True)

    # ── 2. scraper_click ────────────────────────────────────────────────

    async def _click(selector: str, timeout: int = 5000) -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            sel = _resolve_selector(selector)
            await page.click(sel, timeout=timeout)
            _auto_save_truth(truths_store, browser, selector, "click")
            return ToolResult(content=f"Clicked: {selector}")
        except Exception as exc:
            return ToolResult(content=f"Click error: {exc}", is_error=True)

    # ── 3. scraper_fill ─────────────────────────────────────────────────

    async def _fill(selector: str, value: str, timeout: int = 5000) -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            sel = _resolve_selector(selector)
            await page.fill(sel, value, timeout=timeout)
            _auto_save_truth(truths_store, browser, selector, "fill")
            return ToolResult(content=f"Filled '{selector}' with '{value}'")
        except Exception as exc:
            return ToolResult(content=f"Fill error: {exc}", is_error=True)

    # ── 4. scraper_select ───────────────────────────────────────────────

    async def _select(selector: str, value: str, timeout: int = 5000) -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            sel = _resolve_selector(selector)
            await page.select_option(sel, value, timeout=timeout)
            _auto_save_truth(truths_store, browser, selector, "select")
            return ToolResult(content=f"Selected '{value}' in '{selector}'")
        except Exception as exc:
            return ToolResult(content=f"Select error: {exc}", is_error=True)

    # ── 5. scraper_wait ─────────────────────────────────────────────────

    async def _wait(selector: str, state: str = "visible", timeout: int = 10000) -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            sel = _resolve_selector(selector)
            await page.wait_for_selector(sel, state=state, timeout=timeout)
            return ToolResult(content=f"Element '{selector}' is {state}")
        except Exception as exc:
            return ToolResult(content=f"Wait error: {exc}", is_error=True)

    # ── 6. scraper_extract ──────────────────────────────────────────────

    async def _extract(
        selector: str,
        attribute: str = "textContent",
        all_matches: bool = False,
    ) -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            sel = _resolve_selector(selector)

            if all_matches:
                elements = await page.query_selector_all(sel)
                values = []
                for el in elements:
                    if attribute == "textContent":
                        values.append(await el.text_content() or "")
                    elif attribute == "innerHTML":
                        values.append(await el.inner_html())
                    else:
                        values.append(await el.get_attribute(attribute) or "")
                content = "\n".join(f"[{i}] {v.strip()}" for i, v in enumerate(values))
                if values:
                    _auto_save_truth(truths_store, browser, selector, f"extract_all:{attribute}")
                return ToolResult(
                    content=content or "(no matches)",
                    data={"values": values, "count": len(values)},
                )
            else:
                el = await page.query_selector(sel)
                if el is None:
                    return ToolResult(content=f"No element found for: {selector}")
                if attribute == "textContent":
                    val = await el.text_content() or ""
                elif attribute == "innerHTML":
                    val = await el.inner_html()
                else:
                    val = await el.get_attribute(attribute) or ""
                _auto_save_truth(truths_store, browser, selector, f"extract:{attribute}")
                return ToolResult(
                    content=val.strip(),
                    data={"value": val.strip()},
                )
        except Exception as exc:
            return ToolResult(content=f"Extract error: {exc}", is_error=True)

    # ── 7. scraper_screenshot ───────────────────────────────────────────

    async def _screenshot(filename: str = "", full_page: bool = False) -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            fname = filename or f"screenshot_{int(time.time())}"
            if not fname.endswith(".png"):
                fname += ".png"
            path = browser._screenshots_dir / fname
            await page.screenshot(path=str(path), full_page=full_page)
            return ToolResult(
                content=f"Screenshot saved: {path}",
                data={"path": str(path)},
            )
        except Exception as exc:
            return ToolResult(content=f"Screenshot error: {exc}", is_error=True)

    # ── 8. scraper_get_html ─────────────────────────────────────────────

    async def _get_html(
        selector: str = "body",
        outer: bool = False,
        max_length: int = 5000,
    ) -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            sel = _resolve_selector(selector)
            el = await page.query_selector(sel)
            if el is None:
                return ToolResult(content=f"No element found for: {selector}")
            if outer:
                html = await el.evaluate("el => el.outerHTML")
            else:
                html = await el.inner_html()
            truncated = html[:max_length]
            return ToolResult(
                content=truncated + ("... (truncated)" if len(html) > max_length else ""),
                data={"html": html, "truncated": len(html) > max_length},
            )
        except Exception as exc:
            return ToolResult(content=f"HTML error: {exc}", is_error=True)

    # ── 9. scraper_evaluate ─────────────────────────────────────────────

    async def _evaluate(expression: str) -> ToolResult:
        try:
            page = browser.page
            if page is None:
                return ToolResult(content="Browser not started", is_error=True)
            result = await page.evaluate(expression)
            if isinstance(result, (dict, list)):
                content = json.dumps(result, indent=2, ensure_ascii=False, default=str)
            else:
                content = str(result)
            return ToolResult(
                content=content[:10000],
                data={"result": result},
            )
        except Exception as exc:
            return ToolResult(content=f"Evaluate error: {exc}", is_error=True)

    # ── 10. scraper_truths_get ──────────────────────────────────────────

    async def _truths_get(domain: str) -> ToolResult:
        data = truths_store.load(domain)
        if data is None:
            return ToolResult(content=f"No truths stored for domain: {domain}")
        content = json.dumps(data, indent=2, ensure_ascii=False)
        return ToolResult(content=content, data=data)

    # ── 11. scraper_truths_save ─────────────────────────────────────────

    async def _truths_save(
        domain: str,
        category: str,
        key: str,
        value: Any,
        confidence: float = 1.0,
    ) -> ToolResult:
        try:
            truths_store.save_entry(domain, category, key, value, confidence)
            return ToolResult(
                content=f"Saved truth: {domain}/{category}/{key} (confidence={confidence})"
            )
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

    # ── 12. scraper_save_data ───────────────────────────────────────────

    async def _save_data(filename: str, data: Any) -> ToolResult:
        try:
            if not filename.endswith(".json"):
                filename += ".json"
            path = output_dir / filename
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
            return ToolResult(
                content=f"Data saved: {path}",
                data={"path": str(path)},
            )
        except Exception as exc:
            return ToolResult(content=f"Save error: {exc}", is_error=True)

    # ── Assemble tool list ──────────────────────────────────────────────

    return [
        Tool(
            name="scraper_navigate",
            description="Navigate the browser to a URL",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "wait_until": {
                        "type": "string",
                        "description": "Wait condition: domcontentloaded, load, or networkidle",
                        "default": "domcontentloaded",
                    },
                },
                "required": ["url"],
            },
            handler=_navigate,
        ),
        Tool(
            name="scraper_click",
            description="Click an element by CSS or XPath selector",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS or XPath selector"},
                    "timeout": {"type": "integer", "description": "Timeout in ms", "default": 5000},
                },
                "required": ["selector"],
            },
            handler=_click,
        ),
        Tool(
            name="scraper_fill",
            description="Fill an input field with text",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS or XPath selector for the input"},
                    "value": {"type": "string", "description": "Text to fill"},
                    "timeout": {"type": "integer", "description": "Timeout in ms", "default": 5000},
                },
                "required": ["selector", "value"],
            },
            handler=_fill,
        ),
        Tool(
            name="scraper_select",
            description="Select a dropdown option by value",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS or XPath selector for the select element"},
                    "value": {"type": "string", "description": "Option value to select"},
                    "timeout": {"type": "integer", "description": "Timeout in ms", "default": 5000},
                },
                "required": ["selector", "value"],
            },
            handler=_select,
        ),
        Tool(
            name="scraper_wait",
            description="Wait for an element to reach a state (visible, hidden, attached, detached)",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS or XPath selector"},
                    "state": {
                        "type": "string",
                        "description": "State to wait for: visible, hidden, attached, detached",
                        "default": "visible",
                    },
                    "timeout": {"type": "integer", "description": "Timeout in ms", "default": 10000},
                },
                "required": ["selector"],
            },
            handler=_wait,
        ),
        Tool(
            name="scraper_extract",
            description="Extract text or attribute from one or all matching elements",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS or XPath selector"},
                    "attribute": {
                        "type": "string",
                        "description": "Attribute to extract: textContent, innerHTML, href, src, etc.",
                        "default": "textContent",
                    },
                    "all_matches": {
                        "type": "boolean",
                        "description": "Extract from all matching elements (true) or first only (false)",
                        "default": False,
                    },
                },
                "required": ["selector"],
            },
            handler=_extract,
        ),
        Tool(
            name="scraper_screenshot",
            description="Take a screenshot and save to .forktex/scraper/screenshots/",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Screenshot filename (optional)", "default": ""},
                    "full_page": {"type": "boolean", "description": "Capture full page", "default": False},
                },
                "required": [],
            },
            handler=_screenshot,
        ),
        Tool(
            name="scraper_get_html",
            description="Get innerHTML or outerHTML of an element (truncated in content, full in data)",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS or XPath selector", "default": "body"},
                    "outer": {"type": "boolean", "description": "Return outerHTML instead of innerHTML", "default": False},
                    "max_length": {"type": "integer", "description": "Max chars in content field", "default": 5000},
                },
                "required": [],
            },
            handler=_get_html,
        ),
        Tool(
            name="scraper_evaluate",
            description="Run arbitrary JavaScript in the page context and return the result",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "JavaScript expression to evaluate"},
                },
                "required": ["expression"],
            },
            handler=_evaluate,
        ),
        Tool(
            name="scraper_truths_get",
            description="Load existing truths (selectors, flows, mappings) for a domain",
            parameters={
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain name (e.g. e-licitatie.ro)"},
                },
                "required": ["domain"],
            },
            handler=_truths_get,
        ),
        Tool(
            name="scraper_truths_save",
            description="Persist a verified selector, flow, or field mapping for a domain",
            parameters={
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Domain name"},
                    "category": {
                        "type": "string",
                        "description": "Category: selectors, xpaths, flows, field_mappings, or notes",
                    },
                    "key": {"type": "string", "description": "Entry key/name"},
                    "value": {"description": "Entry value (string, object, etc.)"},
                    "confidence": {"type": "number", "description": "Confidence score 0.0-1.0", "default": 1.0},
                },
                "required": ["domain", "category", "key", "value"],
            },
            handler=_truths_save,
        ),
        Tool(
            name="scraper_save_data",
            description="Write structured JSON data to .forktex/scraper/output/",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Output filename (e.g. offers.json)"},
                    "data": {"description": "Data to save (will be JSON-serialized)"},
                },
                "required": ["filename", "data"],
            },
            handler=_save_data,
        ),
    ]
