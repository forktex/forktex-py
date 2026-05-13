# Desktop Control POC

Forktex desktop control starts as an observe-only local tool surface. The
goal is to prove the same data flow as browser automation: list tools, capture
context, return structured metadata, and let the agent reason over it before
any input injection is enabled.

## Current POC

Desktop tools are disabled by default. Enable them explicitly:

```bash
forktex intelligence chat --desktop
forktex intelligence run --desktop "Capture a desktop observation"
FORKTEX_ENABLE_DESKTOP=1 forktex intelligence chat
```

Registered tools:

| Tool | Purpose |
| --- | --- |
| `desktop_info` | Report session, compositor hints, capture backend, and capability flags. |
| `desktop_screenshot` | Capture a PNG screenshot and return path/metadata, with optional base64 data. |
| `desktop_observe` | Capture one structured observation containing desktop info and screenshot metadata. |

The first implementation targets live Ubuntu GNOME on Wayland. It prefers
`grim` for screenshot capture and falls back to `gnome-screenshot` when
available. Captures are saved under `.forktex/desktop-observations/`.

Mouse, keyboard, focus, and accessibility-tree actions are intentionally not
registered in this POC. Capability flags report those surfaces as unavailable.

## Safety

Screenshots can include private data from the user's live desktop. The desktop
tool group is opt-in and should remain off for unattended agents. Input tools
must require a separate explicit safety gate before they are registered.

## Open-Source References

| Project | Fit | Notes |
| --- | --- | --- |
| `isac322/kwin-mcp` | Strong Linux Wayland reference | Rich KWin session control with screenshots, input, windows, and accessibility. Best candidate for an isolated compositor provider. |
| `Touchpoint-Labs/touchpoint` | Cross-platform accessibility MCP | Good reference for element/window abstractions and observe-act APIs. |
| `hathibelagal-dev/mcp-pyautogui` | Simple MCP baseline | Useful for the smallest screenshot/mouse/keyboard schema shape, weaker for Wayland. |
| `huggingface/screenenv` | Isolated desktop environment | Useful for reproducible evaluation and recording rather than live GNOME control. |

## Metin2 Playground Notes

The desktop POC does not depend on a Metin2 server/client stack. Candidate
repositories to evaluate after observe-only control works:

| Project | Role | Notes |
| --- | --- | --- |
| `MeikelLP/quantum-core-x` | Server emulator | Active C# Metin2 emulator, useful for controlled protocol/world experiments. |
| `willianmarquess/open-mt2` | Server emulator | TypeScript/Node emulator for study and lightweight experiments. |
| `NakiuS/Metin2Client` | Client source | Public client source inventory item; build/runtime quality needs validation before use. |
