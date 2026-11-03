# AGENTS.md

`forktex` is a library: the shared foundation for ForkTex's Python services. It
has no CLI and no service of its own.

For consumers: [`README.md`](README.md) and one page per module in
[`docs/`](docs/).

For working on the library: [`docs/development.md`](docs/development.md), the
architecture, layout, commands and conventions. Read it before changing
anything.

`make ci` is the gate. It needs Docker, and should run alone. Publishing is
manual: a person runs `make publish`.

`backlog/` holds code set aside from this repository. It is not built, tested,
linted or shipped.
